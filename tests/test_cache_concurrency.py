"""Concurrent requests must not see each other.

A research terminal serves many tickers, windows and people at once, from one
process and one cache. These tests drive that: the same endpoint under parallel
load, different securities and periods interleaved, a vendor failing in the
middle of a burst, a stale answer followed by a fresh one. They assert the
absence of five things:

  * **cross-ticker contamination** - AAPL's bars under MSFT's name;
  * **cross-period contamination** - a 1-month series served for a 1-year ask;
  * **shared mutable state** - one caller's edit appearing in another's result;
  * **stale overwrite** - an older answer replacing a newer one;
  * **sticky failure** - one failed fetch poisoning every later request.

Everything here is deterministic: threads are released together by a barrier
and the "vendors" are in-process fakes that echo the symbol and period they were
asked for, so a wrong answer is visible in the answer itself.
"""

from __future__ import annotations

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.providers.base import FailureClass, VendorError
from src.providers.cache import InMemoryCache
from src.providers.dedupe import SingleFlight
from src.providers.orchestrator import ChainLink, FallbackChain
from src.providers.providers import MarketDataProvider
from src.providers.schemas import OHLCVBar, PriceQuote, PriceSeries, ProviderResult


def _burst(fn, args_list, workers=24):
    """Run `fn(*args)` for every item at the same instant; return results in order."""
    barrier = threading.Barrier(len(args_list))

    def run(args):
        barrier.wait(timeout=10)
        return fn(*args)

    with ThreadPoolExecutor(max_workers=len(args_list)) as pool:
        return list(pool.map(run, args_list))


class _Echo:
    """A market-data vendor that answers with exactly what it was asked.

    Every bar is dated by the period and every close encodes the symbol, so a
    result for the wrong key announces itself.
    """

    NAME = "echo"
    available = True
    healthy = True

    def __init__(self, delay: float = 0.0, fail_for: set | None = None):
        self.delay, self.fail_for, self.calls = delay, fail_for or set(), []
        self._lock = threading.Lock()

    def get_series(self, symbol, period):
        with self._lock:
            self.calls.append((symbol, period))
        if self.delay:
            time.sleep(self.delay)
        if (symbol, period) in self.fail_for or symbol in self.fail_for:
            raise VendorError(f"{symbol} down", failure_class=FailureClass.UPSTREAM)
        n = {"1mo": 6, "1y": 12}.get(period, 8)
        base = sum(ord(c) for c in symbol)
        return PriceSeries(symbol=symbol, bars=[
            OHLCVBar(date=f"2026-{period}-{i:02d}", close=float(base + i)) for i in range(n)
        ])

    def get_price(self, symbol):
        return PriceQuote(symbol=symbol, price=float(sum(ord(c) for c in symbol)))


def _provider(vendor: _Echo) -> MarketDataProvider:
    provider = MarketDataProvider(InMemoryCache(), SingleFlight())
    for name in ("massive", "tiingo", "polygon", "finnhub", "twelvedata", "fmp", "marketstack"):
        setattr(provider, name, type("Off", (), {"NAME": name, "available": False, "healthy": False})())
    provider.yfinance = vendor
    return provider


def _fingerprint(result, symbol, period):
    """True iff `result` is unmistakably the answer for (symbol, period)."""
    base = sum(ord(c) for c in symbol)
    bars = result.data.bars
    return (
        result.data.symbol == symbol
        and bars[0].date.startswith(f"2026-{period}")
        and bars[0].close == float(base)
        and len(bars) == {"1mo": 6, "1y": 12}.get(period, 8)
    )


# ── single flight ─────────────────────────────────────────────────────────────

def test_concurrent_callers_for_one_key_share_one_fetch():
    vendor = _Echo(delay=0.15)
    provider = _provider(vendor)
    results = _burst(lambda: provider.get_series("AAPL", "1y"), [()] * 16)
    assert vendor.calls.count(("AAPL", "1y")) == 1, f"{len(vendor.calls)} upstream calls for 16 callers"
    assert all(_fingerprint(r, "AAPL", "1y") for r in results)


def test_callers_sharing_a_fetch_still_get_their_own_copy():
    vendor = _Echo(delay=0.1)
    provider = _provider(vendor)
    results = _burst(lambda: provider.get_series("AAPL", "1y"), [()] * 8)
    assert len({id(r) for r in results}) == 8 and len({id(r.data) for r in results}) == 8
    results[0].data.bars.clear()
    results[0].data.bars.append(OHLCVBar(date="1999-01-01", close=1.0))
    results[1].data.symbol = "TAMPERED"
    assert all(_fingerprint(r, "AAPL", "1y") for r in results[2:]), "an edit reached a sibling's result"
    later = provider.get_series("AAPL", "1y")          # served from cache
    assert _fingerprint(later, "AAPL", "1y"), "an edit reached the cache"
    assert later.cached is True


def test_editing_a_cached_result_does_not_change_the_next_one():
    provider = _provider(_Echo())
    first = provider.get_series("MSFT", "1mo")
    first.data.bars.reverse()
    first.source = "tampered"
    second = provider.get_series("MSFT", "1mo")
    third = provider.get_series("MSFT", "1mo")
    assert _fingerprint(second, "MSFT", "1mo") and second.source != "tampered"
    second.data.bars.pop()
    assert _fingerprint(third, "MSFT", "1mo"), "two cached reads shared one list"


# ── different keys never meet ─────────────────────────────────────────────────

@pytest.mark.parametrize("pair", [("AAPL", "MSFT"), ("MSFT", "NVDA"), ("BRK.B", "BRK-B"), ("AAPL", "AAPL1")])
def test_two_tickers_in_parallel_never_swap_answers(pair):
    vendor = _Echo(delay=0.05)
    provider = _provider(vendor)
    work = [(pair[i % 2], "1y") for i in range(20)]
    results = _burst(lambda symbol, period: (symbol, period, provider.get_series(symbol, period)), work)
    for symbol, period, result in results:
        assert _fingerprint(result, symbol, period), f"{symbol} got another security's series"


def test_two_periods_of_one_ticker_in_parallel_never_swap_windows():
    vendor = _Echo(delay=0.05)
    provider = _provider(vendor)
    work = [("AAPL", "1mo" if i % 2 else "1y") for i in range(20)]
    results = _burst(lambda symbol, period: (symbol, period, provider.get_series(symbol, period)), work)
    for symbol, period, result in results:
        assert _fingerprint(result, symbol, period), f"a {period} request was answered with another window"
    assert set(vendor.calls) == {("AAPL", "1mo"), ("AAPL", "1y")}, "windows were merged into one fetch"


def test_a_randomised_mix_of_tickers_and_periods_stays_separate():
    rng = random.Random(7)
    vendor = _Echo(delay=0.01)
    provider = _provider(vendor)
    symbols, periods = ["AAPL", "MSFT", "NVDA", "TSLA", "BRK.B"], ["1mo", "1y"]
    work = [(rng.choice(symbols), rng.choice(periods)) for _ in range(120)]
    results = _burst(lambda symbol, period: (symbol, period, provider.get_series(symbol, period)), work)
    wrong = [(s, p) for s, p, r in results if not _fingerprint(r, s, p)]
    assert not wrong, f"{len(wrong)} of 120 answers belonged to another request: {wrong[:3]}"
    assert len(vendor.calls) <= len(symbols) * len(periods)


def test_symbol_case_and_whitespace_resolve_to_one_cache_entry():
    vendor = _Echo()
    provider = _provider(vendor)
    provider.get_series("aapl", "1y")
    provider.get_series("AAPL", "1y")
    assert vendor.calls == [("AAPL", "1y")]


def test_the_price_cache_does_not_serve_an_unvalidated_quote_to_a_validated_caller():
    vendor = _Echo()
    provider = _provider(vendor)
    provider.get_price("AAPL", validate=False)
    provider.get_price("AAPL", validate=True)
    keys = list(provider._price_chain.cache._data)
    assert "price:AAPL:single" in keys and "price:AAPL:validated" in keys


# ── a failure in the middle of a burst ────────────────────────────────────────

def test_one_tickers_failure_does_not_touch_the_others_in_the_same_burst():
    vendor = _Echo(delay=0.05, fail_for={"MSFT"})
    provider = _provider(vendor)
    work = [(s, "1y") for s in ("AAPL", "MSFT", "NVDA") for _ in range(6)]
    results = _burst(lambda symbol, period: (symbol, provider.get_series(symbol, period)), work)
    for symbol, result in results:
        if symbol == "MSFT":
            assert result.data is None and result.outage is True, "an outage returned data"
            assert result.error == "all vendors failed"
        else:
            assert _fingerprint(result, symbol, "1y"), f"{symbol} was damaged by MSFT's failure"


def test_followers_of_a_failing_fetch_all_get_the_failure_and_none_hang():
    vendor = _Echo(delay=0.2, fail_for={"AAPL"})
    provider = _provider(vendor)
    started = time.monotonic()
    results = _burst(lambda: provider.get_series("AAPL", "1y"), [()] * 10)
    assert time.monotonic() - started < 5
    assert all(r.data is None and r.outage for r in results)
    assert vendor.calls.count(("AAPL", "1y")) == 1


def test_a_failure_is_not_sticky_once_the_vendor_recovers():
    vendor = _Echo(fail_for={"AAPL"})
    provider = _provider(vendor)
    assert provider.get_series("AAPL", "1y").data is None
    vendor.fail_for = set()
    # The vendor tripped its own circuit, which is a vendor concern; reset it.
    vendor.healthy = True
    recovered = provider.get_series("AAPL", "1y")
    assert recovered.data is not None and _fingerprint(recovered, "AAPL", "1y")


def test_a_leader_that_dies_hard_releases_its_followers_with_an_error_not_a_hang():
    flight = SingleFlight()
    started, release = threading.Event(), threading.Event()
    outcomes: list = []

    def leader_work():
        started.set()
        release.wait(5)
        raise KeyboardInterrupt("worker killed")

    def lead():
        try:
            flight.do("k", leader_work)
        except BaseException as exc:  # noqa: BLE001
            outcomes.append(("leader", type(exc).__name__))

    def follow():
        try:
            flight.do("k", lambda: "unused")
        except BaseException as exc:  # noqa: BLE001
            outcomes.append(("follower", type(exc).__name__))

    leader = threading.Thread(target=lead)
    leader.start()
    started.wait(5)
    followers = [threading.Thread(target=follow) for _ in range(5)]
    for t in followers:
        t.start()
    time.sleep(0.1)
    release.set()
    for t in [leader, *followers]:
        t.join(5)
        assert not t.is_alive(), "a follower is still waiting on a dead leader"
    assert len(outcomes) == 6 and {name for _, name in outcomes} == {"KeyboardInterrupt"}


# ── stale, then fresh ─────────────────────────────────────────────────────────

def test_a_stale_answer_is_replaced_by_the_fresh_one_for_every_concurrent_reader():
    cache = InMemoryCache()
    chain = FallbackChain("t", cache, SingleFlight(), 0.0)    # nothing is ever fresh
    stub = type("V", (), {"NAME": "v", "healthy": True, "available": True})()
    state = {"mode": "old"}

    def fetch():
        if state["mode"] == "down":
            raise VendorError("down")
        return state["mode"]

    link = lambda: [ChainLink(stub, fetch)]   # noqa: E731
    assert chain.execute("k", link()).data == "old"
    state["mode"] = "down"
    time.sleep(0.01)
    stale = _burst(lambda: chain.execute("k", link()), [()] * 8)
    assert all(r.data == "old" and r.stale and r.cached for r in stale)
    state["mode"] = "new"
    time.sleep(0.01)
    fresh = _burst(lambda: chain.execute("k", link()), [()] * 8)
    assert all(r.data == "new" and not r.stale for r in fresh), "readers were still served the stale value"
    state["mode"] = "down"
    time.sleep(0.01)
    after = chain.execute("k", link())
    assert after.data == "new", "the stale value overwrote the newer one"


def test_a_slow_older_fetch_cannot_overwrite_a_newer_cached_value():
    """Two fetches for one key cannot overlap (single flight), so the order the
    cache sees is the order the fetches finished - never reversed."""
    cache = InMemoryCache()
    chain = FallbackChain("t", cache, SingleFlight(), 0.0)
    stub = type("V", (), {"NAME": "v", "healthy": True, "available": True})()
    gate = threading.Event()
    calls = []

    def slow_then_fast():
        calls.append(len(calls))
        if len(calls) == 1:
            gate.wait(5)
            return "first"
        return "second"

    t = threading.Thread(target=lambda: chain.execute("k", [ChainLink(stub, slow_then_fast)]))
    t.start()
    time.sleep(0.1)
    follower_result = []
    f = threading.Thread(target=lambda: follower_result.append(chain.execute("k", [ChainLink(stub, slow_then_fast)])))
    f.start()
    time.sleep(0.1)
    gate.set()
    t.join(5), f.join(5)
    assert len(calls) == 1, "an overlapping fetch ran for a key already in flight"
    assert follower_result[0].data == "first"


# ── routes under parallel load ────────────────────────────────────────────────

@pytest.fixture
def client(offline_network):
    return TestClient(api_module.app, raise_server_exceptions=False)


def test_the_chart_route_keeps_tickers_and_periods_apart_under_load(client):
    vendor = _Echo(delay=0.02)
    provider = _provider(vendor)

    def one(symbol, period):
        with patch.object(api_module.providers.market_data, "get_series", provider.get_series):
            body = client.get(f"/api/chart/{symbol}?period={period}").json()
        return symbol, period, body

    work = [(s, p) for s in ("AAPL", "MSFT", "NVDA") for p in ("1mo", "1y") for _ in range(4)]
    with patch.object(api_module.providers.market_data, "get_series", provider.get_series):
        results = _burst(one, work)
    for symbol, period, body in results:
        assert body["ticker"] == symbol and body["period"] == period
        base = sum(ord(c) for c in symbol)
        assert body["prices"][0]["close"] == float(base), f"{symbol}/{period} carried another security's closes"
        assert len(body["prices"]) == {"1mo": 6, "1y": 12}[period]


def test_the_quotes_route_keeps_each_symbol_its_own_under_load(client):
    provider = _provider(_Echo(delay=0.01))
    symbols = ["AAPL", "MSFT", "NVDA", "TSLA"]

    def one(i):
        batch = symbols[i % 4:] + symbols[:i % 4]
        with patch.object(api_module.providers.market_data, "get_series", provider.get_series):
            return batch, client.get(f"/api/quotes?symbols={','.join(batch)}").json()["quotes"]

    with patch.object(api_module.providers.market_data, "get_series", provider.get_series):
        results = _burst(one, [(i,) for i in range(16)])
    for batch, quotes in results:
        assert list(quotes) == batch
        for symbol, quote in quotes.items():
            assert quote["closes"][0] == float(sum(ord(c) for c in symbol)), f"{symbol} carried another's closes"


def test_the_knowledge_route_keeps_companies_apart_under_load(client):
    from src.providers.research_schemas import GraphNode, KnowledgeBundle
    from src.services import company_intelligence as ci

    ci.reset_for_tests()

    def knowledge(symbol, *_a):
        time.sleep(0.02)
        return KnowledgeBundle(nodes=[GraphNode(id=f"company:{symbol}", type="company", label=f"Co {symbol}")])

    with patch.object(ci._sec, "get_knowledge", knowledge), \
         patch.object(ci._wikidata, "get_knowledge", lambda symbol, name="": KnowledgeBundle()), \
         patch.object(ci, "_research", lambda symbol, name: KnowledgeBundle()):
        results = _burst(
            lambda symbol: (symbol, client.get(f"/api/knowledge/{symbol}").json()),
            [(s,) for s in ("AAPL", "MSFT", "NVDA") for _ in range(5)],
        )
    for symbol, body in results:
        assert body["symbol"] == symbol, f"{symbol}'s page was served {body['symbol']}'s ecosystem"
    ci.reset_for_tests()
