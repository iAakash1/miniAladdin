"""
Latency histograms and counters.

## Why averages were not enough

`VendorStats` already recorded `avg_latency_ms` and `max_latency_ms` per
vendor, cumulative since process start. That answers "is this vendor alive?"
and nothing else, and the questions that actually came up were different ones:

- *Where did the dashboard's 25 seconds go?* The average said 780 ms. The
  average is meaningless when the distribution is bimodal — a cache hit at
  0.4 ms and a vendor timing out at 18 s average to something that never
  happened.
- *Which operation is slow?* Stats were aggregated per vendor, so a fast
  `get_company` and a pathological `get_series` were indistinguishable.
- *Is it slow now?* Cumulative counters never forget, so a vendor that failed
  a hundred times an hour ago looks broken forever.

Percentiles answer the first, `(vendor, operation)` labelling answers the
second, and `reset()` plus a `since` timestamp answer the third.

## Design

**Fixed log-spaced buckets, not sampling.** A reservoir gives exact
percentiles for a sample; buckets give approximate percentiles for *every*
observation, in constant memory and constant time per record. For deciding
"is p95 300 ms or 6 s" the bucket width is far below the resolution anyone
acts on, and never dropping an observation matters more — the pathological
calls are rare, and rare is exactly what sampling loses.

**Bounded cardinality.** Every label combination allocates a permanent
series, so labels must be low-cardinality and closed: vendor names,
operation names, outcome. **Never a ticker** — that is unbounded and would
turn this into a memory leak that looks like a metrics system.
`MAX_SERIES` is a hard backstop if that rule is ever broken.

**One lock per series, not one global lock.** The fan-out records from eight
threads at once; a single registry-wide lock would serialise exactly the
concurrency this repository just built.
"""

from __future__ import annotations

import bisect
import threading
import time
from typing import Any, Optional

from src.observability.request import record_in_request

#: Upper bounds in milliseconds. Spans cache hits (sub-millisecond) to a
#: vendor exhausting its 6 s timeout across three retries (~20 s), which is
#: the real observed range.
BUCKET_BOUNDS_MS: tuple[float, ...] = (
    1, 2, 5, 10, 25, 50, 100, 250, 500,
    1_000, 2_500, 5_000, 10_000, 30_000,
)

#: Hard backstop against unbounded label cardinality. Reaching it means a
#: caller is labelling by something like a ticker; the registry refuses to
#: grow and says so rather than leaking until the process dies.
MAX_SERIES = 512


class Histogram:
    """Latency distribution in constant memory.

    Records into `len(BUCKET_BOUNDS_MS) + 1` counters plus exact count, sum,
    min and max. Percentiles are interpolated within the containing bucket,
    so they are approximate by at most the bucket width — documented and
    asserted in `tests/test_observability.py`.
    """

    __slots__ = ("_buckets", "_lock", "count", "total_ms", "min_ms", "max_ms")

    def __init__(self) -> None:
        self._buckets = [0] * (len(BUCKET_BOUNDS_MS) + 1)
        self._lock = threading.Lock()
        self.count = 0
        self.total_ms = 0.0
        self.min_ms = float("inf")
        self.max_ms = 0.0

    def record(self, milliseconds: float) -> None:
        index = bisect.bisect_left(BUCKET_BOUNDS_MS, milliseconds)
        with self._lock:
            self._buckets[index] += 1
            self.count += 1
            self.total_ms += milliseconds
            if milliseconds < self.min_ms:
                self.min_ms = milliseconds
            if milliseconds > self.max_ms:
                self.max_ms = milliseconds

    def percentile(self, fraction: float) -> Optional[float]:
        """Approximate percentile in milliseconds, None when no observations.

        Linear interpolation inside the bucket that contains the target rank.
        The open-ended final bucket cannot be interpolated, so it reports the
        exact observed maximum instead of `inf` — a real number an engineer
        can act on.
        """
        if not 0.0 < fraction <= 1.0:
            raise ValueError(f"fraction must be in (0, 1], got {fraction}")
        with self._lock:
            if self.count == 0:
                return None
            target = fraction * self.count
            cumulative = 0
            for index, bucket_count in enumerate(self._buckets):
                if bucket_count == 0:
                    continue
                if cumulative + bucket_count >= target:
                    if index >= len(BUCKET_BOUNDS_MS):
                        return round(self.max_ms, 2)
                    low = BUCKET_BOUNDS_MS[index - 1] if index else 0.0
                    high = BUCKET_BOUNDS_MS[index]
                    within = (target - cumulative) / bucket_count
                    estimate = low + (high - low) * within
                    # Clamped to the observed range: no percentile can lie
                    # below the smallest observation or above the largest, so
                    # the exact min/max beat the bucket edges whenever the
                    # distribution is narrower than its bucket.
                    return round(min(max(estimate, self.min_ms), self.max_ms), 2)
                cumulative += bucket_count
            return round(self.max_ms, 2)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            count, total = self.count, self.total_ms
            minimum, maximum = self.min_ms, self.max_ms
        if count == 0:
            return {"count": 0}
        return {
            "count": count,
            "mean_ms": round(total / count, 2),
            "min_ms": round(minimum, 2),
            "p50_ms": self.percentile(0.50),
            "p95_ms": self.percentile(0.95),
            "p99_ms": self.percentile(0.99),
            "max_ms": round(maximum, 2),
            "total_ms": round(total, 1),
        }


class MetricsRegistry:
    """Named, labelled histograms and counters.

    Series are created on first use and never removed, which is why labels
    must be closed sets. `reset()` clears observations for a fresh
    measurement window without disturbing anything holding a reference.
    """

    def __init__(self, max_series: int = MAX_SERIES) -> None:
        self._histograms: dict[str, Histogram] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()
        self._max_series = max_series
        self._dropped_series = 0
        self.since = time.time()

    # ── recording ────────────────────────────────────────────────────────

    def observe(self, name: str, milliseconds: float, **labels: str) -> None:
        """Record one observation into this registry and the live request.

        Both, in one call, deliberately. An earlier version had `timer`
        attribute to the request while direct `observe` calls did not, so
        instrumenting a seam the "other" way silently produced a request
        report showing zero work — the metric looked fine and the attribution
        was empty. One path means that cannot happen again.
        """
        key = _series_key(name, labels)
        histogram = self._histogram(key)
        if histogram is not None:
            histogram.record(milliseconds)
        record_in_request(key, milliseconds)

    def increment(self, name: str, amount: int = 1, **labels: str) -> None:
        key = _series_key(name, labels)
        with self._lock:
            if key not in self._counters and self._at_capacity():
                self._dropped_series += 1
                return
            self._counters[key] = self._counters.get(key, 0) + amount

    # ── reading ──────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            histograms = dict(self._histograms)
            counters = dict(self._counters)
            dropped = self._dropped_series
            since = self.since

        report: dict[str, Any] = {
            "since": round(since, 3),
            "window_seconds": round(time.time() - since, 1),
            "timings": {
                key: histogram.snapshot()
                for key, histogram in sorted(histograms.items())
                if histogram.count
            },
            "counters": dict(sorted(counters.items())),
        }
        if dropped:
            # Loud on purpose: this means someone is labelling by something
            # unbounded, which is a bug in the caller, not in the registry.
            report["dropped_series"] = dropped
            report["warning"] = (
                f"series cap of {self._max_series} reached — a caller is using "
                "unbounded labels (a ticker?); metrics are now incomplete"
            )
        return report

    def reset(self) -> None:
        with self._lock:
            self._histograms.clear()
            self._counters.clear()
            self._dropped_series = 0
            self.since = time.time()

    # ── internals ────────────────────────────────────────────────────────

    def _histogram(self, key: str) -> Optional[Histogram]:
        with self._lock:
            existing = self._histograms.get(key)
            if existing is not None:
                return existing
            if self._at_capacity():
                self._dropped_series += 1
                return None
            created = Histogram()
            self._histograms[key] = created
            return created

    def _at_capacity(self) -> bool:
        return len(self._histograms) + len(self._counters) >= self._max_series


def _series_key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    rendered = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{rendered}}}"


class timer:
    """Time a block into the registry and the current request, if any.

    Usable as a context manager or a decorator::

        with timer("vendor.call", vendor="polygon", operation="get_series"):
            ...

    Records regardless of how the block exits, because a call that took six
    seconds and then raised is the most interesting call there is — excluding
    failures would hide precisely the latency worth finding.
    """

    __slots__ = ("_name", "_labels", "_started")

    def __init__(self, name: str, **labels: str) -> None:
        self._name = name
        self._labels = labels
        self._started = 0.0

    def __enter__(self) -> "timer":
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        elapsed_ms = (time.perf_counter() - self._started) * 1000.0
        registry.observe(self._name, elapsed_ms, **self._labels)

    def __call__(self, fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with timer(self._name, **self._labels):
                return fn(*args, **kwargs)

        return wrapper


#: Process-wide registry. A singleton because metrics describe the process,
#: and threading one through every call site would be ceremony for no gain.
registry = MetricsRegistry()
