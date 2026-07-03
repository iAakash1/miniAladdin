"""
Provider registry — process-wide singletons sharing one cache and one
single-flight table. Swap `InMemoryCache` for a Redis-backed CacheBackend
here and every provider follows.

Usage:
    from src.providers import market_data, fundamentals, news, macro, search
    quote = market_data.get_price("NVDA")
"""

from __future__ import annotations

from typing import Any

from src.providers.cache import InMemoryCache
from src.providers.dedupe import SingleFlight
from src.providers.providers import (
    FundamentalsProvider,
    MacroProvider,
    MarketDataProvider,
    NewsProvider,
    SearchProvider,
)

cache = InMemoryCache(max_entries=4096)
_flight = SingleFlight()

market_data = MarketDataProvider(cache, _flight)
fundamentals = FundamentalsProvider(cache, _flight, market=market_data)
news = NewsProvider(cache, _flight)
macro = MacroProvider(cache, _flight)
search = SearchProvider(cache, _flight, news=news)

_ALL = {
    "market_data": market_data,
    "fundamentals": fundamentals,
    "news": news,
    "macro": macro,
    "search": search,
}


def providers_health() -> dict[str, Any]:
    """Aggregated health/latency/success statistics for every vendor."""
    seen: set[int] = set()
    domains: dict[str, list[dict[str, Any]]] = {}
    for name, provider in _ALL.items():
        rows = []
        for vendor in provider.vendors:
            snapshot = vendor.health_snapshot()
            snapshot["shared"] = id(vendor) in seen
            seen.add(id(vendor))
            rows.append(snapshot)
        domains[name] = rows
    return {
        "providers": domains,
        "cache": cache.stats(),
        "deduplicated_requests": _flight.coalesced,
    }
