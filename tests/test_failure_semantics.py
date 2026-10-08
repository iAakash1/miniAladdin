"""A failure keeps its name all the way up.

Each test pins one place where a failure used to be rewritten into something
that reads like an answer: an outage reported as an unknown symbol, a rejected
key reported as "no street data", a thirty-second timeout cached for six hours
as "this company has no ecosystem", an empty reply from the SEC held for the
life of the process.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from provider_faults import SECRET_KEY, FakeResponse, ScriptedSession
from src.providers.base import FailureClass, VendorError
from src.providers.cache import InMemoryCache
from src.providers.dedupe import SingleFlight
from src.providers.orchestrator import ChainLink, FallbackChain
from src.providers.schemas import OHLCVBar, PriceQuote, PriceSeries, ProviderResult, StreetData
from src.providers.validation import MIN_RETENTION, SeriesQuality
from src.providers.vendors.market_vendors import FinnhubVendor
from src.providers.vendors.sec_vendor import SECVendor
from src.services import company_intelligence, graph_service, street_intelligence


# ── the fallback chain: an outage is not "nobody has it" ──────────────────────

class _Stub:
    """Just enough of a vendor for the chain: a name, health, availability."""

    def __init__(self, name: str, healthy: bool = True, available: bool = True):
        self.NAME, self.healthy, self.available = name, healthy, available


def _chain() -> FallbackChain:
    return FallbackChain("t", InMemoryCache(), SingleFlight(), 60.0)


def _raise(exc: Exception):
    def fetch():
        raise exc
    return fetch


def test_every_vendor_raising_is_an_outage():
    result = _chain().execute("k", [
        ChainLink(_Stub("a"), _raise(VendorError("down", failure_class=FailureClass.UPSTREAM))),
        ChainLink(_Stub("b"), _raise(RuntimeError("adapter bug"))),
    ])
    assert result.data is None and result.outage is True
    assert result.error == "all vendors failed"
    assert result.stale is False and result.cached is False and result.confidence == 0.0


def test_every_vendor_answering_nothing_is_not_an_outage():
    """Both vendors were asked, both said "no such symbol": a fact about the
    symbol. Reporting it as an outage would send a reader to retry forever."""
    result = _chain().execute("k", [
        ChainLink(_Stub("a"), lambda: None),
        ChainLink(_Stub("b"), lambda: None),
    ])
    assert result.data is None and result.outage is False
    assert "no vendor" in (result.error or "")


def test_one_vendor_saying_nothing_outweighs_another_failing():
    """If any vendor answered "I do not have it", the others failing does not
    turn that into an outage: somebody looked, and found nothing."""
    result = _chain().execute("k", [
        ChainLink(_Stub("a"), _raise(VendorError("down"))),
        ChainLink(_Stub("b"), lambda: None),
    ])
    assert result.outage is False


def test_no_vendor_able_to_be_asked_is_an_outage():
    result = _chain().execute("k", [ChainLink(_Stub("a", healthy=False, available=False), lambda: 1)])
    assert result.data is None and result.outage is True


def test_a_failed_vendor_is_skipped_to_the_next_and_the_source_is_the_one_that_answered():
    result = _chain().execute("k", [
        ChainLink(_Stub("a"), _raise(VendorError("401", failure_class=FailureClass.AUTH_FAILURE))),
        ChainLink(_Stub("b"), lambda: "value"),
    ])
    assert result.data == "value" and result.source == "b" and result.outage is False
    assert result.sources_consulted == ["a", "b"]
    assert result.confidence < 0.85, "a fallback answer is not as trusted as the primary"


def test_a_cached_value_is_served_stale_not_live_when_every_vendor_fails():
    cache = InMemoryCache()
    chain = FallbackChain("t", cache, SingleFlight(), 0.0)    # expires immediately
    chain.execute("k", [ChainLink(_Stub("a"), lambda: "first")])
    time.sleep(0.01)
    result = chain.execute("k", [ChainLink(_Stub("a"), _raise(VendorError("down")))])
    assert result.data == "first"
    assert result.stale is True and result.cached is True
    assert result.confidence == pytest.approx(0.30)


def test_recovery_replaces_a_stale_answer_with_a_fresh_one():
    chain = FallbackChain("t", InMemoryCache(), SingleFlight(), 0.0)
    chain.execute("k", [ChainLink(_Stub("a"), lambda: "old")])
    time.sleep(0.01)
    stale = chain.execute("k", [ChainLink(_Stub("a"), _raise(VendorError("down")))])
    time.sleep(0.01)
    fresh = chain.execute("k", [ChainLink(_Stub("a"), lambda: "new")])
    assert stale.stale is True and fresh.data == "new" and fresh.stale is False


def test_a_series_that_lost_too_many_bars_is_a_failure_not_a_thin_success():
    bars = [OHLCVBar(date=f"2026-09-{d:02d}", close=100.0 + d) for d in range(1, 11)]
    damaged = PriceSeries(symbol="X", bars=bars, quality=SeriesQuality(dropped_unreadable=5))
    assert damaged.quality.retention < MIN_RETENTION and not damaged.quality.is_trustworthy
    result = _chain().execute("k", [ChainLink(_Stub("a"), lambda: damaged)])
    assert result.data is None, "a series missing a third of its rows was served as good"
    assert result.outage is True


def test_unreadable_rows_are_counted_in_the_series_quality():
    bars = [OHLCVBar(date="2026-09-01", close=100.0), OHLCVBar(date="2026-09-02", close=101.0)]
    quality = PriceSeries(symbol="X", bars=bars, quality=SeriesQuality(dropped_unreadable=2)).quality
    assert quality.bars_received == 4 and quality.bars_kept == 2
    assert quality.dropped == 2 and "unreadable" in quality.summary()


# ── a quote's price is a price ────────────────────────────────────────────────

@pytest.mark.parametrize("price", [0, 0.0, -1, -0.01, float("nan"), float("inf"), float("-inf")])
def test_a_quote_cannot_be_built_around_something_that_is_not_a_price(price):
    with pytest.raises(ValueError):
        PriceQuote(symbol="X", price=price)


def test_a_real_price_is_accepted():
    assert PriceQuote(symbol="X", price=0.0001).price == 0.0001


# ── street data: a down vendor is not "no street data" ────────────────────────

def _street_vendor(monkeypatch, script):
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET_KEY)
    monkeypatch.setenv("PROVIDER_FINNHUB_RPM", "100000")
    monkeypatch.setattr("src.providers.base.time.sleep", lambda _s: None)
    return FinnhubVendor(session=ScriptedSession(script))


def _routed(recommendation, earnings, insider):
    def script(_method, url, _kwargs):
        if "recommendation" in url:
            return recommendation
        if "earnings" in url:
            return earnings
        return insider
    return script


GOOD_RECS = FakeResponse(200, [{"period": "2026-09-01", "strongBuy": 10, "buy": 12, "hold": 8, "sell": 1, "strongSell": 0}])
GOOD_EARN = FakeResponse(200, [{"period": "2026-06-30", "actual": 1.5, "estimate": 1.4}])
GOOD_INSIDER = FakeResponse(200, {"data": [{"mspr": 12.5, "change": 4000}]})


def test_a_rejected_key_is_an_auth_failure_not_an_absence_of_street_data(monkeypatch):
    denied = FakeResponse(401, {"error": "Invalid API key"})
    vendor = _street_vendor(monkeypatch, _routed(denied, denied, denied))
    with pytest.raises(VendorError) as caught:
        vendor.get_street("AAPL")
    assert caught.value.failure_class == FailureClass.AUTH_FAILURE.value


def test_the_worst_failure_is_the_one_reported(monkeypatch):
    # Keep the circuit closed so all three sections are asked; the point here
    # is which of three different failures the caller is told about.
    monkeypatch.setattr(FinnhubVendor, "COOLDOWN_AFTER_FAILURES", 99)
    vendor = _street_vendor(monkeypatch, _routed(
        FakeResponse(503, {}), FakeResponse(429, {}), FakeResponse(403, {}),
    ))
    with pytest.raises(VendorError) as caught:
        vendor.get_street("AAPL")
    # a plan boundary is more actionable than a limit, which beats an outage
    assert caught.value.failure_class == FailureClass.NOT_ENTITLED.value


def test_a_section_that_failed_is_named_not_presented_as_empty(monkeypatch):
    vendor = _street_vendor(monkeypatch, _routed(GOOD_RECS, GOOD_EARN, FakeResponse(500, {})))
    street = vendor.get_street("AAPL")
    assert street is not None
    assert street.missing_sections == ["insider"]
    assert street.insider_mspr is None, "an unread section was filled with a number"
    block = street_intelligence.build(street)
    assert block["missing_sections"] == ["insider"]
    assert "insider" not in block, "the unread section produced an insider reading"


def test_a_complete_answer_names_no_missing_section(monkeypatch):
    vendor = _street_vendor(monkeypatch, _routed(GOOD_RECS, GOOD_EARN, GOOD_INSIDER))
    street = vendor.get_street("AAPL")
    assert street.missing_sections == []
    assert "missing_sections" not in street_intelligence.build(street)


def test_sections_the_vendor_answered_empty_are_not_failures(monkeypatch):
    vendor = _street_vendor(monkeypatch, _routed(
        FakeResponse(200, []), FakeResponse(200, []), FakeResponse(200, {"data": []}),
    ))
    assert vendor.get_street("AAPL") is None


def test_an_outage_stops_asking_after_the_first_section_trips_the_circuit(monkeypatch):
    session_calls = []
    denied = FakeResponse(401, {"error": "Invalid API key"})

    def script(method, url, kwargs):
        session_calls.append(url)
        return denied
    monkeypatch.setenv("FINNHUB_API_KEY", SECRET_KEY)
    monkeypatch.setenv("PROVIDER_FINNHUB_RPM", "100000")
    vendor = FinnhubVendor(session=ScriptedSession(script))
    with pytest.raises(VendorError):
        vendor.get_street("AAPL")
    assert len(session_calls) == 1, f"a rejected key was asked {len(session_calls)} times"


def test_a_recommendation_row_with_no_counts_is_not_zero_analysts(monkeypatch):
    vendor = _street_vendor(monkeypatch, _routed(
        FakeResponse(200, [{"period": "2026-09-01"}]), GOOD_EARN, GOOD_INSIDER,
    ))
    street = vendor.get_street("AAPL")
    assert street.recommendations == [], "a row stating no counts became '0 analysts'"


# ── the SEC ticker index is kept for the life of the process ─────────────────

def test_an_empty_ticker_index_is_a_failure_and_is_not_remembered(monkeypatch):
    monkeypatch.setattr("src.providers.base.time.sleep", lambda _s: None)
    replies = iter([FakeResponse(200, {}), FakeResponse(200, {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    })])
    vendor = SECVendor(session=ScriptedSession(lambda *_a, **_k: next(replies)))
    with pytest.raises(VendorError) as caught:
        vendor.resolve_cik("AAPL")
    assert caught.value.failure_class == FailureClass.PARSE.value
    assert vendor._ticker_map is None, "an empty index was cached for the life of the process"
    assert vendor.resolve_cik("AAPL")["cik"] == "0000320193", "the next call did not retry"


# ── the research route: outage is 503, an unknown symbol is 404 ──────────────

def _research_client(monkeypatch, offline_network, result):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    api_module._macro_cache.clear()
    return TestClient(api_module.app, raise_server_exceptions=False), result


def _no_prediction(result):
    return patch.object(
        api_module.RiskAwarePredictionAgent, "predict", return_value=None,
    ), patch.object(api_module.providers.market_data, "get_series", return_value=result)


def test_a_price_outage_is_reported_as_503_not_as_an_unknown_symbol(monkeypatch, offline_network):
    client, result = _research_client(monkeypatch, offline_network,
                                      ProviderResult(data=None, error="all vendors failed", outage=True))
    p1, p2 = _no_prediction(result)
    with p1, p2:
        response = client.get("/api/research/AAPL?fast=true")
    assert response.status_code == 503, response.text
    assert "outage" in response.json()["detail"].lower()


def test_a_symbol_every_vendor_lacks_is_still_404(monkeypatch, offline_network):
    client, result = _research_client(monkeypatch, offline_network,
                                      ProviderResult(data=None, error="no vendor had data", outage=False))
    p1, p2 = _no_prediction(result)
    with p1, p2:
        response = client.get("/api/research/ZZZZ?fast=true")
    assert response.status_code == 404, response.text


# ── the quote batch: each symbol keeps its own outcome ───────────────────────

def _series(symbol: str, sessions: int, close0: float = 100.0):
    bars = [OHLCVBar(date=f"2026-09-{d + 1:02d}", close=close0 + d) for d in range(sessions)]
    return ProviderResult(data=PriceSeries(symbol=symbol, bars=bars), source="fixture", confidence=0.85)


def test_a_quote_batch_reports_each_symbol_by_what_happened_to_it(monkeypatch, offline_network):
    outcomes = {
        "AAPL": _series("AAPL", 10),
        "MSFT": ProviderResult(data=None, error="all vendors failed", outage=True),
        "ZZZZ": ProviderResult(data=None, error="no vendor had data for this request", outage=False),
        "NEWC": _series("NEWC", 3),
        "NVDA": _series("NVDA", 10, close0=500.0).model_copy(update={"stale": True}),
    }
    client = TestClient(api_module.app, raise_server_exceptions=False)
    with patch.object(api_module.providers.market_data, "get_series",
                      side_effect=lambda symbol, period: outcomes[symbol]):
        body = client.get("/api/quotes?symbols=AAPL,MSFT,ZZZZ,NEWC,NVDA,WAYTOOLONGSYMBOL").json()
    quotes = body["quotes"]
    assert quotes["AAPL"]["status"] == "ok" and quotes["AAPL"]["price"] == 109.0
    assert quotes["NVDA"]["status"] == "stale" and quotes["NVDA"]["stale"] is True
    assert quotes["MSFT"]["status"] == "unavailable" and "price" not in quotes["MSFT"]
    assert quotes["ZZZZ"]["status"] == "no_data" and "price" not in quotes["ZZZZ"]
    assert quotes["NEWC"]["status"] == "insufficient_history" and "price" not in quotes["NEWC"]
    assert quotes["WAYTOOLONGSYMBOL"]["status"] == "invalid"
    assert body["count"] == 6, "a failing symbol dropped another from the batch"
    # one symbol's failure left the others' numbers alone
    assert quotes["AAPL"]["closes"][-1] == 109.0 and quotes["NVDA"]["closes"][-1] == 509.0


def test_a_symbol_whose_lookup_raises_is_an_error_entry_not_a_failed_batch(monkeypatch, offline_network):
    def lookup(symbol, period):
        if symbol == "BAD":
            raise RuntimeError("boom")
        return _series(symbol, 10)
    client = TestClient(api_module.app, raise_server_exceptions=False)
    with patch.object(api_module.providers.market_data, "get_series", side_effect=lookup):
        response = client.get("/api/quotes?symbols=AAPL,BAD,MSFT")
    assert response.status_code == 200
    quotes = response.json()["quotes"]
    assert quotes["BAD"] == {"error": "unavailable", "status": "error"}
    assert quotes["AAPL"]["status"] == quotes["MSFT"]["status"] == "ok"


# ── a fresh fetch of an old observation is still old ─────────────────────────

from datetime import date, timedelta   # noqa: E402

from src.providers.schemas import MacroSnapshot   # noqa: E402
from src.services import dashboard_service, macro_freshness   # noqa: E402


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _macro(dates: dict[str, str], **values):
    fields = dict(yield_spread=0.4, inflation_rate=2.5, fed_funds_rate=3.0)
    fields.update(values)
    return ProviderResult(data=MacroSnapshot(**fields, observation_dates=dates), source="fred", confidence=0.85)


@pytest.fixture
def macro_client(offline_network):
    api_module._macro_cache.clear()
    yield TestClient(api_module.app, raise_server_exceptions=False)
    api_module._macro_cache.clear()


def test_current_observations_are_not_called_stale():
    assert macro_freshness.stale_fields({
        "yield_spread": _iso(3), "inflation_rate": _iso(45), "fed_funds_rate": _iso(40),
    }) == []


def test_each_series_is_judged_by_its_own_cadence():
    # 30 days is stale for a daily series and perfectly current for a monthly one
    assert macro_freshness.stale_fields({"yield_spread": _iso(30)}) == ["yield_spread"]
    assert macro_freshness.stale_fields({"inflation_rate": _iso(30), "fed_funds_rate": _iso(30)}) == []


def test_a_missing_date_is_not_a_staleness_claim_but_an_unreadable_one_cannot_vouch():
    assert macro_freshness.stale_fields({}) == []
    assert macro_freshness.stale_fields({"yield_spread": "not-a-date"}) == ["yield_spread"]


def test_a_stopped_curve_series_withholds_the_regime_instead_of_applying_it(macro_client):
    result = _macro({"yield_spread": _iso(400), "inflation_rate": _iso(40), "fed_funds_rate": _iso(40)})
    with patch.object(api_module.providers.macro, "get_macro", return_value=result):
        body = macro_client.get("/api/macro").json()
    assert body["risk_multiplier"] is None, "a regime was computed from a term spread over a year old"
    assert body["stats"]["status"] == "UNAVAILABLE"
    assert "yield_spread" in body["stats"]["stale_fields"]
    assert "term spread" in body["stats"]["error"]


def test_a_stale_policy_rate_is_dropped_without_taking_the_regime_with_it(macro_client):
    result = _macro({"yield_spread": _iso(2), "inflation_rate": _iso(40), "fed_funds_rate": _iso(300)})
    with patch.object(api_module.providers.macro, "get_macro", return_value=result):
        body = macro_client.get("/api/macro").json()
    assert body["risk_multiplier"] is not None
    assert body["stats"]["fed_funds_rate"] is None, "a year-old policy rate was shown as current"


def test_current_observations_still_produce_a_regime(macro_client):
    result = _macro({"yield_spread": _iso(2), "inflation_rate": _iso(40), "fed_funds_rate": _iso(40)})
    with patch.object(api_module.providers.macro, "get_macro", return_value=result):
        body = macro_client.get("/api/macro").json()
    assert body["risk_multiplier"] is not None and body["stats"]["status"] != "UNAVAILABLE"


def test_the_dashboard_applies_the_same_gate(offline_network):
    result = _macro({"yield_spread": _iso(400), "inflation_rate": _iso(40)})
    with patch.object(dashboard_service, "_gather", return_value=[]), \
         patch.object(dashboard_service.providers.macro, "get_macro", return_value=result):
        regime = dashboard_service._macro_board()["regime"]
    assert regime["available"] is False and regime["status"] == "UNAVAILABLE"
    assert regime["stale_fields"] == ["yield_spread"]
    assert "risk_multiplier" not in regime


def test_the_setup_hint_is_only_given_when_the_key_is_actually_missing(macro_client, monkeypatch):
    """Telling a deployment whose key IS set to "set FRED_API_KEY" sends the
    operator to fix the wrong thing."""
    down = ProviderResult(data=None, error="all vendors failed", outage=True)
    with patch.object(api_module.providers.macro, "get_macro", return_value=down):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        unset = macro_client.get("/api/macro").json()["stats"]["note"]
        api_module._macro_cache.clear()
        monkeypatch.setenv("FRED_API_KEY", "a-configured-key-value")
        configured = macro_client.get("/api/macro").json()["stats"]["note"]
    assert "Set FRED_API_KEY" in unset
    assert "Set FRED_API_KEY" not in configured


# ── the dashboard says how much of itself it could read ──────────────────────

def _sector_row(symbol: str, name: str, above: bool = True) -> dict:
    return {
        "symbol": symbol, "name": name, "price": 100.0, "strength_21d": 1.0, "momentum_63d": 2.0,
        "volatility": 15.0, "above_50d": above, "verdict": "Hold", "source": "fixture",
        "_closes": [(f"2026-0{1 + i // 28}-{(i % 28) + 1:02d}", 100.0 + i) for i in range(160)],
    }


@pytest.fixture
def dash(offline_network):
    dashboard_service.reset_for_tests()
    yield dashboard_service
    dashboard_service.reset_for_tests()


def _assemble(dash, *, cards, sectors, indexes, regime_ok):
    macro = {"cards": cards, "regime": {"available": regime_ok, "status": "STABLE" if regime_ok else "UNAVAILABLE"}}
    with patch.object(dash, "_macro_board", return_value=macro), \
         patch.object(dash, "_gather", side_effect=lambda fn, items, label, describe: (
             sectors if label == "sectors" else indexes if label == "indexes" else [])), \
         patch.object(dash, "_events", return_value=[]):
        return dash.get_dashboard()


def test_a_dashboard_with_nothing_readable_says_unavailable_and_counts_nothing_as_zero(dash):
    body = _assemble(dash, cards=[], sectors=[], indexes=[], regime_ok=False)
    assert body["status"] == "unavailable"
    assert body["coverage"]["sectors"] == {"available": 0, "expected": 11}
    breadth = body["breadth"]
    assert breadth["sectors_above_50d"] is None and breadth["sector_count"] is None, (
        "no readable sector became '0 of 0 above the 50-day'"
    )
    assert breadth["breadth_score"] is None and breadth["leadership"] is None


def test_a_dashboard_missing_some_sections_is_partial_and_states_the_shortfall(dash):
    rows = [_sector_row(f"X{i}", f"Sector {i}") for i in range(7)]
    body = _assemble(dash, cards=[{"id": "FEDFUNDS"}], sectors=rows, indexes=[{"symbol": "SPY"}], regime_ok=True)
    assert body["status"] == "partial"
    assert body["coverage"]["sectors"] == {"available": 7, "expected": 11}
    assert body["coverage"]["macro_cards"]["expected"] == 19
    assert body["breadth"]["sector_count"] == 7 and body["breadth"]["sector_expected"] == 11


def test_a_whole_dashboard_is_complete(dash):
    rows = [_sector_row(f"X{i}", f"Sector {i}") for i in range(11)]
    cards = [{"id": f"C{i}"} for i in range(19)]
    indexes = [{"symbol": s} for s in ("SPY", "QQQ", "DIA", "IWM", "^VIX")]
    assert _assemble(dash, cards=cards, sectors=rows, indexes=indexes, regime_ok=True)["status"] == "complete"


def test_an_unavailable_dashboard_is_not_cached_and_a_partial_one_only_briefly(dash):
    _assemble(dash, cards=[], sectors=[], indexes=[], regime_ok=False)
    assert "dashboard" not in dash._cache, "an unreadable dashboard was cached"

    rows = [_sector_row("X0", "Sector 0")]
    _assemble(dash, cards=[], sectors=rows, indexes=[], regime_ok=False)
    ttl = dash._cache["dashboard"][0] - time.time()
    assert 0 < ttl <= dash.PARTIAL_TTL_SECONDS + 1 < dash.CACHE_TTL_SECONDS

    dash.reset_for_tests()
    cards = [{"id": f"C{i}"} for i in range(19)]
    full = [_sector_row(f"X{i}", f"S{i}") for i in range(11)]
    idx = [{"symbol": s} for s in ("SPY", "QQQ", "DIA", "IWM", "^VIX")]
    _assemble(dash, cards=cards, sectors=full, indexes=idx, regime_ok=True)
    assert dash._cache["dashboard"][0] - time.time() > dash.PARTIAL_TTL_SECONDS


def test_the_cached_flag_never_leaks_onto_the_stored_dashboard(dash):
    rows = [_sector_row(f"X{i}", f"S{i}") for i in range(11)]
    cards = [{"id": f"C{i}"} for i in range(19)]
    idx = [{"symbol": s} for s in ("SPY", "QQQ", "DIA", "IWM", "^VIX")]
    first = _assemble(dash, cards=cards, sectors=rows, indexes=idx, regime_ok=True)
    second = dash.get_dashboard()
    second["breadth"]["indexes"].append({"symbol": "MUTATED"})
    third = dash.get_dashboard()
    assert first["cached"] is False and second["cached"] is True and third["cached"] is True
    assert {"symbol": "MUTATED"} not in third["breadth"]["indexes"], (
        "one reader's edit to the dashboard reached the next reader"
    )
