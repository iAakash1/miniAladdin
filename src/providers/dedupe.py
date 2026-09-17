"""
In-flight request deduplication (single-flight).

When N threads ask for the same key concurrently, exactly one performs the
fetch; the rest block on the same result. Endpoints run in FastAPI's
threadpool, so this is thread-based rather than asyncio-based on purpose.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

T = TypeVar("T")


@dataclass
class _Flight:
    """One in-flight call, shared directly by its leader and followers.

    Followers keep this object alive for exactly as long as they need its
    result.  Keeping completed results in a second dictionary keyed by every
    cache key made the deduplicator an unbounded process-lifetime cache.
    """

    event: threading.Event = field(default_factory=threading.Event)
    value: Any = None
    error: BaseException | None = None


class SingleFlight:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, _Flight] = {}
        self.coalesced = 0  # calls served by someone else's fetch

    def do(self, key: str, fn: Callable[[], T]) -> T:
        with self._lock:
            flight = self._inflight.get(key)
            if flight is None:
                flight = _Flight()
                self._inflight[key] = flight
                leader = True
            else:
                leader = False
                self.coalesced += 1

        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            return flight.value  # type: ignore[return-value]

        try:
            value = fn()
            err: BaseException | None = None
        except BaseException as exc:  # propagated to all waiters
            value, err = None, exc
        with self._lock:
            flight.value = value
            flight.error = err
            # A completed flight is no longer globally reachable. Followers
            # already hold their own reference, so a new call for the same key
            # can safely become a new leader without racing their read.
            if self._inflight.get(key) is flight:
                self._inflight.pop(key)
        flight.event.set()
        if err is not None:
            raise err
        return value  # type: ignore[return-value]
