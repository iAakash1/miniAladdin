#!/usr/bin/env python3
"""Phase II step 3: is the dependence of the EXP-012 T1 gain on a few flagged firms unusual, and how persistent are the six new columns?

EXPLORATORY re-analysis of registered outputs (no refit). Two questions that the leave-top-k-out table in phase2_cluster_diagnostics.py cannot answer on its own:

  1. Removing the most influential firms always lowers a positive statistic, because they are selected for being influential. How much does it lower it when the removed firms are chosen the same way
     from ALL firms, from UNFLAGGED firms only, or at random from the flagged firms? Only the comparison says whether the flagged firms are special.
  2. How much of each new column is a persistent firm trait? Between-firm share of variance, one-year (50 grid steps = 252 sessions) within-firm autocorrelation, and the share of firm-dates whose value
     equals the same firm's value a year earlier. This is what the shifted-timestamp placebo was probing.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_influence_calibration.py
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
OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_influence_calibration.json"
LABEL = "fwd_rank_21"
SEED = 20261012
MIN_NAMES = 10


def spearman(a, b):
    ra, rb = rankdata(a), rankdata(b)
    ra, rb = ra - ra.mean(), rb - rb.mean()
    den = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / den) if den > 0 else np.nan


def load():
    e12 = REPO / "experiments/EXP-012/checkpoints"
    a1 = pd.read_parquet(e12 / "A1_0.parquet").rename(columns={"prediction": "s1"})
    a5 = pd.read_parquet(e12 / "A5_0.parquet")[["date", "symbol", "prediction"]].rename(columns={"prediction": "s5"})
    d = a1.merge(a5, on=["date", "symbol"], validate="one_to_one")
    d["date"] = pd.to_datetime(d["date"])
    rel = pd.read_parquet(REPO / "data/research/derived/reliability_v1.parquet")
    rel["date"] = pd.to_datetime(rel["date"])
    panel = pd.read_parquet(REPO / "data/research/derived/rich_pit_panel.parquet", columns=["date", "symbol", "security_id"])
    panel["date"] = pd.to_datetime(panel["date"])
    d = d.merge(rel, on=["date", "symbol"], how="left").merge(panel, on=["date", "symbol"], how="left")
    d["firm"] = d["security_id"].astype("object").where(d["security_id"].notna(), "sym:" + d["symbol"].astype(str))
    d["flag"] = d["amended_730"].fillna(0) > 0
    return d.sort_values(["date", "symbol"]).reset_index(drop=True)


def main() -> int:
    began = time.perf_counter()
    d = load()
    codes, names = pd.factorize(d["firm"])
    n_firms = len(names)
    s1, s5, y = d["s1"].to_numpy(), d["s5"].to_numpy(), d[LABEL].to_numpy()
    dates = [idx for _, idx in d.groupby("date", sort=True).indices.items()]
    flagged = np.zeros(n_firms, dtype=bool)
    flagged[np.unique(codes[d["flag"].to_numpy()])] = True

    def delta_series(drop: set[int] | None = None) -> np.ndarray:
        out = np.full(len(dates), np.nan)
        mask = None if not drop else ~np.isin(codes, list(drop))
        for k, idx in enumerate(dates):
            sel = idx if mask is None else idx[mask[idx]]
            if len(sel) >= MIN_NAMES:
                out[k] = spearman(s5[sel], y[sel]) - spearman(s1[sel], y[sel])
        return out

    base = delta_series()
    theta = float(np.nanmean(base))
    # influence of each firm (leave-one-out), only dates where the firm is present need recomputation
    firm_rows = [np.flatnonzero(codes == c) for c in range(n_firms)]
    date_of_row = np.empty(len(d), dtype=int)
    for k, idx in enumerate(dates):
        date_of_row[idx] = k
    influence = np.zeros(n_firms)
    for c in range(n_firms):
        delta = base.copy()
        for k in np.unique(date_of_row[firm_rows[c]]):
            idx = dates[k]
            sel = idx[codes[idx] != c]
            if len(sel) >= MIN_NAMES:
                delta[k] = spearman(s5[sel], y[sel]) - spearman(s1[sel], y[sel])
        influence[c] = theta - float(np.nanmean(delta))          # positive: the firm raises the statistic
    order_all = np.argsort(-influence)
    order_unflagged = [c for c in order_all if not flagged[c]]
    order_flagged = [c for c in order_all if flagged[c]]
    rng = np.random.default_rng(SEED)
    table = {}
    for k in (5, 10, 20):
        row = {}
        for label, pick in (("top_k_flagged_by_influence", order_flagged[:k]), ("top_k_unflagged_by_influence", order_unflagged[:k]), ("top_k_of_all_firms_by_influence", list(order_all[:k]))):
            row[label] = float(np.nanmean(delta_series(set(int(c) for c in pick))))
        flagged_ids = np.flatnonzero(flagged)
        draws = [float(np.nanmean(delta_series(set(int(c) for c in rng.choice(flagged_ids, size=k, replace=False))))) for _ in range(40)]
        row["random_k_flagged_mean_of_40_draws"] = float(np.mean(draws))
        row["random_k_flagged_range"] = [float(np.min(draws)), float(np.max(draws))]
        table[str(k)] = row
    # how many of the 20 most influential firms overall are flagged?
    top20 = order_all[:20]
    result = {"status": "EXPLORATORY re-analysis of registered outputs; no refit", "firms": int(n_firms), "flagged_firms": int(flagged.sum()), "mean_delta_ic_all_firms": theta,
              "mean_delta_ic_after_removal": table, "flagged_among_20_most_influential_firms": int(flagged[top20].sum()),
              "reading": "A positive statistic always falls when its most influential contributors are removed; the comparison across the four rows is what matters."}
    # ---- persistence of the six new columns (label-free) ----
    panel = pd.read_parquet(REPO / "data/research/derived/rich_pit_panel.parquet", columns=["date", "symbol", "security_id"])
    rel = pd.read_parquet(REPO / "data/research/derived/reliability_v1.parquet")
    panel["date"], rel["date"] = pd.to_datetime(panel["date"]), pd.to_datetime(rel["date"])
    z = panel.merge(rel, on=["date", "symbol"], how="left")
    z["firm"] = z["security_id"].astype("object").where(z["security_id"].notna(), "sym:" + z["symbol"].astype(str))
    z = z.sort_values(["firm", "date"])
    persistence = {}
    for col in ("amended_730", "latest_report_amended", "periodic_count_400", "lag_deterioration"):
        s = z[["firm", "date", col]].dropna()
        mean_f = s.groupby("firm")[col].transform("mean")
        total = float(s[col].var())
        between = float(mean_f.var())
        lag = s.groupby("firm")[col].shift(50)
        ok = lag.notna()
        same = float((s.loc[ok, col] == lag[ok]).mean()) if ok.any() else np.nan
        ac = float(np.corrcoef(s.loc[ok, col], lag[ok])[0, 1]) if ok.sum() > 10 and s.loc[ok, col].std() > 0 else np.nan
        persistence[col] = {"between_firm_share_of_variance": between / total if total > 0 else np.nan, "autocorr_one_year_within_firm": ac, "share_equal_to_value_one_year_earlier": same, "rows": int(len(s))}
    result["persistence_of_raw_variables"] = persistence
    result["seconds"] = round(time.perf_counter() - began, 1)
    OUT.write_text(json.dumps(result, indent=1, default=float) + "\n")
    print(json.dumps(result, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
