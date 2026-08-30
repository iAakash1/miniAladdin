"""
Recompute PBO for a completed experiment, without re-running it.

PBO reported `None` in EXP-004's first artifact because one constant-prediction
baseline traded 12 periods and the inner join across configurations collapsed
the matrix below the 32 rows CSCV needs. The fix excludes degenerate
configurations before aligning; this script applies it to the stored
predictions rather than repeating a 90-minute study to change one number.

    python -m scripts.quant.recompute_pbo --experiment EXP-004
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as Date
from pathlib import Path

import pandas as pd

from src.quant.datasets.store import RawStore
from src.quant.pit.dataset import DatasetBuilder
from src.quant.pit.universe import UniverseHistory
from src.quant.study.experiment import get_experiment
from src.quant.study.run import _backtest, _pbo

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s", stream=sys.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompute PBO from stored predictions")
    parser.add_argument("--experiment", default="EXP-004")
    parser.add_argument("--root", default="data/research")
    parser.add_argument("--out", default="experiments")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    definition = get_experiment(args.experiment)
    directory = Path(args.out) / definition.experiment_id
    metrics_path = directory / "metrics.json"
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))

    print("rebuilding returns panel ...", flush=True)
    dataset = DatasetBuilder(
        RawStore(args.root), UniverseHistory.load(Path(args.root) / "universe")
    ).build(
        start=definition.start, end=Date.today(),
        step_sessions=definition.step_sessions, workers=args.workers,
    )
    forward_column = f"fwd_ret_{definition.step_sessions}"
    returns_panel = dataset.frame[["date", "symbol", "dollar_volume", forward_column]]

    for target in definition.targets:
        path = directory / f"predictions_{target}.parquet"
        if not path.exists():
            print(f"  {target}: no stored predictions, skipped")
            continue
        stored = pd.read_parquet(path)
        series = {}
        for model, group in stored.groupby("model"):
            result = _backtest(
                group.drop(columns=["model"]), returns_panel, definition,
                definition.primary_half_spread_bps, forward_column,
            )
            if result is not None:
                series[str(model)] = result.net_returns

        report = _pbo(series)
        payload["labels"][target]["probability_of_backtest_overfitting"] = report
        print(f"  {target}: PBO {report.get('pbo')} over {report.get('configurations')} "
              f"configurations, {report.get('aligned_periods')} aligned periods; "
              f"excluded {report.get('excluded')}")

    metrics_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"updated {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
