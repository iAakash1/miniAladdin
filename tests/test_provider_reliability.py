"""Reliability boundaries that answered a different question than the one asked.

A limiter that only counts while everything works, a window that silently
becomes three months, a class share that cannot be searched for, and an outage
drawn as an empty chart.
"""

from unittest.mock import patch

import requests

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.providers.base import VendorClient, VendorError
from src.providers.vendors.market_vendors import PERIOD_DAYS, UnknownPeriod, _period_to_days


# ── one rate-limit token per physical request ───────────────────────────────

class _Counting(VendorClient):
    """A vendor whose transport always fails transiently."""

    KEY_ENV = None
    NAME = "counting"
    MAX_RETRIES = 2
    BACKOFF_BASE = 0.0

    def __init__(self):
        super().__init__()
        self.sent = 0


def _always_transient(self, *a, **kw):
    self.sent += 1
    raise VendorError("HTTP 503", transient=True)


def test_every_retry_consumes_a_rate_limit_token():
    """The limiter was acquired once for up to three physical requests.

    It therefore undercounted precisely when the vendor was already failing —
    the moment its quota matters most and the moment retries push the outbound
    rate highest.
    """
    vendor = _Counting()
    taken = []
    # A transport error the loop actually retries — a bare Exception is not
    # caught there, and using one would prove nothing about the retry path.
    with patch.object(type(vendor.rate_limiter), "try_acquire",
                      side_effect=lambda: (taken.append(1), True)[1]), \
         patch.object(vendor._session, "request",
                      side_effect=requests.ConnectionError("refused")):
        with pytest.raises(VendorError):
            vendor._request_json("GET", "https://example.invalid/x", operation="probe")
    assert len(taken) == vendor.MAX_RETRIES + 1, (
        f"{vendor.MAX_RETRIES + 1} physical requests consumed {len(taken)} tokens"
    )


def test_a_single_successful_call_takes_exactly_one_token():
    vendor = _Counting()
    taken = []

    class _OK:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"ok": True}

    with patch.object(type(vendor.rate_limiter), "try_acquire",
                      side_effect=lambda: (taken.append(1), True)[1]), \
         patch.object(vendor._session, "request", return_value=_OK()):
        vendor._request_json("GET", "https://example.invalid/x", operation="probe")
    assert len(taken) == 1


def test_being_rate_limited_before_the_first_request_still_raises():
    vendor = _Counting()
    with patch.object(type(vendor.rate_limiter), "try_acquire", return_value=False), \
         patch.object(vendor._session, "request") as send:
        with pytest.raises(VendorError, match="rate limit"):
            vendor._request_json("GET", "https://example.invalid/x", operation="probe")
    assert send.call_count == 0, "a request was sent without a token"


# ── an unknown period is refused, not resolved ──────────────────────────────

@pytest.mark.parametrize("period", sorted(PERIOD_DAYS))
def test_every_named_period_still_resolves(period):
    assert _period_to_days(period) == PERIOD_DAYS[period]


@pytest.mark.parametrize("period", ["1w", "10y", "3momths", "", "3MO", "max "])
def test_an_unnamed_period_is_refused(period):
    """It used to fall through to 92 days under whatever label was asked for."""
    with pytest.raises(UnknownPeriod):
        _period_to_days(period)


@pytest.fixture
def client():
    return TestClient(api.app)


def test_the_chart_endpoint_refuses_an_unknown_period(client):
    r = client.get("/api/chart/AAPL?period=1w")
    assert r.status_code == 422, f"an unknown period answered {r.status_code}"
    assert "1w" in r.json()["detail"]


def test_the_chart_endpoint_accepts_every_named_period(client):
    for period in PERIOD_DAYS:
        with patch.object(api.providers.market_data, "get_series") as fetch:
            fetch.return_value = type("R", (), {
                "ok": False, "error": "stub", "sources_consulted": [], "stale": False,
            })()
            r = client.get(f"/api/chart/AAPL?period={period}")
        assert r.status_code == 200, f"{period} was refused"


# ── a provider failure is not an empty chart ────────────────────────────────

def _result(ok, bars=None, error=None, stale=False, source="v"):
    data = type("D", (), {"bars": bars or []})()
    return type("R", (), {
        "ok": ok, "data": data, "error": error, "stale": stale,
        "source": source, "sources_consulted": ["a", "b"],
    })()


def test_a_provider_outage_is_reported_as_unavailable(client):
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(False, error="all vendors failed")):
        body = client.get("/api/chart/AAPL").json()
    assert body["status"] == "unavailable", "an outage was drawn as an empty chart"
    assert body["prices"] == []
    assert body["error"] == "all vendors failed"
    assert body["sources_consulted"] == ["a", "b"]


def test_a_security_with_no_sessions_is_reported_as_empty(client):
    """Every provider answered and none had a bar. A fact about the security."""
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(True, bars=[])):
        body = client.get("/api/chart/AAPL").json()
    assert body["status"] == "empty"
    assert body["error"] is None, "an empty history was reported as an error"
    assert body["prices"] == []


def test_the_two_empty_states_are_distinguishable(client):
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(False, error="down")):
        outage = client.get("/api/chart/AAPL").json()
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(True, bars=[])):
        empty = client.get("/api/chart/AAPL").json()
    assert outage["prices"] == empty["prices"] == []
    assert outage["status"] != empty["status"], (
        "a provider outage and a security with no history are indistinguishable"
    )


def test_an_exception_is_reported_as_an_error_not_an_empty_chart(client):
    with patch.object(api.providers.market_data, "get_series", side_effect=RuntimeError("x")):
        body = client.get("/api/chart/AAPL").json()
    assert body["status"] == "error"
    assert body["prices"] == []


def test_a_stale_series_is_labelled_stale(client):
    bar = type("B", (), {"date": "2026-09-04", "close": 100.0, "volume": 10})()
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(True, bars=[bar], stale=True)):
        body = client.get("/api/chart/AAPL").json()
    assert body["status"] == "stale" and body["stale"] is True
    assert len(body["prices"]) == 1


def test_a_healthy_series_is_ok_and_names_its_source(client):
    bar = type("B", (), {"date": "2026-09-04", "close": 100.0, "volume": 10})()
    with patch.object(api.providers.market_data, "get_series",
                      return_value=_result(True, bars=[bar], source="polygon")):
        body = client.get("/api/chart/AAPL").json()
    assert body["status"] == "ok" and body["source"] == "polygon"


# ── class shares survive search ─────────────────────────────────────────────

def test_symbol_search_no_longer_filters_on_punctuation():
    """`"." not in symbol` dropped BRK.B, BF.B and every other class share."""
    import inspect
    from src.providers.vendors.market_vendors import FinnhubVendor
    src = inspect.getsource(FinnhubVendor.search_symbols)
    assert '"." not in' not in src, "search still rejects dotted tickers"
    assert 'exchange="US"' in src, (
        "search does not ask the vendor to filter by exchange, which is the "
        "only thing that can tell BRK.B from VOD.L"
    )


# ── native library calls are bounded ────────────────────────────────────────

class _Native(VendorClient):
    KEY_ENV = None
    NAME = "native"
    CALL_TIMEOUT_SECONDS = 0.3
    COOLDOWN_AFTER_FAILURES = 99  # keep cooldown out of these assertions


def test_a_hanging_library_call_is_cut_off():
    """A timeout that is never enforced is not a timeout.

    yfinance and fredapi do their own networking, where `requests`' timeout
    cannot reach, so an unbounded call held a FastAPI worker until restart.
    """
    import time as _t
    vendor = _Native()
    started = _t.perf_counter()
    with pytest.raises(VendorError, match="exceeded"):
        vendor.timed_call(lambda: _t.sleep(30), operation="hang")
    elapsed = _t.perf_counter() - started
    assert elapsed < 5, f"the call was not bounded; it took {elapsed:.1f}s"


def test_a_timeout_is_recorded_as_a_failure():
    import time as _t
    vendor = _Native()
    with pytest.raises(VendorError):
        vendor.timed_call(lambda: _t.sleep(30), operation="hang")
    assert vendor.stats.consecutive_failures >= 1, "a timeout was not recorded as a failure"


def test_a_timeout_is_transient_so_the_chain_falls_through():
    import time as _t
    vendor = _Native()
    try:
        vendor.timed_call(lambda: _t.sleep(30), operation="hang")
    except VendorError as exc:
        assert exc.transient is True, "a timeout was terminal, so no fallback was tried"


def test_a_fast_call_is_unaffected():
    vendor = _Native()
    assert vendor.timed_call(lambda: 42, operation="quick") == 42


def test_an_explicit_budget_overrides_the_default():
    import time as _t
    vendor = _Native()
    assert vendor.timed_call(lambda: (_t.sleep(0.05), "ok")[1], operation="q", timeout=5) == "ok"


def test_a_raising_call_is_still_normalised_to_a_vendor_error():
    vendor = _Native()
    with pytest.raises(VendorError):
        vendor.timed_call(lambda: (_ for _ in ()).throw(RuntimeError("boom")), operation="bad")


def test_the_earnings_lookup_goes_through_the_reliability_layer():
    """It called `yf.Ticker(...).calendar` inside the research request path."""
    import inspect
    src = inspect.getsource(api.research_ticker) if hasattr(api, "research_ticker") else \
        api.Path("api/index.py").read_text()
    assert "timed_call(_fetch, operation=\"earnings_calendar\")" in src, (
        "the earnings calendar still bypasses rate limiting, stats and timeout"
    )
