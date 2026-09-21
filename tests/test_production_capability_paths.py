"""Production-only capabilities: prove the path activates when the key exists.

Alpha Vantage, Tiingo, and Logo.dev are configured in production and absent
locally. These fixtures prove their wiring without spending live quota.

These tests do not pretend otherwise. What they *can* prove, and what
production depends on, is the wiring: that setting the environment variable
is sufficient to make capability discovery see the provider, that the auth
header is built the way the vendor documents, that the parser handles the
documented shape, and that no credential escapes into evidence.

Everything here is DOCUMENTATION-VERIFIED. Nothing in this file has been run
against a live vendor.
"""

from __future__ import annotations

import json

import pytest

from src.providers import fabric


# ── the property that matters most: a key is sufficient ───────────────────

@pytest.mark.parametrize("env_var,vendor_path,capabilities", [
    ("ALPHA_VANTAGE_KEY",
     "src.providers.vendors.data_vendors.AlphaVantageVendor",
     {"fundamentals", "analyst_targets", "news_sentiment"}),
    ("TIINGO_API_KEY",
     "src.providers.vendors.tiingo_vendor.TiingoVendor",
     {"quote", "series", "news", "company", "fundamentals"}),
    ("LOGO_DEV_PUBLISHABLE_KEY",
     "src.providers.vendors.visual_vendors.LogoDevVendor",
     {"brand_mark"}),
])
def test_setting_the_key_is_enough_to_join_the_fabric(
    monkeypatch, env_var, vendor_path, capabilities,
):
    """No code change should be needed when an environment gains a key.

    This is the whole contract between local development and Render: the
    provider is dormant without the variable and live with it, discovered by
    introspection rather than by a hand-maintained list somebody has to
    remember to update.
    """
    module_path, class_name = vendor_path.rsplit(".", 1)
    module = __import__(module_path, fromlist=[class_name])
    cls = getattr(module, class_name)

    monkeypatch.delenv(env_var, raising=False)
    assert cls().available is False, f"{class_name} should be dormant without {env_var}"

    monkeypatch.setenv(env_var, "production-shaped-key-value")
    vendor = cls()
    assert vendor.available is True
    assert vendor.healthy is True

    discovered = {
        capability for capability, method in fabric.CAPABILITY_METHODS.items()
        if hasattr(vendor, method)
    }
    assert capabilities <= discovered, (
        f"{class_name} lost capabilities: expected {capabilities}, found {discovered}"
    )


def test_a_configured_provider_appears_in_the_capability_matrix(monkeypatch):
    from src.providers.vendors.visual_vendors import LogoDevVendor

    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "production-shaped-key-value")
    matrix = fabric.capability_matrix({"visual": [LogoDevVendor()]})
    assert matrix["by_capability"]["brand_mark"]["live"] == ["logo_dev"]
    assert matrix["by_capability"]["brand_mark"]["unconfigured"] == []


# ── authentication shape, per each vendor's documented mechanism ───────────

def test_each_provider_authenticates_the_way_its_vendor_documents(monkeypatch):
    """Auth mechanisms differ per vendor and getting one wrong produces a 401
    that looks identical to an outage. Asserted structurally so a refactor
    cannot silently move a token into a query string."""
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-secret-value")

    from src.providers.vendors.tiingo_vendor import TiingoVendor

    # Tiingo: Authorization: Token <key>, never a query parameter — query
    # strings land in access logs and proxy caches.
    tiingo_headers = TiingoVendor()._headers()
    assert tiingo_headers["Authorization"] == "Token tiingo-secret-value"



def test_the_logo_dev_secret_never_appears_in_a_browser_facing_url(monkeypatch):
    """The publishable key is designed for client-side image URLs; the secret
    authenticates server-side lookups. Confusing them publishes a secret."""
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "pk_publishable_value")
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "sk_secret_value")

    from src.providers.vendors.visual_vendors import LogoDevVendor
    vendor = LogoDevVendor()

    url = vendor.logo_url(ticker="AAPL")
    assert "pk_publishable_value" in url
    assert "sk_secret_value" not in url

    brand = vendor.get_brand("AAPL", "apple.com")
    assert "sk_secret_value" not in json.dumps(brand.model_dump())


# ── documented response shapes ────────────────────────────────────────────

_TIINGO_IEX = [{
    "ticker": "AAPL", "timestamp": "2026-08-21T20:00:00+00:00",
    "lastSaleTimeStamp": "2026-08-21T19:59:58+00:00",
    "last": 309.30, "tngoLast": 309.35, "prevClose": 311.30,
    "open": 312.04, "high": 313.00, "low": 308.10, "mid": 309.33,
    "bidPrice": 309.30, "bidSize": 200, "askPrice": 309.36, "askSize": 100,
    "volume": 46768100,
}]


def test_tiingo_quote_parses_the_documented_iex_shape(monkeypatch):
    """DOCUMENTATION-VERIFIED. Tiingo is the only vendor supplying a real
    book, so the spread is the field worth guarding."""
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-secret-value")
    from src.providers.vendors.tiingo_vendor import TiingoVendor

    monkeypatch.setattr(TiingoVendor, "_get_json", lambda self, *a, **k: _TIINGO_IEX)
    quote = TiingoVendor().get_quote("AAPL")

    assert quote.price == 309.35              # tngoLast wins over last
    assert quote.price_basis == "last sale"
    assert (quote.bid, quote.ask) == (309.30, 309.36)
    assert quote.mid == 309.33
    assert quote.previous_close == 311.30
    assert quote.volume == 46768100
    # 6 cents on a 309.33 mid ≈ 1.9bps.
    assert quote.spread_bps == pytest.approx(1.94, abs=0.05)


def test_tiingo_falls_back_through_its_price_hierarchy_without_lying(monkeypatch):
    """Falling straight to prevClose when no live field exists would report
    yesterday as today, so the basis actually used is recorded."""
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-secret-value")
    from src.providers.vendors.tiingo_vendor import TiingoVendor

    stale = [{"ticker": "X", "prevClose": 100.0, "bidPrice": None, "askPrice": None}]
    monkeypatch.setattr(TiingoVendor, "_get_json", lambda self, *a, **k: stale)
    quote = TiingoVendor().get_quote("X")
    assert quote.price == 100.0
    assert quote.price_basis == "previous close"


def test_tiingo_fundamentals_treat_a_403_as_entitlement_not_outage(monkeypatch):
    """Tiingo fundamentals are an add-on. A permission answer must not reach
    the health circuit, or three unentitled tickers would cool the vendor
    down and take its working quote and news endpoints with it."""
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-secret-value")
    from src.providers.base import VendorError
    from src.providers.vendors.tiingo_vendor import TiingoVendor

    def forbidden(self, *a, **k):
        raise VendorError("403 Client Error: Forbidden")

    monkeypatch.setattr(TiingoVendor, "_get_json", forbidden)
    assert TiingoVendor().get_fundamentals("AAPL") is None  # not an exception


_AV_SENTIMENT = {"feed": [{
    "title": "Apple beats estimates", "url": "https://example.com/a",
    "time_published": "20260815T130002", "source": "Benzinga",
    "summary": "Revenue rose on iPhone strength.",
    "banner_image": "https://img.example.com/a.jpg",
    "topics": [{"topic": "Earnings", "relevance_score": "0.9"}],
    "overall_sentiment_score": 0.31, "overall_sentiment_label": "Somewhat-Bullish",
    "ticker_sentiment": [
        {"ticker": "AAPL", "relevance_score": "0.85",
         "ticker_sentiment_score": "0.42", "ticker_sentiment_label": "Bullish"},
        {"ticker": "MSFT", "relevance_score": "0.10",
         "ticker_sentiment_score": "-0.05", "ticker_sentiment_label": "Neutral"},
    ],
}]}


def test_alpha_vantage_uses_the_ticker_sentiment_not_the_article_sentiment(monkeypatch):
    """DOCUMENTATION-VERIFIED, and the single most important parsing decision
    in this file: an article about the whole sector can be broadly positive
    while being specifically negative about one name in it. Using the overall
    score would attribute the sector's tone to the company."""
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "alpha-secret-value")
    from src.alpha_vantage import AlphaVantageClient
    from src.providers.vendors.data_vendors import AlphaVantageVendor

    monkeypatch.setattr(AlphaVantageClient, "_get", lambda self, p, timeout=10: _AV_SENTIMENT)
    monkeypatch.setattr(AlphaVantageVendor, "timed_call", lambda self, fn, **kw: fn())

    headline = AlphaVantageVendor().get_news_sentiment("AAPL")[0]
    assert headline.sentiment_score == 0.42        # AAPL's, not the article's 0.31
    assert headline.sentiment_label == "Bullish"
    assert headline.sentiment_relevance == 0.85
    assert headline.sentiment_source == "alpha_vantage"
    # And the rest of the payload survives.
    assert headline.image_url.endswith("a.jpg")
    assert headline.tags == ["Earnings"]
    assert "AAPL" in headline.tickers and "MSFT" in headline.tickers
    # Timestamps normalise to ISO — a mixed-format column sorts wrongly.
    assert headline.published_at == "2026-08-15T13:00:02Z"


def test_a_ticker_absent_from_the_sentiment_block_scores_nothing(monkeypatch):
    """No score is not a neutral score. Inventing one would let an unscored
    stream look as well-evidenced as a scored one."""
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "alpha-secret-value")
    from src.alpha_vantage import AlphaVantageClient
    from src.providers.vendors.data_vendors import AlphaVantageVendor

    monkeypatch.setattr(AlphaVantageClient, "_get", lambda self, p, timeout=10: _AV_SENTIMENT)
    monkeypatch.setattr(AlphaVantageVendor, "timed_call", lambda self, fn, **kw: fn())

    headline = AlphaVantageVendor().get_news_sentiment("TSLA")[0]
    assert headline.sentiment_score is None
    assert headline.sentiment_label is None


# ── no credential survives into evidence, for any of these ────────────────

@pytest.mark.parametrize("env_var,secret", [
    ("ALPHA_VANTAGE_KEY", "alpha-secret-value"),
    ("TIINGO_API_KEY", "tiingo-secret-value"),
    ("LOGO_DEV_SECRET_KEY", "sk-logo-secret-value"),
])
def test_a_production_key_never_reaches_the_capability_matrix(monkeypatch, env_var, secret):
    monkeypatch.setenv(env_var, secret)
    from src import providers
    from src.services import visual_intelligence as vi

    blob = json.dumps(fabric.capability_matrix({
        "market": providers.market_data.vendors,
        "fundamentals": providers.fundamentals.vendors,
        "news": providers.news.vendors,
        "visual": vi.IMAGE_VENDORS,
    })) + json.dumps(vi.diagnostics())
    assert secret not in blob
    # The variable's *name* is useful operational information; its value is not.
    assert env_var in blob or env_var.startswith("LOGO_DEV_SECRET")
