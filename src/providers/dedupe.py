"""
In-flight request deduplication (single-flight).

When N threads ask for the same key concurrently, exactly one performs the
fetch; the rest block on the same result. Endpoints run in FastAPI's
threadpool, so this is thread-based rather than asyncio-based on purpose.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class SingleFlight:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._results: dict[str, tuple[Any, BaseException | None]] = {}
        self.coalesced = 0  # calls served by someone else's fetch

    def do(self, key: str, fn: Callable[[], T]) -> T:
        with self._lock:
            event = self._inflight.get(key)
            if event is None:
                event = threading.Event()
                self._inflight[key] = event
                leader = True
            else:
                leader = False
                self.coalesced += 1

        if not leader:
            event.wait()
            value, err = self._results[key]
            if err is not None:
                raise err
            return value  # type: ignore[return-value]

        try:
            value = fn()
            err: BaseException | None = None
        except BaseException as exc:  # propagated to all waiters
            value, err = None, exc
        with self._lock:
            self._results[key] = (value, err)
            self._inflight.pop(key, None)
        event.set()
        # Results are cleared lazily on the next leader for the same key;
        # bounded because keys are cache keys with finite cardinality.
        if err is not None:
            raise err
        return value  # type: ignore[return-value]
