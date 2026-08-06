#!/usr/bin/env python3
"""
Instrumentation overhead benchmark.

Metrics that cost more than they reveal are a net loss, and "it's just a
counter" is exactly the assumption that turns out to be wrong under a lock at
eight threads. So the overhead is measured, not asserted, and the number is
published next to the subsystem that claims to be cheap.

The bar: overhead must be negligible against what is being measured. A
provider call is 300–20,000 ms. If recording one costs microseconds, it is
free in the only sense that matters.

    python benchmarks/observability.py
    python benchmarks/observability.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.observability.metrics import Histogram, MetricsRegistry  # noqa: E402
from src.observability.request import RequestProfile  # noqa: E402


def _per_op_us(fn, iterations: int) -> float:
    fn(1000)  # warm
    best = min(_time(fn, iterations) for _ in range(3))
    return best / iterations * 1e6


def _time(fn, iterations: int) -> float:
    started = time.perf_counter()
    fn(iterations)
    return time.perf_counter() - started


def run(iterations: int, threads: int) -> dict:
    histogram = Histogram()
    registry = MetricsRegistry()
    profile = RequestProfile("bench")

    def record_histogram(count):
        for index in range(count):
            histogram.record(index % 1000)

    def record_registry(count):
        for index in range(count):
            registry.observe("vendor.call", index % 1000,
                             vendor="polygon", operation="get_series", outcome="ok")

    def record_request(count):
        for index in range(count):
            profile.record("vendor.call{vendor=polygon}", index % 1000)

    def baseline(count):
        total = 0
        for index in range(count):
            total += index % 1000
        return total

    results = {
        "baseline_loop_us": round(_per_op_us(baseline, iterations), 4),
        "histogram_record_us": round(_per_op_us(record_histogram, iterations), 4),
        "registry_observe_us": round(_per_op_us(record_registry, iterations), 4),
        "request_record_us": round(_per_op_us(record_request, iterations), 4),
    }

    # Contended: the fan-out records from several threads onto one series,
    # which is the worst case for a per-series lock.
    contended = Histogram()
    per_thread = iterations // threads

    def hammer():
        for index in range(per_thread):
            contended.record(index % 1000)

    workers = [threading.Thread(target=hammer) for _ in range(threads)]
    started = time.perf_counter()
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    elapsed = time.perf_counter() - started
    results["contended_record_us"] = round(elapsed / (per_thread * threads) * 1e6, 4)
    results["contended_threads"] = threads
    results["observations_kept"] = contended.count

    # Percentile reads are the query path — rare, but must not be pathological.
    started = time.perf_counter()
    for _ in range(1000):
        histogram.percentile(0.95)
    results["percentile_read_us"] = round((time.perf_counter() - started) / 1000 * 1e6, 3)

    # What it costs relative to the thing being measured.
    provider_call_ms = 300.0
    results["overhead_pct_of_a_300ms_call"] = round(
        results["registry_observe_us"] / 1000 / provider_call_ms * 100, 6
    )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200_000)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.iterations, args.threads)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"\n  INSTRUMENTATION OVERHEAD — {args.iterations:,} iterations\n")
    print(f"    bare loop (baseline)        {report['baseline_loop_us']:>9.4f} µs")
    print(f"    Histogram.record            {report['histogram_record_us']:>9.4f} µs")
    print(f"    registry.observe (4 labels) {report['registry_observe_us']:>9.4f} µs")
    print(f"    request.record              {report['request_record_us']:>9.4f} µs")
    print(f"    contended ({report['contended_threads']} threads)       "
          f"{report['contended_record_us']:>9.4f} µs")
    print(f"    percentile read             {report['percentile_read_us']:>9.3f} µs")
    print(f"\n    cost of instrumenting one 300 ms provider call: "
          f"{report['overhead_pct_of_a_300ms_call']:.6f}%\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
