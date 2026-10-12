#!/usr/bin/env python3
"""Phase II step 4b: how believable is the discovery-sample amendment coefficient once the small number of treated firms is respected?

EXPLORATORY, on the discovery sample (EXP-012/013 validation rows). `phase2_regression_discovery.py` reported two-way clustered t statistics near -6 for the value-changing amendment indicator. With about a
dozen treated firms those asymptotic statistics are not trustworthy: in a simulation with three treated firms of fifty and no effect, a plain firm-clustered t rejects 22% of the time at the nominal 5%
(`tests/quant/test_exp014_inference.py`). The wild-cluster bootstrap with the null imposed (Webb weights, 9,999 draws) is the appropriate check, so this script repeats the discovery regressions with it, and
also removes the most influential treated firms.

The sample, the variables and the controls are exactly those of `phase2_regression_discovery.build_frame`; nothing is tuned and nothing here feeds the registration of EXP-014 except as a reason for using the
bootstrap there.

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/phase2_wild_bootstrap_discovery.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from src.quant.study import exp014_inference as inf  # noqa: E402

OUT = REPO / "docs/research/market-signal-review-2026-10-11/validation/phase2_wild_bootstrap_discovery.json"
DRAWS = 9999
SEED = 20261013


def load_builder():
    spec = importlib.util.spec_from_file_location("discovery", Path(__file__).with_name("phase2_regression_discovery.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(d: pd.DataFrame, focus: str, regs: list[str], fe: str | None, label: str, firm_codes: np.ndarray, exclude: np.ndarray | None = None) -> dict:
    keep = d[["label", *regs]].notna().all(axis=1).to_numpy()
    if exclude is not None and len(exclude):
        keep &= ~np.isin(firm_codes, exclude)
    s = d[keep].reset_index(drop=True)
    groups = [s["date"]] if fe is None else [s["date"], s[fe].astype(str)]
    z = inf.absorb(s, ["label", *regs], groups)
    X = z[regs].to_numpy(float)
    y = z["label"].to_numpy(float)
    firm = pd.factorize(s["firm"])[0]
    date = pd.factorize(s["date"])[0]
    names = list(regs)
    fit = inf.ols(y, X, names, firm, date)
    two_way = inf.summary(fit, inf.cgm_two_way(fit, X, firm, date), focus)
    one_way = inf.summary(fit, inf.one_way(fit, X, firm), focus)
    j = names.index(focus)
    boot = inf.wild_cluster_bootstrap(y, X[:, j], np.delete(X, j, axis=1), firm, draws=DRAWS, seed=SEED)
    treated = s.loc[s[focus] > 0, "firm"].nunique()
    return {"label": label, "focus": focus, "rows": int(len(s)), "firms": int(s["firm"].nunique()), "treated_firms": int(treated), "treated_rows": int((s[focus] > 0).sum()),
            "coef": two_way["coef"], "t_two_way_firm_date": two_way["t"], "t_one_way_firm": one_way["t"],
            "wild_cluster_bootstrap": {"t_obs": boot["t_obs"], "p_one_sided_negative": boot["p_one_sided_negative"], "p_two_sided": boot["p_two_sided"], "draws": boot["draws"],
                                       "t_star_q025": boot["t_star_quantiles"]["0.025"], "t_star_q975": boot["t_star_quantiles"]["0.975"]}}


def main() -> int:
    disc = load_builder()
    d, ctrl = disc.build_frame()
    firm_codes_all = pd.factorize(d["firm"])[0]
    base = ["score", *ctrl]
    res = {"status": "EXPLORATORY discovery-sample inference with few treated firms; not confirmatory", "draws": DRAWS, "seed": SEED, "models": []}
    specs = [
        ("M3 any amendment 730d, date FE", "D_any_730", ["D_any_730", *base], None),
        ("M3 any amendment 730d, date x FF12 FE", "D_any_730", ["D_any_730", *base], "ff12"),
        ("M4 core-changing 730d (with unchanged and unclassifiable), date FE", "D_core_730", ["D_core_730", "D_unchanged_730", "D_unclass_730", *base], None),
        ("M4 core-changing 730d, date x FF12 FE", "D_core_730", ["D_core_730", "D_unchanged_730", "D_unclass_730", *base], "ff12"),
        ("M4 unchanged-numbers amendments 730d (comparator), date FE", "D_unchanged_730", ["D_core_730", "D_unchanged_730", "D_unclass_730", *base], None),
        ("window 365d any amendment, date FE", "D_any_365", ["D_any_365", *base], None),
        ("window 1095d any amendment, date FE", "D_any_1095", ["D_any_1095", *base], None),
    ]
    for label, focus, regs, fe in specs:
        out = run(d, focus, regs, fe, label, firm_codes_all)
        res["models"].append(out)
        b = out["wild_cluster_bootstrap"]
        print(f"{label:70s} coef {out['coef']:+.4f} treated firms {out['treated_firms']:3d} | t two-way {out['t_two_way_firm_date']:+.2f}  t firm {out['t_one_way_firm']:+.2f}  WCR p(neg) {b['p_one_sided_negative']:.4f}")
    # influence: remove the treated firms that move the core-changing coefficient most
    regs = ["D_core_730", "D_unchanged_730", "D_unclass_730", *base]
    keep = d[["label", *regs]].notna().all(axis=1).to_numpy()
    s = d[keep].reset_index(drop=True)
    z = inf.absorb(s, ["label", *regs], [s["date"]])
    firm_s = pd.factorize(s["firm"])[0]
    treated_codes = np.unique(firm_s[(s["D_core_730"] > 0).to_numpy()])
    table = inf.influence_by_cluster(z["label"].to_numpy(float), z[regs].to_numpy(float), 0, firm_s, only=treated_codes)
    table["firm"] = [s["firm"].iloc[np.argmax(firm_s == c)] for c in table["cluster"]]
    table = table.sort_values("delta", ascending=False)                     # deleting these firms moves the coefficient up (towards zero) the most
    res["core_influence_top"] = [{"firm": str(r.firm), "rows": int(r.rows), "delta_if_deleted": float(r.delta)} for r in table.head(10).itertuples()]
    firm_all = {f: c for c, f in enumerate(pd.unique(d["firm"]))}
    res["core_leave_out"] = []
    for k in (3, 5, 10):
        drop = [firm_all[f] for f in table["firm"].head(k)]
        out = run(d, "D_core_730", regs, None, f"M4 core-changing 730d without the {k} most influential treated firms", np.array([firm_all[f] for f in d["firm"]]), np.array(drop))
        res["core_leave_out"].append(out)
        b = out["wild_cluster_bootstrap"]
        print(f"{out['label']:70s} coef {out['coef']:+.4f} treated firms {out['treated_firms']:3d} | t two-way {out['t_two_way_firm_date']:+.2f}  t firm {out['t_one_way_firm']:+.2f}  WCR p(neg) {b['p_one_sided_negative']:.4f}")
    OUT.write_text(json.dumps(res, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
