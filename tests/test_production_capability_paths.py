"""Production-only capabilities: prove the path activates when the key exists.

Five providers — Alpha Vantage, Tiingo, Logo.dev, Pexels, Unsplash — are
configured on Render and absent locally. That makes them the highest-risk
surface in the system: the code is written, the tests are fixtures, and
nothing has ever executed against a real payload.

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
    ("PEXELS_API_KEY",
     "src.providers.vendors.visual_vendors.PexelsVendor",
     {"image_search"}),
    ("UNSPLASH_ACCESS_KEY",
     "src.providers.vendors.visual_vendors.UnsplashVendor",
     {"image_search"}),
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
    from src.providers.vendors.visual_vendors import PexelsVendor, UnsplashVendor

    monkeypatch.setenv("PEXELS_API_KEY", "production-shaped-key-value")
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "production-shaped-key-value")
    matrix = fabric.capability_matrix({"visual": [PexelsVendor(), UnsplashVendor()]})
    live = matrix["by_capability"]["image_search"]["live"]
    assert sorted(live) == ["pexels", "unsplash"]
    assert matrix["by_capability"]["image_search"]["unconfigured"] == []


# ── authentication shape, per each vendor's documented mechanism ───────────

def test_each_provider_authenticates_the_way_its_vendor_documents(monkeypatch):
    """Auth mechanisms differ per vendor and getting one wrong produces a 401
    that looks identical to an outage. Asserted structurally so a refactor
    cannot silently move a token into a query string."""
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-secret-value")
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-secret-value")
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "unsplash-secret-value")

    from src.providers.vendors.tiingo_vendor import TiingoVendor
    from src.providers.vendors.visual_vendors import UnsplashVendor

    # Tiingo: Authorization: Token <key>, never a query parameter — query
    # strings land in access logs and proxy caches.
    tiingo_headers = TiingoVendor()._headers()
    assert tiingo_headers["Authorization"] == "Token tiingo-secret-value"

    # Unsplash: Client-ID, and the *access* key rather than the secret. The
    # secret is only for OAuth user authorisation, which this integration
    # does not perform.
    unsplash_headers = UnsplashVendor()._headers()
    assert unsplash_headers["Authorization"] == "Client-ID unsplash-secret-value"
    assert unsplash_headers["Accept-Version"] == "v1"


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


_PEXELS = {"photos": [{
    "id": 1234, "width": 1920, "height": 1080,
    "url": "https://www.pexels.com/photo/1234/",
    "photographer": "A Photographer",
    "photographer_url": "https://www.pexels.com/@someone",
    "avg_color": "#3B4A5A",
    "src": {"large2x": "https://images.pexels.com/1234-2x.jpg",
            "medium": "https://images.pexels.com/1234-m.jpg"},
    "alt": "semiconductor fabrication cleanroom",
}]}

_UNSPLASH = {"results": [{
    "id": "abc123", "width": 4000, "height": 2500, "color": "#26343F",
    "alt_description": "aerial view of a data centre",
    "urls": {"regular": "https://images.unsplash.com/abc123?w=1080",
             "small": "https://images.unsplash.com/abc123?w=400"},
    "links": {"html": "https://unsplash.com/photos/abc123",
              "download_location": "https://api.unsplash.com/photos/abc123/download"},
    "user": {"name": "A Creator", "links": {"html": "https://unsplash.com/@creator"}},
    "tags": [{"title": "data center"}, {"title": "technology"}],
}]}


def test_pexels_parses_the_documented_photo_shape(monkeypatch):
    """DOCUMENTATION-VERIFIED."""
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-secret-value")
    from src.providers.vendors.visual_vendors import PexelsVendor

    monkeypatch.setattr(PexelsVendor, "_get_json", lambda self, *a, **k: _PEXELS)
    assets = PexelsVendor().search_images("semiconductors")
    asset = assets[0]
    assert asset.provider == "pexels"
    assert asset.provider_asset_id == "1234"
    assert asset.image_url.endswith("1234-2x.jpg")
    assert asset.thumbnail_url.endswith("1234-m.jpg")
    assert asset.aspect_ratio == pytest.approx(1.778, abs=0.01)
    assert asset.photographer == "A Photographer"
    # Both libraries require credit with a link back; the flag travels on the
    # asset so a renderer cannot omit it by forgetting the provider.
    assert asset.attribution_required is True
    assert asset.provider_metadata["avg_color"] == "#3B4A5A"


def test_unsplash_keeps_the_download_endpoint_for_the_chosen_asset(monkeypatch):
    """Unsplash asks that a download be registered when an image is actually
    displayed. The endpoint has to survive parsing or that is impossible."""
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "unsplash-secret-value")
    from src.providers.vendors.visual_vendors import UnsplashVendor

    monkeypatch.setattr(UnsplashVendor, "_get_json", lambda self, *a, **k: _UNSPLASH)
    asset = UnsplashVendor().search_images("data center")[0]
    assert asset.provider_asset_id == "abc123"
    assert asset.photographer == "A Creator"
    assert asset.provider_metadata["download_location"].endswith("/download")
    assert asset.provider_metadata["tags"] == ["data center", "technology"]


def test_malformed_visual_payloads_yield_nothing_rather_than_raising(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pexels-secret-value")
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "unsplash-secret-value")
    from src.providers.vendors.visual_vendors import PexelsVendor, UnsplashVendor

    for cls, junk in [
        (PexelsVendor, {"photos": "not a list"}),
        (PexelsVendor, {"photos": [{"id": 1}]}),          # no src -> unusable
        (UnsplashVendor, {"results": [{"id": "x"}]}),      # no urls -> unusable
        (UnsplashVendor, []),                              # wrong root type
    ]:
        monkeypatch.setattr(cls, "_get_json", lambda self, *a, _j=junk, **k: _j)
        assert cls().search_images("q") is None


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
    ("PEXELS_API_KEY", "pexels-secret-value"),
    ("UNSPLASH_ACCESS_KEY", "unsplash-secret-value"),
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
