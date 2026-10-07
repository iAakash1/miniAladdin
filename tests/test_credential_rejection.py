"""A credential a vendor refuses must be reported as refused — everywhere.

The production NewsAPI secret holds a value NewsAPI answers with
`apiKeyInvalid`. The provider chain already logged "HTTP 401, falling through",
but four other places still said the opposite:

  * `/api/health` reported `news_api: true` because a key string existed;
  * the research-provider inventory reported `available: true`;
  * a paused vendor was labelled COOLDOWN rather than AUTH_FAILURE, which reads
    as transient for a fault only the key's owner can fix;
  * the dead key was re-probed every 60 seconds, forever.

None of this fabricated news — the chain fell through to other sources — but a
status page that says "available" for a source that has never answered is a
false claim about the data's provenance.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import requests
from fastapi.testclient import TestClient

import api.index as api_module
import src.news_api as legacy
from src.providers.base import FailureClass, VendorError
from src.providers.vendors.news_vendors import NewsApiVendor
from src.services.research.providers import NewsApiProvider

KEY = "not-a-real-key-but-long-enough"


class _Resp:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code = status
        self.headers: dict = {}
        self._body = body if body is not None else {}
        self.text = str(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}", response=self)


@pytest.fixture
def vendor(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", KEY)
    return NewsApiVendor()


def _reject(vendor: NewsApiVendor) -> None:
    with patch.object(vendor._session, "request", return_value=_Resp(401, {"code": "apiKeyInvalid"})):
        with pytest.raises(VendorError):
            vendor.get_news("AAPL")


# ── the vendor's own state ───────────────────────────────────────────────────

def test_a_configured_key_nothing_has_used_is_unverified_not_accepted(vendor):
    assert vendor.available is True
    assert vendor.credential_state == "unverified"
    assert vendor.operational is True


def test_one_401_marks_the_credential_rejected(vendor):
    _reject(vendor)
    assert vendor.credential_rejected is True
    assert vendor.credential_state == "rejected"
    assert vendor.operational is False
    assert vendor.available is True, "the key is still *configured*; that is a separate fact"


def test_a_rejected_credential_is_reported_as_auth_failure_even_while_paused(vendor):
    """The cooldown used to win, labelling a wrong key "paused after failures"."""
    _reject(vendor)
    snapshot = vendor.health_snapshot()
    assert snapshot["cooling_down"] is True
    assert snapshot["health_state"] == "AUTH_FAILURE"
    assert snapshot["credential_state"] == "rejected"
    assert snapshot["configured"] is True


def test_a_rejected_credential_is_left_alone_far_longer_than_a_transient_fault(vendor):
    _reject(vendor)
    remaining = vendor.health_snapshot()["cooldown_remaining_seconds"]
    assert remaining > vendor.COOLDOWN_SECONDS * 5, (
        f"{remaining}s: a bad key would be re-probed about once a minute"
    )
    assert vendor.healthy is False


def test_a_transient_failure_does_not_trigger_the_long_cooldown(vendor):
    with patch.object(vendor._session, "request", return_value=_Resp(503)):
        for _ in range(2):
            with pytest.raises(VendorError):
                vendor.get_news("AAPL")
    assert vendor.credential_rejected is False
    assert vendor.credential_state == "unverified"
    assert vendor.health_snapshot()["health_state"] != "AUTH_FAILURE"


def test_the_credential_is_trusted_again_after_a_later_success(vendor):
    _reject(vendor)
    vendor._cooldown_until = 0.0  # the window has passed
    ok = _Resp(200, {"status": "ok", "articles": []})
    with patch.object(vendor._session, "request", return_value=ok):
        vendor.get_news("AAPL")
    assert vendor.credential_rejected is False
    assert vendor.credential_state == "accepted"
    assert vendor.health_snapshot()["health_state"] != "AUTH_FAILURE"


def test_a_missing_key_is_not_configured_and_never_called_rejected(monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    vendor = NewsApiVendor()
    assert vendor.credential_state == "not_configured"
    assert vendor.operational is False
    assert vendor.health_snapshot()["health_state"] == "NOT_CONFIGURED"


def test_a_keyless_vendor_has_no_credential_to_reject():
    from src.providers.vendors.news_vendors import YahooRssVendor

    assert YahooRssVendor().credential_state == "not_required"


# ── the places that used to say "available" ──────────────────────────────────

def test_the_research_provider_inventory_says_configured_but_not_available(vendor):
    provider = NewsApiProvider()
    provider._vendor = vendor
    _reject(vendor)
    health = provider.health()
    assert health.configured is True
    assert health.available is False


def test_a_rejected_research_provider_is_not_called_again(vendor):
    provider = NewsApiProvider()
    provider._vendor = vendor
    _reject(vendor)
    with patch.object(vendor._session, "request") as send:
        assert provider.search("AAPL") == []
    send.assert_not_called()


def test_health_does_not_advertise_a_news_source_whose_key_was_refused(vendor, monkeypatch):
    monkeypatch.setattr(api_module.providers.news, "newsapi", vendor)
    monkeypatch.setattr(legacy, "_rejected_until", 0.0)
    client = TestClient(api_module.app)

    assert client.get("/api/health").json()["data_sources"]["news_api"] is True
    _reject(vendor)
    assert client.get("/api/health").json()["data_sources"]["news_api"] is False


# ── the legacy client behind sentiment ───────────────────────────────────────

class _LegacyResponse(_Resp):
    pass


@pytest.fixture
def legacy_client(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", KEY)
    monkeypatch.setattr(legacy, "_rejected_until", 0.0)
    return legacy.NewsAPIClient()


def test_a_401_empties_the_legacy_result_and_is_remembered(legacy_client):
    with patch.object(legacy_client._session, "get", return_value=_LegacyResponse(401)) as get:
        assert legacy_client.fetch_headlines("AAPL") == []
    assert get.call_count == 1
    assert legacy.credential_rejected() is True


def test_the_legacy_client_stops_sending_a_key_that_was_refused(legacy_client):
    with patch.object(legacy_client._session, "get", return_value=_LegacyResponse(401)):
        legacy_client.fetch_headlines("AAPL")
    with patch.object(legacy_client._session, "get") as get:
        assert legacy_client.fetch_headlines("MSFT") == []
    get.assert_not_called()


def test_a_new_legacy_client_does_not_report_a_refused_key_as_available(legacy_client):
    with patch.object(legacy_client._session, "get", return_value=_LegacyResponse(401)):
        legacy_client.fetch_headlines("AAPL")
    assert legacy.NewsAPIClient().available is False


def test_the_legacy_rejection_expires(legacy_client, monkeypatch):
    with patch.object(legacy_client._session, "get", return_value=_LegacyResponse(401)):
        legacy_client.fetch_headlines("AAPL")
    monkeypatch.setattr(legacy, "_rejected_until", time.monotonic() - 1)
    assert legacy.credential_rejected() is False
    assert legacy.NewsAPIClient().available is True


def test_the_sentiment_path_falls_through_and_names_the_source_that_answered(legacy_client, monkeypatch):
    """A refused NewsAPI key must not read as "no news exists".

    The headlines come from the next source, and `source_used` says which.
    """
    from src.sentiment_edge import SentimentAnalyzer

    analyzer = SentimentAnalyzer.__new__(SentimentAnalyzer)
    analyzer.news_client = legacy_client
    analyzer.max_headlines = 5
    rss = [{"title": "Apple unveils a new product line today", "source": "Yahoo", "is_breaking": False}]
    monkeypatch.setattr(analyzer, "_fetch_yahoo_rss", lambda ticker: rss)
    monkeypatch.setattr(analyzer, "_fetch_yahoo_html", lambda ticker: [])
    seen = {}
    monkeypatch.setattr(analyzer, "analyze_headlines", lambda headlines: seen.setdefault("n", len(headlines)) or None)
    with patch.object(legacy_client._session, "get", return_value=_LegacyResponse(401)):
        analyzer.analyze_ticker("AAPL")
    assert seen["n"] == 1, "headlines from the fallback source were discarded"
    assert FailureClass.AUTH_FAILURE.value == "auth_failure"


# ── one vendor, one health record ────────────────────────────────────────────

def test_research_providers_share_the_registry_vendor_so_a_rejection_is_seen_everywhere():
    """Found on the live service: after a real request settled NewsAPI as
    rejected, `/api/research/providers/health` still said available.

    The research provider had built its own private copy of the vendor, which
    nothing had called, so it reported the copy's idle state. A vendor now has
    one health record: whatever the shared chain learns, every view reports.
    """
    shared = api_module.providers.news.newsapi
    assert NewsApiProvider()._vendor is shared
    from src.services.research.providers import ExaProvider, GNewsProvider, NewsProvider, TavilyProvider

    assert GNewsProvider()._vendor is api_module.providers.news.gnews
    assert TavilyProvider()._vendor is api_module.providers.news.tavily
    assert ExaProvider()._vendor is api_module.providers.search.exa
    assert NewsProvider()._vendor is api_module.providers.news.yahoo_rss


def test_a_rejection_seen_by_the_chain_reaches_the_research_inventory(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", KEY)
    fresh = NewsApiVendor()
    monkeypatch.setattr(api_module.providers.news, "newsapi", fresh)
    provider = NewsApiProvider()          # built after, as the engine builds it on first use
    assert provider.health().available is True
    _reject(fresh)                         # the chain's own request is refused
    assert provider.health().available is False
    assert provider.health().configured is True
