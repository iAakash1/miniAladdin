"""
Post-run descriptive report for EXP-009B. Exploratory; changes no classification.

The preregistered run records the criteria's inputs. A reader also needs to see where
the aggregate came from — fold by fold, and what the books actually held — so this
module re-reads the *saved* predictions (never refits anything, never reads a return
that the run did not already use) and adds:

  * per-fold gross return, net return, turnover, Rank IC and whether the fold improved
    on the control, for both portfolio constructions;
  * holdings statistics (names replaced per rebalance, average holding spell, breadth)
    from the same portfolio engine, with weights recorded;
  * rank turnover: the mean absolute move in each name's predicted percentile between
    consecutive dates.

Nothing here adds a cell, a threshold or a criterion.
"""

from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.backtest.turnover_diagnostics import lagged_frame
from src.quant.study import exp009a, exp009b

CELLS = ["R0_sklearn_gb", "R1_boosted_l2", "R2_boosted_lambdamart", "R3_boosted_pairwise"]
CONSTRUCTIONS = {"A_immediate": {"rule": "baseline"}, "C_topk_dropout_10": exp009b._C}


def rank_turnover(predictions: pd.DataFrame) -> dict[str, float]:
    by_date = {d: g.set_index("symbol")["prediction"].rank(pct=True) for d, g in predictions.groupby("date")}
    dates = sorted(by_date)
    moves = []
    for previous, current in zip(dates[:-1], dates[1:]):
        common = by_date[previous].index.intersection(by_date[current].index)
        if len(common) >= 20:
            moves.append(float((by_date[current].loc[common] - by_date[previous].loc[common]).abs().mean()))
    return {"mean_abs_percentile_move": float(np.mean(moves)), "dates": len(moves)}


def fold_ic_series(predictions: pd.DataFrame) -> dict[int, float]:
    return {int(k): float(exp009b._ic_series(g).mean()) for k, g in predictions.groupby("fold")}


def run_report(root: Path = Path("."), *, directory: Path | None = None) -> dict[str, Any]:
    root = Path(root)
    directory = directory or (root / exp009b.OUTPUT_DIR)
    exp009b.arm_firewall(root)
    frame, _ = exp009b.load_frame(root)
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    preds = {c: pd.read_parquet(directory / f"predictions_{c}.parquet") for c in CELLS}
    for p in preds.values():
        p["date"] = pd.to_datetime(p["date"]).dt.date
    fold_map = exp009a.fold_of_dates(preds["R1_boosted_l2"])
    ic_by_fold = {c: fold_ic_series(p) for c, p in preds.items()}

    out: dict[str, Any] = {"label": "EXPLORATORY - post-run descriptive - changes no classification", "cells": {}}
    for cell, pred in preds.items():
        entry: dict[str, Any] = {"rank_turnover": rank_turnover(pred), "constructions": {}}
        lag = lagged_frame(pred[["date", "symbol", "prediction"]],
                           panel[["date", "symbol", "dollar_volume", "fwd_ret_5"]], lag=1)
        for name, spec in CONSTRUCTIONS.items():
            result = exp009a._backtest(pred, panel, spec, 10.0, record_weights=True)
            holdings = exp009a.holdings_metrics(result, lag, panel, 1_000_000.0)
            folds = exp009a.fold_table(result.periods, fold_map)
            entry["constructions"][name] = {
                "names_replaced_per_rebalance": holdings["names_replaced_per_rebalance"],
                "holding_duration_periods": holdings["holding_duration_periods"],
                "breadth": holdings["breadth"],
                "per_fold": [
                    {**f, "rank_ic": ic_by_fold[cell][f["fold"]]} for f in folds
                ],
            }
        out["cells"][cell] = entry

    control = out["cells"]["R1_boosted_l2"]
    for cell, entry in out["cells"].items():
        for name, block in entry["constructions"].items():
            ref = control["constructions"][name]["per_fold"]
            for f, r in zip(block["per_fold"], ref):
                f["improved_net_vs_control"] = bool(f["mean_net_return_bp"] > r["mean_net_return_bp"])
                f["improved_ic_vs_control"] = bool(f["rank_ic"] > r["rank_ic"])
        # Does one fold dominate the aggregate net difference to the control?
        for name, block in entry["constructions"].items():
            ref = control["constructions"][name]["per_fold"]
            diffs = [f["mean_net_return_bp"] * f["periods"] - r["mean_net_return_bp"] * r["periods"]
                     for f, r in zip(block["per_fold"], ref)]
            total = float(sum(diffs))
            block["largest_fold_share_of_net_difference_to_control"] = (
                float(max(diffs, key=abs) / total) if abs(total) > 1e-9 else None)
    (directory / "posthoc_descriptive.json").write_text(json.dumps(out, indent=2, sort_keys=True, default=str) + "\n")
    return out
