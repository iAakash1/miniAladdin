"""EXP-011 - does richer point-in-time company information improve cross-sectional ranking?

Data value is isolated from model complexity by crossing two feature sets with two model classes:

    E0  baseline 26 features  x Ridge                 E1  rich PIT features  x Ridge
    E2  baseline 26 features  x GradientBoosting      E3  rich PIT features  x GradientBoosting

Target (`fwd_rank_21`), folds (the eight recorded EXP-006 folds), boosting hyper-parameters, imputation
(fold-local), downstream portfolio (the frozen EXP-010B 21-session implementation, 10% dropout, the
1/3/5/10/20 bp cost grid) and the ten seeds are all fixed.  E2 *is* EXP-010A: its ten frozen, hash-verified
prediction files are reused, not refit.  Nothing here selects a best seed, tunes a hyper-parameter, or
touches the sealed holdout.
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import json
import multiprocessing
import os
import platform
import sys
import time
from datetime import date as Date
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.pit import rich_panel as R
from src.quant.study import exp009a, exp009b, exp010a, exp010b, prereg
from src.quant.study.firewall import FIREWALL, HoldoutBreach
from src.quant.validation.metrics import ic_summary, per_date_ic
from src.quant.validation.runner import ExperimentResult, run_walk_forward

EXPERIMENT_ID = "EXP-011"
PARENT_EXPERIMENT = "EXP-010B"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_011_PREREGISTRATION.md")
RICH_PANEL = Path("data/research/derived/rich_pit_panel.parquet")
RICH_MANIFEST = Path("data/manifests/rich_pit_panel_manifest.json")
LABEL = exp009b.LABEL
SEEDS = exp010a.SEEDS
RIDGE_PARAMS = {"alpha": 10.0}
GBR_PARAMS = dict(exp010a.HYPERPARAMETERS)
NOISE = exp010b.NOISE_FLOOR
IC_SPAN = NOISE["mean_rank_ic"]["p95_minus_p05"]        # 0.004156: EXP-010A reseed range of Rank IC
IC_SD = NOISE["mean_rank_ic"]["sample_std"]
SHARPE_SD = NOISE["net_sharpe_10bp"]["sample_std"]
ECONOMICS_ARM = "B1"                                    # the frozen EXP-010B 21-session implementation

ARMS: dict[str, dict[str, Any]] = {
    "E0": {"model": "ridge", "features": "baseline", "seeds": (0,), "params": RIDGE_PARAMS, "fit": True},
    "E1": {"model": "ridge", "features": "rich", "seeds": (0,), "params": RIDGE_PARAMS, "fit": True},
    "E2": {"model": "gradient_boosting", "features": "baseline", "seeds": SEEDS, "params": GBR_PARAMS, "fit": False},
    "E3": {"model": "gradient_boosting", "features": "rich", "seeds": SEEDS, "params": GBR_PARAMS, "fit": True},
}
FIT_ORDER = ("E0", "E1", "E3")

# Pinned from the built rich panel (data/manifests/rich_pit_panel_manifest.json).
RICH_DATASET_ID = "ds-richpit-ff3d3f556488b7da"
RICH_CONTENT_HASH = "ff3d3f556488b7daa20bbbeab49d1f0abad9a869976b593f211cf92b6eb7c5da"
RICH_FEATURE_HASH = "7212297bc55a45f66ffceb3548000e899773e1959e365b266fb477f24d8b8614"
BASELINE_VALUES_HASH = "f48c47f02da6407e060ca52ff1745935a99c0898fa5a7ce3fa6df3c5d7d5906e"
RICH_ROWS = 139292
RICH_FEATURE_COUNT = 76
RICH_FEATURES: tuple[str, ...] = (
    "gross_profitability_xs",
    "roa_xs",
    "roe_xs",
    "operating_profitability_xs",
    "cash_profitability_xs",
    "gross_margin_xs",
    "operating_margin_xs",
    "net_margin_xs",
    "cash_flow_margin_xs",
    "ebitda_margin_xs",
    "asset_turnover_xs",
    "asset_growth_xs",
    "capex_to_assets_xs",
    "capex_to_revenue_xs",
    "capex_growth_xs",
    "inventory_growth_xs",
    "inventory_to_assets_change_xs",
    "working_capital_growth_xs",
    "receivables_growth_xs",
    "accruals_xs",
    "cash_flow_quality_xs",
    "gross_margin_stability_xs",
    "roa_stability_xs",
    "cash_conversion_xs",
    "debt_to_assets_xs",
    "debt_to_equity_xs",
    "net_debt_to_assets_xs",
    "liabilities_to_assets_xs",
    "current_ratio_xs",
    "cash_to_assets_xs",
    "revenue_growth_xs",
    "gross_profit_growth_xs",
    "earnings_growth_xs",
    "operating_income_growth_xs",
    "ocf_growth_xs",
    "fcf_growth_xs",
    "debt_growth_xs",
    "equity_issuance_proxy_xs",
    "seasonal_ni_surprise_xs",
    "filing_lag_days_xs",
    "book_to_market_xs",
    "earnings_yield_xs",
    "sales_yield_xs",
    "fcf_yield_xs",
    "ocf_yield_xs",
    "operating_income_to_ev_xs",
    "gross_profit_to_ev_xs",
    "sales_to_ev_xs",
    "shares_growth_xs",
    "days_since_report_xs",
)

INTERPRETATION = {
    "unit_ic": f"EXP-010A Rank-IC reseed p95-p05 range ({IC_SPAN}); seed SD {IC_SD}",
    "unit_sharpe": f"EXP-010A net-Sharpe seed SD ({SHARPE_SD}); economics are reported, never labelled",
    "pair_status": {
        "IMPROVES": "median paired ΔIC >= IC range AND ΔIC > 0 in >= 9 of 10 seeds (Ridge, one deterministic fit: ΔIC >= IC range AND > 0 in >= 5 of 8 folds)",
        "DEGRADES": "the mirror: median ΔIC <= -IC range AND < 0 in >= 9 of 10 seeds (Ridge: <= -IC range AND < 0 in >= 5 of 8 folds)",
        "NO_DETECTABLE_CHANGE": "otherwise",
    },
    "fold_robust": "seed-median fold ΔIC > 0 in >= 5 of 8 folds AND every leave-one-fold-out median ΔIC > 0",
    "labels": {
        "RICH_DATA_IMPROVES_ORDERING": "boosted pair IMPROVES and is fold-robust, and the linear pair also IMPROVES",
        "IMPROVES_ONLY_WITH_BOOSTING": "boosted pair IMPROVES and is fold-robust, linear pair NO_DETECTABLE_CHANGE",
        "IMPROVES_ONLY_LINEAR": "linear pair IMPROVES, boosted pair not IMPROVES and not DEGRADES",
        "NO_DETECTABLE_ORDERING_GAIN": "neither pair IMPROVES or DEGRADES",
        "RICH_DATA_DEGRADES_ORDERING": "at least one pair DEGRADES and no pair IMPROVES",
        "MIXED": "one pair IMPROVES and the other DEGRADES, or the boosted pair IMPROVES but is not fold-robust",
    },
    "no_threshold_invented_later": True, "promotion": "NOT ASSESSED",
}


def _definition() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID, "parent_experiment": PARENT_EXPERIMENT,
        "status": "EXPERIMENTAL - DATA-VALUE STUDY - PROMOTION NOT ASSESSED",
        "question": ("Does a richer, genuinely point-in-time company information set improve cross-sectional ranking "
                     "beyond the existing 26-feature price/liquidity/macro panel, holding target, folds, models and portfolio fixed?"),
        "arms": {name: {k: (list(v) if isinstance(v, tuple) else v) for k, v in spec.items()} for name, spec in ARMS.items()},
        "design": {
            "crossed_factors": ["feature set (baseline 26 | rich PIT)", "model class (Ridge | GradientBoostingRegressor)"],
            "e2_is_exp010a": "E2 reuses the ten frozen EXP-010A prediction files (hash-verified); it is not refit",
            "no_other_models": "no XGBoost/LightGBM/MLP arm; no model zoo", "target": LABEL, "target_unchanged": True,
            "folds": "the eight recorded EXP-006 folds, unchanged", "seeds": list(SEEDS), "best_seed_selected": False,
            "ridge": {"params": RIDGE_PARAMS, "note": "alpha 10.0 is the pre-existing EXP-006 Ridge configuration; no search",
                      "seeds": "deterministic: one fit per fold"},
            "gradient_boosting": {"params": GBR_PARAMS, "hyperparameter_search": "none"},
            "imputation": "FoldImputer fitted independently on each training fold (standardising for Ridge)",
        },
        "data": {
            "rich_dataset_id": RICH_DATASET_ID, "rich_content_hash": RICH_CONTENT_HASH, "rich_feature_hash": RICH_FEATURE_HASH,
            "baseline_values_hash": BASELINE_VALUES_HASH, "rows": RICH_ROWS, "feature_count": RICH_FEATURE_COUNT,
            "rich_features": list(RICH_FEATURES), "baseline_features": list(R.BASELINE_FEATURES),
            "baseline_dataset": R.BASELINE_DATASET_ID, "end": "2025-05-09",
            "panel_manifest": str(RICH_MANIFEST),
        },
        "portfolio": {
            "implementation": "frozen EXP-010B B1: 21-session calendar cadence, one 5-session-old signal, top-k dropout 10%, long/short quintiles",
            "cost_half_spread_bps": list(exp010b.COSTS), "primary_cost_bps": exp010b.PRIMARY_BPS,
            "cadence_retuned": False, "dropout_changed": False, "costs_changed": False,
        },
        "metrics": {
            "ordering": ["mean Rank IC", "HAC t-stat (4 lags)", "ICIR", "8 fold IC", "positive folds", "worst fold"],
            "economics_b1": ["gross Sharpe", "net Sharpe at 1/3/5/10/20 bp", "annualised turnover", "cost share of gross", "net max drawdown"],
            "diagnostics": ["Rank IC on the covered subset (rows where the new features are present)", "prediction-rank correlation E1-E0 and E3-E2"],
        },
        "paired": {
            "data_value_boosted": "E3 - E2, per seed 0-9", "data_value_linear": "E1 - E0, one deterministic pair",
            "model_value_baseline": "E2(seed) - E0", "model_value_rich": "E3(seed) - E1",
            "interaction": "(E3 - E2)(seed) - (E1 - E0)",
            "statistics": ["mean", "median", "sample_std", "min", "max", "p05", "p95"],
            "against_noise": "every effect is also expressed in EXP-010A seed SDs and p95-p05 ranges, descriptively",
        },
        "noise_context": {"source": "EXP-010A ten-seed noise floor", **NOISE, "use": "descriptive scale; the interpretation rule below is fixed in advance"},
        "interpretation": INTERPRETATION,
        "known_limits": [
            "the rich features exist only for names with an identity link graded A or B; the covered-subset diagnostic and the panel audit report the rest",
            "missingness of fundamentals correlates with delisting; the panel audit measures that association and the models see missing values, not zeros",
            "date-sampling uncertainty is not tested; ten seeds capture model-seed noise only",
            "one Ridge fit per arm; no linear-model seed distribution exists",
        ],
        "outputs": ["definition.json", "config.json", "manifest.json", "metrics.json", "per_arm_metrics.csv", "fold_metrics.csv",
                    "paired_differences.csv", "prediction_hashes.json", "checkpoints/*"],
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
    }


DEFINITION: dict[str, Any] = _definition()

METHOD_SOURCES = (
    "src/quant/validation/runner.py", "src/quant/models/linear.py", "src/quant/models/trees.py", "src/quant/models/base.py",
    "src/quant/pit/rich_panel.py", "src/quant/features/pit_fundamentals.py", "src/quant/pit/pit_coverage.py",
    "src/quant/backtest/engine.py", "src/quant/backtest/rules.py", "src/quant/study/exp009a.py", "src/quant/study/exp009b.py",
    "src/quant/study/exp010a.py", "src/quant/study/exp010b.py", "src/quant/study/exp011.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


# ── data ─────────────────────────────────────────────────────────────────────

def feature_list(kind: str) -> list[str]:
    if kind == "baseline":
        return list(R.BASELINE_FEATURES)
    if kind == "rich":
        return [*R.BASELINE_FEATURES, *RICH_FEATURES]
    raise ValueError(kind)


def baseline_values_hash(panel: pd.DataFrame) -> str:
    cols = ["date", "symbol", *R.BASELINE_FEATURES]
    ordered = panel[cols].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.strftime("%Y-%m-%d")
    ordered = ordered.sort_values(["date", "symbol"], kind="mergesort")
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def load_rich_panel(root: Path = Path("."), path: Optional[Path] = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read the rich panel and refuse it unless every registered identity check passes."""
    root = Path(root)
    exp009b.arm_firewall(root)
    path = Path(path) if path else root / RICH_PANEL
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; rebuild with `python -m scripts.quant.build_pit_data build-rich-panel`")
    panel = pd.read_parquet(path)
    panel["date"] = pd.to_datetime(panel["date"])
    columns = ["date", "symbol", "security_id", "cik", "identity_grade", "ff12", "ff17", "ff48", "sic", *R.PASSTHROUGH, *R.LABELS,
               *feature_list("rich")]
    checks = {
        "rows": len(panel) == DEFINITION["data"]["rows"],
        "feature_hash": R.feature_hash(feature_list("rich")) == RICH_FEATURE_HASH,
        "baseline_values_hash": baseline_values_hash(panel) == BASELINE_VALUES_HASH,
        "content_hash": R.content_hash(panel, [c for c in columns if c in panel.columns]) == RICH_CONTENT_HASH,
        "last_date_before_holdout": panel["date"].max().date() <= Date(2025, 5, 9),
        "features_present": all(c in panel.columns for c in feature_list("rich")),
        "no_label_in_features": not any("fwd" in c for c in feature_list("rich")),
    }
    panel["date"] = panel["date"].dt.date
    FIREWALL.assert_clear(panel, context="EXP-011 rich panel")
    if not all(checks.values()):
        raise RuntimeError(f"EXP-011 INVALID rich panel: {checks}")
    return panel, checks


# ── fitting ──────────────────────────────────────────────────────────────────

_WORKER: dict[str, Any] = {}


def _init_worker(root: str) -> None:
    frame, _ = load_rich_panel(Path(root))
    _WORKER["frame"] = frame
    _WORKER["plan"] = exp009b.recorded_plan(Path(root))


def fit_arm_seed(arm: str, seed: int, frame: pd.DataFrame, plan: Any) -> ExperimentResult:
    spec_arm = ARMS[arm]
    spec = ModelSpec(f"{spec_arm['model']}_{arm}_seed_{seed}", spec_arm["model"], tuple(spec_arm["params"].items()), seed)
    return run_walk_forward(spec.build, frame, plan, features=feature_list(spec_arm["features"]), label=LABEL, step_sessions=5)


def _worker_task(task: tuple[str, int]) -> tuple[str, int, pd.DataFrame, float, list[str]]:
    arm, seed = task
    result = fit_arm_seed(arm, seed, _WORKER["frame"], _WORKER["plan"])
    if result.errors or result.predictions is None or len(result.folds) != 8:
        return arm, seed, pd.DataFrame(), 0.0, list(result.errors) or ["incomplete folds"]
    return arm, seed, result.predictions, float(result.seconds), []


def receipt_for(arm: str, seed: int, predictions: pd.DataFrame, seconds: float, *, fingerprint: str, root: Path,
                device: str = "cpu", commit: Optional[str] = None) -> dict[str, Any]:
    versions = dependency_versions()
    return {
        "experiment_id": EXPERIMENT_ID, "arm": arm, "seed": seed, "definition_fingerprint": fingerprint,
        "rich_dataset_id": RICH_DATASET_ID, "rich_content_hash": RICH_CONTENT_HASH, "rich_feature_hash": RICH_FEATURE_HASH,
        "features": len(feature_list(ARMS[arm]["features"])), "folds": int(predictions["fold"].nunique()),
        "rows": int(len(predictions)), "prediction_sha256": exp010a._prediction_hash(predictions),
        "fit_seconds": seconds, "device": device, "python": platform.python_version(), "platform": platform.platform(),
        "dependency_versions": versions, "cuda": os.environ.get("CUDA_VERSION"),
        "git_commit": commit or exp009a._git_state(root)["git_commit"],
    }


def verify_receipt(receipt: dict[str, Any], predictions: pd.DataFrame, *, arm: str, seed: int, fingerprint: str,
                   strict_versions: bool = True) -> list[str]:
    """Reasons a checkpoint (local or imported from Kaggle) must be rejected; empty means accepted."""
    problems = []
    expected = {"experiment_id": EXPERIMENT_ID, "arm": arm, "seed": seed, "definition_fingerprint": fingerprint,
                "rich_dataset_id": RICH_DATASET_ID, "rich_content_hash": RICH_CONTENT_HASH, "rich_feature_hash": RICH_FEATURE_HASH}
    for key, value in expected.items():
        if receipt.get(key) != value:
            problems.append(f"{key}: {receipt.get(key)!r} != {value!r}")
    if receipt.get("prediction_sha256") != exp010a._prediction_hash(predictions):
        problems.append("prediction hash does not match the prediction file")
    if int(predictions["fold"].nunique()) != 8 or receipt.get("folds") != 8:
        problems.append("not all eight folds are present")
    if not receipt.get("git_commit") or not receipt.get("device") or receipt.get("fit_seconds") is None:
        problems.append("receipt lacks commit, device or runtime")
    if strict_versions:
        parent = json.loads((Path(".") / exp010a.OUTPUT_DIR / "manifest.json").read_text())["dependency_versions"]
        theirs = receipt.get("dependency_versions") or {}
        for package in ("numpy", "pandas", "sklearn"):
            if package in parent and theirs.get(package) != parent[package]:
                problems.append(f"{package} {theirs.get(package)!r} != recorded {parent[package]!r}")
    return problems


# ── reporting ────────────────────────────────────────────────────────────────

def ordering_report(predictions: pd.DataFrame) -> dict[str, Any]:
    dated = per_date_ic(predictions, prediction_column="prediction", target_column=LABEL)
    summary = ic_summary(dated, horizon_sessions=21, step_sessions=5)
    folds = []
    for fold, group in predictions.groupby("fold"):
        series = per_date_ic(group, prediction_column="prediction", target_column=LABEL)
        folds.append(float(series.mean()))
    return {"mean_rank_ic": summary.get("mean_ic"), "hac_t_stat": summary.get("t_stat"), "ic_ir": summary.get("ic_ir"),
            "fold_ic": folds, "positive_fold_count": int(sum(v > 0 for v in folds)), "worst_fold_ic": float(min(folds))}


def covered_subset_ic(predictions: pd.DataFrame, panel: pd.DataFrame, minimum_features: int = 20) -> dict[str, Any]:
    """Rank IC only where the new characteristics exist: a diagnostic against coverage-driven artefacts."""
    new = [f"{n}_xs" for n in R.NEW_FEATURES if f"{n}_xs" in panel.columns]
    present = panel[new].notna().sum(axis=1)
    covered = panel.loc[(present >= minimum_features) & panel["security_id"].notna(), ["date", "symbol"]]
    merged = predictions.merge(covered, on=["date", "symbol"], how="inner")
    if merged.empty:
        return {"mean_rank_ic": None, "rows": 0}
    series = per_date_ic(merged, prediction_column="prediction", target_column=LABEL)
    return {"mean_rank_ic": float(series.mean()), "rows": int(len(merged)), "share_of_rows": float(len(merged) / len(predictions))}


def prediction_rank_correlation(left: pd.DataFrame, right: pd.DataFrame) -> float:
    return exp010a._rank_correlation(left, right)


def paired(rows_left: Sequence[dict[str, Any]], rows_right: Sequence[dict[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    """right - left, element-wise, for the listed scalar keys (lists must be aligned: same length)."""
    out = []
    for left, right in zip(rows_left, rows_right):
        for key in keys:
            a, b = left.get(key), right.get(key)
            if a is None or b is None:
                continue
            out.append({"seed": left.get("seed", 0), "metric": key, "base": float(a), "rich": float(b), "difference": float(b) - float(a)})
    return out


def broadcast(single: dict[str, Any], seeds: Sequence[int]) -> list[dict[str, Any]]:
    return [{**single, "seed": s} for s in seeds]


def pair_status(diffs: Sequence[float], fold_diffs: Optional[Sequence[float]] = None) -> str:
    """The preregistered ordering rule.  `diffs` per seed (boosted) or a single value (Ridge, with fold ΔIC)."""
    values = np.asarray(diffs, dtype=float)
    if len(values) >= 2:
        median, positive, negative = float(np.median(values)), int((values > 0).sum()), int((values < 0).sum())
        if median >= IC_SPAN and positive >= 9:
            return "IMPROVES"
        if median <= -IC_SPAN and negative >= 9:
            return "DEGRADES"
        return "NO_DETECTABLE_CHANGE"
    value = float(values[0])
    folds = np.asarray(fold_diffs if fold_diffs is not None else [], dtype=float)
    if value >= IC_SPAN and int((folds > 0).sum()) >= 5:
        return "IMPROVES"
    if value <= -IC_SPAN and int((folds < 0).sum()) >= 5:
        return "DEGRADES"
    return "NO_DETECTABLE_CHANGE"


def fold_robust(seed_fold_diffs: np.ndarray, per_seed_fold_ic_leave_out: Sequence[float]) -> bool:
    """`seed_fold_diffs`: seeds x folds ΔIC.  Robust: median-by-fold positive in >=5 folds and every leave-one-fold-out median positive."""
    by_fold = np.median(seed_fold_diffs, axis=0)
    return bool((by_fold > 0).sum() >= 5 and all(v > 0 for v in per_seed_fold_ic_leave_out))


def leave_one_fold_out_median(seed_fold_diffs: np.ndarray) -> list[float]:
    out = []
    for removed in range(seed_fold_diffs.shape[1]):
        keep = [i for i in range(seed_fold_diffs.shape[1]) if i != removed]
        out.append(float(np.median(seed_fold_diffs[:, keep].mean(axis=1))))
    return out


def classify(boosted: str, linear: str, boosted_robust: bool) -> str:
    """The preregistered label, applied mechanically to the two pair statuses."""
    if boosted == "IMPROVES":
        if linear == "DEGRADES" or not boosted_robust:
            return "MIXED"
        return "RICH_DATA_IMPROVES_ORDERING" if linear == "IMPROVES" else "IMPROVES_ONLY_WITH_BOOSTING"
    if linear == "IMPROVES":
        return "MIXED" if boosted == "DEGRADES" else "IMPROVES_ONLY_LINEAR"
    if "DEGRADES" in (boosted, linear):
        return "RICH_DATA_DEGRADES_ORDERING"
    return "NO_DETECTABLE_ORDERING_GAIN"


def context(delta_ic: float, delta_sharpe: Optional[float] = None) -> dict[str, Any]:
    out = {"delta_ic_in_seed_sds": delta_ic / IC_SD, "delta_ic_in_ranges": delta_ic / IC_SPAN}
    if delta_sharpe is not None:
        out["delta_net_sharpe_in_seed_sds"] = delta_sharpe / SHARPE_SD
    return out


# ── checkpoints, run, dry run ────────────────────────────────────────────────

def checkpoint_paths(output: Path, arm: str, seed: int) -> tuple[Path, Path]:
    directory = Path(output) / "checkpoints"
    return directory / f"{arm}_seed_{seed:02d}_predictions.parquet", directory / f"{arm}_seed_{seed:02d}.json"


def load_checkpoint(output: Path, arm: str, seed: int, fingerprint: str) -> Optional[pd.DataFrame]:
    parquet, receipt_path = checkpoint_paths(output, arm, seed)
    if not (parquet.exists() and receipt_path.exists()):
        return None
    predictions = pd.read_parquet(parquet)
    predictions["date"] = pd.to_datetime(predictions["date"]).dt.date
    problems = verify_receipt(json.loads(receipt_path.read_text()), predictions, arm=arm, seed=seed, fingerprint=fingerprint)
    if problems:
        raise RuntimeError(f"checkpoint {arm} seed {seed} rejected: {problems}; move it aside rather than mixing runs")
    return predictions


def _run_tasks(tasks: list[tuple[str, int]], root: Path, output: Path, fingerprint: str, workers: int,
               frame: pd.DataFrame, plan: Any, began: float) -> None:
    def save(arm: str, seed: int, predictions: pd.DataFrame, seconds: float) -> None:
        parquet, receipt_path = checkpoint_paths(output, arm, seed)
        FIREWALL.assert_clear(predictions, context=f"EXP-011 {arm} seed {seed}")
        exp010a._atomic_parquet(parquet, predictions)
        exp010a._atomic_json(receipt_path, receipt_for(arm, seed, predictions, seconds, fingerprint=fingerprint, root=root))

    done = 0
    if workers <= 1:
        for arm, seed in tasks:
            result = fit_arm_seed(arm, seed, frame, plan)
            if result.errors or result.predictions is None or len(result.folds) != 8:
                raise RuntimeError(f"{arm} seed {seed} failed: {result.errors}")
            save(arm, seed, result.predictions, float(result.seconds))
            done += 1
            print(f"EXP-011 {arm} seed {seed} done ({done}/{len(tasks)}) | elapsed {(time.perf_counter() - began) / 60:.1f}m", flush=True)
        return
    context = multiprocessing.get_context("spawn")
    with futures.ProcessPoolExecutor(max_workers=workers, mp_context=context, initializer=_init_worker, initargs=(str(root),)) as pool:
        for arm, seed, predictions, seconds, errors in pool.map(_worker_task, tasks):
            if errors:
                raise RuntimeError(f"{arm} seed {seed} failed: {errors}")
            save(arm, seed, predictions, seconds)
            done += 1
            print(f"EXP-011 {arm} seed {seed} done ({done}/{len(tasks)}) | elapsed {(time.perf_counter() - began) / 60:.1f}m", flush=True)


def gather_predictions(root: Path, output: Path, fingerprint: str) -> dict[str, dict[int, pd.DataFrame]]:
    """Every arm's predictions: E2 from the frozen EXP-010A files, the rest from verified checkpoints."""
    out: dict[str, dict[int, pd.DataFrame]] = {arm: {} for arm in ARMS}
    for arm, spec in ARMS.items():
        for seed in spec["seeds"]:
            if arm == "E2":
                out[arm][seed] = exp010b.load_seed_predictions(seed, root)
            else:
                loaded = load_checkpoint(output, arm, seed, fingerprint)
                if loaded is None:
                    raise FileNotFoundError(f"missing checkpoint {arm} seed {seed}")
                out[arm][seed] = loaded
    return out


def arm_seed_report(arm: str, seed: int, predictions: pd.DataFrame, panel: pd.DataFrame, universe: pd.DataFrame,
                    calendar: Any, schedule: Sequence[Date]) -> dict[str, Any]:
    ordering = ordering_report(predictions)
    fold_by_grid = predictions.groupby("date")["fold"].first().astype(int).to_dict()
    aligned = exp010b.align_signals(predictions[["date", "symbol", "prediction"]], universe, calendar, schedule)
    economics, _, _, _ = exp010b.arm_report(seed, ECONOMICS_ARM, aligned, universe, fold_by_grid)
    covered = covered_subset_ic(predictions, panel)
    flat = {k: v for k, v in economics.items() if k != "costs"}
    return {"arm": arm, "seed": seed, **ordering, "covered_mean_rank_ic": covered["mean_rank_ic"], "covered_rows": covered["rows"],
            **{f"b1_{k}": v for k, v in flat.items() if isinstance(v, (int, float)) and k not in ("seed",)},
            "costs": economics["costs"]}


def analyse(reports: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Paired comparisons, fold-robustness and the preregistered label from per-arm reports."""
    keys = ["mean_rank_ic", "b1_net_sharpe_10bp", "b1_gross_sharpe", "b1_annualised_turnover", "b1_net_max_drawdown",
            "b1_cost_share_of_gross", "positive_fold_count"]
    e0, e1 = reports["E0"][0], reports["E1"][0]
    e2 = {r["seed"]: r for r in reports["E2"]}
    e3 = {r["seed"]: r for r in reports["E3"]}
    seeds = list(SEEDS)
    boosted_rows = paired([e2[s] for s in seeds], [e3[s] for s in seeds], keys)      # `paired` carries each pair's own seed
    linear_rows = paired([e0], [e1], keys)
    model_base = paired(broadcast(e0, seeds), [e2[s] for s in seeds], keys)
    model_rich = paired(broadcast(e1, seeds), [e3[s] for s in seeds], keys)
    table = pd.DataFrame(boosted_rows)
    seed_fold_diffs = np.array([np.array(e3[s]["fold_ic"]) - np.array(e2[s]["fold_ic"]) for s in seeds])
    linear_fold_diffs = np.array(e1["fold_ic"]) - np.array(e0["fold_ic"])
    boosted_ic = table[table["metric"] == "mean_rank_ic"]["difference"].to_numpy()
    boosted_status = pair_status(boosted_ic)
    linear_status = pair_status([linear_rows[0]["difference"]], linear_fold_diffs)
    lofo = leave_one_fold_out_median(seed_fold_diffs)
    robust = fold_robust(seed_fold_diffs, lofo)
    label = classify(boosted_status, linear_status, robust)
    summary = lambda rows: {m: exp010b.distribution(g["difference"].to_numpy()) for m, g in pd.DataFrame(rows).groupby("metric")}
    interaction = [{"seed": s, "difference": float(b["difference"] - linear_rows[0]["difference"])}
                   for s in seeds for b in boosted_rows if b["seed"] == s and b["metric"] == "mean_rank_ic"]
    return {
        "paired": {"data_value_boosted": boosted_rows, "data_value_linear": linear_rows,
                   "model_value_baseline": model_base, "model_value_rich": model_rich, "interaction_rank_ic": interaction},
        "summary": {"data_value_boosted": summary(boosted_rows), "model_value_baseline": summary(model_base),
                    "model_value_rich": summary(model_rich), "interaction_rank_ic": exp010b.distribution([r["difference"] for r in interaction])},
        "fold_delta_ic": {"boosted_seed_median_by_fold": [float(v) for v in np.median(seed_fold_diffs, axis=0)],
                          "boosted_seeds_positive_by_fold": [int(v) for v in (seed_fold_diffs > 0).sum(axis=0)],
                          "linear_by_fold": [float(v) for v in linear_fold_diffs],
                          "leave_one_fold_out_median": lofo, "exp010a_mean_fold_rank_ic": exp010b.EXP010A_MEAN_FOLD_IC},
        "noise_context": {"boosted_median_delta_ic": context(float(np.median(boosted_ic)), float(np.median(table[table["metric"] == "b1_net_sharpe_10bp"]["difference"]))),
                          "linear_delta_ic": context(float(linear_rows[0]["difference"]))},
        "classification": {"label": label, "boosted_status": boosted_status, "linear_status": linear_status, "boosted_fold_robust": robust,
                           "ic_unit": IC_SPAN, "economics_labelled": False, "best_seed_selected": False, "promotion": "NOT ASSESSED"},
    }


def dry_run(root: Path = Path("."), *, workers: int = 4) -> dict[str, Any]:
    """Inputs, hashes, checkpoints and schedule.  No arm is fit and no validation prediction is scored."""
    began = time.perf_counter()
    root = Path(root)
    guard = exp010b.holdout_guard(root)
    panel, checks = load_rich_panel(root)
    parent = exp010b.verify_parent_artifacts(root)
    hashes = {}
    for seed in SEEDS:
        hashes[str(seed)] = exp010a._prediction_hash(exp010b.load_seed_predictions(seed, root))
    fingerprint = definition_fingerprint(root)
    output = root / OUTPUT_DIR
    existing = {arm: [s for s in spec["seeds"] if checkpoint_paths(output, arm, s)[0].exists()] for arm, spec in ARMS.items() if spec["fit"]}
    fits = sum(len(spec["seeds"]) for spec in (ARMS[a] for a in FIT_ORDER))
    return {
        "experiment_id": EXPERIMENT_ID, "real_evaluation_executed": False, "fitted_now": False,
        "rich_panel_checks": checks, "rows": int(len(panel)), "features_baseline": len(feature_list("baseline")),
        "features_rich": len(feature_list("rich")), "parent_artifacts_verified": parent["passed"],
        "e2_prediction_hashes_verified": hashes == {str(k): v for k, v in exp010b.PARENT_PREDICTION_SHA256.items()},
        "fits_required": fits, "checkpoints_present": existing, "workers": workers,
        "fingerprint": fingerprint, "holdout": guard, "wall_seconds": round(time.perf_counter() - began, 1),
    }


def benchmark(root: Path = Path(".")) -> dict[str, Any]:
    """Time one gradient-boosting fit on fold-0 TRAINING rows for each feature set.  Nothing is predicted or scored."""
    root = Path(root)
    panel, _ = load_rich_panel(root)
    plan = exp009b.recorded_plan(root)
    frame = panel[panel["in_universe"]].dropna(subset=[LABEL])
    train, _ = plan.folds[0].split(frame, date_column="date")
    from src.quant.models.base import FoldImputer
    out = {"train_rows": int(len(train))}
    for kind in ("baseline", "rich"):
        names = feature_list(kind)
        X = FoldImputer(standardise=False).fit_transform(train[names].to_numpy(dtype=float), feature_names=names)
        model = ModelSpec("timing", "gradient_boosting", tuple(GBR_PARAMS.items()), 0).build()
        started = time.perf_counter()
        model.fit(X, train[LABEL].to_numpy(dtype=float), feature_names=names)
        out[f"gbr_fit_seconds_{kind}_fold0"] = round(time.perf_counter() - started, 1)
    return out


def run_study(root: Path = Path("."), *, output: Optional[Path] = None, workers: int = 4) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or root / OUTPUT_DIR
    gate = prereg_gate(root)                       # mandatory: before any data is read
    git_state = exp009a._git_state(root)
    guard = exp010b.holdout_guard(root)
    parent = exp010b.verify_parent_artifacts(root)
    if not parent["passed"]:
        raise RuntimeError(f"EXP-010A artifacts differ from those registered: {parent['checks']}")
    fingerprint = definition_fingerprint(root)
    frame, panel_checks = load_rich_panel(root)
    plan = exp009b.recorded_plan(root)
    tasks = [(arm, seed) for arm in FIT_ORDER for seed in ARMS[arm]["seeds"] if load_checkpoint(output, arm, seed, fingerprint) is None]
    if tasks:
        _run_tasks(tasks, root, output, fingerprint, workers, frame, plan, began)
    predictions = gather_predictions(root, output, fingerprint)

    daily, calendar = exp010b.build_daily_panel(root)
    universe = daily[daily["in_universe"]]
    schedule = exp010b.rebalance_schedule(calendar, exp010b.ARMS[ECONOMICS_ARM]["step_sessions"])
    reports: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    hashes: dict[str, str] = {}
    for arm, spec in ARMS.items():
        for seed in spec["seeds"]:
            frame_p = predictions[arm][seed]
            hashes[f"{arm}_{seed}"] = exp010a._prediction_hash(frame_p)
            reports[arm].append(arm_seed_report(arm, seed, frame_p, frame, universe, calendar, schedule))
    ranks = {"E1_vs_E0": prediction_rank_correlation(predictions["E1"][0], predictions["E0"][0]),
             "E3_vs_E2_by_seed": {str(s): prediction_rank_correlation(predictions["E3"][s], predictions["E2"][s]) for s in SEEDS}}
    analysis = analyse(reports)

    output.mkdir(parents=True, exist_ok=True)
    exp010a._atomic_json(output / "definition.json", DEFINITION)
    exp010a._atomic_json(output / "config.json", {"arms": ARMS, "features": {k: feature_list(k) for k in ("baseline", "rich")},
                                                  "folds": [f.as_dict() for f in plan.folds], "costs": list(exp010b.COSTS)})
    flat = pd.DataFrame([{k: v for k, v in r.items() if k not in ("costs", "fold_ic")} for arm in ARMS for r in reports[arm]])
    flat.to_csv(output / "per_arm_metrics.csv", index=False)
    pd.DataFrame([{"arm": r["arm"], "seed": r["seed"], "fold": i, "mean_rank_ic": v}
                  for arm in ARMS for r in reports[arm] for i, v in enumerate(r["fold_ic"])]).to_csv(output / "fold_metrics.csv", index=False)
    pd.DataFrame([{"comparison": name, **row} for name, rows in analysis["paired"].items() for row in rows]).to_csv(output / "paired_differences.csv", index=False)
    exp010a._atomic_json(output / "prediction_hashes.json", hashes)
    exp010a._atomic_json(output / "metrics.json", {"per_arm": reports, **analysis, "prediction_rank_correlations": ranks})
    manifest = {
        "experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state,
        "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "inputs": {"rich_dataset_id": RICH_DATASET_ID, "rich_content_hash": RICH_CONTENT_HASH, "rich_feature_hash": RICH_FEATURE_HASH,
                   "panel_checks": panel_checks, "parent_artifacts_verified": parent["passed"]},
        "dependency_versions": dependency_versions(),
        "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(), "workers": workers,
                    "platform": platform.platform(), "python": platform.python_version()},
        "holdout": guard, "seeds": list(SEEDS), "arms": list(ARMS), "best_seed_selected": False,
        "classification": analysis["classification"]["label"], "completion": "COMPLETE",
    }
    manifest["output_sha256"] = {p.name: prereg.sha256_file(p) for p in sorted(output.glob("*")) if p.is_file() and p.name != "manifest.json"}
    exp010a._atomic_json(output / "manifest.json", manifest)
    print(f"EXP-011 COMPLETE: {analysis['classification']['label']}; outputs: {output}", flush=True)
    return {"manifest": manifest, "analysis": analysis}


def read_summary(root: Path = Path(".")) -> dict[str, Any]:
    path = Path(root) / OUTPUT_DIR / "metrics.json"
    if not path.exists():
        return {"status": "NOT_RUN", "expected": str(path)}
    payload = json.loads(path.read_text())
    return {"status": "COMPLETE", "classification": payload["classification"], "summary": payload["summary"],
            "fold_delta_ic": payload["fold_delta_ic"], "noise_context": payload["noise_context"],
            "prediction_rank_correlations": payload["prediction_rank_correlations"], "best_seed_selected": False}
