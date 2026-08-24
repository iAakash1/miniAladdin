"""Fields that arrived in a response and used to be thrown away.

Each test here corresponds to a payload the product was already paying for
and parsing only part of. They are written against synthetic payloads rather
than live calls so they assert *our* parsing rather than a vendor's mood —
Yahoo's feed answers 429 often enough that a live assertion would be a
coin flip.
"""

from __future__ import annotations

from unittest.mock import patch

from src.providers.vendors.market_vendors import (
    PolygonVendor,
    TwelveDataVendor,
    _registrable_domain,
)
from src.providers.vendors.news_vendors import YahooRssVendor


# ── Yahoo RSS: image and summary ──────────────────────────────────────────

_FEED = b"""<?xml version="1.0"?>
<rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
  <item>
    <title>Apple beats estimates</title>
    <link>https://finance.yahoo.com/news/a</link>
    <pubDate>Mon, 24 Aug 2026 10:00:00 GMT</pubDate>
    <description>Revenue rose on iPhone strength.</description>
    <media:content url="https://img.yahoo.com/a.jpg" medium="image"/>
  </item>
  <item>
    <title>Video roundup</title>
    <link>https://finance.yahoo.com/news/b</link>
    <media:content url="https://video.yahoo.com/b.mp4" type="video/mp4"/>
  </item>
</channel></rss>"""


def test_yahoo_rss_keeps_the_publishers_image_and_summary():
    """Both were in every item and both were dropped, leaving Yahoo as a
    title-and-link feed when it is considerably more than that."""
    with patch.object(YahooRssVendor, "timed_call", lambda self, fn, **kw: _FEED):
        rows = YahooRssVendor().get_news("AAPL", limit=5)
    assert rows[0].image_url == "https://img.yahoo.com/a.jpg"
    assert rows[0].summary == "Revenue rose on iPhone strength."


def test_a_video_enclosure_is_not_mistaken_for_an_article_image():
    """`media:content` sometimes points at a video; rendering that URL in an
    <img> produces a broken image on an otherwise fine article."""
    with patch.object(YahooRssVendor, "timed_call", lambda self, fn, **kw: _FEED):
        rows = YahooRssVendor().get_news("AAPL", limit=5)
    assert rows[1].image_url == ""


# ── TwelveData: /quote instead of /price ──────────────────────────────────

_QUOTE = {
    "symbol": "AAPL", "close": "309.35", "open": "312.04", "high": "313.0",
    "low": "308.1", "previous_close": "311.30", "volume": "46768100",
    "datetime": "2026-08-21",
    "fifty_two_week": {"high": "344.57", "low": "223.78"},
}


def test_twelvedata_returns_a_session_not_a_bare_price():
    """`/price` returns one number; `/quote` costs the same request against
    the same 8-per-minute budget and returns the whole session."""
    with patch.object(TwelveDataVendor, "_get_json", lambda self, *a, **k: _QUOTE):
        q = TwelveDataVendor().get_price("AAPL")
    assert q.price == 309.35
    assert q.day_open == 312.04 and q.previous_close == 311.30
    assert q.volume == 46768100
    assert q.week_52_high == 344.57 and q.week_52_low == 223.78
    assert q.price_basis == "last sale"


def test_a_twelvedata_error_payload_yields_no_quote_rather_than_a_zero():
    with patch.object(TwelveDataVendor, "_get_json",
                      lambda self, *a, **k: {"status": "error", "message": "no"}):
        assert TwelveDataVendor().get_price("AAPL") is None


# ── Polygon: reference data ───────────────────────────────────────────────

_TICKER = {"results": {
    "name": "Apple Inc.", "homepage_url": "https://www.apple.com",
    "sic_description": "ELECTRONIC COMPUTERS", "total_employees": 166000,
    "market_cap": 4.5e12, "primary_exchange": "XNAS", "locale": "us",
    "list_date": "1980-12-12", "currency_name": "usd",
    "description": "Apple designs and sells consumer electronics.",
}}


def test_polygon_reference_data_yields_a_profile_and_a_domain():
    """Polygon was wired for prices only. Its reference endpoint carries a
    business description and the homepage — and the homepage is what the
    logo provider is keyed on."""
    with patch.object(PolygonVendor, "_get_json", lambda self, *a, **k: _TICKER):
        p = PolygonVendor().get_company("AAPL")
    assert p.name == "Apple Inc."
    assert p.domain == "apple.com"
    assert p.employees == 166000
    assert p.description.startswith("Apple designs")
    assert p.currency == "USD" and p.country == "US"


def test_polygon_with_no_result_returns_none_rather_than_a_blank_profile():
    with patch.object(PolygonVendor, "_get_json", lambda self, *a, **k: {"results": {}}):
        assert PolygonVendor().get_company("ZZZZ") is None


# ── domain extraction ─────────────────────────────────────────────────────

def test_every_spelling_of_a_website_reduces_to_one_domain():
    """Vendors return three spellings of the same company; two spellings in
    the logo cache is two lookups against one rate limit."""
    for raw in ("https://www.apple.com/", "http://apple.com", "apple.com/investor?x=1"):
        assert _registrable_domain(raw) == "apple.com"
    assert _registrable_domain("") == ""
    assert _registrable_domain("not a url") == ""
