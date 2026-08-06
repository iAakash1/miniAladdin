"""
Research prefetch tests.

The prefetch is a latency optimisation that works by side effect: it warms
caches the handler will read, and the handler is not modified at all. That
makes two properties load-bearing, and neither is visible by reading the
handler:

  1. Warming must actually produce a cache hit, or the prefetch is pure
     overhead — it would double every vendor call instead of removing waits.
  2. Warming must never raise, or a speculative optimisation becomes a new
     failure mode for the main research endpoint.

Both are asserted here rather than assumed.
"""

from __future__ import annotations

import threading
import time

import pytest

from src.providers.cache import InMemoryCache
from src.providers.dedupe import SingleFlight
from src.providers.orchestrator import ChainLink, FallbackChain
from src.services import research_prefetch


# ── the cache-hit property ───────────────────────────────────────────────────

class _CountingVendor:
    """Minimal vendor stand-in that records how often it was really called."""

    NAME = "counting"

    def __init__(self, delay: float = 0.0):
        self.calls = 0
        self.delay = delay
        self._lock = threading.Lock()

    @property
    def healthy(self) -> bool:
        return True

    @property
    def available(self) -> bool:
        return True

    def fetch(self, payload="value"):
        time.sleep(self.delay)
        with self._lock:
            self.calls += 1
        return payload


def _chain() -> tuple[FallbackChain, InMemoryCache]:
    cache = InMemoryCache(max_entries=64)
    return FallbackChain("test", cache, SingleFlight(), ttl_seconds=60.0), cache


def test_a_warmed_key_is_served_from_cache_not_the_vendor():
    """The property the whole prefetch design rests on."""
    chain, _ = _chain()
    vendor = _CountingVendor()

    for _ in range(2):
        chain.execute("key:AAPL", [ChainLink(vendor, vendor.fetch)])

    assert vendor.calls == 1, "second call should have been a cache hit"


def test_a_call_racing_the_warm_joins_it_instead_of_duplicating():
    """Single-flight is what makes prefetching safe under concurrency.

    Without it, a handler call arriving while the prefetch is still in
    flight would start a second identical fetch — the prefetch would double
    vendor load rather than remove latency.
    """
    chain, _ = _chain()
    vendor = _CountingVendor(delay=0.15)

    from src.providers.parallel import map_concurrent

    outcomes = map_concurrent(
        lambda _: chain.execute("key:MSFT", [ChainLink(vendor, vendor.fetch)]),
        list(range(6)),
        workers=6,
    )

    assert all(outcome.ok for outcome in outcomes)
    assert vendor.calls == 1, f"expected coalescing, vendor was hit {vendor.calls}x"


# ── never raises ─────────────────────────────────────────────────────────────

def test_warm_reports_every_upstream(monkeypatch):
    monkeypatch.setattr(research_prefetch, "_WARMERS", tuple(
        (label, lambda _t, v=label: (lambda: v))
        for label in ("a", "b", "c")
    ))
    assert research_prefetch.warm("AAPL") == {"a": True, "b": True, "c": True}


def test_warm_survives_every_upstream_failing(monkeypatch):
    """A cold cache is slower, never wrong. Failure here must be invisible."""
    def explode(_ticker):
        def inner():
            raise RuntimeError("vendor down")
        return inner

    monkeypatch.setattr(research_prefetch, "_WARMERS", tuple(
        (label, explode) for label in ("a", "b")
    ))
    assert research_prefetch.warm("AAPL") == {"a": False, "b": False}


def test_warm_survives_a_partial_failure(monkeypatch):
    def maybe(label):
        def factory(_ticker):
            def inner():
                if label == "bad":
                    raise ValueError("nope")
                return label
            return inner
        return factory

    monkeypatch.setattr(research_prefetch, "_WARMERS", (
        ("good", maybe("good")), ("bad", maybe("bad")),
    ))
    assert research_prefetch.warm("AAPL") == {"good": True, "bad": False}


def test_warm_normalises_the_ticker(monkeypatch):
    seen = []
    monkeypatch.setattr(research_prefetch, "_WARMERS", (
        ("only", lambda ticker: lambda: seen.append(ticker)),
    ))
    research_prefetch.warm("  aapl  ".strip())
    assert seen == ["AAPL"]


def test_warmers_cover_the_independent_upstreams():
    """Pins the set, so adding a fetch to the handler without prefetching it
    is a visible omission rather than a silent latency regression."""
    labels = {label for label, _ in research_prefetch._WARMERS}  # noqa: SLF001
    assert labels == {
        "series", "benchmark", "company", "fundamentals",
        "street", "quality", "pead",
    }


def test_news_is_deliberately_not_prefetched():
    """News depends on the company name, which is not known until `company`
    resolves; warming a guessed key would spend budget on a key nobody reads."""
    labels = {label for label, _ in research_prefetch._WARMERS}  # noqa: SLF001
    assert "news" not in labels
