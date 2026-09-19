"""
EXP-009C — does point-in-time analyst-revision information add anything to the base features?

## One arm, isolated

    BASE  = the 27 frozen `C_base` features
    ARM   = BASE + eight point-in-time analyst features (`analyst_pit.FEATURE_NAMES`, each
            cross-sectionally ranked within the universe on its date)

The model, hyper-parameters, seed, folds, imputation, target and portfolio logic are
identical in both arms. Only the feature set differs. No other feature family, no second
model, no second target: an isolated, attributable question with a *low prior* (the
repository's own EXP-005 ablation was negative; the one 2026 paper that finds predictive
value in analyst revisions needs analyst identity that this data does not have).

## The data gate comes first

`docs/ANALYST_DATA_FORENSICS.md` found the vintage table usable but with hazards the
earlier construction did not handle. Before any model is trained the run must show, on the
**real** table and the **real** panel, that

  1. features built from vintages truncated at a cutoff equal the same features built from
     the full table, for every row dated at or before the cutoff;
  2. rewriting every vintage dated after the cutoff (to absurd values) changes no feature of
     a panel row dated at or before it;
  3. no feature is attached from a vintage dated on or after its own row.

If any fails the outcome is `BLOCKED_DATA_QUALITY` and nothing is trained.

## Which folds can speak

The analyst tables begin 2017-10-26; EXP-006's training windows begin 2014-04-01. A fold whose
training window holds little analyst history cannot learn a relationship from it, so its
result is uninformative rather than negative. A fold is **evaluable** only if its training
window contains at least 24 months of analyst-feature history. That is a function of the
recorded plan (folds 3-7 here), fixed before any result. Folds that are not evaluable are
reported descriptively and never enter a criterion.

Nothing here promotes a model; results are EXPERIMENTAL / PROMOTION NOT ASSESSED; the sealed
holdout is never read.
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
from src.quant.features import analyst_pit
from src.quant.features import cross_section as xs
from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study import exp009a, exp009b, prereg
from src.quant.study.firewall import FIREWALL
from src.quant.validation.metrics import ic_summary, per_date_ic
from src.quant.validation.parallel import evaluate_specs
from src.quant.validation.significance import deflated_sharpe_ratio

EXPERIMENT_ID = "EXP-009C"
PARENT_EXPERIMENT = "EXP-006"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_009C_ANALYST_PREREGISTRATION.md")
PERIODS_PER_YEAR = exp009b.PERIODS_PER_YEAR
LABEL = exp009b.LABEL
ANALYST_STARTS = Date(2017, 10, 26)
MIN_ANALYST_MONTHS = 24
GATE_CUTOFF = Date(2022, 12, 31)

ANALYST_XS = [f"{name}_xs" for name in analyst_pit.FEATURE_NAMES]

# Chosen by the EXP-009B preregistered carry-forward rule, then frozen by the fingerprint.
BASE_MODEL: dict[str, Any] = {
    "name": "sklearn_gb", "kind": "gradient_boosting", "params": (),
    "source": "EXP-009B carry-forward rule: no ranker met all criteria, so BASE is the sklearn "
              "GradientBoostingRegressor (EXP-006's frozen point-regression baseline), repository defaults, seed 0",
    "reference_cell": None,     # None: BASE must equal EXP-006's frozen gradient_boosting predictions to 1e-9
}

_C = exp009b._C

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - PROMOTION NOT ASSESSED",
    "data": {
        "dataset_id": exp009b.DEFINITION["data"]["dataset_id"],
        "returns_panel_sha256": exp009b.DEFINITION["data"]["returns_panel_sha256"],
        "target": LABEL,
        "base_features": exp009b.FEATURES,
        "analyst_features_raw": list(analyst_pit.FEATURE_NAMES),
        "analyst_features_used": ANALYST_XS,
        "analyst_construction": "src/quant/features/analyst_pit.py: calendar lookbacks, strictly-earlier attach, "
                                "dispersion NULL below two analysts, 45-day staleness, then within-universe rank on each date",
        "folds": "the 8 folds recorded in experiments/EXP-006/metrics.json",
    },
    "base_model": BASE_MODEL,
    "arms": [
        {"id": "BASE", "features": "27 C_base features"},
        {"id": "ARM", "features": "27 C_base features + 8 analyst_*_xs"},
    ],
    "evaluable_folds": {
        "rule": f"training window contains at least {MIN_ANALYST_MONTHS} months of analyst history "
                f"(analyst tables start {ANALYST_STARTS})",
        "expected": [3, 4, 5, 6, 7],
        "others": "reported descriptively; never enter a criterion",
    },
    "portfolio": {"immediate_replacement": {"rule": "baseline"}, "frozen_turnover_mechanism": _C},
    "gates": {
        "dataset_and_panel": "rebuilt dataset id and returns-panel hash equal the preregistered values",
        "base_reproduces": "the BASE arm equals the reference predictions of the model it uses to 1e-9",
        "analyst_pit": [
            f"truncation invariance at {GATE_CUTOFF}: features from vintages <= cutoff equal the full-table features on every row <= cutoff",
            f"future-perturbation at {GATE_CUTOFF}: rewriting all later vintages changes no earlier feature",
            "strict attach: no feature is drawn from a vintage dated on or after its row",
        ],
        "on_failure": "BLOCKED_DATA_QUALITY: nothing is trained, no metric is computed",
    },
    "criteria": {
        "O1_ordering": "over evaluable folds, paired per-date Rank-IC difference (ARM - BASE) > 0 with one-sided HAC lower bound "
                       "(Bartlett, 4 lags, z = 1.645) > 0",
        "O2_consistency": "IC difference > 0 in at least 4 of the 5 evaluable folds AND worst evaluable-fold IC >= BASE's - 0.005",
        "E1_economics": "under top-k dropout: annualised turnover <= 1.10 x BASE's AND the paired block-bootstrap (block 8, 10000 draws, seed 0) "
                        "one-sided lower bound of the net-Sharpe difference at 10 bp, level 0.95, is > 0",
        "classification": {
            "ANALYST_VALUE_CONFIRMED": "O1 and O2 and E1",
            "ANALYST_ORDERING_ONLY": "O1 and O2 and not E1",
            "ANALYST_NO_RELIABLE_VALUE": "otherwise",
            "BLOCKED_DATA_QUALITY": "any analyst_pit gate fails",
        },
        "descriptive_only": [
            "non-evaluable folds", "feature-importance share of the analyst block", "stability metrics",
            "immediate-replacement portfolio", "deflated Sharpe", "factor alpha",
        ],
        "promotion": "NOT ASSESSED",
    },
    "inference": {"one_sided_alpha": 0.05, "hac_lags": 4, "bootstrap_block": 8, "bootstrap_draws": 10000, "seed": 0},
    "trials": {"declared": 1, "note": "one added-feature arm; BASE is a control", "prior_cumulative_evaluations": 163,
               "cumulative_evaluations": 164},
    "holdout": {"read": False},
}

METHOD_SOURCES = (
    "src/quant/features/analyst_pit.py",
    "src/quant/features/cross_section.py",
    "src/quant/backtest/rules.py",
    "src/quant/backtest/engine.py",
    "src/quant/backtest/ordering.py",
    "src/quant/models/ranking.py",
    "src/quant/validation/runner.py",
    "src/quant/study/exp009b.py",
    "src/quant/study/exp009c.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


# ── analyst features on the real panel ──────────────────────────────────────

def _estimates(root: Path, *, until: Date) -> tuple[pd.DataFrame, pd.DataFrame]:
    from src.quant.datasets.store import RawStore

    store = RawStore(str(Path(root) / "data/research"))
    tables = []
    for dataset in ("dolthub_earnings_eps_estimate", "dolthub_earnings_sales_estimate"):
        frame = store.read(dataset)
        frame["date"] = pd.to_datetime(frame["date"])
        tables.append(frame[frame["date"] <= pd.Timestamp(until)])
    return tables[0], tables[1]


def analyst_columns(frame: pd.DataFrame, eps: pd.DataFrame, sales: pd.DataFrame,
                    universe_for: dict) -> pd.DataFrame:
    """The eight analyst columns, attached strictly-before and ranked within the universe."""
    features = analyst_pit.build_analyst_features(eps, sales)
    panel = frame[["date", "symbol", "in_universe"]].copy()
    attached = analyst_pit.attach_analyst_features(panel, features)
    ranked = xs.cross_sectional_frame(
        attached, list(analyst_pit.FEATURE_NAMES), universe_for=universe_for, method="rank")
    return ranked[ANALYST_XS]


def pit_gates(frame: pd.DataFrame, root: Path, universe_for: dict) -> dict[str, Any]:
    """Truncation invariance, future perturbation and strict attach on the REAL data."""
    end = Date.fromisoformat(exp009b.DEFINITION["data"]["dataset_end"])
    eps_all, sales_all = _estimates(root, until=end)
    cutoff = pd.Timestamp(GATE_CUTOFF)
    panel = frame[["date", "symbol"]].copy()
    early = pd.to_datetime(panel["date"]) <= cutoff

    full = analyst_pit.build_analyst_features(eps_all, sales_all)

    # 1. truncation invariance: vintages after the cutoff cannot alter any earlier feature row.
    cut = analyst_pit.build_analyst_features(
        eps_all[eps_all["date"] <= cutoff], sales_all[sales_all["date"] <= cutoff])
    truncation_ok = _identical(full[full["available_from"] <= cutoff].reset_index(drop=True),
                               cut.reset_index(drop=True))

    # 2. future perturbation: rewrite every later vintage; no earlier panel feature may move.
    def rewritten(table: pd.DataFrame) -> pd.DataFrame:
        out = table.copy()
        late = out["date"] > cutoff
        for column in ("consensus", "high", "low", "count", "year_ago"):
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce").astype(float)
                out.loc[late, column] = 1234.5
        return out

    features_pert = analyst_pit.build_analyst_features(rewritten(eps_all), rewritten(sales_all))
    a = analyst_pit.attach_analyst_features(panel[early], full)
    b = analyst_pit.attach_analyst_features(panel[early], features_pert)
    perturbation_ok = _frames_equal(a[list(analyst_pit.FEATURE_NAMES)], b[list(analyst_pit.FEATURE_NAMES)])

    # 3. strict attach: carry each vintage's own date through the attach step as a "feature".
    sample = panel.sample(n=min(50_000, len(panel)), random_state=0)
    probe = full.assign(analyst_eps_coverage=full["available_from"].astype("int64") / 1e9)
    attached = analyst_pit.attach_analyst_features(sample, probe)
    row_seconds = pd.to_datetime(sample["date"]).astype("int64") / 1e9
    seen = attached["analyst_eps_coverage"]
    present = seen.notna()
    strict_ok = bool((seen[present] < row_seconds[present]).all()) and int(present.sum()) > 0

    return {
        "truncation_invariance": truncation_ok,
        "future_perturbation": perturbation_ok,
        "strict_attach": strict_ok,
        "passed": bool(truncation_ok and perturbation_ok and strict_ok),
        "cutoff": str(GATE_CUTOFF),
        "rows_checked_early": int(early.sum()),
        "attached_rows_checked_for_strictness": int(present.sum()),
    }


def _identical(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(a, b, check_exact=True)
        return True
    except AssertionError:
        return False


def _frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a.shape != b.shape:
        return False
    return bool(np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True, rtol=0, atol=0))


# ── which folds can speak ────────────────────────────────────────────────────

def evaluable_folds(plan: Any) -> list[int]:
    out = []
    for fold in plan.folds:
        months = (fold.train_end.year - ANALYST_STARTS.year) * 12 + (fold.train_end.month - ANALYST_STARTS.month)
        if months >= MIN_ANALYST_MONTHS:
            out.append(fold.index)
    return out


# ── criteria ─────────────────────────────────────────────────────────────────

def classify(paired: dict[str, Any], folds_improved: int, n_evaluable: int, worst_ok: bool,
             econ: dict[str, Any], gates_passed: bool) -> dict[str, Any]:
    if not gates_passed:
        return {"classification": "BLOCKED_DATA_QUALITY", "promotion": "NOT ASSESSED"}
    o1 = bool(paired["mean_difference"] > 0 and paired["one_sided_lower_bound"] > 0)
    required = 4 if n_evaluable == 5 else math.ceil(0.8 * n_evaluable)
    o2 = bool(folds_improved >= required and worst_ok)
    e1 = bool(econ["turnover_ratio"] <= 1.10 and econ["net_sharpe_lower_bound"] > 0)
    if o1 and o2 and e1:
        label = "ANALYST_VALUE_CONFIRMED"
    elif o1 and o2:
        label = "ANALYST_ORDERING_ONLY"
    else:
        label = "ANALYST_NO_RELIABLE_VALUE"
    return {"O1_ordering": o1, "O2_consistency": o2, "E1_economics": e1, "classification": label,
            "promotion": "NOT ASSESSED"}


def _restrict(predictions: pd.DataFrame, folds: list[int]) -> pd.DataFrame:
    return predictions[predictions["fold"].isin(folds)]


def paired_ic_one_sided(base: pd.Series, arm: pd.Series) -> dict[str, Any]:
    common = base.index.intersection(arm.index)
    diff = (arm.loc[common] - base.loc[common]).to_numpy()
    hac = exp009a.newey_west_mean_t(diff, DEFINITION["inference"]["hac_lags"])
    z = float(norm.ppf(1.0 - DEFINITION["inference"]["one_sided_alpha"]))
    rng = np.random.default_rng(DEFINITION["inference"]["seed"])
    block, draws = DEFINITION["inference"]["bootstrap_block"], DEFINITION["inference"]["bootstrap_draws"]
    n = len(diff)
    starts = rng.integers(0, n, size=(draws, math.ceil(n / block)))
    index = ((starts[:, :, None] + np.arange(block)[None, None, :]) % n).reshape(draws, -1)[:, :n]
    boot = diff[index].mean(axis=1)
    return {"dates": int(n), "mean_difference": hac["mean"], "hac_se": hac["hac_se"], "hac_t": hac["hac_t"],
            "one_sided_lower_bound": hac["mean"] - z * hac["hac_se"], "z": z,
            "bootstrap_ci95": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
            "bootstrap_share_at_or_below_zero": float((boot <= 0).mean())}


def _write(directory: Path, name: str, payload: Any) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 2) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or (root / OUTPUT_DIR)
    gate = prereg_gate(root)

    start, end = exp009b.arm_firewall(root)
    frame, build = exp009b.load_frame(root)
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    manifest: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID, "parent": PARENT_EXPERIMENT, "status": DEFINITION["status"], **gate,
        **exp009a._git_state(root),
        "dataset": {"dataset_version": build["dataset_version"], "content_hash": build["content_hash"],
                    "rows": build["rows"], "end": build["end"]},
        "seed": exp009b.DEFINITION["shared_hyperparameters"]["seed"],
        "dependency_versions": dependency_versions(),
        "holdout": {"start": str(start), "end": str(end), "touched": False, "firewall": FIREWALL.status()},
    }
    checks = {
        "dataset_id": build["dataset_version"] == DEFINITION["data"]["dataset_id"],
        "returns_panel_hash": exp009a.panel_content_hash(panel) == DEFINITION["data"]["returns_panel_sha256"],
    }
    manifest["validity_checks"] = checks
    if not all(checks.values()):
        manifest["decision"] = f"INVALID - {checks}"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    from src.quant.pit.universe import UniverseHistory

    universe = UniverseHistory.load(Path(root) / "data/research" / "universe")
    dates = sorted(frame["date"].unique())
    universe_for = xs.universe_map(universe, dates)

    gates = pit_gates(frame, root, universe_for)
    manifest["analyst_pit_gates"] = gates
    if not gates["passed"]:
        manifest["decision"] = {"classification": "BLOCKED_DATA_QUALITY", "promotion": "NOT ASSESSED",
                                "gates": gates}
        _write(output, "manifest.json", manifest)
        return {"manifest": manifest, "decision": manifest["decision"]}

    eps, sales = _estimates(root, until=Date.fromisoformat(exp009b.DEFINITION["data"]["dataset_end"]))
    columns = analyst_columns(frame, eps, sales, universe_for)
    frame = frame.copy()
    for name in ANALYST_XS:
        frame[name] = columns[name].to_numpy()
    coverage = frame[frame["in_universe"]].assign(year=lambda f: pd.to_datetime(f["date"]).dt.year).groupby("year")[
        ANALYST_XS].apply(lambda g: g.notna().mean()).round(4)
    manifest["analyst_feature_coverage_by_year"] = coverage.to_dict(orient="index")

    plan = exp009b.recorded_plan(root)
    evaluable = evaluable_folds(plan)
    manifest["evaluable_folds"] = evaluable
    if evaluable != DEFINITION["evaluable_folds"]["expected"]:
        manifest["decision"] = f"INVALID - evaluable folds {evaluable} differ from the preregistered set"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    base = ModelSpec(BASE_MODEL["name"] + "_BASE", BASE_MODEL["kind"], tuple(BASE_MODEL["params"]),
                     exp009b.DEFINITION["shared_hyperparameters"]["seed"])
    arm = ModelSpec(BASE_MODEL["name"] + "_ARM", BASE_MODEL["kind"], tuple(BASE_MODEL["params"]),
                    exp009b.DEFINITION["shared_hyperparameters"]["seed"])

    results = {}
    for label, spec, features in (("BASE", base, exp009b.FEATURES), ("ARM", arm, exp009b.FEATURES + ANALYST_XS)):
        res, failures, timing = evaluate_specs(
            [spec], frame, plan, features=features, label=LABEL, step_sessions=5, workers=1)
        if failures or not res:
            manifest["decision"] = f"INVALID - {label} failed: {failures}"
            _write(output, "manifest.json", manifest)
            raise RuntimeError(manifest["decision"])
        results[label] = res[0]
    manifest["base_model"] = BASE_MODEL

    reference = _reference_predictions(root)
    joined = results["BASE"].predictions.merge(
        reference, on=["date", "symbol"], suffixes=("", "_reference"))
    gap = float((joined["prediction"] - joined["prediction_reference"]).abs().max()) if len(joined) else float("inf")
    manifest["base_reproduction"] = {"rows_joined": int(len(joined)), "max_abs_prediction_difference": gap,
                                     "passed": bool(len(joined) == len(results["BASE"].predictions) and gap <= 1e-9)}
    if not manifest["base_reproduction"]["passed"]:
        manifest["decision"] = "INVALID - the BASE arm does not reproduce its reference predictions"
        _write(output, "manifest.json", manifest)
        raise RuntimeError(manifest["decision"])

    fold_map = exp009a.fold_of_dates(results["BASE"].predictions)
    cells: dict[str, Any] = {}
    for label, res in results.items():
        pred = res.predictions
        ev = _restrict(pred, evaluable)
        cells[label] = {
            "rank_ic_all_folds": ic_summary(exp009b._ic_series(pred), horizon_sessions=21, step_sessions=5),
            "rank_ic_evaluable_folds": ic_summary(exp009b._ic_series(ev), horizon_sessions=21, step_sessions=5),
            "fold_ic": {int(k): float(exp009b._ic_series(g).mean()) for k, g in pred.groupby("fold")},
            "ordering_evaluable": {c: float(per_date_ordering(ev, k=50)[c].mean()) for c in
                                   ("ndcg_long", "ndcg_short", "realised_rank_spread")},
            "stability_evaluable": stability(ev),
            "explanation_top": res.explanation.get("top", [])[:12] if isinstance(res.explanation, dict) else None,
            "portfolios": {
                "A_immediate": exp009b.portfolio_view(pred, panel, {"rule": "baseline"}, fold_map),
                "C_topk_dropout_10": exp009b.portfolio_view(pred, panel, _C, fold_map),
            },
        }
    analyst_share = None
    exp = results["ARM"].explanation
    if isinstance(exp, dict) and "values" in exp:
        analyst_share = float(sum(v for k, v in exp["values"].items() if k in ANALYST_XS))

    base_ic = exp009b._ic_series(_restrict(results["BASE"].predictions, evaluable))
    arm_ic = exp009b._ic_series(_restrict(results["ARM"].predictions, evaluable))
    paired = paired_ic_one_sided(base_ic, arm_ic)
    folds_up = sum(1 for k in evaluable if cells["ARM"]["fold_ic"][k] > cells["BASE"]["fold_ic"][k])
    worst_ok = min(cells["ARM"]["fold_ic"][k] for k in evaluable) >= min(cells["BASE"]["fold_ic"][k] for k in evaluable) - 0.005

    def net(view: str, label: str, keep: list[int]) -> pd.Series:
        p = cells[label]["portfolios"][view]["_periods"].copy()
        p["fold"] = [fold_map.get(d) for d in p["date"]]
        return p[p["fold"].isin(keep)].set_index("date")["net_return"]

    net_b, net_a = net("C_topk_dropout_10", "BASE", evaluable), net("C_topk_dropout_10", "ARM", evaluable)
    common = net_b.index.intersection(net_a.index)
    boot = exp009a.paired_block_bootstrap_sharpe_diff(
        net_a.loc[common].to_numpy(), net_b.loc[common].to_numpy(),
        block=DEFINITION["inference"]["bootstrap_block"], draws=DEFINITION["inference"]["bootstrap_draws"],
        seed=DEFINITION["inference"]["seed"], periods_per_year=PERIODS_PER_YEAR,
        one_sided_level=1.0 - DEFINITION["inference"]["one_sided_alpha"])
    econ = {"turnover_ratio": cells["ARM"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"]
            / cells["BASE"]["portfolios"]["C_topk_dropout_10"]["metrics_at_10bp"]["annualised_turnover"],
            "net_sharpe_lower_bound": boot["one_sided_lower_bound"], "net_sharpe_bootstrap": boot,
            "evaluable_folds_only": True}
    criteria = classify(paired, folds_up, len(evaluable), bool(worst_ok), econ, gates["passed"])
    criteria.update({"O2_folds_improved": folds_up, "O2_evaluable_folds": len(evaluable)})

    decision = {"classification": criteria["classification"], "promotion": "NOT ASSESSED",
                "analyst_block_importance_share": analyst_share}
    manifest.update({
        "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "workers": workers,
                    "cpu_count": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
                    "trials_counted_for_deflation": DEFINITION["trials"]["cumulative_evaluations"]},
        "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "decision": decision,
    })
    output.mkdir(parents=True, exist_ok=True)
    _write(output, "definition.json", DEFINITION)
    for label, res in results.items():
        FIREWALL.assert_clear(res.predictions, context=f"EXP-009C {label} predictions")
        res.predictions.to_parquet(output / f"predictions_{label}.parquet", compression="zstd")
        for name, view in cells[label]["portfolios"].items():
            view["_periods"].to_parquet(output / f"periods_{label}_{name}.parquet", compression="zstd")
    _write(output, "metrics.json", {"definition": DEFINITION, "cells": exp009b._strip(cells), "paired_ic": paired,
                                    "economics": econ, "criteria": criteria, "decision": decision})
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*"))
                                 if p.name != "manifest.json"}
    _write(output, "manifest.json", manifest)
    return {"manifest": manifest, "paired_ic": paired, "economics": econ, "criteria": criteria, "decision": decision}


def _reference_predictions(root: Path) -> pd.DataFrame:
    """The predictions BASE must reproduce: EXP-009B's cell, else EXP-006's frozen gradient boosting."""
    path = Path(root) / "experiments/EXP-009B" / f"predictions_{DEFINITION['base_model']['reference_cell']}.parquet" \
        if DEFINITION["base_model"].get("reference_cell") else None
    if path is not None and path.exists():
        ref = pd.read_parquet(path)
    else:
        ref = pd.read_parquet(Path(root) / exp009a.FROZEN_PREDICTIONS)
        ref = ref[ref["model"] == "gradient_boosting"]
    ref = ref[["date", "symbol", "prediction"]].copy()
    ref["date"] = pd.to_datetime(ref["date"]).dt.date
    return ref
