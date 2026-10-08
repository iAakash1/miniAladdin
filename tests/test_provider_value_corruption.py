"""A corrupt *value* inside an otherwise good reply must not become a number.

`test_provider_failure_matrix` covers replies that are wrong as a whole.  This
covers the quieter case: the reply is well-formed and nearly right, and one
field is not.  NaN, Infinity, `null`, `"n/a"`, an empty string, a zero where a
price should be, a negative where a price should be.  Each is substituted into
every numeric field of a realistic payload, one at a time, and four things are
required of whatever comes out:

  * it is a `VendorError`, `None`, or a model - nothing else escapes;
  * no number in the model is NaN or infinite;
  * no number appears that was not in the clean answer or the payload - in
    particular no zero conjured from a field that was merely unreadable;
  * a quote's price and every bar's close is finite and positive.

And for replies that carry many records, one unreadable record costs exactly
that record: the other bars, headlines and observations survive.  A batch is not
all-or-nothing because one row was damaged.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest

from provider_faults import (
    SECRET_KEY,
    FakeResponse,
    ScriptedSession,
    contains_non_finite,
    numeric_paths,
    with_value,
)
from src.providers.base import VendorError
from src.providers.vendors.macro_vendors import (
    BeaVendor,
    BlsVendor,
    EcbVendor,
    EiaVendor,
    TreasuryFiscalVendor,
    WorldBankVendor,
)
from src.providers.vendors.market_vendors import (
    FinnhubVendor,
    FMPVendor,
    MarketStackVendor,
    PolygonVendor,
    TwelveDataVendor,
)
from src.providers.vendors.massive_vendor import MassiveVendor
from src.providers.vendors.news_vendors import GNewsVendor, MarketauxVendor, NewsApiVendor
from src.providers.vendors.tiingo_vendor import TiingoVendor

NOW = datetime.now(timezone.utc)


def _day(back: int) -> datetime:
    return (NOW - timedelta(days=back)).replace(hour=14, minute=0, second=0, microsecond=0)


def _ms(back: int) -> int:
    return int(_day(back).timestamp() * 1000)


def _iso(back: int) -> str:
    return _day(back).date().isoformat()


BACKS = (6, 5, 4, 3, 2)   # five recent sessions, oldest first


# ── clean payloads, one per operation ─────────────────────────────────────────

def polygon_quote():
    return {"status": "OK", "resultsCount": 1, "results": [
        {"c": 189.5, "h": 191.0, "l": 188.0, "o": 189.0, "v": 51000000.0, "vw": 189.7, "n": 600000, "t": _ms(1)}]}


def polygon_series():
    return {"status": "OK", "results": [
        {"c": 100.0 + i, "h": 101.0 + i, "l": 99.0 + i, "o": 100.5 + i, "v": 1000000.0 + i, "t": _ms(b)}
        for i, b in enumerate(BACKS)]}


def polygon_company():
    return {"status": "OK", "results": {
        "name": "Apple Inc.", "homepage_url": "https://www.apple.com", "market_cap": 3.0e12,
        "total_employees": 160000, "sic_description": "ELECTRONIC COMPUTERS",
        "primary_exchange": "XNAS", "currency_name": "usd", "description": "Designs devices.",
        "locale": "us", "list_date": "1980-12-12"}}


def finnhub_quote():
    return {"c": 189.5, "d": 1.2, "dp": 0.64, "h": 191.0, "l": 188.0, "o": 189.0, "pc": 188.3, "t": int(_day(1).timestamp())}


def finnhub_company():
    return {"name": "Apple Inc", "finnhubIndustry": "Technology", "marketCapitalization": 3000000.0,
            "currency": "USD", "exchange": "NASDAQ", "weburl": "https://www.apple.com/",
            "ipo": "1980-12-12", "logo": "https://x/logo.png", "country": "US"}


def finnhub_fundamentals():
    return {"metric": {"peTTM": 30.5, "epsTTM": 6.1, "beta": 1.2, "52WeekHigh": 200.0, "52WeekLow": 150.0,
                       "currentDividendYieldTTM": 0.5, "netProfitMarginTTM": 25.3, "psTTM": 8.1,
                       "pbQuarterly": 40.2, "roeTTM": 150.0, "revenueGrowthTTMYoy": 5.5}}


def finnhub_targets():
    return {"targetMean": 210.0, "targetHigh": 250.0, "targetLow": 170.0, "numberOfAnalysts": 40}


def twelvedata_quote():
    return {"symbol": "AAPL", "close": "189.5", "open": "189.0", "high": "191.0", "low": "188.0",
            "previous_close": "188.3", "volume": "5000000", "datetime": _iso(1),
            "fifty_two_week": {"high": "200.0", "low": "150.0"}}


def twelvedata_series():
    return {"meta": {"symbol": "AAPL"}, "status": "ok", "values": [
        {"datetime": _iso(b), "open": str(100.5 + i), "high": str(101.0 + i), "low": str(99.0 + i),
         "close": str(100.0 + i), "volume": str(1000000 + i)} for i, b in enumerate(BACKS)]}


def fmp_quote():
    return [{"symbol": "AAPL", "price": 189.5, "change": 1.2, "changePercentage": 0.64, "volume": 5000000.0,
             "dayLow": 188.0, "dayHigh": 191.0, "yearHigh": 200.0, "yearLow": 150.0, "marketCap": 3.0e12,
             "priceAvg50": 185.0, "priceAvg200": 170.0, "exchange": "NASDAQ", "open": 189.0,
             "previousClose": 188.3, "timestamp": int(_day(1).timestamp())}]


def fmp_series():
    return [{"symbol": "AAPL", "date": _iso(b), "adjOpen": 100.5 + i, "adjHigh": 101.0 + i,
             "adjLow": 99.0 + i, "adjClose": 100.0 + i, "volume": 1000000 + i}
            for i, b in reversed(list(enumerate(BACKS)))]


def fmp_company():
    return [{"companyName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics",
             "marketCap": 3.0e12, "currency": "USD", "exchange": "NASDAQ", "website": "https://www.apple.com",
             "description": "Designs devices.", "ceo": "Tim Cook", "fullTimeEmployees": "164000",
             "country": "US", "ipoDate": "1980-12-12", "beta": 1.2, "image": "https://x/i.png"}]


def fmp_fundamentals():
    return [{"priceToEarningsRatioTTM": 30.5, "netIncomePerShareTTM": 6.1}]


def marketstack_series():
    return {"pagination": {"count": 5}, "data": [
        {"date": f"{_iso(b)}T00:00:00+0000", "open": 100.5 + i, "high": 101.0 + i, "low": 99.0 + i,
         "close": 100.0 + i, "adj_close": 100.0 + i, "volume": 1000000.0 + i}
        for i, b in reversed(list(enumerate(BACKS)))]}


def tiingo_quote():
    return [{"ticker": "AAPL", "tngoLast": 189.5, "last": 189.4, "bidPrice": 189.4, "askPrice": 189.6,
             "mid": 189.5, "prevClose": 188.3, "open": 189.0, "high": 191.0, "low": 188.0,
             "volume": 5000000, "bidSize": 100, "askSize": 100,
             "lastSaleTimeStamp": _day(1).isoformat()}]


def tiingo_series():
    return [{"date": f"{_iso(b)}T00:00:00.000Z", "close": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
             "open": 100.5 + i, "volume": 1000000 + i, "adjClose": 100.0 + i, "adjHigh": 101.0 + i,
             "adjLow": 99.0 + i, "adjOpen": 100.5 + i, "adjVolume": 1000000 + i}
            for i, b in enumerate(BACKS)]


def _article(i: int) -> dict[str, Any]:
    return {"title": f"Apple announces development number {i} today", "description": "Details.",
            "url": f"https://news.example/{i}", "publishedAt": _day(i).isoformat(),
            "source": {"name": "Reuters"}, "urlToImage": "https://x/i.jpg", "author": "A. Writer"}


def newsapi_payload():
    return {"status": "ok", "totalResults": 4, "articles": [_article(i) for i in range(1, 5)]}


def gnews_payload():
    return {"totalArticles": 4, "articles": [dict(_article(i), image="https://x/i.jpg") for i in range(1, 5)]}


def marketaux_payload():
    return {"meta": {"found": 4}, "data": [
        {"title": f"Apple announces development number {i} today", "source": "reuters.com",
         "url": f"https://news.example/{i}", "published_at": _day(i).isoformat(),
         "description": "Details.", "image_url": "https://x/i.jpg",
         "entities": [{"symbol": "AAPL", "sentiment_score": 0.3}]} for i in range(1, 5)]}


def tiingo_news():
    return [{"title": f"Apple announces development number {i} today", "source": "reuters",
             "url": f"https://news.example/{i}", "publishedDate": _day(i).isoformat(),
             "description": "Details.", "tags": ["earnings"], "tickers": ["aapl"]} for i in range(1, 5)]


def bls_payload():
    return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [
        {"year": "2026", "period": f"M0{m}", "value": f"{4.0 + m / 10:.1f}"} for m in range(1, 6)]}]}}


def eia_payload():
    return {"response": {"data": [
        {"series": "RWTC", "period": f"2026-0{m}", "value": 70.0 + m} for m in range(1, 6)]}}


def treasury_payload():
    return {"data": [{"record_date": f"2026-0{m}-28", "security_desc": "Total Marketable",
                      "avg_interest_rate_amt": f"{3.0 + m / 10:.1f}"} for m in range(1, 6)]}


def ecb_payload():
    return {"dataSets": [{"series": {"0:0:0:0:0:0:0": {"observations": {str(i): [2.0 + i / 4] for i in range(5)}}}}],
            "structure": {"dimensions": {"observation": [{"values": [{"id": f"2026-0{m}-01"} for m in range(1, 6)]}]}}}


def worldbank_payload():
    return [{"page": 1}, [{"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "WLD",
                           "date": str(2020 + i), "value": 2.0 + i / 10} for i in range(5)]]


def bea_payload():
    return {"BEAAPI": {"Results": {"Data": [
        {"LineNumber": "1", "SeriesCode": "A191RL", "CL_UNIT": "Percent change, annual rate",
         "TimePeriod": f"202{y}Q{q}", "DataValue": f"{2.0 + q / 10:.1f}"} for y in (4, 5) for q in (1, 2, 3)]}}}


class Case:
    def __init__(self, vendor, method, args, payload: Callable[[], Any], kind: str, *, records=None):
        self.vendor, self.method, self.args = vendor, method, args
        self.payload, self.kind = payload, kind
        #: JSON-path (tuple of keys) to the list of records, for survival checks.
        self.records = records

    @property
    def id(self) -> str:
        return f"{self.vendor.NAME}.{self.method}"


CASES = [
    Case(PolygonVendor, "get_price", ("AAPL",), polygon_quote, "quote"),
    Case(PolygonVendor, "get_series", ("AAPL", "1mo"), polygon_series, "series", records=("results",)),
    Case(PolygonVendor, "get_company", ("AAPL",), polygon_company, "profile"),
    Case(MassiveVendor, "get_price", ("AAPL",), polygon_quote, "quote"),
    Case(MassiveVendor, "get_series", ("AAPL", "1mo"), polygon_series, "series", records=("results",)),
    Case(MassiveVendor, "get_company", ("AAPL",), polygon_company, "profile"),
    Case(FinnhubVendor, "get_price", ("AAPL",), finnhub_quote, "quote"),
    Case(FinnhubVendor, "get_company", ("AAPL",), finnhub_company, "profile"),
    Case(FinnhubVendor, "get_fundamentals", ("AAPL",), finnhub_fundamentals, "metrics"),
    Case(FinnhubVendor, "get_analyst_targets", ("AAPL",), finnhub_targets, "metrics"),
    Case(TwelveDataVendor, "get_price", ("AAPL",), twelvedata_quote, "quote"),
    Case(TwelveDataVendor, "get_series", ("AAPL", "1mo"), twelvedata_series, "series", records=("values",)),
    Case(FMPVendor, "get_price", ("AAPL",), fmp_quote, "quote"),
    Case(FMPVendor, "get_series", ("AAPL", "1mo"), fmp_series, "series", records=()),
    Case(FMPVendor, "get_company", ("AAPL",), fmp_company, "profile"),
    Case(FMPVendor, "get_fundamentals", ("AAPL",), fmp_fundamentals, "metrics"),
    Case(MarketStackVendor, "get_series", ("AAPL", "1mo"), marketstack_series, "series", records=("data",)),
    Case(TiingoVendor, "get_quote", ("AAPL",), tiingo_quote, "quote"),
    Case(TiingoVendor, "get_series", ("AAPL", "1mo"), tiingo_series, "series", records=()),
    Case(TiingoVendor, "get_news", ("AAPL", 8), tiingo_news, "news", records=()),
    Case(NewsApiVendor, "get_news", ("AAPL", "Apple", 8), newsapi_payload, "news", records=("articles",)),
    Case(GNewsVendor, "get_news", ("AAPL", "Apple", 8), gnews_payload, "news", records=("articles",)),
    Case(MarketauxVendor, "get_news", ("AAPL", "Apple", 8), marketaux_payload, "news", records=("data",)),
    Case(BlsVendor, "get_official_series", ("UNRATE", 8), bls_payload, "observations",
         records=("Results", "series", 0, "data")),
    Case(EiaVendor, "get_energy_series", ("EIA_WTI_M", 8), eia_payload, "observations",
         records=("response", "data")),
    Case(TreasuryFiscalVendor, "get_context_series", ("TSY_AVG_RATE", 8), treasury_payload, "observations",
         records=("data",)),
    Case(EcbVendor, "get_context_series", ("ECB_DFR", 8), ecb_payload, "observations"),
    Case(WorldBankVendor, "get_context_series", ("WB_GDP_WORLD", 8), worldbank_payload, "observations",
         records=(1,)),
    Case(BeaVendor, "get_official_series", ("A191RL1Q225SBEA", 8), bea_payload, "observations",
         records=("BEAAPI", "Results", "Data")),
]

#: What a damaged value is replaced with.  `0` and `-1` are the dangerous ones:
#: they are numbers, so nothing downstream will question them.
JUNK = (float("nan"), float("inf"), float("-inf"), None, "NaN", "Infinity", "n/a", "", 0, -1)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr("src.providers.base.time.sleep", lambda _s: None)
    for case in CASES:
        monkeypatch.setenv(f"PROVIDER_{case.vendor.NAME.upper()}_RPM", "100000")


def _run(case: Case, payload: Any, monkeypatch) -> tuple[Any, BaseException | None]:
    if case.vendor.KEY_ENV:
        monkeypatch.setenv(case.vendor.KEY_ENV, SECRET_KEY)
    vendor = case.vendor(session=ScriptedSession(FakeResponse(200, payload)))
    try:
        return getattr(vendor, case.method)(*case.args), None
    except BaseException as exc:  # noqa: BLE001
        return None, exc


def _numbers(node: Any) -> list[float]:
    """Every finite number in a model/dict/list, bools excluded.

    `quality` is bookkeeping about the series (how many bars were received,
    dropped, kept), not data the vendor sent, so it is not part of the answer.
    """
    if hasattr(node, "model_dump"):
        node = node.model_dump(exclude={"quality"} if hasattr(node, "quality") else None)
    out: list[float] = []
    if isinstance(node, dict):
        for value in node.values():
            out.extend(_numbers(value))
    elif isinstance(node, (list, tuple)):
        for value in node:
            out.extend(_numbers(value))
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.append(float(node))
    elif isinstance(node, str):
        try:
            out.append(float(node))
        except ValueError:
            pass
    return out


def _payload_numbers(node: Any) -> set[float]:
    return {n for n in _numbers(node) if math.isfinite(n)}


def _leaf_paths(case: Case) -> list[tuple]:
    base = case.payload()
    paths = numeric_paths(base)
    # Numeric strings ("189.5", "4.3") are numbers as far as the adapters care.
    def strings(node, prefix=()):
        found = []
        if isinstance(node, dict):
            for k, v in node.items():
                found.extend(strings(v, prefix + (k,)))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                found.extend(strings(v, prefix + (i,)))
        elif isinstance(node, str):
            try:
                float(node)
                found.append(prefix)
            except ValueError:
                pass
        return found
    return paths + strings(base)


def _all_cases():
    for case in CASES:
        for path in _leaf_paths(case):
            yield pytest.param(case, path, id=f"{case.id}:{'.'.join(map(str, path))}")


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_the_clean_payload_is_actually_accepted(case, monkeypatch):
    """Guards the fixtures themselves: a corruption test over a payload the
    adapter rejects outright would pass for the wrong reason."""
    value, exc = _run(case, case.payload(), monkeypatch)
    assert exc is None, f"{case.id} rejected its own clean fixture: {exc!r}"
    assert value, f"{case.id} returned nothing for its clean fixture"


@pytest.mark.parametrize("case,path", list(_all_cases()))
def test_a_damaged_value_never_becomes_a_number_nobody_sent(case, path, monkeypatch):
    clean_value, clean_exc = _run(case, case.payload(), monkeypatch)
    assert clean_exc is None
    allowed = _payload_numbers(clean_value) | _payload_numbers(case.payload())
    baseline_has_zero = 0.0 in {n for n in _numbers(clean_value)}

    for junk in JUNK:
        damaged = with_value(case.payload(), path, junk)
        value, exc = _run(case, damaged, monkeypatch)
        label = f"{case.id} with {'.'.join(map(str, path))}={junk!r}"
        if exc is not None:
            assert isinstance(exc, VendorError), f"{label} leaked {type(exc).__name__}: {exc}"
            continue
        if value is None:
            continue
        assert not contains_non_finite(value), f"{label} produced a non-finite number"
        produced = _numbers(value)
        stray = {n for n in produced if math.isfinite(n)} - allowed
        # A vendor that sends 0 or -1 has *sent a number*; passing it through a
        # non-price field is reporting, not inventing. (Price and close are held
        # to "finite and positive" separately, below.)
        if junk in (0, -1):
            stray -= {float(junk)}
        assert not stray, f"{label} produced numbers nobody sent: {sorted(stray)}"
        if not baseline_has_zero:
            assert 0.0 not in produced or junk == 0, f"{label} conjured a zero"
        if case.kind == "quote":
            assert value.price > 0 and math.isfinite(value.price), f"{label}: price {value.price!r}"
        if case.kind == "series":
            assert all(b.close > 0 and math.isfinite(b.close) for b in value.bars), (
                f"{label}: non-positive close in {[b.close for b in value.bars]}"
            )


# ── one bad record must cost one record ──────────────────────────────────────

def _records(case: Case, payload: Any) -> list:
    cursor = payload
    for step in case.records:
        cursor = cursor[step]
    return cursor


def _outcome_size(case: Case, value: Any) -> int:
    if case.kind == "series":
        return len(value.bars)
    return len(value)


SURVIVAL = [c for c in CASES if c.records is not None]
REQUIRED_FIELD = {
    # which key of a record makes the record unusable when it is destroyed
    "series": {"PolygonVendor": "c", "MassiveVendor": "c", "TwelveDataVendor": "close",
               "FMPVendor": "adjClose", "MarketStackVendor": "close", "TiingoVendor": "adjClose"},
    "news": {"TiingoVendor": "title", "NewsApiVendor": "title", "GNewsVendor": "title",
             "MarketauxVendor": "title"},
}


@pytest.mark.parametrize("case", [c for c in SURVIVAL if c.kind in REQUIRED_FIELD], ids=lambda c: c.id)
@pytest.mark.parametrize("damage", ["not_a_dict", "null_record", "required_field_wrong_type"])
def test_one_unreadable_record_costs_that_record_and_no_other(case, damage, monkeypatch):
    clean_value, exc = _run(case, case.payload(), monkeypatch)
    assert exc is None
    total = _outcome_size(case, clean_value)
    assert total >= 4

    payload = case.payload()
    records = _records(case, payload)
    required = REQUIRED_FIELD[case.kind][case.vendor.__name__]
    if damage == "not_a_dict":
        records[2] = "garbage"
    elif damage == "null_record":
        records[2] = None
    else:
        records[2][required] = ["unexpected", "list"]

    value, exc = _run(case, payload, monkeypatch)
    assert exc is None, (
        f"{case.id}: one {damage} record failed the whole batch of {total}: {exc!r}"
    )
    survived = _outcome_size(case, value)
    assert survived >= total - 1, (
        f"{case.id}: {total} records, one damaged ({damage}), only {survived} survived"
    )
