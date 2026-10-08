"""Failure injection for the three vendors that do not speak HTTP through us.

yfinance, fredapi and Alpha Vantage's own client do their networking inside a
library, so the transport-level matrix cannot reach them. These tests inject at
the library boundary instead: the call raises, hangs, or returns the strange
things those libraries really return - an empty frame, a column of NaN, an
infinite volume, a rate-limit message where data should be.
"""

from __future__ import annotations

import math
import sys
import time
import types

import numpy as np
import pandas as pd
import pytest
import requests

from provider_faults import SECRET_KEY, FakeResponse, ScriptedSession, contains_non_finite
from src.alpha_vantage import AlphaVantageClient
from src.providers.base import FailureClass, VendorClient, VendorError
from src.providers.vendors.data_vendors import AlphaVantageVendor, FredVendor
from src.providers.vendors.market_vendors import YFinanceVendor


# ── yfinance ──────────────────────────────────────────────────────────────────

def _frame(closes, volumes=None, start="2026-09-01"):
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({
        "Open": closes, "High": [c * 1.01 if c == c else c for c in closes],
        "Low": [c * 0.99 if c == c else c for c in closes], "Close": closes,
        "Volume": volumes if volumes is not None else [1_000_000] * len(closes),
    }, index=index)


class _Ticker:
    def __init__(self, history=None, info=None, boom=None):
        self._history, self._info, self._boom = history, info, boom

    def history(self, period="1mo"):
        if self._boom:
            raise self._boom
        return self._history

    @property
    def info(self):
        if self._boom:
            raise self._boom
        return self._info


@pytest.fixture
def yf(monkeypatch):
    holder = {}
    module = types.SimpleNamespace(Ticker=lambda symbol: holder["ticker"], Search=None)
    monkeypatch.setitem(sys.modules, "yfinance", module)
    monkeypatch.setenv("PROVIDER_YFINANCE_RPM", "100000")
    vendor = YFinanceVendor()
    vendor.use = lambda **kw: holder.__setitem__("ticker", _Ticker(**kw))
    return vendor


def test_a_library_exception_is_a_typed_recorded_failure(yf):
    yf.use(boom=RuntimeError("Too Many Requests. Rate limited. Try after a while."))
    with pytest.raises(VendorError) as caught:
        yf.get_series("AAPL", "1mo")
    assert caught.value.failure_class == FailureClass.UNAVAILABLE.value
    assert yf.health_snapshot()["health_state"] != "HEALTHY"


def test_an_empty_frame_is_no_data_not_a_series(yf):
    yf.use(history=pd.DataFrame())
    assert yf.get_series("AAPL", "1mo") is None
    assert yf.get_price("AAPL") is None


def test_a_none_frame_is_no_data(yf):
    yf.use(history=None)
    assert yf.get_series("AAPL", "1mo") is None


def test_non_finite_and_non_positive_closes_never_reach_the_series(yf):
    closes = [100.0, float("nan"), float("inf"), 0.0, -5.0, 101.0, 102.0]
    yf.use(history=_frame(closes))
    series = yf.get_series("AAPL", "1mo")
    assert [b.close for b in series.bars] == [100.0, 101.0, 102.0]
    assert not contains_non_finite(series)


def test_an_infinite_volume_costs_that_field_not_the_history(yf):
    yf.use(history=_frame([100.0, 101.0, 102.0], volumes=[1_000_000, float("inf"), float("nan")]))
    series = yf.get_series("AAPL", "1mo")
    assert [b.close for b in series.bars] == [100.0, 101.0, 102.0]
    assert [b.volume for b in series.bars] == [1_000_000, None, None]


def test_a_quote_made_from_the_last_bar_is_dated_and_labelled(yf):
    yf.use(history=_frame([100.0, 101.0, 102.0]))
    quote = yf.get_price("AAPL")
    assert quote.price == 102.0
    assert quote.as_of == series_last_date(yf)
    assert quote.price_basis == "daily close", "a daily close was presented without saying so"


def series_last_date(vendor):
    return vendor.get_series("AAPL", "1mo").bars[-1].date


def test_a_stale_history_is_dated_so_it_cannot_pass_for_today(yf):
    yf.use(history=_frame([100.0, 101.0], start="2024-01-02"))
    quote = yf.get_price("AAPL")
    assert quote.as_of.startswith("2024-"), "a two-year-old close carried no date"


def test_an_info_payload_of_nothing_is_not_a_company(yf):
    yf.use(info={})
    assert yf.get_company("AAPL") is None
    assert yf.get_fundamentals("AAPL") is None


def test_info_numbers_that_are_not_numbers_are_absent_not_zero(yf):
    yf.use(info={
        "longName": "Apple Inc.", "marketCap": float("nan"), "trailingPE": float("inf"),
        "profitMargins": "n/a", "trailingEps": -3.2, "beta": None, "enterpriseValue": float("-inf"),
    })
    profile = yf.get_company("AAPL")
    assert profile.market_cap is None and profile.beta is None
    fundamentals = yf.get_fundamentals("AAPL")
    assert fundamentals.pe_ratio is None and fundamentals.net_margin_ttm is None
    assert fundamentals.eps == -3.2, "a real negative EPS was dropped"
    assert "enterprise_value" not in fundamentals.vendor_metrics
    assert not contains_non_finite(fundamentals)


# ── a hung library call is cut off ───────────────────────────────────────────

def test_a_hanging_library_call_is_a_timeout_not_a_stuck_worker(yf):
    class Hang(_Ticker):
        def history(self, period="1mo"):
            time.sleep(5)

    yf.CALL_TIMEOUT_SECONDS = 0.2
    holder = sys.modules["yfinance"]
    holder.Ticker = lambda symbol: Hang()
    started = time.monotonic()
    with pytest.raises(VendorError) as caught:
        yf.get_series("AAPL", "1mo")
    assert time.monotonic() - started < 2
    assert caught.value.failure_class == FailureClass.TIMEOUT.value


# ── FRED ──────────────────────────────────────────────────────────────────────

class _Fred:
    def __init__(self, **series):
        self.series, self.calls = series, []

    def get_series(self, series_id):
        self.calls.append(series_id)
        value = self.series[series_id]
        if isinstance(value, BaseException):
            raise value
        return value


def _monthly(values, end="2026-09-01"):
    return pd.Series(values, index=pd.date_range(end=end, periods=len(values), freq="MS"))


def _daily(values, end="2026-10-06"):
    return pd.Series(values, index=pd.bdate_range(end=end, periods=len(values)))


@pytest.fixture
def fred(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", SECRET_KEY)
    monkeypatch.setenv("PROVIDER_FRED_RPM", "100000")
    return FredVendor()


def test_a_missing_fred_key_is_not_configured_not_an_empty_series(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(VendorError):
        FredVendor().get_observations("DGS10")


def test_a_fred_error_is_a_typed_failure(fred):
    fred._fred = _Fred(DGS10=ValueError("Bad Request.  The series does not exist."))
    with pytest.raises(VendorError) as caught:
        fred.get_observations("DGS10")
    assert caught.value.failure_class == FailureClass.UNAVAILABLE.value
    assert SECRET_KEY not in str(caught.value)


def test_an_all_missing_series_is_none_not_an_empty_list(fred):
    fred._fred = _Fred(DGS10=_daily([np.nan, np.nan, np.nan]))
    assert fred.get_observations("DGS10") is None


def test_infinite_observations_are_dropped_not_reported(fred):
    fred._fred = _Fred(DGS10=_daily([4.1, np.inf, 4.2, -np.inf, 4.3]))
    observations = fred.get_observations("DGS10", count=8)
    assert [v for _, v in observations] == [4.1, 4.2, 4.3]
    assert not contains_non_finite(observations)


def test_the_latest_good_observation_is_used_when_the_newest_is_not_a_number(fred):
    fred._fred = _Fred(
        T10Y2Y=_daily([0.30, 0.31, np.inf]),
        CPIAUCNS=_monthly([300.0 + i for i in range(14)]),
        FEDFUNDS=_monthly([4.33, 4.33]),
    )
    snapshot = fred.get_macro()
    assert snapshot.yield_spread == 0.31 and not contains_non_finite(snapshot)
    assert snapshot.observation_dates["yield_spread"] < "2026-10-06", (
        "the date of the older observation must travel with its value"
    )


def test_a_series_with_nothing_readable_is_a_failure_not_a_zero_spread(fred):
    fred._fred = _Fred(
        T10Y2Y=_daily([np.nan, np.inf]), CPIAUCNS=_monthly([300.0] * 14), FEDFUNDS=_monthly([4.33]),
    )
    with pytest.raises(VendorError):
        fred.get_macro()


def test_a_short_cpi_history_leaves_inflation_unknown_not_zero(fred):
    fred._fred = _Fred(
        T10Y2Y=_daily([0.3, 0.31]), CPIAUCNS=_monthly([300.0 + i for i in range(6)]), FEDFUNDS=_monthly([4.33]),
    )
    snapshot = fred.get_macro()
    assert snapshot.inflation_rate is None and snapshot.yield_spread == 0.31


def test_a_failing_optional_policy_rate_does_not_fail_the_snapshot(fred):
    fred._fred = _Fred(
        T10Y2Y=_daily([0.3, 0.31]), CPIAUCNS=_monthly([300.0 + i for i in range(14)]),
        FEDFUNDS=RuntimeError("series discontinued"),
    )
    snapshot = fred.get_macro()
    assert snapshot.fed_funds_rate is None and snapshot.yield_spread == 0.31
    assert "fed_funds_rate" not in snapshot.observation_dates


# ── Alpha Vantage ─────────────────────────────────────────────────────────────

def _av(script, monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", SECRET_KEY)
    monkeypatch.setenv("PROVIDER_ALPHA_VANTAGE_RPM", "100000")
    vendor = AlphaVantageVendor()
    vendor._client._session = ScriptedSession(script)
    return vendor


GOOD_OVERVIEW = {"Symbol": "AAPL", "Name": "Apple Inc", "PERatio": "30.5", "EPS": "6.1", "MarketCapitalization": "3000000000000",
                 "AnalystTargetPrice": "210", "Beta": "1.2"}


@pytest.mark.parametrize("response,expected", [
    (FakeResponse(401, {}), FailureClass.AUTH_FAILURE),
    (FakeResponse(403, {}), FailureClass.NOT_ENTITLED),
    (FakeResponse(429, {}), FailureClass.RATE_LIMITED),
    (FakeResponse(200, {"Note": "Thank you for using Alpha Vantage! Our standard API call frequency is 5 calls per minute."}), FailureClass.RATE_LIMITED),
    (FakeResponse(200, {"Information": "Our standard API rate limit is 25 requests per day."}), FailureClass.RATE_LIMITED),
    (FakeResponse(200, {"Information": "This is a premium endpoint. Subscribe to a premium plan."}), FailureClass.NOT_ENTITLED),
    (FakeResponse(200, json_error="Expecting value"), FailureClass.PARSE),
    (FakeResponse(200, [1, 2, 3]), FailureClass.PARSE),
    (requests.exceptions.ReadTimeout("slow"), FailureClass.TIMEOUT),
    (requests.exceptions.ConnectionError(f"failed apikey={SECRET_KEY}"), FailureClass.UPSTREAM),
], ids=["401", "403", "429", "note_rate", "information_rate", "premium", "bad_json", "list_body", "timeout", "connection"])
def test_an_alpha_vantage_failure_keeps_its_name(response, expected, monkeypatch):
    vendor = _av(lambda *a, **k: response, monkeypatch)
    for call in (lambda: vendor.get_fundamentals("AAPL"), lambda: vendor.get_analyst_targets("AAPL"),
                 lambda: vendor.get_news_sentiment("AAPL")):
        with pytest.raises(VendorError) as caught:
            call()
        assert caught.value.failure_class == expected.value
        assert SECRET_KEY not in str(caught.value)


def test_an_empty_overview_is_no_data_not_a_failure(monkeypatch):
    vendor = _av(lambda *a, **k: FakeResponse(200, {}), monkeypatch)
    assert vendor.get_fundamentals("ZZZZ") is None
    assert vendor.get_analyst_targets("ZZZZ") is None


def test_alpha_vantage_numbers_that_are_not_numbers_are_absent(monkeypatch):
    payload = dict(GOOD_OVERVIEW, PERatio="nan", EPS="inf", Beta="-inf", AnalystTargetPrice="None")
    vendor = _av(lambda *a, **k: FakeResponse(200, payload), monkeypatch)
    data = vendor.get_fundamentals("AAPL")
    assert data.pe_ratio is None and data.eps is None and data.beta is None
    assert data.profile.market_cap == 3e12
    assert not contains_non_finite(data)


def test_failures_do_not_leak_between_threads(monkeypatch):
    """One client serves every request thread; a failure belongs to the thread
    that suffered it."""
    import threading

    vendor = _av(lambda *a, **k: FakeResponse(200, GOOD_OVERVIEW), monkeypatch)
    client = vendor._client
    seen = []

    def failing():
        client._session = ScriptedSession(lambda *a, **k: FakeResponse(429, {}))
        client._get({"function": "OVERVIEW"})
        seen.append(client.last_failure()[0])

    t = threading.Thread(target=failing)
    t.start(), t.join()
    assert seen == [FailureClass.RATE_LIMITED.value]
    assert client.last_failure() == (None, ""), "this thread was told about another thread's failure"


# ── Yahoo RSS: a 200 that is not a feed ──────────────────────────────────────

_EMPTY_FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><title>Yahoo</title></channel></rss>'
_ONE_ITEM = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
             b'<item><title>Apple beats</title><link>https://finance.yahoo.com/n/a</link></item>'
             b'</channel></rss>')


@pytest.fixture
def yahoo(monkeypatch):
    """A Yahoo RSS adapter whose fetch returns the given body, for the whole test."""
    from src.providers.vendors.news_vendors import YahooRssVendor

    def make(body: bytes):
        monkeypatch.setattr(YahooRssVendor, "timed_call", lambda self, fn, **kw: body)
        return YahooRssVendor()

    return make


def test_an_empty_feed_is_no_headlines_not_a_failure(yahoo):
    vendor = yahoo(_EMPTY_FEED)
    assert vendor.get_news("AAPL", limit=5) is None
    assert vendor.stats.last_failure_class is None


def test_a_feed_with_a_story_is_read(yahoo):
    [headline] = yahoo(_ONE_ITEM).get_news("AAPL", limit=5)
    assert headline.title == "Apple beats"


@pytest.mark.parametrize("body", [
    b"<html><body>Rate limited</body></html>",
    b"<!doctype html><html><head><title>Consent</title></head></html>",
    b"",
    b"not xml at all",
    b'{"error": "blocked"}',
])
def test_a_200_that_is_not_a_feed_is_a_recorded_failure_not_no_headlines(yahoo, body):
    vendor = yahoo(body)
    with pytest.raises(VendorError) as caught:
        vendor.get_news("AAPL", limit=5)
    assert caught.value.failure_class == FailureClass.PARSE.value
    assert vendor.stats.last_failure_class == FailureClass.PARSE.value
