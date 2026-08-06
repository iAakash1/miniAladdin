#!/usr/bin/env python3
"""
Panel benchmark — build throughput, storage footprint, read latency.

Runs on synthetic price data, deliberately: a benchmark that depends on a
vendor measures the vendor's latency, not ours, and cannot be reproduced by
anyone reading the numbers later.

    python benchmarks/panel_build.py
    python benchmarks/panel_build.py --symbols 100 --days 1260 --json

What each number means:

  build       wall time to compute every factor for every (symbol, date).
              The unit that matters is µs/cell — it is what tells you
              whether a 500-name, 10-year panel is a coffee break or an
              overnight job.
  write       Arrow conversion + zstd + fsync + atomic rename.
  read full   the whole snapshot back into pandas.
  read cols   three columns only. The gap between this and `read full` is
              the entire argument for a columnar format.
  read as_of  the point-in-time query, the one research actually issues.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.panel.builder import LOOKBACK_BARS, PanelBuilder  # noqa: E402
from src.panel.storage import PanelStore  # noqa: E402
from src.panel.universe import Universe  # noqa: E402


def synthetic_prices(days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(end=date.today(), periods=days)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.012, days)))
    return pd.DataFrame(
        {
            "Open": closes * 0.997,
            "High": closes * 1.009,
            "Low": closes * 0.991,
            "Close": closes,
            "Volume": rng.integers(1_000_000, 9_000_000, days).astype(float),
        },
        index=index,
    )


def timed(fn, repeats: int = 1) -> tuple[float, object]:
    """Best-of-N seconds. Best, not mean: the minimum is the least
    contaminated by scheduler noise on a laptop that is also running a browser."""
    result = None
    samples = []
    for _ in range(repeats):
        began = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - began)
    return min(samples), result


def run(symbol_count: int, days: int, step: int, repeats: int,
        lookback: int = LOOKBACK_BARS, vectorized: bool = True) -> dict:
    symbols = [f"SYM{index:04d}" for index in range(symbol_count)]
    frames = {symbol: synthetic_prices(days, seed=index)
              for index, symbol in enumerate(symbols)}
    frames["SPY"] = synthetic_prices(days, seed=99_999)

    universe = Universe.custom(symbols, name="bench")
    builder = PanelBuilder(
        load_prices=lambda symbol: frames.get(symbol),
        lookback=lookback,
        vectorized=vectorized,
    )

    # Observations only start once MIN_BARS of history exists.
    start = frames[symbols[0]].index[0].date()
    end = frames[symbols[0]].index[-1].date()

    build_seconds, built = timed(
        lambda: builder.build(universe, start, end, step=step)
    )
    frame, manifest = built
    cells = len(frame)

    root = Path(tempfile.mkdtemp(prefix="panel-bench-"))
    try:
        store = PanelStore(root)
        write_seconds, written = timed(lambda: store.write(frame, manifest))
        store.publish(written.snapshot_id)

        parquet_path = store.snapshots_dir / written.snapshot_id / "panel.parquet"
        on_disk = parquet_path.stat().st_size

        read_all, _ = timed(lambda: store.read(), repeats)
        read_cols, _ = timed(
            lambda: store.read(columns=["symbol", "date", "r12_1"]), repeats
        )
        midpoint = start + (end - start) // 2
        read_pit, pit_frame = timed(lambda: store.read_as_of(midpoint), repeats)

        in_memory = int(frame.memory_usage(deep=True).sum())

        return {
            "config": {
                "symbols": symbol_count, "days": days, "step": step,
                "lookback": lookback, "engine": "vectorized" if vectorized else "scalar",
                "range": f"{start} → {end}",
            },
            "build": {
                "seconds": round(build_seconds, 3),
                "cells": cells,
                "us_per_cell": round(build_seconds / cells * 1e6, 1) if cells else None,
                "cells_per_second": round(cells / build_seconds) if build_seconds else None,
            },
            "storage": {
                "write_seconds": round(write_seconds, 3),
                "parquet_bytes": on_disk,
                "bytes_per_cell": round(on_disk / cells, 1) if cells else None,
                "pandas_bytes": in_memory,
                "compression_ratio": round(in_memory / on_disk, 1) if on_disk else None,
            },
            "read": {
                "full_seconds": round(read_all, 4),
                "three_columns_seconds": round(read_cols, 4),
                "projection_speedup": round(read_all / read_cols, 1) if read_cols else None,
                "as_of_seconds": round(read_pit, 4),
                "as_of_rows": len(pit_frame),
            },
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def render(report: dict) -> None:
    config, build, storage, read = (
        report["config"], report["build"], report["storage"], report["read"]
    )
    print(f"\n  PANEL BENCHMARK — {config['symbols']} symbols × {config['days']} days"
          f" (step {config['step']}d, lookback {config['lookback']}, {config['engine']})")
    print(f"  {config['range']}\n")

    print(f"  BUILD")
    print(f"    cells                {build['cells']:>14,}")
    print(f"    wall time            {build['seconds']:>14.3f} s")
    print(f"    per cell             {build['us_per_cell']:>14.1f} µs")
    print(f"    throughput           {build['cells_per_second']:>14,} cells/s")

    print(f"\n  STORAGE")
    print(f"    write                {storage['write_seconds']:>14.3f} s")
    print(f"    parquet on disk      {storage['parquet_bytes'] / 1024:>14,.1f} KiB")
    print(f"    per cell             {storage['bytes_per_cell']:>14.1f} B")
    print(f"    pandas in memory     {storage['pandas_bytes'] / 1024:>14,.1f} KiB")
    print(f"    compression          {storage['compression_ratio']:>13.1f}×")

    print(f"\n  READ")
    print(f"    full snapshot        {read['full_seconds'] * 1000:>14.1f} ms")
    print(f"    three columns        {read['three_columns_seconds'] * 1000:>14.1f} ms")
    print(f"    projection speedup   {read['projection_speedup']:>13.1f}×")
    print(f"    point-in-time read   {read['as_of_seconds'] * 1000:>14.1f} ms"
          f"   ({read['as_of_rows']:,} rows)")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark panel build and storage.")
    parser.add_argument("--symbols", type=int, default=30)
    parser.add_argument("--days", type=int, default=756, help="trading days (~3y)")
    parser.add_argument("--step", type=int, default=1, help="observation stride")
    parser.add_argument("--repeats", type=int, default=5, help="read repeats (best-of)")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_BARS,
                        help=f"trailing bars per observation (default: {LOOKBACK_BARS})")
    parser.add_argument("--scalar", action="store_true",
                        help="force the scalar engine (the oracle) instead of the fast path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.symbols, args.days, args.step, args.repeats, args.lookback,
                 vectorized=not args.scalar)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        render(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
