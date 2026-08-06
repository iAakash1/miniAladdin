"""
Per-request latency attribution — "where did this request's time go?"

## Flat, not a tree

The obvious design is a span tree, and it is the wrong one here. This
backend fans out provider calls across eight threads, so sibling spans
*overlap*. A tree that shows a 4 s parent containing six 3 s children is not
describing nesting, it is describing parallelism, and the arithmetic
underneath it stops meaning anything.

A flat accumulator keyed by `name{labels}` stays honest under concurrency,
and it answers the two questions that actually come up:

- **Where did the time go?** Total milliseconds per label, sorted.
- **Was it parallel?** `work_ms / wall_ms`. A ratio near 1 means the request
  was serialised; the dashboard's fan-out should show roughly 3, and if it
  ever drops back to 1 the concurrency has silently regressed.

That second number is the one that would have caught a fan-out degrading to
a sequential loop, which no per-vendor average could ever reveal.

## Threads

The profile lives in a `contextvars.ContextVar`, and `contextvars` do **not**
propagate into `ThreadPoolExecutor` workers automatically. `map_concurrent`
therefore copies the calling context into each worker, so a provider call
made inside a fan-out attributes to the request that caused it. Because the
copied context shares the *same* profile object, every mutation is behind a
lock.
"""

from __future__ import annotations

import contextvars
import threading
import time
from typing import Any, Optional

#: Keeps a pathological request from allocating unboundedly. Labels are
#: closed sets, so hitting this means a caller is labelling by something
#: unbounded — the same bug `MetricsRegistry.MAX_SERIES` guards against.
MAX_LABELS_PER_REQUEST = 128


class RequestProfile:
    """Accumulated time per label for one request. Thread-safe."""

    __slots__ = ("name", "started", "_totals", "_counts", "_lock", "_dropped")

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = time.perf_counter()
        self._totals: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._dropped = 0

    def record(self, key: str, milliseconds: float) -> None:
        with self._lock:
            if key not in self._totals and len(self._totals) >= MAX_LABELS_PER_REQUEST:
                self._dropped += 1
                return
            self._totals[key] = self._totals.get(key, 0.0) + milliseconds
            self._counts[key] = self._counts.get(key, 0) + 1

    def report(self) -> dict[str, Any]:
        wall_ms = (time.perf_counter() - self.started) * 1000.0
        with self._lock:
            totals = dict(self._totals)
            counts = dict(self._counts)
            dropped = self._dropped

        work_ms = sum(totals.values())
        breakdown = [
            {
                "label": key,
                "calls": counts[key],
                "total_ms": round(total, 1),
                "share_pct": round(100.0 * total / work_ms, 1) if work_ms else 0.0,
            }
            for key, total in sorted(totals.items(), key=lambda kv: -kv[1])
        ]

        report: dict[str, Any] = {
            "request": self.name,
            "wall_ms": round(wall_ms, 1),
            "work_ms": round(work_ms, 1),
            # >1 means work happened in parallel; ~1 means serialised. This is
            # the number that reveals a fan-out silently degrading.
            "parallelism": round(work_ms / wall_ms, 2) if wall_ms > 0 else 0.0,
            # Time not attributed to any instrumented span: our own compute,
            # plus anything nobody thought to measure. A large value here is
            # a prompt to instrument something, not a rounding error.
            "unattributed_ms": round(max(0.0, wall_ms - work_ms), 1),
            "breakdown": breakdown,
        }
        if dropped:
            report["dropped_labels"] = dropped
        return report


_current: contextvars.ContextVar[Optional[RequestProfile]] = contextvars.ContextVar(
    "omnisignal_request_profile", default=None
)


def begin(name: str) -> RequestProfile:
    """Start profiling. Replaces any profile already in this context."""
    profile = RequestProfile(name)
    _current.set(profile)
    return profile


def current() -> Optional[RequestProfile]:
    return _current.get()


def clear() -> None:
    _current.set(None)


def record_in_request(key: str, milliseconds: float) -> None:
    """Attribute time to the active request, if there is one.

    A no-op outside a request — background work, CLI runs and tests still
    record into the global registry, they just have nothing to attribute to.
    """
    profile = _current.get()
    if profile is not None:
        profile.record(key, milliseconds)


class profiled:
    """Context manager that profiles a block and returns its report.

        with profiled("dashboard") as run:
            ...
        run.report()
    """

    __slots__ = ("_name", "profile")

    def __init__(self, name: str) -> None:
        self._name = name
        self.profile: Optional[RequestProfile] = None

    def __enter__(self) -> RequestProfile:
        self.profile = begin(self._name)
        return self.profile

    def __exit__(self, *exc_info: Any) -> None:
        clear()
