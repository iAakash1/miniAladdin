"""
EXP-009B — does a ranking objective order the cross-section better than a point loss?

## The question

EXP-006's model is a gradient-boosted *regression* of the within-date rank label
`fwd_rank_21`. The book it feeds holds the top and bottom quintile, so what matters is
the ordering at the ends of the list, and a squared-error loss does not optimise that
directly. Learning-to-rank losses do (LambdaMART weights pairs by their effect on NDCG;
a pairwise loss weights them equally). The published evidence that this helps is gross
of costs and compares against weak regression baselines (see
`docs/DEEP_METHOD_RECONSTRUCTION.md`); this study asks the question on OmniSignal's
own data, net of costs, against a *matched* control.

## Identical in every cell except the objective

Same dataset (`ds-491d761b9f2a6fc4`), same 27 `C_base` features, same target, same
eight folds (recovered from EXP-006's recorded plan), same imputation, same universe
restriction, same tree learner, hyper-parameters, number of rounds and seed, same
random stream. The only argument that changes is `objective`: `l2` (the control),
`lambdamart`, `pairwise`. The engine-matched control is what makes a difference
attributable to the loss and not to the library.

`R0` refits scikit-learn's `GradientBoostingRegressor` through the same pipeline. It is
not a trial: it is a **validity gate**. If it does not reproduce EXP-006's frozen
predictions to 1e-9, the rebuilt dataset or pipeline is not the one EXP-006 used and
nothing else is reported.

## What "better" has to mean

Ordering (portfolio-free): pooled Rank IC with HAC inference, fold consistency, worst
fold, and NDCG at both ends. Stability: the ordering must not be bought by reshuffling
weekly. Economics: net Sharpe under the *frozen EXP-009A construction* (top-k dropout)
as well as the immediate-replacement control, because a ranking loss is not a turnover
control (the 2021 listwise paper's own turnover was higher than its regression baseline's)
and the two effects must not be confounded.

`prereg_gate` (from `src/quant/study/prereg.py`) refuses to run unless the preregistration
is committed unchanged and already on `origin/main`. Nothing here promotes a model;
results are EXPERIMENTAL / PROMOTION NOT ASSESSED; the sealed holdout is never read.
"""

from __future__ import annotations

import json
import math
import os
import platform
import time
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.quant.backtest.ordering import per_date_ordering, stability
from src.quant.backtest.turnover_diagnostics import breakeven_half_spread
from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study import exp009a
from src.quant.study import prereg
from src.quant.study.firewall import FIREWALL, HoldoutBreach  # noqa: F401
from src.quant.validation.metrics import ic_summary, per_date_ic
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.significance import deflated_sharpe_ratio
from src.quant.validation.walkforward import Fold, WalkForwardPlan

EXPERIMENT_ID = "EXP-009B"
PARENT_EXPERIMENT = "EXP-006"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_009B_LTR_PREREGISTRATION.md")
FRAME_CACHE = Path("data/research/derived/exp009b_frame.parquet")
FRAME_MANIFEST = Path("data/research/derived/exp009b_manifest.json")
PERIODS_PER_YEAR = 252 / 5
LABEL = "fwd_rank_21"

FEATURES = [
    "acceleration_xs", "dist_52w_high_xs", "ma_gap_xs", "mom_21_xs", "mom_252_21_xs", "mom_63_xs",
    "reversal_5_xs", "trend_strength_63_xs", "downside_vol_63_xs", "max_drawdown_252_xs", "vol_21_xs",
    "vol_63_xs", "vol_ratio_xs", "amihud_21_xs", "log_dollar_volume_21_xs", "volume_shock_xs",
    "market_drawdown", "market_mom_21", "market_mom_252", "market_vol_21", "market_vol_63",
    "market_vol_percentile", "rates_change_63", "rates_curvature", "rates_level", "rates_short",
    "rates_slope",
]

_COMMON = (
    ("n_estimators", 200), ("learning_rate", 0.03), ("max_depth", 3),
    ("subsample", 0.7), ("min_samples_leaf", 50),
)

#: The construction EXP-009A froze as the turnover mechanism (carried forward by its
#: preregistered rule). Reported next to the immediate-replacement control.
_C = {"rule": "topk_dropout", "quantiles": 5, "drop_fraction": 0.10}

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - PROMOTION NOT ASSESSED",
    "data": {
        "dataset_id": "ds-491d761b9f2a6fc4",
        "dataset_end": "2025-05-09",
        "returns_panel_sha256": "d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e",
        "target": LABEL,
        "features": FEATURES,
        "universe_only": True,
        "folds": "the 8 folds recorded in experiments/EXP-006/metrics.json (walk_forward_plan)",
        "imputation": "FoldImputer, training-fold median (unchanged)",
    },
    "cells": [
        {"id": "R0_sklearn_gb", "kind": "gradient_boosting", "role": "validity_gate",
         "note": "sklearn GradientBoostingRegressor refit; must reproduce EXP-006's frozen predictions to 1e-9; not a trial"},
        {"id": "R1_boosted_l2", "kind": "boosted_l2", "role": "control",
         "note": "same boosting loop, squared error on the continuous rank label"},
        {"id": "R2_boosted_lambdamart", "kind": "boosted_lambdamart", "role": "ranker",
         "note": "pairs weighted by |delta NDCG|; linear gains; log2 discount; whole list; sigma 1"},
        {"id": "R3_boosted_pairwise", "kind": "boosted_pairwise", "role": "ranker",
         "note": "pairwise logistic loss, uniform pair weights (position-agnostic)"},
    ],
    "shared_hyperparameters": dict(_COMMON) | {"seed": 0, "relevance_levels": 5, "sigma": 1.0, "truncation": None},
    "relevance": "clip(floor((rank + 1) / 2 * 5), 0, 4): the within-date quintile of the 21-session forward return",
    "queries": "one query per prediction date; pairs only inside a date",
    "hyperparameter_search": "none",
    "portfolio": {
        "immediate_replacement": {"rule": "baseline"},
        "frozen_turnover_mechanism": _C,
        "engine": "EXP-009A engine settings unchanged (lag 1, quintiles, 10 bp primary, 1/3/5/10/20 sweep)",
    },
    "ordering_metrics": {"ndcg_k": 50, "relevance": "quintile bins, linear gains, log2 discount; short end by reversing both",
                         "ic_hac_lags": 4},
    "criteria": {
        "validity": [
            "rebuilt dataset id and returns-panel hash equal the preregistered values",
            "the sklearn refit reproduces EXP-006's frozen gradient_boosting predictions to 1e-9 (max abs difference)",
        ],
        "O1_ordering": "paired mean difference in per-date Rank IC (ranker - control) > 0 with one-sided HAC lower bound (Bartlett, 4 lags, z = 1.96) > 0",
        "O2_consistency": "IC difference > 0 in at least 6 of 8 folds AND worst-fold IC >= control's worst-fold IC - 0.005",
        "O3_stability": "consecutive-date rank correlation >= control's - 0.02 AND top-group retention >= control's - 0.02 AND bottom-group retention >= control's - 0.02",
        "E1_economics": (
            "under the frozen turnover mechanism (top-k dropout): annualised turnover <= 1.10 x the control's AND the paired "
            "block-bootstrap (block 8, 10000 draws, seed 0) one-sided lower bound of the net-Sharpe difference at 10 bp, level 1 - 0.05/2, is > 0"
        ),
        "classification": {
            "ORDERING_AND_NET_IMPROVED": "O1 and O2 and O3 and E1",
            "ORDERING_IMPROVED_NOT_ECONOMIC": "O1 and O2 and O3 and not E1",
            "ORDERING_IMPROVED_UNSTABLE": "O1 and not (O2 and O3)",
            "NO_ORDERING_GAIN": "not O1",
        },
        "carry_forward": (
            "the model used as BASE in EXP-009C is the ORDERING_AND_NET_IMPROVED ranker with the larger IC difference; "
            "if none, BASE is the sklearn GradientBoostingRegressor (the frozen point-regression baseline)"
        ),
        "descriptive_only": [
            "immediate-replacement portfolio results", "deflated Sharpe", "factor alpha", "train-validation IC gap",
            "prediction dispersion", "break-even half-spread",
        ],
        "promotion": "NOT ASSESSED",
    },
    "inference": {"family_alpha": 0.05, "n_rankers": 2, "bootstrap_block": 8, "bootstrap_draws": 10000, "seed": 0},
    "trials": {
        "declared": 3, "note": "control + two rankers; the sklearn refit is a gate, not a trial",
        "prior_cumulative_evaluations": 160, "cumulative_evaluations": 163,
        "not_run": ["LightGBM / XGBoost (not installed; OpenMP runtime absent)", "listwise ListNet/ListMLE", "hyperparameter search",
                    "two-sided (both-tail) NDCG training", "any neural ranker"],
    },
    "holdout": {"read": False},
}

METHOD_SOURCES = (
    "src/quant/models/ranking.py",
    "src/quant/models/base.py",
    "src/quant/validation/runner.py",
    "src/quant/backtest/rules.py",
    "src/quant/backtest/engine.py",
    "src/quant/backtest/ordering.py",
    "src/quant/study/exp009b.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


# ── inputs ───────────────────────────────────────────────────────────────────

def holdout_window(root: Path = Path(".")) -> tuple[Date, Date]:
    """The widest sealed window EXP-006 recorded anywhere (plan vs contract differ by two sessions)."""
    metrics = json.loads((Path(root) / exp009a.FROZEN_METRICS).read_text())
    plan = metrics["labels"][LABEL]["walk_forward_plan"]
    starts = [Date.fromisoformat(metrics["holdout"]["start"]), Date.fromisoformat(plan["holdout_start"])]
    ends = [Date.fromisoformat(metrics["holdout"]["end"]), Date.fromisoformat(plan["holdout_end"])]
    return min(starts), max(ends)


def arm_firewall(root: Path = Path(".")) -> tuple[Date, Date]:
    start, end = holdout_window(root)
    FIREWALL.arm_window(start, end)
    return start, end


def recorded_plan(root: Path = Path(".")) -> WalkForwardPlan:
    """EXP-006's eight folds, rebuilt from the recorded dates rather than re-derived.

    Re-deriving them from a calendar that ends at 2025-05-09 would place the holdout
    differently and move every fold; the recorded plan is the identical split.
    """
    plan = json.loads((Path(root) / exp009a.FROZEN_METRICS).read_text())["labels"][LABEL]["walk_forward_plan"]
    folds = [
        Fold(
            index=f["index"], train_start=Date.fromisoformat(f["train_start"]),
            train_end=Date.fromisoformat(f["train_end"]), purge_end=Date.fromisoformat(f["purge_end"]),
            validation_start=Date.fromisoformat(f["validation_start"]),
            validation_end=Date.fromisoformat(f["validation_end"]),
            label_horizon_sessions=f["label_horizon_sessions"], embargo_sessions=f["embargo_sessions"],
            gap_sessions=f["gap_sessions"],
        )
        for f in plan["folds"]
    ]
    return WalkForwardPlan(
        folds=folds, holdout_start=Date.fromisoformat(plan["holdout_start"]),
        holdout_end=Date.fromisoformat(plan["holdout_end"]), scheme=plan["scheme"],
        label_horizon_sessions=plan["label_horizon_sessions"], embargo_sessions=plan["embargo_sessions"],
        train_sessions=plan["train_sessions"], validation_sessions=plan["validation_sessions"],
        notes=list(plan["notes"]),
    )


def load_frame(root: Path = Path(".")) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The pre-holdout dataset, built once through the real builder and cached."""
    arm_firewall(root)
    cache, manifest_path = Path(root) / FRAME_CACHE, Path(root) / FRAME_MANIFEST
    end = Date.fromisoformat(DEFINITION["data"]["dataset_end"])
    if not (cache.exists() and manifest_path.exists()):
        from src.quant.datasets.store import RawStore
        from src.quant.pit.dataset import DatasetBuilder
        from src.quant.pit.universe import UniverseHistory

        store = RawStore(Path(root) / "data/research")
        universe = UniverseHistory.load(Path(root) / "data/research" / "universe")
        dataset = DatasetBuilder(store, universe).build(
            start=Date(2014, 4, 1), end=end, step_sessions=5, workers=6)
        cache.parent.mkdir(parents=True, exist_ok=True)
        dataset.frame.to_parquet(cache, compression="zstd")
        manifest_path.write_text(json.dumps(dataset.manifest.as_dict(), default=str))
    frame = pd.read_parquet(cache)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    FIREWALL.assert_clear(frame, context="EXP-009B dataset")
    manifest = json.loads(manifest_path.read_text())
    return frame, manifest


def specs() -> list[ModelSpec]:
    seed = DEFINITION["shared_hyperparameters"]["seed"]
    out = []
    for cell in DEFINITION["cells"]:
        if cell["kind"] == "gradient_boosting":
            out.append(ModelSpec(cell["id"], cell["kind"], (), seed))
        else:
            out.append(ModelSpec(cell["id"], cell["kind"], _COMMON, seed))
    return out


# ── metrics ──────────────────────────────────────────────────────────────────

def _ic_series(predictions: pd.DataFrame) -> pd.Series:
    return per_date_ic(predictions, prediction_column="prediction", target_column=LABEL)


def fold_ic(predictions: pd.DataFrame) -> list[float]:
    return [float(_ic_series(g).mean()) for _, g in predictions.groupby("fold")]


def paired_ic(control: pd.Series, treatment: pd.Series) -> dict[str, Any]:
    common = control.index.intersection(treatment.index)
    diff = (treatment.loc[common] - control.loc[common]).to_numpy()
    hac = exp009a.newey_west_mean_t(diff, DEFINITION["ordering_metrics"]["ic_hac_lags"])
    z = float(norm.ppf(1.0 - DEFINITION["inference"]["family_alpha"] / DEFINITION["inference"]["n_rankers"]))
    rng = np.random.default_rng(DEFINITION["inference"]["seed"])
    block, draws = DEFINITION["inference"]["bootstrap_block"], DEFINITION["inference"]["bootstrap_draws"]
    n = len(diff)
    starts = rng.integers(0, n, size=(draws, math.ceil(n / block)))
    index = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(draws, -1)[:, :n]
    boot = diff[index].mean(axis=1)
    return {
        "dates": int(n), "mean_difference": hac["mean"], "hac_se": hac["hac_se"], "hac_t": hac["hac_t"],
        "one_sided_lower_bound": hac["mean"] - z * hac["hac_se"], "z": z,
        "bootstrap_ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
        "bootstrap_share_at_or_below_zero": float((boot <= 0).mean()),
    }


def portfolio_view(predictions: pd.DataFrame, panel: pd.DataFrame, spec: dict[str, Any],
                   fold_map: dict[Date, int]) -> dict[str, Any]:
    result = exp009a._backtest(predictions, panel, spec, DEFINITION_COSTS["primary"], record_weights=False)
    sweep = []
    for bps in DEFINITION_COSTS["sweep"]:
        m = exp009a._backtest(predictions, panel, spec, bps).metrics
        sweep.append({"half_spread_bps": bps, **{k: m.get(k) for k in (
            "gross_sharpe", "net_sharpe", "net_cagr", "annualised_turnover", "cost_share_of_gross", "net_max_drawdown")}})
    return {
        "metrics_at_10bp": result.metrics, "cost_sweep": sweep,
        "breakeven": breakeven_half_spread(result.periods),
        "fold_metrics": exp009a.fold_table(result.periods, fold_map),
        "_periods": result.periods,
    }


DEFINITION_COSTS = {"primary": 10.0, "sweep": [1.0, 3.0, 5.0, 10.0, 20.0]}


def cell_report(predictions: pd.DataFrame, result: Any, panel: pd.DataFrame,
                fold_map: dict[Date, int]) -> dict[str, Any]:
    ic = _ic_series(predictions)
    per_fold = fold_ic(predictions)
    ordering = per_date_ordering(predictions, k=DEFINITION["ordering_metrics"]["ndcg_k"])
    train_ics = [f.metrics.get("train_mean_ic") for f in result.folds if f.metrics.get("train_mean_ic") is not None]
    dispersion = predictions.groupby("date")["prediction"].std()
    return {
        "rank_ic": ic_summary(ic, horizon_sessions=21, step_sessions=5),
        "fold_ic": {"values": per_fold, "worst": float(min(per_fold)), "positive_folds": int(sum(v > 0 for v in per_fold)),
                    "sd": float(np.std(per_fold, ddof=1))},
        "ordering": {c: float(ordering[c].mean()) for c in
                     ("ndcg_long", "ndcg_short", "top_realised_rank", "bottom_realised_rank", "realised_rank_spread")},
        "stability": stability(predictions),
        "train_mean_ic": float(np.mean(train_ics)) if train_ics else None,
        "train_validation_ic_gap": (float(np.mean(train_ics)) - float(ic.mean())) if train_ics else None,
        "prediction_dispersion": {"mean_cross_sectional_sd": float(dispersion.mean()),
                                  "note": "native units; not comparable across objectives"},
        "fit_seconds_per_fold": [round(f.fit_seconds, 1) for f in result.folds],
        "portfolios": {
            "A_immediate": portfolio_view(predictions, panel, {"rule": "baseline"}, fold_map),
            "C_topk_dropout_10": portfolio_view(predictions, panel, _C, fold_map),
        },
        "_ic_series": ic,
    }


def classify_ranker(control: dict[str, Any], ranker: dict[str, Any], paired: dict[str, Any],
                    econ: dict[str, Any]) -> dict[str, Any]:
    """Apply the preregistered criteria. Pure function of the numbers passed in."""
    o1 = bool(paired["mean_difference"] > 0 and paired["one_sided_lower_bound"] > 0)
    folds_up = sum(1 for a, b in zip(ranker["fold_ic"]["values"], control["fold_ic"]["values"]) if a > b)
    worst_ok = ranker["fold_ic"]["worst"] >= control["fold_ic"]["worst"] - 0.005
    o2 = bool(folds_up >= 6 and worst_ok)
    s, c = ranker["stability"], control["stability"]
    o3 = bool(
        s["mean_rank_correlation_between_consecutive_dates"] >= c["mean_rank_correlation_between_consecutive_dates"] - 0.02
        and s["top_group_retention"] >= c["top_group_retention"] - 0.02
        and s["bottom_group_retention"] >= c["bottom_group_retention"] - 0.02
    )
    e1 = bool(econ["turnover_ratio"] <= 1.10 and econ["net_sharpe_lower_bound"] > 0)
    if o1 and o2 and o3 and e1:
        label = "ORDERING_AND_NET_IMPROVED"
    elif o1 and o2 and o3:
        label = "ORDERING_IMPROVED_NOT_ECONOMIC"
    elif o1:
        label = "ORDERING_IMPROVED_UNSTABLE"
    else:
        label = "NO_ORDERING_GAIN"
    return {"O1_ordering": o1, "O2_consistency": o2, "O2_folds_improved": folds_up, "O2_worst_fold_ok": bool(worst_ok),
            "O3_stability": o3, "E1_economics": e1, "classification": label, "promotion": "NOT ASSESSED"}


def reproduce_frozen(root: Path, refit: pd.DataFrame) -> dict[str, Any]:
    """The validity gate: the sklearn refit must equal EXP-006's frozen predictions."""
    frozen = pd.read_parquet(Path(root) / exp009a.FROZEN_PREDICTIONS)
    frozen = frozen[frozen["model"] == "gradient_boosting"].copy()
    frozen["date"] = pd.to_datetime(frozen["date"]).dt.date
    joined = refit.merge(frozen[["date", "symbol", "prediction"]], on=["date", "symbol"], suffixes=("", "_frozen"))
    gap = float((joined["prediction"] - joined["prediction_frozen"]).abs().max()) if len(joined) else float("inf")
    return {
        "rows_refit": int(len(refit)), "rows_frozen": int(len(frozen)), "rows_joined": int(len(joined)),
        "max_abs_prediction_difference": gap,
        "passed": bool(len(joined) == len(frozen) == len(refit) and gap <= 1e-9),
    }


def _write(directory: Path, name: str, payload: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _strip(obj: Any) -> Any:
    """Drop private (underscore) entries — frames and series — before serialising."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 4) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    gate = prereg_gate(root)                                   # mandatory, before anything is read

    start, end = arm_firewall(root)
    frame, build = load_frame(root)
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID, "parent": PARENT_EXPERIMENT, "status": DEFINITION["status"], **gate,
        **exp009a._git_state(root),
        "dataset": {"dataset_version": build["dataset_version"], "content_hash": build["content_hash"],
                    "rows": build["rows"], "features_in_dataset": len(build["features"]),
                    "end": build["end"]},
        "feature_list_sha256": prereg.sha256_bytes("\n".join(FEATURES).encode()),
        "features_used": FEATURES, "seed": DEFINITION["shared_hyperparameters"]["seed"],
        "dependency_versions": dependency_versions(),
        "holdout": {"start": str(start), "end": str(end), "touched": False, "firewall": FIREWALL.status()},
    }

    checks = {
        "dataset_id": build["dataset_version"] == DEFINITION["data"]["dataset_id"],
        "returns_panel_hash": exp009a.panel_content_hash(panel) == DEFINITION["data"]["returns_panel_sha256"],
        "features_present": all(f in frame.columns for f in FEATURES),
    }
    manifest["validity_checks"] = checks
    if not all(checks.values()):
        manifest["decision"] = f"INVALID - {checks}"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    plan = recorded_plan(root)
    results, failures, timing = evaluate_specs(
        specs(), frame, plan, features=FEATURES, label=LABEL, step_sessions=5, workers=workers)
    by_id = {r.model_id: r for r in results}
    manifest["timing"] = timing
    if failures or set(by_id) != {c["id"] for c in DEFINITION["cells"]}:
        manifest["decision"] = f"INVALID - a model failed: {failures}"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    refit = by_id["R0_sklearn_gb"].predictions
    manifest["baseline_reproduction"] = reproduce_frozen(root, refit)
    if not manifest["baseline_reproduction"]["passed"]:
        manifest["decision"] = "INVALID - the sklearn refit does not reproduce EXP-006's frozen predictions"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    fold_map = exp009a.fold_of_dates(refit)
    reports = {cid: cell_report(r.predictions, r, panel, fold_map) for cid, r in by_id.items()}
    control = reports["R1_boosted_l2"]

    comparisons: dict[str, Any] = {}
    for cid in ("R2_boosted_lambdamart", "R3_boosted_pairwise"):
        r = reports[cid]
        paired = paired_ic(control["_ic_series"], r["_ic_series"])
        level = 1.0 - DEFINITION["inference"]["family_alpha"] / DEFINITION["inference"]["n_rankers"]
        net_c, net_r = (rep["portfolios"]["C_topk_dropout_10"]["_periods"].set_index("date")["net_return"]
                        for rep in (control, r))
        common = net_c.index.intersection(net_r.index)
        boot = exp009a.paired_block_bootstrap_sharpe_diff(
            net_r.loc[common].to_numpy(), net_c.loc[common].to_numpy(),
            block=DEFINITION["inference"]["bootstrap_block"], draws=DEFINITION["inference"]["bootstrap_draws"],
            seed=DEFINITION["inference"]["seed"], periods_per_year=PERIODS_PER_YEAR, one_sided_level=level)
        boot_a = None
        econ = {
            "turnover_ratio": r["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"]
            / control["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"],
            "net_sharpe_lower_bound": boot["one_sided_lower_bound"], "net_sharpe_bootstrap": boot,
        }
        net_ca, net_ra = (rep["portfolios"]["A_immediate"]["_periods"].set_index("date")["net_return"]
                          for rep in (control, r))
        common_a = net_ca.index.intersection(net_ra.index)
        boot_a = exp009a.paired_block_bootstrap_sharpe_diff(
            net_ra.loc[common_a].to_numpy(), net_ca.loc[common_a].to_numpy(),
            block=DEFINITION["inference"]["bootstrap_block"], draws=DEFINITION["inference"]["bootstrap_draws"],
            seed=DEFINITION["inference"]["seed"], periods_per_year=PERIODS_PER_YEAR, one_sided_level=level)
        comparisons[cid] = {
            "paired_ic": paired, "economics_under_topk_dropout": econ,
            "net_sharpe_difference_under_immediate_replacement": boot_a,
            "ordering_difference": {k: r["ordering"][k] - control["ordering"][k] for k in control["ordering"]},
            "stability_difference": {k: r["stability"][k] - control["stability"][k]
                                     for k in control["stability"] if k != "dates_compared"},
            "criteria": classify_ranker(control, r, paired, econ),
        }

    confirmed = {cid: c["paired_ic"]["mean_difference"] for cid, c in comparisons.items()
                 if c["criteria"]["classification"] == "ORDERING_AND_NET_IMPROVED"}
    carried = max(confirmed, key=confirmed.get) if confirmed else "R0_sklearn_gb"
    decision = {
        "confirmed_rankers": sorted(confirmed), "base_model_for_exp_009c": carried,
        "summary": (f"{carried} is the BASE for EXP-009C" if confirmed else
                    "no ranker met all criteria; BASE for EXP-009C is the sklearn point-regression baseline"),
        "promotion": "NOT ASSESSED",
    }

    trial_sharpes = [
        rep["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["net_sharpe"] / math.sqrt(PERIODS_PER_YEAR)
        for cid, rep in reports.items() if cid != "R0_sklearn_gb"
    ]
    for cid, rep in reports.items():
        net = rep["portfolios"]["C_topk_dropout_10"]["_periods"]["net_return"].to_numpy()
        rep["deflated_sharpe_topk_dropout"] = deflated_sharpe_ratio(
            net, trials=DEFINITION["trials"]["cumulative_evaluations"], periods_per_year=PERIODS_PER_YEAR,
            trial_sharpes=trial_sharpes).as_dict()

    manifest.update({
        "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "workers": workers,
                    "cpu_count": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
                    "gpu": None, "trials_counted_for_deflation": DEFINITION["trials"]["cumulative_evaluations"]},
        "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "decision": decision,
    })

    output.mkdir(parents=True, exist_ok=True)
    _write(output, "definition.json", DEFINITION)
    for cid, res in by_id.items():
        FIREWALL.assert_clear(res.predictions, context=f"EXP-009B {cid} predictions")
        res.predictions.to_parquet(output / f"predictions_{cid}.parquet", compression="zstd")
        for name, view in reports[cid]["portfolios"].items():
            view["_periods"].to_parquet(output / f"periods_{cid}_{name}.parquet", compression="zstd")
    _write(output, "metrics.json", {"definition": DEFINITION, "cells": _strip(reports),
                                    "comparisons": _strip(comparisons), "decision": decision})
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*"))
                                 if p.name != "manifest.json"}
    _write(output, "manifest.json", manifest)
    return {"manifest": manifest, "comparisons": comparisons, "decision": decision}
