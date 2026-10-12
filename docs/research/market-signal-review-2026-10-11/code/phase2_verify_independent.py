#!/usr/bin/env python3
"""Phase II step 1: independently recompute the decisive EXP-012 / EXP-013 numbers from the saved prediction files.

Deliberately does not import the study code (`src/quant/study/exp012.py`, `exp013.py`, `validation.metrics`). It reads the checkpoint parquet files, recomputes the per-date Spearman Rank IC with
scipy, the paired differences, the mean, a Newey-West t (Bartlett kernel, 4 lags, written out here), a moving-block bootstrap interval (block 6, 4,000 draws, seed 20261012), the fold signs and the
Holm adjustment, and compares each with the value the study recorded. It also checks the sample itself: dates, row counts, fold assignment, label identity across arms, finiteness, and that no date lies
after the registered panel end.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_verify_independent.py

Writes validation/phase2_independent_verification.json. Read-only with respect to the study outputs.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

REPO = Path(__file__).resolve().parents[4]
E12, E13 = REPO / "experiments/EXP-012", REPO / "experiments/EXP-013"
OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_independent_verification.json"
LABEL = "fwd_rank_21"
PANEL_END = pd.Timestamp("2025-05-09")
HOLDOUT_START = pd.Timestamp("2025-08-26")


def per_date_ic(frame: pd.DataFrame) -> pd.Series:
    out = {}
    for day, g in frame.groupby("date", sort=True):
        r = spearmanr(g["prediction"].to_numpy(), g[LABEL].to_numpy())[0]
        if np.isfinite(r):
            out[day] = r
    return pd.Series(out, dtype=float)


def newey_west_t(x: np.ndarray, lags: int = 4) -> float:
    """t-statistic of the mean with the Bartlett-kernel long-run variance; no small-sample correction."""
    n = len(x)
    d = x - x.mean()
    lrv = float(d @ d) / n
    for k in range(1, lags + 1):
        lrv += 2.0 * (1.0 - k / (lags + 1)) * float(d[k:] @ d[:-k]) / n
    return float(x.mean() / np.sqrt(lrv / n))


def block_bootstrap(diff: np.ndarray, block: int = 6, draws: int = 4000, seed: int = 20261012) -> tuple[float, float]:
    n = len(diff)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(draws, int(np.ceil(n / block))))
    means = np.array([np.concatenate([diff[j:j + block] for j in s])[:n].mean() for s in starts])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def holm(p: dict[str, float]) -> dict[str, float]:
    order = sorted(p, key=p.get)
    out, run = {}, 0.0
    for rank, k in enumerate(order):
        run = max(run, min(1.0, (len(order) - rank) * p[k]))
        out[k] = run
    return out


def load(directory: Path, arm: str, seed: int = 0) -> pd.DataFrame:
    frame = pd.read_parquet(directory / "checkpoints" / f"{arm}_{seed}.parquet")
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def paired(left: pd.Series, right: pd.Series, left_folds: np.ndarray, right_folds: np.ndarray) -> dict:
    both = pd.concat([left.rename("l"), right.rename("r")], axis=1).dropna()
    diff = (both["l"] - both["r"]).to_numpy()
    t = newey_west_t(diff)
    lo, hi = block_bootstrap(diff)
    fd = left_folds - right_folds
    return {"dates": len(diff), "mean_diff": float(diff.mean()), "hac_t": t, "p_one_sided": float(1 - norm.cdf(t)), "boot_lo": lo, "boot_hi": hi, "positive_folds": int((fd > 0).sum()), "fold_diffs": fd.tolist()}


def main() -> None:
    result: dict = {"method": "independent recomputation; study code not imported", "checks": {}, "contrasts": {}}
    # ---- the sample ----
    a1, a5 = load(E12, "A1"), load(E12, "A5")
    result["checks"]["rows_per_arm"] = {"A1": len(a1), "A5": len(a5)}
    result["checks"]["dates"] = int(a1["date"].nunique())
    result["checks"]["date_min"], result["checks"]["date_max"] = str(a1["date"].min().date()), str(a1["date"].max().date())
    result["checks"]["no_date_after_panel_end"] = bool(a1["date"].max() <= PANEL_END)
    result["checks"]["no_date_in_holdout_window"] = bool(a1["date"].max() < HOLDOUT_START)
    key = ["date", "symbol"]
    merged = a1[key + ["fold", LABEL]].merge(a5[key + ["fold", LABEL]], on=key, suffixes=("_1", "_5"), validate="one_to_one")
    result["checks"]["same_rows_in_A1_and_A5"] = bool(len(merged) == len(a1) == len(a5))
    result["checks"]["same_label_in_A1_and_A5"] = bool(np.allclose(merged[f"{LABEL}_1"], merged[f"{LABEL}_5"]))
    result["checks"]["same_fold_in_A1_and_A5"] = bool((merged["fold_1"] == merged["fold_5"]).all())
    result["checks"]["predictions_finite"] = bool(np.isfinite(a1["prediction"]).all() and np.isfinite(a5["prediction"]).all())
    result["checks"]["label_range"] = [float(a1[LABEL].min()), float(a1[LABEL].max())]
    result["checks"]["rows_per_fold"] = {int(k): int(v) for k, v in a1.groupby("fold").size().items()}
    # ---- per-arm IC series ----
    def series_for(directory, arm, seeds=(0,)):
        s = [per_date_ic(load(directory, arm, k)) for k in seeds]
        return pd.concat(s, axis=1).mean(axis=1)

    def folds_for(directory, arm, seeds=(0,)):
        out = []
        for k in seeds:
            f = load(directory, arm, k)
            out.append([per_date_ic(f[f["fold"] == j]).mean() for j in range(8)])
        return np.mean(out, axis=0)

    arms12 = {"A1": (0,), "A5": (0,), "A2": (0,), "A6": (0,), "P0": (0, 1, 2, 3, 4), "P0s": (0,), "P1": (0, 1, 2, 3, 4), "P2": (0,), "P3": (0, 1, 2, 3, 4)}
    ics = {a: series_for(E12, a, s) for a, s in arms12.items()}
    fo = {a: folds_for(E12, a, s) for a, s in arms12.items()}
    recorded = {r["contrast"]: r for r in csv.DictReader((E12 / "paired_tests.csv").open())}
    spec = {"T1": ("A5", "A1"), "T2": ("A6", "A5"), "T3": ("A1", "A2"), "C1": ("A5", "P0"), "C2": ("A5", "P0s"), "C3": ("A6", "P1"), "C4": ("A6", "P2"), "C5": ("A1", "P3")}
    for name, (l, r) in spec.items():
        mine = paired(ics[l], ics[r], fo[l], fo[r])
        rec = recorded[name]
        mine["recorded"] = {"mean_diff": float(rec["mean_diff"]), "hac_t": float(rec["hac_t"]), "p_one_sided": float(rec["p_one_sided"]), "boot_lo": float(rec["boot95_low"]), "boot_hi": float(rec["boot95_high"]),
                            "positive_folds": int(rec["positive_folds"])}
        mine["abs_diff_mean"] = abs(mine["mean_diff"] - mine["recorded"]["mean_diff"])
        mine["abs_diff_t"] = abs(mine["hac_t"] - mine["recorded"]["hac_t"])
        result["contrasts"][f"EXP-012 {name} ({l}-{r})"] = mine
    holm_mine = holm({k: result["contrasts"][f"EXP-012 {k} ({spec[k][0]}-{spec[k][1]})"]["p_one_sided"] for k in ("T1", "T2", "T3")})
    manifest12 = json.loads((E12 / "manifest.json").read_text())
    result["holm_adjusted"] = {"mine": holm_mine, "recorded": {k: manifest12["verdicts"][k]["adjusted_p"] for k in ("T1", "T2", "T3")}}
    # ---- EXP-013 headline contrasts ----
    arms13 = {"B1": (0,), "B5": (0,), "C_amended": (0,), "C_P": (0,), "D_P": (0,), "C_missing": (0,), "C_u": (0,)}
    ic13 = {a: series_for(E13, a, s) for a, s in arms13.items()}
    fo13 = {a: folds_for(E13, a, s) for a, s in arms13.items()}
    rec13 = {r["contrast"]: r for r in csv.DictReader((E13 / "paired_tests.csv").open())}
    spec13 = {"add_amended": ("C_amended", "B1"), "G_P": ("C_P", "B1"), "G_M": ("C_missing", "B1"), "G_U": ("C_u", "B1"), "P_drop": ("B5", "D_P"), "total": ("B5", "B1")}
    for name, (l, r) in spec13.items():
        mine = paired(ic13[l], ic13[r], fo13[l], fo13[r])
        rec = rec13[name]
        mine["recorded"] = {"mean_diff": float(rec["mean_diff"]), "hac_t": float(rec["hac_t"]), "p_one_sided": float(rec["p_one_sided"]), "positive_folds": int(rec["positive_folds"])}
        mine["abs_diff_mean"] = abs(mine["mean_diff"] - mine["recorded"]["mean_diff"])
        mine["abs_diff_t"] = abs(mine["hac_t"] - mine["recorded"]["hac_t"])
        result["contrasts"][f"EXP-013 {name} ({l}-{r})"] = mine
    holm13 = holm({k: result["contrasts"][f"EXP-013 {k} ({spec13[k][0]}-{spec13[k][1]})"]["p_one_sided"] for k in ("G_P", "G_M", "G_U")})
    result["holm_adjusted"]["exp013_mine"] = holm13
    result["holm_adjusted"]["exp013_recorded"] = {k: float(rec13[k]["holm_adjusted_p"]) for k in ("G_P", "G_M", "G_U")}
    worst_mean = max(c["abs_diff_mean"] for c in result["contrasts"].values())
    worst_t = max(c["abs_diff_t"] for c in result["contrasts"].values())
    result["summary"] = {"largest_abs_difference_in_mean": worst_mean, "largest_abs_difference_in_t": worst_t,
                         "all_positive_fold_counts_equal": all(c["positive_folds"] == c["recorded"]["positive_folds"] for c in result["contrasts"].values())}
    OUT.write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps({"checks": result["checks"], "summary": result["summary"], "holm": result["holm_adjusted"]}, indent=1, default=float))
    for k, c in result["contrasts"].items():
        print(f"{k:34} mean {c['mean_diff']:+.6f} (rec {c['recorded']['mean_diff']:+.6f})  t {c['hac_t']:.3f} (rec {c['recorded']['hac_t']:.3f})  folds+ {c['positive_folds']} (rec {c['recorded']['positive_folds']})")


if __name__ == "__main__":
    sys.exit(main())
