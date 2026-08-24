"""Identity is not context, secrets do not travel, and nothing is invented.

Three properties this module exists to hold. The first two are the ones that
would be invisible if they broke: a stock photograph rendered where a logo
belongs still *looks* fine, and a leaked key is only discovered by someone
who reads a JSON payload.
"""

from __future__ import annotations

import os

import pytest

from src.providers.fabric import Evidence
from src.providers.schemas import VisualAsset
from src.providers.vendors.visual_vendors import LogoDevVendor, stable_pick
from src.services import visual_intelligence as vi


@pytest.fixture(autouse=True)
def _clean():
    vi.reset_for_tests()
    yield
    vi.reset_for_tests()


def _asset(provider="pexels", aid="1", alt="", w=1600, h=1000, url=None):
    return VisualAsset(
        provider=provider, provider_asset_id=aid,
        image_url=url or f"https://cdn/{provider}/{aid}.jpg",
        alt_text=alt, width=w, height=h,
        aspect_ratio=round(w / h, 3) if h else None,
    )


# ── query construction ────────────────────────────────────────────────────

def test_the_query_is_built_from_industry_not_from_the_company_name():
    """Searching a stock library for a brand returns either nothing or
    somebody else's photograph of that brand — which is exactly the
    identity/context confusion this module exists to prevent."""
    query = vi.build_query(name="NVIDIA Corp", sector="Technology", industry="Semiconductors")
    assert query == "semiconductors"
    assert "nvidia" not in query


def test_sector_is_used_when_no_industry_is_recorded():
    assert vi.build_query(name="JPMorgan Chase & Co", sector="Financial Services") == \
        "financial services industry"


def test_a_name_only_company_falls_back_to_a_stripped_name():
    # Corporate suffixes carry no visual meaning and would only dilute the query.
    assert vi.build_query(name="Apple Inc.") == "apple"


def test_no_profile_yields_no_query_rather_than_a_guess():
    assert vi.build_query() == ""
    assert vi.context_images("")["assets"] == []


def test_queries_normalise_so_the_cache_is_not_fragmented():
    # Two spellings of one industry must not be two entries against a
    # 200-requests-per-hour budget.
    assert vi._normalise("Semiconductors  &  Equipment") == "semiconductors equipment"
    assert vi._normalise("SEMICONDUCTORS and equipment") == "semiconductors and equipment"


# ── ranking & dedupe ──────────────────────────────────────────────────────

def test_ranking_prefers_a_described_landscape_image_of_usable_size():
    described = _asset(alt="semiconductor fabrication plant", w=1600, h=1000)
    bare = _asset(aid="2", alt="", w=1600, h=1000)
    tiny = _asset(aid="3", alt="semiconductor fabrication", w=320, h=200)
    square = _asset(aid="4", alt="semiconductor fabrication", w=1000, h=1000)

    q = "semiconductor fabrication"
    assert vi.score(described, q) > vi.score(bare, q)
    assert vi.score(described, q) > vi.score(tiny, q)
    assert vi.score(described, q) > vi.score(square, q)


def test_the_same_photograph_from_one_provider_is_not_shown_twice():
    assets = [_asset(aid="1"), _asset(aid="1"), _asset(aid="2")]
    assert len(vi._dedupe(assets)) == 2


def test_two_different_photographs_of_one_subject_both_survive():
    """Collapsing visually similar images would shrink the pool the ranking
    is supposed to choose from."""
    assets = [_asset(provider="pexels", aid="1"), _asset(provider="unsplash", aid="9")]
    assert len(vi._dedupe(assets)) == 2


def test_selection_is_stable_for_a_ticker_and_differs_between_tickers():
    """An image that reshuffles on refresh reads as decoration; two companies
    in one industry showing the same photograph reads as a bug."""
    pool = [_asset(aid=str(i)) for i in range(8)]
    assert stable_pick(pool, "NVDA").provider_asset_id == stable_pick(pool, "NVDA").provider_asset_id
    picks = {stable_pick(pool, t).provider_asset_id for t in ("NVDA", "AMD", "INTC", "TSM")}
    assert len(picks) > 1


def test_stable_pick_on_an_empty_pool_is_none_not_an_error():
    assert stable_pick([], "NVDA") is None


# ── fabric behaviour ──────────────────────────────────────────────────────

def test_both_libraries_are_merged_rather_than_one_winning(monkeypatch):
    """The core requirement: a successful provider must not suppress the
    other. Two libraries have different contributor bases."""
    def fake_collect(capability, query, vendors, call, **kw):
        return [
            Evidence("pexels", capability, query, True, [_asset("pexels", "p1", alt=query)]),
            Evidence("unsplash", capability, query, True, [_asset("unsplash", "u1", alt=query)]),
        ]

    monkeypatch.setattr(vi.fabric, "collect", fake_collect)
    out = vi.context_images("semiconductors")
    assert out["providers"] == ["pexels", "unsplash"]
    assert {a["provider"] for a in out["assets"]} == {"pexels", "unsplash"}


def test_one_library_failing_does_not_lose_the_other(monkeypatch):
    def fake_collect(capability, query, vendors, call, **kw):
        return [
            Evidence("pexels", capability, query, True, [_asset("pexels", "p1", alt=query)]),
            Evidence("unsplash", capability, query, False, status="rate_limited"),
        ]

    monkeypatch.setattr(vi.fabric, "collect", fake_collect)
    out = vi.context_images("semiconductors")
    assert len(out["assets"]) == 1
    # And the failure is retained as evidence, not swallowed.
    statuses = {e["provider"]: e["status"] for e in out["evidence"]}
    assert statuses["unsplash"] == "rate_limited"


def test_a_successful_lookup_is_cached_but_an_empty_one_is_not(monkeypatch):
    calls = {"n": 0}

    def fake_collect(capability, query, vendors, call, **kw):
        calls["n"] += 1
        return [Evidence("pexels", capability, query, True, [_asset(alt=query)])]

    monkeypatch.setattr(vi.fabric, "collect", fake_collect)
    vi.context_images("semiconductors")
    second = vi.context_images("semiconductors")
    assert calls["n"] == 1
    assert second["cached"] is True

    # An outage must not be cached — a transient 429 would otherwise cost a
    # full day of imagery.
    def empty(capability, query, vendors, call, **kw):
        calls["n"] += 1
        return [Evidence("pexels", capability, query, False, status="rate_limited")]

    monkeypatch.setattr(vi.fabric, "collect", empty)
    vi.context_images("banking")
    vi.context_images("banking")
    assert calls["n"] == 3


def test_a_context_image_is_labelled_as_context_not_as_the_company(monkeypatch):
    monkeypatch.setattr(
        vi.fabric, "collect",
        lambda c, q, v, call, **kw: [Evidence("pexels", c, q, True, [_asset(alt=q)])],
    )
    hero = vi.hero_for_company("NVDA", name="NVIDIA", sector="Technology", industry="Semiconductors")
    assert hero["kind"] == "editorial_context"
    assert "not a photograph of this company" in hero["disclaimer"]


# ── credentials ───────────────────────────────────────────────────────────

def test_no_publishable_key_means_no_logo_url_rather_than_a_broken_one():
    os.environ.pop("LOGO_DEV_PUBLISHABLE_KEY", None)
    assert LogoDevVendor().logo_url(ticker="AAPL") == ""
    assert LogoDevVendor().get_brand("AAPL") is None


def test_the_logo_url_carries_only_the_publishable_key(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "pk_public_123")
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "sk_secret_do_not_leak")
    url = LogoDevVendor().logo_url(ticker="AAPL")
    assert "pk_public_123" in url
    # The property that matters: the secret must never reach a browser URL.
    assert "sk_secret_do_not_leak" not in url


def test_diagnostics_report_configuration_without_revealing_a_secret(monkeypatch):
    monkeypatch.setenv("LOGO_DEV_PUBLISHABLE_KEY", "pk_public_123")
    monkeypatch.setenv("LOGO_DEV_SECRET_KEY", "sk_secret_do_not_leak")
    import json
    blob = json.dumps(vi.diagnostics())
    assert "sk_secret_do_not_leak" not in blob
    assert "pk_public_123" not in blob


def test_vendor_errors_never_carry_a_credential():
    """Several vendors only accept auth in the query string, so `requests`
    embeds the key in every HTTPError message — which then travels into
    Evidence.error and out through the provenance payload."""
    from src.providers.base import redact
    leaked = ("403 Client Error: Forbidden for url: "
              "https://fmp.com/api/v3/profile/AAPL?apikey=REALSECRET123")
    assert "REALSECRET123" not in redact(leaked)
    assert "apikey=<redacted>" in redact(leaked)
    for param in ("token", "access_key", "api_key", "client_secret"):
        assert "SEKRIT" not in redact(f"https://x.com?{param}=SEKRIT&a=1")


# ── credential-leak regression ────────────────────────────────────────────
#
# The failure this guards against actually happened: vendors that
# authenticate by query string made `requests` embed the key in every
# HTTPError message, which travelled into Evidence.error and out through the
# provenance payload. A single 403 was enough to publish a key to the browser.

import json as _json

import pytest as _pytest

from src.providers.base import VendorError, redact
from src.providers.fabric import Evidence, collect
from src.services.provenance import Ledger


_FAKE_SECRETS = [
    "FMP_TEST_SECRET_123",
    "ALPHA_SECRET_456",
    "BEARER_SECRET_789",
    "sk_logo_dev_SECRET_000",
]


@_pytest.mark.parametrize("secret", _FAKE_SECRETS)
@_pytest.mark.parametrize("template", [
    "403 Client Error: Forbidden for url: https://v.com/api?apikey={s}",
    "401 for https://v.com/x?token={s}&sym=AAPL",
    "connection failed: https://v.com/y?access_key={s}",
    "https://v.com/z?api_key={s}",
    "https://v.com/w?client_secret={s}&id=1",
])
def test_no_credential_shape_survives_redaction(secret, template):
    cleaned = redact(template.format(s=secret))
    assert secret not in cleaned


def test_a_vendor_exception_carrying_a_key_never_reaches_provenance():
    """End-to-end: an exploding vendor -> Evidence -> ledger -> JSON payload.
    This is the exact path the leak took."""
    class Leaky:
        NAME, healthy, available = "leaky", True, True

        def get_price(self, symbol):
            raise VendorError(redact(
                "403 Client Error: Forbidden for url: "
                "https://v.com/api/v3/quote/AAPL?apikey=FMP_TEST_SECRET_123"
            ))

    evidence = collect("quote", "AAPL", [Leaky()], lambda v: v.get_price("AAPL"))
    ledger = Ledger("AAPL")
    ledger.record_fabric(label="Consensus quote", kind="market", evidence=evidence)
    payload = _json.dumps(ledger.build())

    assert "FMP_TEST_SECRET_123" not in payload
    # And the failure is still reported — redaction must not swallow evidence.
    assert "leaky" in payload
    assert "403" in payload


def test_redaction_leaves_non_credential_text_intact():
    """Over-redaction is its own failure: an error nobody can read is not
    safer, it is just useless."""
    message = "503 Service Unavailable for url: https://v.com/api/v3/quote/AAPL"
    assert redact(message) == message
