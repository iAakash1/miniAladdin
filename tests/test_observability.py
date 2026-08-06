"""
Observability tests.

Instrumentation is the one subsystem that lies quietly: a broken metric does
not crash anything, it just reports a number nobody can act on. So these
tests assert the properties that make the numbers *trustworthy* — percentile
accuracy against an exact reference, bounded memory under hostile labels,
correctness under concurrency, and attribution surviving the thread boundary
of the fan-out.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from src.observability import request as request_module
from src.observability.metrics import (
    BUCKET_BOUNDS_MS,
    Histogram,
    MetricsRegistry,
    timer,
)
from src.observability.request import profiled
from src.providers.parallel import map_concurrent


# ── histogram accuracy ───────────────────────────────────────────────────────

def test_percentiles_track_an_exact_reference():
    """Bucketed percentiles must stay within one bucket width of the truth.

    Compared against NumPy's exact percentile over the same sample — a
    histogram that is merely self-consistent is worthless.
    """
    rng = np.random.default_rng(7)
    sample = np.concatenate([
        rng.uniform(0.5, 5, 4000),      # cache hits
        rng.uniform(200, 900, 800),     # healthy vendor calls
        rng.uniform(5000, 20000, 60),   # the pathological tail
    ])

    histogram = Histogram()
    for value in sample:
        histogram.record(float(value))

    for fraction in (0.50, 0.95, 0.99):
        exact = float(np.percentile(sample, fraction * 100))
        estimate = histogram.percentile(fraction)
        bucket_width = _containing_bucket_width(exact)
        assert abs(estimate - exact) <= bucket_width, (
            f"p{fraction:.0%}: estimate {estimate} vs exact {exact} "
            f"(bucket width {bucket_width})"
        )


def _containing_bucket_width(value: float) -> float:
    bounds = (0.0,) + BUCKET_BOUNDS_MS
    for index in range(1, len(bounds)):
        if value <= bounds[index]:
            return bounds[index] - bounds[index - 1]
    return float("inf")


def test_percentiles_are_exact_for_a_single_observation():
    histogram = Histogram()
    histogram.record(42.0)
    assert histogram.percentile(0.50) == pytest.approx(42.0, abs=1.0)
    assert histogram.percentile(0.99) == pytest.approx(42.0, abs=1.0)


def test_empty_histogram_reports_nothing_rather_than_zero():
    """Zero latency is a claim. No observations is the truth."""
    assert Histogram().percentile(0.5) is None
    assert Histogram().snapshot() == {"count": 0}


def test_the_open_ended_bucket_reports_the_real_maximum():
    """The last bucket has no upper bound; reporting `inf` helps nobody."""
    histogram = Histogram()
    for _ in range(10):
        histogram.record(1.0)
    histogram.record(95_000.0)
    assert histogram.percentile(1.0) == pytest.approx(95_000.0)


def test_exact_aggregates_are_not_bucketed():
    histogram = Histogram()
    for value in (1.5, 300.0, 12_000.0):
        histogram.record(value)
    snapshot = histogram.snapshot()
    assert snapshot["count"] == 3
    assert snapshot["min_ms"] == pytest.approx(1.5)
    assert snapshot["max_ms"] == pytest.approx(12_000.0)
    assert snapshot["total_ms"] == pytest.approx(12_301.5)


@pytest.mark.parametrize("bound,lower", [(25, 10), (250, 100), (5_000, 2_500)])
def test_a_value_on_a_bound_lands_in_that_bucket_not_the_next(bound, lower):
    """`BUCKET_BOUNDS_MS` are inclusive upper bounds — `bisect_left`.

    Needs observations either side of the bound. With a single observation
    `min == max`, so the percentile clamp returns the exact value whichever
    bucket it was filed in, and the assertion proves nothing — an earlier
    version of this test was vacuous for exactly that reason.
    """
    histogram = Histogram()
    histogram.record(0.5)                       # anchors min below the bound
    for _ in range(98):
        histogram.record(float(bound))
    histogram.record(90_000.0)                  # anchors max above

    estimate = histogram.percentile(0.5)
    assert lower <= estimate <= bound, (
        f"{bound} ms was filed above its own bound (got p50={estimate})"
    )


def test_percentile_at_an_exact_rank_boundary():
    """Guards the `>=` in the rank scan.

    With 10 observations, p50 targets rank 5.0 exactly. A `>` comparison
    walks one bucket too far and reports a latency nobody experienced.
    """
    histogram = Histogram()
    for _ in range(5):
        histogram.record(3.0)       # bucket (2, 5]
    for _ in range(5):
        histogram.record(400.0)     # bucket (250, 500]

    assert histogram.percentile(0.5) == pytest.approx(3.0, abs=2.0)


def test_counters_respect_the_series_cap():
    """The cap must bound counters too, not only histograms."""
    registry = MetricsRegistry(max_series=8)
    for index in range(200):
        registry.increment("bad", ticker=f"SYM{index}")

    snapshot = registry.snapshot()
    assert len(snapshot["counters"]) <= 8
    assert snapshot["dropped_series"] > 0


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.5])
def test_invalid_percentile_is_rejected(fraction):
    with pytest.raises(ValueError, match="fraction must be"):
        Histogram().percentile(fraction)


def test_the_average_hides_what_percentiles_reveal():
    """The motivating case, as an assertion.

    A bimodal distribution — cache hits and a timing-out vendor — has a mean
    that describes nothing that ever happened. This is why the subsystem
    exists, so it is pinned rather than left in a comment.
    """
    histogram = Histogram()
    for _ in range(95):
        histogram.record(0.4)
    for _ in range(5):
        histogram.record(18_000.0)

    snapshot = histogram.snapshot()
    assert 800 < snapshot["mean_ms"] < 1000     # a value that never occurred
    assert snapshot["p50_ms"] < 5               # what almost everyone got
    assert snapshot["p99_ms"] > 10_000          # what actually hurt


# ── concurrency ──────────────────────────────────────────────────────────────

def test_no_observations_are_lost_under_concurrent_recording():
    """The fan-out records from eight threads; a dropped count is a silent lie."""
    histogram = Histogram()

    def hammer():
        for _ in range(500):
            histogram.record(10.0)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert histogram.count == 4000
    assert histogram.total_ms == pytest.approx(40_000.0)


def test_registry_is_safe_under_concurrent_series_creation():
    registry = MetricsRegistry()

    def record(index):
        registry.observe("op", 5.0, vendor=f"v{index % 4}")
        registry.increment("calls", vendor=f"v{index % 4}")

    map_concurrent(record, list(range(200)), workers=8)
    snapshot = registry.snapshot()
    assert sum(t["count"] for t in snapshot["timings"].values()) == 200
    assert sum(snapshot["counters"].values()) == 200


# ── bounded memory ───────────────────────────────────────────────────────────

def test_unbounded_labels_are_capped_not_leaked():
    """A caller labelling by ticker must degrade the metrics, not the process."""
    registry = MetricsRegistry(max_series=16)
    for index in range(500):
        registry.observe("bad", 1.0, ticker=f"SYM{index}")

    snapshot = registry.snapshot()
    assert len(snapshot["timings"]) <= 16
    assert snapshot["dropped_series"] > 0
    assert "unbounded labels" in snapshot["warning"]


def test_capped_registry_keeps_serving_existing_series():
    """Hitting the cap must not stop recording what is already tracked."""
    registry = MetricsRegistry(max_series=2)
    registry.observe("a", 1.0)
    registry.observe("b", 1.0)
    registry.observe("c", 1.0)          # refused
    registry.observe("a", 3.0)          # still accepted

    assert registry.snapshot()["timings"]["a"]["count"] == 2


def test_reset_starts_a_fresh_window():
    """Cumulative counters never forget; a vendor fixed an hour ago should
    not look broken forever."""
    registry = MetricsRegistry()
    registry.observe("op", 100.0)
    registry.increment("calls")
    before = registry.since

    time.sleep(0.01)
    registry.reset()

    assert registry.snapshot()["timings"] == {}
    assert registry.snapshot()["counters"] == {}
    assert registry.since > before


def test_label_keys_are_order_independent():
    """Two spellings of the same series would split its observations."""
    registry = MetricsRegistry()
    registry.observe("call", 1.0, vendor="fmp", operation="series")
    registry.observe("call", 1.0, operation="series", vendor="fmp")
    assert len(registry.snapshot()["timings"]) == 1


# ── the timer ────────────────────────────────────────────────────────────────

def test_timer_records_elapsed_time():
    registry = MetricsRegistry()
    import src.observability.metrics as metrics_module

    original, metrics_module.registry = metrics_module.registry, registry
    try:
        with timer("work", kind="test"):
            time.sleep(0.03)
    finally:
        metrics_module.registry = original

    entry = registry.snapshot()["timings"]["work{kind=test}"]
    assert entry["count"] == 1
    assert entry["max_ms"] >= 25


def test_timer_records_even_when_the_block_raises():
    """A call that took six seconds and then failed is the most interesting
    call there is; excluding it would hide the worst latency."""
    registry = MetricsRegistry()
    import src.observability.metrics as metrics_module

    original, metrics_module.registry = metrics_module.registry, registry
    try:
        with pytest.raises(RuntimeError):
            with timer("failing"):
                time.sleep(0.02)
                raise RuntimeError("vendor down")
    finally:
        metrics_module.registry = original

    assert registry.snapshot()["timings"]["failing"]["count"] == 1


# ── request attribution ──────────────────────────────────────────────────────

def test_request_profile_attributes_time_by_label():
    with profiled("test-request") as profile:
        profile.record("vendor.call{vendor=a}", 100.0)
        profile.record("vendor.call{vendor=b}", 300.0)
        profile.record("vendor.call{vendor=a}", 100.0)

    report = profile.report()
    assert report["work_ms"] == pytest.approx(500.0)
    assert report["breakdown"][0]["label"] == "vendor.call{vendor=b}"
    assert report["breakdown"][0]["share_pct"] == pytest.approx(60.0)
    assert report["breakdown"][1]["calls"] == 2


def test_parallelism_ratio_detects_serial_work():
    """~1 means serialised. This is the number that catches a fan-out
    silently degrading back into a loop."""
    with profiled("serial") as profile:
        for _ in range(4):
            with timer("unit"):
                time.sleep(0.02)

    report = profile.report()
    assert report["parallelism"] == pytest.approx(1.0, abs=0.3)


def test_parallelism_ratio_detects_concurrent_work():
    with profiled("parallel") as profile:
        map_concurrent(
            lambda _: _sleep_timed(0.05), list(range(6)), workers=6, label="t"
        )

    report = profile.report()
    assert report["parallelism"] > 2.5, (
        f"expected concurrency to show, got {report['parallelism']}x"
    )


def _sleep_timed(seconds: float):
    with timer("unit"):
        time.sleep(seconds)


def test_attribution_survives_the_fan_out_thread_boundary():
    """contextvars do not cross a ThreadPoolExecutor on their own.

    Without explicit propagation this is exactly where attribution would be
    lost — in the requests that spend the most time.
    """
    with profiled("fanout") as profile:
        map_concurrent(lambda _: _sleep_timed(0.01), list(range(5)), workers=5)

    report = profile.report()
    assert report["breakdown"], "no time attributed — context did not propagate"
    assert report["breakdown"][0]["calls"] == 5


def test_unattributed_time_is_reported():
    """Time nobody instrumented is a prompt, not a rounding error."""
    with profiled("partial") as profile:
        with timer("measured"):
            time.sleep(0.01)
        time.sleep(0.04)  # nobody is watching this

    report = profile.report()
    assert report["unattributed_ms"] > 25


def test_recording_outside_a_request_is_a_no_op():
    """CLI runs, tests and background work must not need a request."""
    request_module.clear()
    request_module.record_in_request("orphan", 5.0)   # must not raise
    assert request_module.current() is None


def test_labels_per_request_are_bounded():
    from src.observability.request import MAX_LABELS_PER_REQUEST, RequestProfile

    profile = RequestProfile("hostile")
    for index in range(MAX_LABELS_PER_REQUEST + 50):
        profile.record(f"label-{index}", 1.0)

    report = profile.report()
    assert len(report["breakdown"]) == MAX_LABELS_PER_REQUEST
    assert report["dropped_labels"] == 50
