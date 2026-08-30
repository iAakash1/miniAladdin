"""
Dataset integrity verification — run before any experiment consumes the data.

Runs the contamination probes against the REAL builder rather than a synthetic
stand-in, at several truncation points, and writes a machine-readable verdict.
An experiment that starts without this passing is an experiment whose result
cannot be interpreted.

    python -m scripts.quant.verify_dataset --out data/research/reports/integrity.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.quant.audit.contamination import (
    adversarial_invariance,
    compare_overlapping,
    summarise,
)
from src.quant.datasets.store import RawStore
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s", stream=sys.stdout)
logger = logging.getLogger("verify")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dataset temporal integrity")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--start", default="2014-04-01")
    parser.add_argument("--end", default="")
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="data/research/reports/integrity.json")
    parser.add_argument(
        "--cutoffs", default="",
        help="comma-separated truncation dates; default is four spread across the range",
    )
    args = parser.parse_args()

    store = RawStore(args.root)
    universe = UniverseHistory.load(Path(args.root) / "universe")
    start = Date.fromisoformat(args.start)
    end = Date.fromisoformat(args.end) if args.end else Date.today()

    def build(cutoff: Optional[Date]):
        return DatasetBuilder(store, universe).build(
            start=start, end=cutoff or end, step_sessions=args.step, workers=args.workers,
        )

    began = time.perf_counter()
    print("building full matrix ...", flush=True)
    full = build(None)
    features = list(full.manifest.features)
    print(
        f"  {full.manifest.rows:,} rows | {full.manifest.symbols} symbols | "
        f"{full.manifest.dates} dates | {len(features)} features",
        flush=True,
    )

    if args.cutoffs:
        cutoffs = [Date.fromisoformat(c.strip()) for c in args.cutoffs.split(",") if c.strip()]
    else:
        # Spread across the range. A leak with a bounded reach only shows at a
        # cutoff inside its span, so one cutoff is not a test.
        span = (end - start).days
        cutoffs = [start + timedelta(days=int(span * f)) for f in (0.45, 0.62, 0.79, 0.93)]

    results = []
    for cutoff in cutoffs:
        print(f"truncating at {cutoff} ...", flush=True)
        truncated = build(cutoff)
        result = compare_overlapping(
            full.frame[full.frame["date"] <= cutoff],
            truncated.frame[truncated.frame["date"] <= cutoff],
            features, label=f"truncate@{cutoff}",
        )
        status = "CLEAN" if result.clean else f"CONTAMINATED ({result.differing_count if hasattr(result,'differing_count') else len(result.differing)})"
        print(f"  {result.rows_compared:,} rows, {result.columns_compared} features -> {status}", flush=True)
        results.append(result)

    report = summarise(results)
    report.update({
        "dataset_version": full.manifest.dataset_version,
        "content_hash": full.manifest.content_hash,
        "rows": full.manifest.rows,
        "symbols": full.manifest.symbols,
        "dates": full.manifest.dates,
        "features": len(features),
        "start": str(start),
        "end": str(end),
        "step_sessions": args.step,
        "cutoffs": [str(c) for c in cutoffs],
        "guard_report": full.manifest.guard_report,
        "elapsed_seconds": round(time.perf_counter() - began, 1),
    })

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 66)
    print(f"DATASET INTEGRITY: {'CLEAN' if report['clean'] else 'CONTAMINATED'}")
    print(f"  dataset      {report['dataset_version']}  hash {report['content_hash']}")
    print(f"  compared     {report['rows_compared']:,} rows x {report['columns_compared']} features")
    print(f"  cutoffs      {', '.join(report['cutoffs'])}")
    print(f"  guards       {report['guard_report'].get('passed')}")
    print(f"  elapsed      {report['elapsed_seconds']}s")
    if not report["clean"]:
        for failure in report["failed"]:
            print(f"  FAILED {failure['label']}: {failure['differing'][:4]}")
    print("=" * 66)
    print(f"wrote {target}")
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
