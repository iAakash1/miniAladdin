#!/usr/bin/env python3
"""Phase II step 2: does the EXP-012 T1 gain survive firm-level dependence, and where does it come from?

EXPLORATORY RE-ANALYSIS of the registered outputs (no model is refit, no feature is changed). It uses the saved out-of-sample predictions of EXP-012 (A1 = rich set, A5 = rich set plus the new block) and
EXP-013 (B1, B5, C_amended), the point-in-time reliability table, and the panel's firm identifier. It is performed on the sample that discovered the effect, before any new protocol is registered, and is
labelled exploratory in every document that cites it.

What it computes (all paired on identical dates, on the 100,246 validation rows):
  1. The registered statistic (mean per-date Rank IC difference) and its date-based Newey-West t, for reference.
  2. A delete-one-firm jackknife (cluster-robust variance) of that statistic, the most influential firms, and the statistic after removing the most influential flagged firms from the evaluation.
  3. A firm-cluster bootstrap (resample firms with all their dates; Rank IC recomputed on the resampled cross-sections) and a two-way (firm x date-block) pigeonhole bootstrap.
  4. Decomposition by flagged status (amendment in the trailing 730 days): the same IC difference on unflagged rows only, the score shift the model gives flagged rows, and the raw mean label rank of flagged rows.
  5. Stability by validation year (fold).

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_cluster_diagnostics.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_cluster_diagnostics.json"
LABEL = "fwd_rank_21"
SEED = 20261012


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = rankdata(a), rankdata(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / den) if den > 0 else np.nan


def nw_t(x: np.ndarray, lags: int = 4) -> float:
    n = len(x)
    d = x - x.mean()
    lrv = float(d @ d) / n + sum(2.0 * (1 - k / (lags + 1)) * float(d[k:] @ d[:-k]) / n for k in range(1, lags + 1))
    return float(x.mean() / np.sqrt(lrv / n))


def load() -> pd.DataFrame:
    e12, e13 = REPO / "experiments/EXP-012/checkpoints", REPO / "experiments/EXP-013/checkpoints"
    a1 = pd.read_parquet(e12 / "A1_0.parquet").rename(columns={"prediction": "s1"})
    a5 = pd.read_parquet(e12 / "A5_0.parquet")[["date", "symbol", "prediction"]].rename(columns={"prediction": "s5"})
    ca = pd.read_parquet(e13 / "C_amended_0.parquet")[["date", "symbol", "prediction"]].rename(columns={"prediction": "sa"})
    d = a1.merge(a5, on=["date", "symbol"], validate="one_to_one").merge(ca, on=["date", "symbol"], validate="one_to_one")
    d["date"] = pd.to_datetime(d["date"])
    rel = pd.read_parquet(REPO / "data/research/derived/reliability_v1.parquet", columns=["date", "symbol", "amended_730"])
    rel["date"] = pd.to_datetime(rel["date"])
    panel = pd.read_parquet(REPO / "data/research/derived/rich_pit_panel.parquet", columns=["date", "symbol", "security_id", "cik"])
    panel["date"] = pd.to_datetime(panel["date"])
    d = d.merge(rel, on=["date", "symbol"], how="left").merge(panel, on=["date", "symbol"], how="left")
    d["firm"] = d["security_id"].astype("object").where(d["security_id"].notna(), "sym:" + d["symbol"].astype(str))
    d["flag"] = d["amended_730"].fillna(0) > 0
    return d.sort_values(["date", "symbol"]).reset_index(drop=True)


def per_date_arrays(d: pd.DataFrame, firm_codes: np.ndarray):
    out = []
    for day, idx in d.groupby("date", sort=True).indices.items():
        out.append((day, idx, firm_codes[idx]))
    return out


def delta_ic(d: pd.DataFrame, groups, left: str, right: str, keep: np.ndarray | None = None, weights: np.ndarray | None = None) -> np.ndarray:
    """Per-date IC(left) - IC(right) on the rows kept (boolean mask over rows) and repeated by `weights` (per row, integer)."""
    s_l, s_r, y = d[left].to_numpy(), d[right].to_numpy(), d[LABEL].to_numpy()
    res = np.full(len(groups), np.nan)
    for k, (_, idx, _) in enumerate(groups):
        sel = idx if keep is None else idx[keep[idx]]
        if weights is not None:
            sel = np.repeat(sel, weights[sel])
        if len(sel) < 20:
            continue
        res[k] = spearman(s_l[sel], y[sel]) - spearman(s_r[sel], y[sel])
    return res


def main() -> int:
    began = time.perf_counter()
    d = load()
    firm_codes, firm_names = pd.factorize(d["firm"])
    groups = per_date_arrays(d, firm_codes)
    n_firms, n_dates = len(firm_names), len(groups)
    result: dict = {"status": "EXPLORATORY re-analysis of registered outputs; no model refit", "rows": len(d), "dates": n_dates, "firms": int(n_firms),
                    "flagged_rows": int(d["flag"].sum()), "flagged_firms": int(d.loc[d["flag"], "firm"].nunique())}

    # ---- 1. the registered statistic ----
    base = delta_ic(d, groups, "s5", "s1")
    result["registered_statistic"] = {"mean_delta_ic": float(np.nanmean(base)), "nw_t": nw_t(base[np.isfinite(base)]), "n": int(np.isfinite(base).sum())}
    theta = float(np.nanmean(base))
    result["amendment_only_statistic"] = {"mean_delta_ic": float(np.nanmean(delta_ic(d, groups, "sa", "s1"))), "note": "EXP-013 C_amended minus B1 (= EXP-012 A1)"}

    # ---- 2. delete-one-firm jackknife ----
    s5, s1, y = d["s5"].to_numpy(), d["s1"].to_numpy(), d[LABEL].to_numpy()
    flagged_firms = sorted(d.loc[d["flag"], "firm"].unique(), key=str)
    code_of = {name: i for i, name in enumerate(firm_names)}
    loo = np.full(n_firms, np.nan)
    firm_rows = {c: np.flatnonzero(firm_codes == c) for c in range(n_firms)}
    date_of_row = np.empty(len(d), dtype=int)
    for k, (_, idx, _) in enumerate(groups):
        date_of_row[idx] = k
    for c in range(n_firms):
        rows = firm_rows[c]
        if len(rows) == 0:
            continue
        delta = base.copy()
        for k in np.unique(date_of_row[rows]):
            idx = groups[k][1]
            sel = idx[firm_codes[idx] != c]
            delta[k] = spearman(s5[sel], y[sel]) - spearman(s1[sel], y[sel])
        loo[c] = float(np.nanmean(delta))
    ok = np.isfinite(loo)
    g = int(ok.sum())
    se_j = float(np.sqrt((g - 1) / g * np.sum((loo[ok] - loo[ok].mean()) ** 2)))
    result["jackknife_by_firm"] = {"firms": g, "se": se_j, "t": theta / se_j, "date_based_se": theta / result["registered_statistic"]["nw_t"]}
    influence = pd.Series(theta - loo, index=firm_names).dropna().sort_values(ascending=False)  # positive: the firm raises the statistic
    result["most_influential_firms"] = [{"firm": str(k), "influence_on_mean_delta_ic": float(v), "flagged": bool(k in set(flagged_firms))} for k, v in influence.head(12).items()]
    top_flagged = [f for f in influence.index if f in set(flagged_firms)]
    drops = {}
    for k in (1, 3, 5, 10, 20):
        drop = {code_of[f] for f in top_flagged[:k]}
        keep = ~np.isin(firm_codes, list(drop))
        dd = delta_ic(d, groups, "s5", "s1", keep=keep)
        drops[str(k)] = {"mean_delta_ic": float(np.nanmean(dd)), "nw_t": nw_t(dd[np.isfinite(dd)])}
    result["after_removing_most_influential_flagged_firms_from_evaluation"] = drops

    # ---- 3. firm-cluster and two-way bootstrap ----
    rng = np.random.default_rng(SEED)
    draws = 400
    boots = np.empty((draws, n_dates))
    for b in range(draws):
        m = rng.multinomial(n_firms, np.full(n_firms, 1.0 / n_firms))
        boots[b] = delta_ic(d, groups, "s5", "s1", weights=m[firm_codes])
    firm_means = np.nanmean(boots, axis=1)
    result["firm_cluster_bootstrap"] = {"draws": draws, "ci95": [float(np.percentile(firm_means, 2.5)), float(np.percentile(firm_means, 97.5))], "se": float(firm_means.std(ddof=1)),
                                        "share_of_draws_not_above_zero": float((firm_means <= 0).mean())}
    block, nb = 6, int(np.ceil(n_dates / 6))
    two_way = np.empty(draws)
    for b in range(draws):
        starts = rng.integers(0, n_dates - block + 1, size=nb)
        cols = np.concatenate([np.arange(s, s + block) for s in starts])[:n_dates]
        two_way[b] = np.nanmean(boots[b][cols])
    result["two_way_pigeonhole_bootstrap"] = {"draws": draws, "block": block, "ci95": [float(np.percentile(two_way, 2.5)), float(np.percentile(two_way, 97.5))], "se": float(two_way.std(ddof=1)),
                                              "share_of_draws_not_above_zero": float((two_way <= 0).mean()), "note": "firms and date blocks resampled independently; conservative by construction"}

    # ---- 4. decomposition by flagged status ----
    keep_unflagged = ~d["flag"].to_numpy()
    unf = delta_ic(d, groups, "s5", "s1", keep=keep_unflagged)
    result["decomposition"] = {"delta_ic_all_rows": theta, "delta_ic_unflagged_rows_only": float(np.nanmean(unf)), "nw_t_unflagged": nw_t(unf[np.isfinite(unf)])}
    r1 = d.groupby("date")["s1"].rank(pct=True) - 0.5
    r5 = d.groupby("date")["s5"].rank(pct=True) - 0.5
    shift = (r5 - r1).to_numpy()
    flag = d["flag"].to_numpy()
    result["decomposition"]["mean_rank_shift_A5_minus_A1"] = {"flagged": float(shift[flag].mean()), "unflagged": float(shift[~flag].mean()), "sd_unflagged": float(shift[~flag].std())}
    result["decomposition"]["mean_label_rank"] = {"flagged": float(y[flag].mean()), "unflagged": float(y[~flag].mean())}
    fl = pd.DataFrame({"firm": firm_codes[flag], "y": y[flag]})
    per_firm = fl.groupby("firm")["y"].agg(["mean", "size"])
    boot_means = []
    for _ in range(2000):
        pick = rng.integers(0, len(per_firm), len(per_firm))
        boot_means.append(np.average(per_firm["mean"].to_numpy()[pick], weights=per_firm["size"].to_numpy()[pick]))
    result["decomposition"]["flagged_label_rank_firm_cluster_bootstrap"] = {"mean": float(np.average(per_firm["mean"], weights=per_firm["size"])), "ci95": [float(np.percentile(boot_means, 2.5)), float(np.percentile(boot_means, 97.5))],
                                                                             "firms": int(len(per_firm)), "note": "raw mean cross-sectional return rank of flagged rows (0 = median); no control"}
    # ---- 5. by validation year ----
    folds = d["fold"].to_numpy()
    by_fold = {}
    date_fold = np.array([int(np.bincount(folds[idx]).argmax()) for _, idx, _ in groups])
    for f in range(8):
        sel = date_fold == f
        by_fold[str(f)] = {"delta_ic": float(np.nanmean(base[sel])), "dates": int(sel.sum()), "flagged_share_of_rows": float(flag[folds == f].mean()), "flagged_firms": int(pd.Series(firm_codes[(folds == f) & flag]).nunique())}
    result["by_fold"] = by_fold
    result["seconds"] = round(time.perf_counter() - began, 1)
    OUT.write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps(result, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
