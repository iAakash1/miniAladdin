#!/usr/bin/env python3
"""Phase II step 4: discovery-sample regressions of the amendment signal with controls and two-way clustered errors.

EXPLORATORY, on the sample that discovered the effect (EXP-012/013 validation rows, 100,246 name-dates, 2017-05 to 2025-05). Its purpose is to inform the protocol of the next, independent study: which
amendment definition is natural, how large the effect is with controls, which component carries it, and how large the clustered errors are. Nothing here is a confirmatory result and nothing is tuned to
a p-value: the definitions are fixed in advance from first principles (window 730 days as in EXP-012; windows 365 and 1,095 and the component split are listed variants).

Design (one row = one firm-date; y = the 21-session forward return rank `fwd_rank_21`, centred, as in every earlier experiment):
    y_it = a_t + b * score_it + c' controls_it + g * amendment_it + e_it
  a_t   date fixed effects (variables demeaned within date; optionally within date x Fama-French 12 group)
  score the out-of-sample prediction of the conventional model (EXP-012 arm A1: 76 point-in-time features), rank-normalised within date
  controls (rank-transformed within date, as in the panel): liquidity/size proxies, momentum, reversal, volatility, value, profitability, investment, leverage, accruals, reporting lag and staleness,
          filing frequency
  errors  Cameron-Gelbach-Miller two-way clustering on firm and date, with the eigenvalue correction if the combined matrix is not positive semi-definite

The PIT amendment components come from `classify_amendments.py` (value-changing versus unchanged numbers), counted from each amendment's own availability session over a trailing window.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_regression_discovery.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from src.quant.pit import reliability as rel  # noqa: E402
from src.quant.study import exp010b  # noqa: E402

OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_regression_discovery.json"
LABEL = "fwd_rank_21"
CONTROLS = ["log_dollar_volume_21_xs", "amihud_21_xs", "mom_252_21_xs", "mom_21_xs", "reversal_5_xs", "vol_63_xs", "book_to_market_xs", "roa_xs", "gross_profitability_xs", "asset_growth_xs",
            "liabilities_to_assets_xs", "accruals_xs", "filing_lag_days_xs", "days_since_report_xs"]
CORE = ["revenue", "net_income", "assets", "liabilities", "equity", "operating_cash_flow"]


def cgm_two_way(X: np.ndarray, e: np.ndarray, g1: np.ndarray, g2: np.ndarray) -> np.ndarray:
    """Cameron-Gelbach-Miller two-way cluster-robust covariance of OLS coefficients."""
    n, k = X.shape
    bread = np.linalg.inv(X.T @ X)

    def meat(codes: np.ndarray) -> np.ndarray:
        s = np.zeros((codes.max() + 1, k))
        np.add.at(s, codes, X * e[:, None])
        g = len(np.unique(codes))
        return (g / (g - 1)) * (s.T @ s)

    inter = np.unique(np.stack([g1, g2], axis=1), axis=0, return_inverse=True)[1].ravel()
    m = meat(g1) + meat(g2) - meat(inter)
    v = bread @ m @ bread
    w, q = np.linalg.eigh((v + v.T) / 2)
    return (q * np.maximum(w, 0)) @ q.T


def demean(frame: pd.DataFrame, cols: list[str], by) -> pd.DataFrame:
    return frame[cols] - frame.groupby(by)[cols].transform("mean")


def fit(d: pd.DataFrame, y: str, regressors: list[str], fe=None, label: str = "") -> dict:
    keep = d[[y, *regressors]].notna().all(axis=1)
    s = d[keep]
    by = s["date"] if fe is None else [s["date"], s[fe]]
    z = demean(s.assign(_one=1.0)[[y, *regressors]], [y, *regressors], by if fe is None else s[["date", fe]].astype(str).agg("|".join, axis=1))
    X, yy = z[regressors].to_numpy(float), z[y].to_numpy(float)
    beta = np.linalg.lstsq(X, yy, rcond=None)[0]
    e = yy - X @ beta
    firm = pd.factorize(s["firm"])[0]
    date = pd.factorize(s["date"])[0]
    v = cgm_two_way(X, e, firm, date)
    se = np.sqrt(np.diag(v))
    return {"label": label, "n": int(len(s)), "firms": int(s["firm"].nunique()), "dates": int(s["date"].nunique()),
            "coef": {r: float(b) for r, b in zip(regressors, beta)}, "se_two_way": {r: float(x) for r, x in zip(regressors, se)},
            "t": {r: float(b / x) for r, b, x in zip(regressors, beta, se)}, "p_one_sided_negative": {r: float(norm.cdf(b / x)) for r, b, x in zip(regressors, beta, se)}}


def build_frame() -> tuple[pd.DataFrame, list[str]]:
    """The discovery-sample frame: validation predictions, controls, point-in-time amendment components. Returns it with the list of control columns."""
    e12 = REPO / "experiments/EXP-012/checkpoints"
    d = pd.read_parquet(e12 / "A1_0.parquet").rename(columns={"prediction": "score"})
    d["date"] = pd.to_datetime(d["date"])
    panel = pd.read_parquet(REPO / "data/research/derived/rich_pit_panel.parquet", columns=["date", "symbol", "security_id", "cik", "ff12", *CONTROLS])
    panel["date"] = pd.to_datetime(panel["date"])
    relt = pd.read_parquet(REPO / "data/research/derived/reliability_v1.parquet")
    relt["date"] = pd.to_datetime(relt["date"])
    d = d.merge(panel, on=["date", "symbol"], how="left").merge(relt, on=["date", "symbol"], how="left")
    d["firm"] = d["security_id"].astype("object").where(d["security_id"].notna(), "sym:" + d["symbol"].astype(str))
    d["score"] = d.groupby("date")["score"].rank(pct=True) - 0.5
    for col in ("periodic_count_400", "lag_deterioration"):
        d[f"{col}_r"] = d.groupby("date")[col].rank(pct=True) - 0.5
    # point-in-time amendment components from the amendment classification
    filings = pd.read_parquet(REPO / rel.FILINGS)
    calendar = exp010b.build_daily_panel(REPO)[1]
    ciks = {int(c) for c in d["cik"].dropna().unique()}
    table = rel.filing_table(filings, calendar, ciks)
    cls = pd.read_parquet(REPO / "data/research/derived/amendment_classification_v1.parquet")[["adsh", "classifiable", "core_changing_1pct", "unchanged_numbers", "value_changing_1pct"]]
    amend = table[table["is_amend"]].merge(cls, on="adsh", how="left")
    amend["classifiable"] = amend["classifiable"].fillna(False)
    amend["core"] = amend["core_changing_1pct"].fillna(False).astype(bool)
    amend["unchanged"] = amend["unchanged_numbers"].fillna(False).astype(bool)
    amend["unclass"] = ~amend["classifiable"].astype(bool)
    days = rel.epoch_days(d["date"]).astype("int64")
    d["_day"] = days
    comps = {}
    for name, mask in (("any", np.ones(len(amend), dtype=bool)), ("core", amend["core"].to_numpy()), ("unchanged", amend["unchanged"].to_numpy()), ("unclass", amend["unclass"].to_numpy()),
                       ("10K", (amend["form"].isin(["10-K/A", "10-KT/A"])).to_numpy()), ("10Q", (amend["form"].isin(["10-Q/A", "10-QT/A"])).to_numpy())):
        for window in (365, 730, 1095):
            comps[f"{name}_{window}"] = np.zeros(len(d))
        sub = amend[mask]
        by_cik = {int(c): np.sort(g["avail_d"].to_numpy()) for c, g in sub.groupby("cik")}
        for cik, idx in d.groupby(d["cik"].fillna(-1).astype("int64")).indices.items():
            a = by_cik.get(int(cik))
            if a is None or cik < 0:
                continue
            day = days[idx]
            hi = np.searchsorted(a, day, side="right")
            for window in (365, 730, 1095):
                comps[f"{name}_{window}"][idx] = hi - np.searchsorted(a, day - window, side="right")
    for k, v in comps.items():
        d[f"n_{k}"] = v
        d[f"D_{k}"] = (v > 0).astype(float)
    assert np.allclose(d["D_any_730"], (d["amended_730"].fillna(0) > 0).astype(float)), "the recomputed 730-day indicator must equal the registered variable"
    ctrl = [*CONTROLS, "periodic_count_400_r", "lag_deterioration_r"]
    for c in CONTROLS:
        d[c] = d[c].fillna(0.0)                                   # rank-transformed, centred: missing = neutral
    d[["periodic_count_400_r", "lag_deterioration_r"]] = d[["periodic_count_400_r", "lag_deterioration_r"]].fillna(0.0)
    d["n_log_any_730"] = np.log1p(d["n_any_730"])
    d["label"] = d[LABEL]
    return d, ctrl


def main() -> int:
    d, ctrl = build_frame()
    res = {"status": "EXPLORATORY discovery-sample regressions; informs the next protocol; not confirmatory", "rows": len(d),
           "prevalence_of_D_any_730": float(d["D_any_730"].mean()), "firms_ever_flagged_any_730": int(d.loc[d["D_any_730"] > 0, "firm"].nunique()),
           "prevalence": {k: float(d[f"D_{k}"].mean()) for k in ("any_730", "core_730", "unchanged_730", "unclass_730", "10K_730", "10Q_730", "any_365", "any_1095")}, "models": []}
    runs = [
        ("M0 raw: D_any_730", "label", ["D_any_730"], None),
        ("M1 + conventional OOS score", "label", ["D_any_730", "score"], None),
        ("M2 + explicit controls", "label", ["D_any_730", *ctrl], None),
        ("M3 + score + explicit controls", "label", ["D_any_730", "score", *ctrl], None),
        ("M3 with date x FF12 fixed effects", "label", ["D_any_730", "score", *ctrl], "ff12"),
        ("M4 components (core-changing / unchanged / unclassifiable), score + controls", "label", ["D_core_730", "D_unchanged_730", "D_unclass_730", "score", *ctrl], None),
        ("M5 form split (10-K/A vs 10-Q/A), score + controls", "label", ["D_10K_730", "D_10Q_730", "score", *ctrl], None),
        ("M6 window 365, score + controls", "label", ["D_any_365", "score", *ctrl], None),
        ("M7 window 1095, score + controls", "label", ["D_any_1095", "score", *ctrl], None),
        ("M8 count (log1p of amendments in 730 days), score + controls", "label", ["n_log_any_730", "score", *ctrl], None),
    ]
    for name, y, regs, fe in runs:
        out = fit(d, y, regs, fe, name)
        out["focus"] = {r: {"coef": out["coef"][r], "se_two_way": out["se_two_way"][r], "t": out["t"][r], "p_one_sided_negative": out["p_one_sided_negative"][r]} for r in regs if r.startswith(("D_", "n_log"))}
        for key in ("coef", "se_two_way", "t", "p_one_sided_negative"):
            out.pop(key)
        res["models"].append(out)
        print(name, "|", {r: (round(v["coef"], 4), round(v["t"], 2)) for r, v in out["focus"].items()})
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
