#!/usr/bin/env python3
"""Pre-declared naive reference for EXP-012 (preregistration section 7, "Reference rows").

N0 is the baseline's own 12-1 momentum rank (`mom_252_21_xs`), unfitted, used directly as the score and evaluated on exactly the rows and dates that arm A1
predicts, with the same per-date Spearman Rank IC, the same Newey-West statistic and the frozen EXP-010B 21-session portfolio at 10 bp as every other arm.
It has no parameters and no contrast: it anchors the scale ("does a fitted model beat the plainest signal in the set?") and is chosen before the study by the
literature (Jegadeesh and Titman), not by any result. Rows where the feature is missing are scored 0 (the neutral rank).

Run after the registered study:  .venv/bin/python docs/research/market-signal-review-2026-10-11/code/naive_reference.py
Writes experiments/EXP-012/reference_naive.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp010b, exp011, exp012  # noqa: E402
from src.quant.validation.metrics import ic_summary  # noqa: E402

FEATURE = "mom_252_21_xs"
EXPERIMENT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "experiments" / "EXP-012"     # an argument allows a test on a rehearsal output
OUT = EXPERIMENT_DIR / "reference_naive.json"


def main() -> None:
    frame = exp012.load_frame(REPO)
    a1 = pd.read_parquet(EXPERIMENT_DIR / "checkpoints" / "A1_0.parquet")
    keyed = a1.merge(frame[["date", "symbol", FEATURE]], on=["date", "symbol"], how="left", validate="one_to_one")
    covered = float(keyed[FEATURE].notna().mean())
    naive = keyed.assign(prediction=keyed[FEATURE].fillna(0.0).to_numpy(dtype=float)).drop(columns=[FEATURE])
    series = exp012.ic_series(naive)
    summary = ic_summary(series, horizon_sessions=21, step_sessions=exp012.GRID_STEP)
    folds = [float(exp012.ic_series(naive[naive["fold"] == k]).mean()) for k in sorted(naive["fold"].unique())]
    daily, calendar = exp010b.build_daily_panel(REPO)
    universe = daily[daily["in_universe"]]
    schedule = exp010b.rebalance_schedule(calendar, exp010b.ARMS[exp011.ECONOMICS_ARM]["step_sessions"])
    report = exp011.arm_seed_report("N0", 0, naive, frame, universe, calendar, schedule)
    keep = ("mean_rank_ic", "hac_t_stat", "ic_ir", "positive_fold_count", "worst_fold_ic", "b1_gross_sharpe", "b1_net_sharpe_10bp", "b1_annualised_turnover", "b1_net_max_drawdown", "b1_cost_share_of_gross")
    result = {
        "reference": "N0", "score": FEATURE, "definition": "baseline 12-1 momentum cross-sectional rank, unfitted; missing scored 0", "rows": int(len(naive)), "dates": int(len(series)),
        "feature_coverage_of_prediction_rows": round(covered, 4), "mean_rank_ic": float(series.mean()), "hac_t": summary.get("t_stat"), "fold_ic": folds,
        "positive_folds": int(sum(f > 0 for f in folds)), "portfolio_b1_10bp": {k: report.get(k) for k in keep},
        "note": "pre-declared reference; not a contrast and not adjusted; see the preregistration, section 7",
    }
    OUT.write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps(result, indent=1, default=float))


if __name__ == "__main__":
    main()
