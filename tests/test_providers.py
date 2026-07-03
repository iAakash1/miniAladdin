"""
Unit tests for the provider framework: fallback chains, cooldown skipping,
stale-cache last resort, single-flight dedupe, confidence scoring and the
TTL cache. No network — vendors are fakes.
"""

from __future__ import annotations

import threading
import time

from src.providers.base import VendorClient, VendorError
from src.providers.cache import InMemoryCache
from src.providers.dedupe import SingleFlight
from src.providers.orchestrator import (
    CONF_DISAGREE,
    CONF_FALLBACK,
    CONF_MULTI_AGREE,
    CONF_PRIMARY,
    CONF_STALE,
    ChainLink,
    FallbackChain,
)
from src.providers.schemas import PriceQuote


class FakeVendor(VendorClient):
    KEY_ENV = None  # keyless → always configured
    DEFAULT_RPM = 10_000

    def __init__(self, name: str, price=None, fail: bool = False):
        self.NAME = name
        super().__init__()
        self._price = price
        self._fail = fail
        self.calls = 0

    def fetch(self):
        self.calls += 1
        if self._fail:
            raise VendorError(f"{self.NAME} down", transient=False)
        if self._price is None:
            return None
        return PriceQuote(symbol="TEST", price=self._price)


def make_chain(ttl: float = 60.0):
    cache = InMemoryCache()
    return FallbackChain[PriceQuote]("test.price", cache, SingleFlight(), ttl), cache


def link(vendor: FakeVendor) -> ChainLink[PriceQuote]:
    return ChainLink(vendor, vendor.fetch)


class TestFallback:
    def test_primary_success_uses_first_vendor(self):
        chain, _ = make_chain()
        first, second = FakeVendor("a", 100.0), FakeVendor("b", 101.0)
        result = chain.execute("k1", [link(first), link(second)])
        assert result.ok and result.source == "a"
        assert result.confidence == CONF_PRIMARY
        assert second.calls == 0

    def test_falls_through_failed_vendors(self):
        chain, _ = make_chain()
        result = chain.execute(
            "k2",
            [link(FakeVendor("a", fail=True)), link(FakeVendor("b", price=None)), link(FakeVendor("c", 99.0))],
        )
        assert result.ok and result.source == "c"
        assert result.confidence == CONF_FALLBACK
        assert result.sources_consulted == ["a", "b", "c"]

    def test_unconfigured_vendor_is_skipped(self):
        chain, _ = make_chain()

        class KeyedVendor(FakeVendor):
            KEY_ENV = "DEFINITELY_NOT_SET_ENV_VAR"

        keyed = KeyedVendor("keyed", 50.0)
        backup = FakeVendor("backup", 51.0)
        result = chain.execute("k3", [link(keyed), link(backup)])
        assert result.source == "backup"
        assert keyed.calls == 0

    def test_cooldown_vendor_is_skipped(self):
        chain, _ = make_chain()
        hot = FakeVendor("hot", 42.0)
        cooling = FakeVendor("cooling", 41.0)
        cooling._cooldown_until = time.monotonic() + 60
        result = chain.execute("k4", [link(cooling), link(hot)])
        assert result.source == "hot"
        assert cooling.calls == 0

    def test_all_vendors_failed_no_cache_returns_error(self):
        chain, _ = make_chain()
        result = chain.execute("k5", [link(FakeVendor("a", fail=True))])
        assert not result.ok
        assert result.confidence == 0.0
        assert result.error


class TestCacheBehavior:
    def test_fresh_cache_served_without_vendor_call(self):
        chain, _ = make_chain()
        vendor = FakeVendor("a", 10.0)
        chain.execute("k6", [link(vendor)])
        second = chain.execute("k6", [link(vendor)])
        assert vendor.calls == 1
        assert second.cached is True and second.stale is False

    def test_stale_cache_is_last_resort_with_low_confidence(self):
        chain, cache = make_chain(ttl=0.01)
        good = FakeVendor("a", 10.0)
        chain.execute("k7", [link(good)])
        time.sleep(0.03)  # entry now stale but retained
        dead = FakeVendor("a", fail=True)
        result = chain.execute("k7", [link(dead)])
        assert result.ok and result.stale is True
        assert result.confidence == CONF_STALE
        assert result.data.price == 10.0

    def test_lru_bound(self):
        cache = InMemoryCache(max_entries=2)
        cache.set("a", 1, 60)
        cache.set("b", 2, 60)
        cache.set("c", 3, 60)
        assert cache.get("a") is None
        assert cache.get("c") == (3, False)


class TestConfidence:
    def test_two_sources_agree_full_confidence(self):
        chain, _ = make_chain()
        result = chain.execute(
            "k8",
            [link(FakeVendor("a", 100.0)), link(FakeVendor("b", 100.2))],
            cross_validate=lambda quote: quote.price,
        )
        assert result.confidence == CONF_MULTI_AGREE
        assert not result.disagreement
        assert len(result.readings) == 2

    def test_material_disagreement_lowers_confidence(self):
        chain, _ = make_chain()
        result = chain.execute(
            "k9",
            [link(FakeVendor("a", 100.0)), link(FakeVendor("b", 110.0))],
            cross_validate=lambda quote: quote.price,
        )
        assert result.confidence == CONF_DISAGREE
        assert result.disagreement is True

    def test_single_source_keeps_primary_confidence(self):
        chain, _ = make_chain()
        result = chain.execute(
            "k10",
            [link(FakeVendor("a", 100.0))],
            cross_validate=lambda quote: quote.price,
        )
        assert result.confidence == CONF_PRIMARY


class TestSingleFlight:
    def test_concurrent_calls_coalesce_to_one_fetch(self):
        chain, _ = make_chain()
        slow_calls = []

        class SlowVendor(FakeVendor):
            def fetch(self):
                slow_calls.append(1)
                time.sleep(0.05)
                return PriceQuote(symbol="TEST", price=7.0)

        vendor = SlowVendor("slow")
        results = []

        def run():
            results.append(chain.execute("k11", [link(vendor)]))

        threads = [threading.Thread(target=run) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(slow_calls) == 1
        assert len(results) == 5
        assert all(item.ok and item.data.price == 7.0 for item in results)


class TestRateLimiter:
    def test_local_rate_limit_raises_transient_vendor_error(self):
        class TinyLimit(FakeVendor):
            DEFAULT_RPM = 1

        vendor = TinyLimit("tiny", 5.0)
        assert vendor.rate_limiter.try_acquire() is True
        assert vendor.rate_limiter.try_acquire() is False
