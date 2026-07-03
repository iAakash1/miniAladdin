"""
Cache layer for the provider architecture.

`CacheBackend` is the seam for Redis later: implement the three methods
against redis-py and pass it to the registry — nothing else changes.
The default `InMemoryCache` is thread-safe with TTL + LRU bounding, and
retains expired entries so the orchestrator can serve *stale* values as a
last resort when every vendor is down.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Protocol


class CacheBackend(Protocol):
    def get(self, key: str) -> Optional[tuple[Any, bool]]:
        """Return (value, is_stale) or None when absent."""
        ...

    def set(self, key: str, value: Any, ttl_seconds: float) -> None: ...

    def purge(self) -> None: ...


class InMemoryCache:
    """Thread-safe TTL cache with LRU bound and stale retention."""

    def __init__(self, max_entries: int = 2048, stale_retention_seconds: float = 86400.0):
        self._data: OrderedDict[str, tuple[float, float, Any]] = OrderedDict()
        # key -> (fresh_until, stale_until, value)
        self._lock = threading.Lock()
        self._max = max_entries
        self._stale_retention = stale_retention_seconds
        self.hits = 0
        self.stale_hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[tuple[Any, bool]]:
        now = time.time()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            fresh_until, stale_until, value = entry
            if now <= fresh_until:
                self._data.move_to_end(key)
                self.hits += 1
                return value, False
            if now <= stale_until:
                self.stale_hits += 1
                return value, True
            del self._data[key]
            self.misses += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: float) -> None:
        now = time.time()
        with self._lock:
            self._data[key] = (now + ttl_seconds, now + ttl_seconds + self._stale_retention, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def purge(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._data),
                "hits": self.hits,
                "stale_hits": self.stale_hits,
                "misses": self.misses,
            }
