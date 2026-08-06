#!/usr/bin/env python3
"""
Concurrent fan-out benchmark.

Simulated latency, deliberately. A benchmark that calls real vendors measures
the vendors' health on the day it ran — during development this machine put
three vendors into cooldown, which changed the "serial equivalent" from 43.6s
to 70.0s between two runs of the same code. Numbers like that cannot be
reproduced by anyone reading them later, so they do not belong in a
benchmark. Real-world observations are reported separately in
docs/PROVIDERS-AUDIT.md, with their confounds named.

Models the dashboard's actual call shape: 14 macro series + 11 sector ETFs +
5 indices + 2 singles = 32 independent provider calls.

    python benchmarks/provider_fanout.py
    python benchmarks/provider_fanout.py --latency 0.4 --tail 3.0 --json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.providers.parallel import DEFAULT_WORKERS, map_concurrent  # noqa: E402

# The dashboard's real fan-out groups, in call order.
GROUPS = [("macro", 14), ("sectors", 11), ("indexes", 5), ("singles", 2)]


def _make_call(latency: float, tail: float, tail_rate: float, seed: int):
    """A provider call: mostly `latency`, occasionally a slow-vendor tail.

    The tail matters more than the mean. Concurrency hides a slow call behind
    its peers, so a benchmark with uniform latency overstates how evenly the
    win lands.
    """
    rng = random.Random(seed)

    def call(item):
        delay = tail if rng.random() < tail_rate else latency * rng.uniform(0.7, 1.3)
        time.sleep(delay)
        return item

    return call


def run(latency: float, tail: float, tail_rate: float, workers: int,
        repeats: int) -> dict:
    sequential_times, concurrent_times = [], []

    for attempt in range(repeats):
        call = _make_call(latency, tail, tail_rate, seed=attempt)

        started = time.perf_counter()
        for _, count in GROUPS:
            for item in range(count):
                call(item)
        sequential_times.append(time.perf_counter() - started)

        call = _make_call(latency, tail, tail_rate, seed=attempt)
        started = time.perf_counter()
        for label, count in GROUPS:
            map_concurrent(call, list(range(count)), workers=workers, label=label)
        concurrent_times.append(time.perf_counter() - started)

    sequential = min(sequential_times)
    concurrent = min(concurrent_times)
    return {
        "config": {
            "calls": sum(count for _, count in GROUPS),
            "groups": {label: count for label, count in GROUPS},
            "latency_seconds": latency,
            "tail_seconds": tail,
            "tail_rate": tail_rate,
            "workers": workers,
            "repeats": repeats,
        },
        "sequential_seconds": round(sequential, 3),
        "concurrent_seconds": round(concurrent, 3),
        "speedup": round(sequential / concurrent, 2) if concurrent else None,
        "seconds_saved": round(sequential - concurrent, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latency", type=float, default=0.35,
                        help="typical per-call latency in seconds")
    parser.add_argument("--tail", type=float, default=2.5,
                        help="slow-vendor latency in seconds")
    parser.add_argument("--tail-rate", type=float, default=0.1,
                        help="fraction of calls that hit the tail")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.latency, args.tail, args.tail_rate, args.workers, args.repeats)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    config = report["config"]
    print(f"\n  PROVIDER FAN-OUT — {config['calls']} calls "
          f"({', '.join(f'{k}:{v}' for k, v in config['groups'].items())})")
    print(f"  latency {config['latency_seconds']}s, "
          f"{config['tail_rate']:.0%} tail at {config['tail_seconds']}s, "
          f"{config['workers']} workers\n")
    print(f"    sequential         {report['sequential_seconds']:>8.2f} s")
    print(f"    concurrent         {report['concurrent_seconds']:>8.2f} s")
    print(f"    speedup            {report['speedup']:>8.2f}x")
    print(f"    saved              {report['seconds_saved']:>8.2f} s\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
