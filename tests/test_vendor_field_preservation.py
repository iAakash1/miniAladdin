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


# ── Finnhub: the ratio surface ────────────────────────────────────────────

_METRIC = {"metric": {
    "peTTM": 32.1, "epsTTM": 9.6, "beta": 1.09,
    "52WeekHigh": 344.57, "52WeekLow": 223.78,
    "currentDividendYieldTTM": 0.35, "netProfitMarginTTM": 27.62,
    "psTTM": 9.49, "pbQuarterly": 38.49, "evEbitdaTTM": 26.64, "evRevenueTTM": 9.59,
    "grossMarginTTM": 48.65, "operatingMarginTTM": 33.17, "netProfitMargin5Y": 25.48,
    "roeTTM": 137.18, "roaTTM": 34.55, "roiTTM": 70.25,
    "revenueGrowthTTMYoy": 14.24, "revenueGrowth3Y": 1.81,
    "epsGrowthTTMYoy": 32.61, "epsGrowth3Y": 6.89,
    "currentRatioQuarterly": 1.0033, "quickRatioQuarterly": 0.929,
    "totalDebt/totalEquityQuarterly": 0.7844, "longTermDebt/equityQuarterly": 0.6635,
    "payoutRatioTTM": 12.13,
    "someUnmappedVendorFigure": 42.0,
}}


def test_finnhub_keeps_the_ratio_surface_it_was_already_paying_for():
    """One request returns 133 figures; the adapter kept seven. Margins,
    returns, growth and leverage are exactly what a fundamentals panel is
    for, and they were being fetched and discarded on every research run."""
    from src.providers.vendors.market_vendors import FinnhubVendor
    with patch.object(FinnhubVendor, "_get_json", lambda self, *a, **k: _METRIC):
        f = FinnhubVendor().get_fundamentals("AAPL")
    assert f.roe_ttm == 137.18
    assert f.gross_margin_ttm == 48.65
    assert f.ev_to_ebitda == 26.64
    assert f.revenue_growth_ttm_yoy == 14.24
    assert f.debt_to_equity == 0.7844
    assert f.current_ratio == 1.0033


def test_periods_are_kept_apart_so_nothing_can_average_them():
    """A trailing margin and a five-year average are different measurements.
    Separate fields make that structural rather than a naming convention."""
    from src.providers.vendors.market_vendors import FinnhubVendor
    with patch.object(FinnhubVendor, "_get_json", lambda self, *a, **k: _METRIC):
        f = FinnhubVendor().get_fundamentals("AAPL")
    assert f.net_margin_ttm == 27.62
    assert f.net_margin_5y == 25.48
    assert f.net_margin_ttm != f.net_margin_5y


def test_unmapped_vendor_figures_survive_rather_than_being_dropped():
    """A later feature should not need a new round trip to recover a number
    this response already contained."""
    from src.providers.vendors.market_vendors import FinnhubVendor
    with patch.object(FinnhubVendor, "_get_json", lambda self, *a, **k: _METRIC):
        f = FinnhubVendor().get_fundamentals("AAPL")
    assert f.vendor_metrics["someUnmappedVendorFigure"] == 42.0
    # Non-numeric junk is excluded so the bag stays a numeric surface.
    assert all(isinstance(v, (int, float)) for v in f.vendor_metrics.values())


def test_an_empty_metric_block_yields_no_fundamentals_rather_than_zeros():
    from src.providers.vendors.market_vendors import FinnhubVendor
    with patch.object(FinnhubVendor, "_get_json", lambda self, *a, **k: {"metric": {}}):
        assert FinnhubVendor().get_fundamentals("ZZZZ") is None


# ── Alpha Vantage OVERVIEW ────────────────────────────────────────────────
#
# DOCUMENTATION-VERIFIED, NOT LIVE-VERIFIED. ALPHA_VANTAGE_KEY exists only on
# Render, so this payload is built from the documented OVERVIEW contract and
# these tests assert our parsing, not the vendor's behaviour.

_OVERVIEW = {
    "Symbol": "AAPL", "Name": "Apple Inc", "Sector": "TECHNOLOGY",
    "Industry": "ELECTRONIC COMPUTERS", "Exchange": "NASDAQ", "Currency": "USD",
    "Country": "USA", "Description": "Apple Inc. designs consumer electronics.",
    "FiscalYearEnd": "September", "LatestQuarter": "2026-06-30",
    "MarketCapitalization": "4514709504000", "EBITDA": "142000000000",
    "PERatio": "32.1", "PEGRatio": "2.4", "BookValue": "4.38",
    "DividendPerShare": "1.04", "DividendYield": "0.0035", "EPS": "9.6",
    "RevenuePerShareTTM": "26.4", "ProfitMargin": "0.2762",
    "OperatingMarginTTM": "0.3317", "ReturnOnAssetsTTM": "0.2455",
    "ReturnOnEquityTTM": "1.3718", "RevenueTTM": "408000000000",
    "GrossProfitTTM": "198000000000", "DilutedEPSTTM": "9.55",
    "QuarterlyEarningsGrowthYOY": "0.326", "QuarterlyRevenueGrowthYOY": "0.1424",
    "AnalystTargetPrice": "340.0", "AnalystRatingStrongBuy": "12",
    "AnalystRatingBuy": "20", "AnalystRatingHold": "8",
    "AnalystRatingSell": "1", "AnalystRatingStrongSell": "0",
    "TrailingPE": "32.1", "ForwardPE": "29.4",
    "PriceToSalesRatioTTM": "9.49", "PriceToBookRatio": "38.49",
    "EVToRevenue": "9.59", "EVToEBITDA": "26.64", "Beta": "1.09",
    "52WeekHigh": "344.57", "52WeekLow": "223.78",
    "SharesOutstanding": "14840000000",
    "DividendDate": "2026-08-14", "ExDividendDate": "2026-08-08",
}


def test_alpha_vantage_overview_keeps_what_it_was_already_returning():
    """Roughly sixty fields for one call against a 25-calls-per-day tier, and
    twelve were being kept. Documentation-verified: the key is Render-only."""
    from src.alpha_vantage import AlphaVantageClient
    client = AlphaVantageClient(api_key="fixture-key-not-real")
    with patch.object(AlphaVantageClient, "_get", lambda self, p, timeout=10: _OVERVIEW):
        f = client.get_fundamentals("AAPL")
    assert f.error is None
    assert f.revenue_ttm == 408_000_000_000
    assert f.ebitda == 142_000_000_000
    assert f.return_on_equity_ttm == 1.3718
    assert f.peg_ratio == 2.4
    assert f.shares_outstanding == 14_840_000_000
    assert f.industry == "ELECTRONIC COMPUTERS"
    assert f.fiscal_year_end == "September"
    assert f.latest_quarter == "2026-06-30"


def test_the_analyst_rating_is_kept_as_a_distribution_not_a_score():
    """The spread between strong-buy and hold counts is the informative part;
    a single averaged 'rating' would erase it."""
    from src.alpha_vantage import AlphaVantageClient
    client = AlphaVantageClient(api_key="fixture-key-not-real")
    with patch.object(AlphaVantageClient, "_get", lambda self, p, timeout=10: _OVERVIEW):
        f = client.get_fundamentals("AAPL")
    assert (f.analyst_strong_buy, f.analyst_buy, f.analyst_hold) == (12, 20, 8)
    assert (f.analyst_sell, f.analyst_strong_sell) == (1, 0)


def test_a_missing_overview_reports_an_error_rather_than_empty_fundamentals():
    from src.alpha_vantage import AlphaVantageClient
    client = AlphaVantageClient(api_key="fixture-key-not-real")
    with patch.object(AlphaVantageClient, "_get", lambda self, p, timeout=10: {}):
        f = client.get_fundamentals("ZZZZ")
    assert f.error
    assert f.revenue_ttm is None


def test_alpha_vantage_fields_reach_the_normalized_fundamentals_object(monkeypatch):
    """A field recovered in the client that never crosses the adapter is
    still a discarded field.

    The key is set for this test only so the vendor constructs an enabled
    client — the HTTP layer is patched out, so no request is made and the
    value is never used for anything but the `available` check."""
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", "fixture-key-not-real")
    from src.alpha_vantage import AlphaVantageClient
    from src.providers.vendors.data_vendors import AlphaVantageVendor

    vendor = AlphaVantageVendor()
    with patch.object(AlphaVantageClient, "_get", lambda self, p, timeout=10: _OVERVIEW):
        with patch.object(AlphaVantageVendor, "timed_call",
                          lambda self, fn, **kw: fn()):
            data = vendor.get_fundamentals("AAPL")
    assert data.roe_ttm == 1.3718
    assert data.ev_to_ebitda == 26.64
    assert data.vendor_metrics["revenue_ttm"] == 408_000_000_000
    assert data.vendor_metrics["analyst_strong_buy"] == 12
    # And the profile the same response carried.
    assert data.profile.industry == "ELECTRONIC COMPUTERS"
    assert data.profile.country == "USA"
    assert data.profile.description.startswith("Apple Inc.")


# ── yfinance: 185 fields, twelve were used ────────────────────────────────

_INFO = {
    "longName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
    "website": "https://www.apple.com", "marketCap": 4.5e12, "currency": "USD",
    "exchange": "NMS", "country": "United States", "beta": 1.086,
    "longBusinessSummary": "Apple designs consumer electronics.",
    "fullTimeEmployees": 150000,
    # Everything below was arriving and being dropped.
    "trailingPE": 35.48, "forwardPE": 30.1, "trailingEps": 9.6,
    "fiftyTwoWeekHigh": 344.57, "fiftyTwoWeekLow": 223.78,
    "priceToSalesTrailing12Months": 9.49, "priceToBook": 42.03,
    "enterpriseToEbitda": 27.01, "enterpriseToRevenue": 9.718,
    "grossMargins": 0.48653, "operatingMargins": 0.32623, "profitMargins": 0.2762,
    "returnOnEquity": 1.4875, "returnOnAssets": 0.27082,
    "revenueGrowth": 0.164, "earningsGrowth": 0.287,
    "currentRatio": 1.003, "quickRatio": 0.812, "debtToEquity": 78.445,
    "dividendYield": 0.0035, "enterpriseValue": 4.5e12, "totalRevenue": 4.66e11,
    "ebitda": 1.67e11, "freeCashflow": 1.07e11, "operatingCashflow": 1.46e11,
    "totalCash": 6.2e10, "totalDebt": 8.4e10, "bookValue": 7.36,
    "trailingPegRatio": 2.4944, "ebitdaMargins": 0.35979,
    "sharesOutstanding": 14594180000, "floatShares": 14569223952,
    "heldPercentInsiders": 0.01648, "heldPercentInstitutions": 0.66417,
    "sharesShort": 141606163, "shortPercentOfFloat": 0.0097, "shortRatio": 2.58,
    "dateShortInterest": 1785456000,
    "targetMeanPrice": 324.45, "targetHighPrice": 400.0, "targetLowPrice": 215.0,
    "numberOfAnalystOpinions": 39, "recommendationKey": "buy",
    "recommendationMean": 2.18,
}


def _yf(monkeypatch):
    from src.providers.vendors.market_vendors import YFinanceVendor
    monkeypatch.setattr(YFinanceVendor, "timed_call", lambda self, fn, **kw: _INFO)
    return YFinanceVendor()


def test_yfinance_units_are_normalised_so_agreement_is_real(monkeypatch):
    """Yahoo reports margins as fractions and debt/equity as a percentage;
    Finnhub does the opposite of each. Left unconverted, two vendors that
    agree exactly would look like they disagree by 100x."""
    f = _yf(monkeypatch).get_fundamentals("AAPL")
    assert f.gross_margin_ttm == 48.653      # 0.48653 -> percent
    assert f.roe_ttm == 148.75               # 1.4875  -> percent
    assert f.debt_to_equity == 0.7844        # 78.445  -> ratio
    # And this matches the Finnhub fixture's value for the same field.
    assert f.debt_to_equity == _METRIC["metric"]["totalDebt/totalEquityQuarterly"]


def test_yfinance_contributes_to_fundamentals_at_all(monkeypatch):
    """It is the only keyless fundamentals source, so it is the one that
    answers when every authenticated vendor is unconfigured — which is the
    normal state in local development and CI."""
    f = _yf(monkeypatch).get_fundamentals("AAPL")
    assert f.pe_ratio == 35.48
    assert f.ev_to_ebitda == 27.01
    assert f.vendor_metrics["free_cash_flow"] == 1.07e11
    assert f.vendor_metrics["enterprise_value"] == 4.5e12


def test_ownership_and_short_interest_are_recovered(monkeypatch):
    o = _yf(monkeypatch).get_ownership("AAPL")
    assert o.held_percent_institutions == 0.66417
    assert o.short_percent_of_float == 0.0097
    assert o.float_shares == 14569223952
    assert o.source == "yfinance"


def test_short_interest_always_carries_its_settlement_date(monkeypatch):
    """Exchanges publish this twice a month. A short figure read as current
    is wrong by up to two weeks of trading, so the date is not optional."""
    o = _yf(monkeypatch).get_ownership("AAPL")
    assert o.short_interest_date is not None
    assert o.short_interest_date.count("-") == 2


def test_a_nonsense_short_timestamp_drops_the_date_not_the_block(monkeypatch):
    from src.providers.vendors.market_vendors import YFinanceVendor
    broken = {**_INFO, "dateShortInterest": 9.9e18}
    monkeypatch.setattr(YFinanceVendor, "timed_call", lambda self, fn, **kw: broken)
    o = YFinanceVendor().get_ownership("AAPL")
    assert o is not None
    assert o.short_interest_date is None


def test_the_analyst_rating_keeps_its_scale_with_it(monkeypatch):
    """A mean of 2.18 is meaningless without knowing whose scale it is on."""
    a = _yf(monkeypatch).get_analyst_consensus("AAPL")
    assert a.target_mean == 324.45
    assert (a.target_low, a.target_high) == (215.0, 400.0)
    assert a.recommendation == "buy"
    assert a.recommendation_mean == 2.18
    assert a.source == "yfinance"


def test_an_empty_info_payload_yields_nothing_rather_than_zeroed_objects(monkeypatch):
    from src.providers.vendors.market_vendors import YFinanceVendor
    monkeypatch.setattr(YFinanceVendor, "timed_call", lambda self, fn, **kw: {})
    v = YFinanceVendor()
    assert v.get_fundamentals("ZZZZ") is None
    assert v.get_ownership("ZZZZ") is None
    assert v.get_analyst_consensus("ZZZZ") is None
