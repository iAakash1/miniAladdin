"""Shared eviction primitives for small process-local service caches."""

from __future__ import annotations

from typing import Any, MutableMapping


def put_ttl(
    cache: MutableMapping[str, tuple[float, Any]],
    key: str,
    expires_at: float,
    value: Any,
    *,
    max_entries: int,
    now: float,
) -> None:
    """Insert after purging expired values, then evict oldest expiries."""
    if max_entries < 1:
        raise ValueError("max_entries must be positive")
    for candidate, entry in list(cache.items()):
        if entry[0] <= now:
            cache.pop(candidate, None)
    cache.pop(key, None)
    cache[key] = (expires_at, value)
    while len(cache) > max_entries:
        victim = min(cache, key=lambda candidate: cache[candidate][0])
        cache.pop(victim, None)


def put_bounded(
    cache: MutableMapping[str, Any], key: str, value: Any, *, max_entries: int
) -> None:
    """Insertion-ordered bound for maps whose values have no TTL."""
    if max_entries < 1:
        raise ValueError("max_entries must be positive")
    cache.pop(key, None)
    cache[key] = value
    while len(cache) > max_entries:
        cache.pop(next(iter(cache)))
