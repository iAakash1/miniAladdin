"""EXP-010A — ten-seed noise floor for the frozen deduplicated baseline.

This is a diagnostic, not model selection.  Every seed is reported and no seed
is promoted.  The sealed holdout is armed before data load and cannot enter a
fold, prediction, checkpoint, or portfolio.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.quant.models.factory import ModelSpec
from src.quant.models.registry import dependency_versions
from src.quant.study import exp009a, exp009b, exp009d, prereg
from src.quant.study.firewall import FIREWALL
from src.quant.validation.metrics import ic_summary, per_date_ic
from src.quant.validation.runner import ExperimentResult, run_walk_forward

EXPERIMENT_ID = "EXP-010A"
PARENT_EXPERIMENT = "EXP-009D"
OUTPUT_DIR = Path("experiments") / EXPERIMENT_ID
PREREG_DOC = Path("docs/EXP_010A_PREREGISTRATION.md")
LABEL = exp009b.LABEL
FEATURES = tuple(exp009d.DEFINITION["data"]["features_dedup"])
SEEDS = tuple(range(10))
COSTS = (1.0, 3.0, 5.0, 10.0, 20.0)
PORTFOLIO = dict(exp009b._C)
HYPERPARAMETERS = dict(exp009b._COMMON)
DATASET_ROWS = 452_524
FEATURE_HASH = hashlib.sha256(json.dumps(FEATURES, separators=(",", ":")).encode()).hexdigest()

DEFINITION: dict[str, Any] = {
    "experiment_id": EXPERIMENT_ID,
    "parent_experiment": PARENT_EXPERIMENT,
    "status": "EXPERIMENTAL - NOISE DIAGNOSTIC - PROMOTION NOT ASSESSED",
    "question": "How much variation in ordering and portfolio economics is caused purely by random seed variation in the existing model specification?",
    "data": {
        "dataset_id": "ds-491d761b9f2a6fc4", "dataset_content_hash": "7deb8601ae7a34074cade997397f1947",
        "rows": DATASET_ROWS, "end": "2025-05-09",
        "returns_panel_sha256": exp009b.DEFINITION["data"]["returns_panel_sha256"],
        "target": LABEL, "features": list(FEATURES), "feature_count": len(FEATURES),
        "feature_list_sha256": FEATURE_HASH, "universe_only": True,
        "folds": "the exact 8 folds recorded in EXP-006 and reused by EXP-009D",
    },
    "model": {
        "class": "sklearn.ensemble.GradientBoostingRegressor", "repository_kind": "gradient_boosting",
        "hyperparameters": HYPERPARAMETERS, "seeds": list(SEEDS), "hyperparameter_search": "none",
        "imputation": "FoldImputer trained independently inside each training fold",
    },
    "portfolio": {
        **PORTFOLIO, "source": "frozen EXP-009A selected rule",
        "cost_half_spread_bps": list(COSTS), "primary_cost_bps": 10.0,
        "engine": "EXP-009A settings unchanged: one-period execution lag, long/short quintiles, commission and impact included",
    },
    "per_seed_metrics": [
        "mean Rank IC", "HAC t-stat (4 lags)", "ICIR", "8 fold IC values", "positive fold count",
        "worst fold", "mean cross-sectional prediction dispersion", "prediction-rank correlation to seed 0",
        "portfolio overlap to seed 0", "annualised one-way turnover", "gross Sharpe",
        "net Sharpe at 1/3/5/10/20 bp", "net maximum drawdown", "cost share of gross",
    ],
    "across_seed_metrics": {
        "statistics": ["mean", "sample_std", "median", "min", "max", "p05", "p95", "p95_minus_p05"],
        "primary": ["mean_rank_ic", "net_sharpe_10bp", "annualised_turnover"],
        "also": ["all pairwise prediction-rank correlations", "all pairwise portfolio overlaps", "fold stability"],
    },
    "interpretation": {
        "purpose": "descriptive stochastic noise floor for later preregistered comparisons",
        "no_best_seed": True, "selection": "none", "promotion": "NOT ASSESSED",
        "later_rule": "Later effects must be reported against both the sample standard deviation and p95-p05 range; EXP-010A defines no automatic pass threshold.",
    },
    "resume": "one atomic prediction Parquet plus metadata JSON per completed seed; matching checkpoints are resumed, mismatches are refused",
    "outputs": ["definition.json", "config.json", "manifest.json", "metrics.json", "per_seed_metrics.csv", "fold_metrics.csv", "prediction_hashes.json", "checkpoints/seed_XX_predictions.parquet"],
    "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
}

METHOD_SOURCES = (
    "src/quant/models/trees.py", "src/quant/models/base.py", "src/quant/validation/runner.py",
    "src/quant/backtest/rules.py", "src/quant/backtest/engine.py", "src/quant/study/exp009a.py",
    "src/quant/study/exp009b.py", "src/quant/study/exp010a.py",
)


def definition_fingerprint(root: Path = Path(".")) -> str:
    return prereg.fingerprint(DEFINITION, METHOD_SOURCES, root)


def prereg_gate(root: Path = Path("."), *, fetch: bool = True) -> dict[str, Any]:
    return prereg.check(document=PREREG_DOC, expected_fingerprint=definition_fingerprint(root),
                        method_sources=METHOD_SOURCES, root=root, fetch=fetch)


def dry_run(root: Path = Path(".")) -> dict[str, Any]:
    """Definition/input checks only: does not read labels, fit, or backtest."""
    manifest = json.loads((Path(root) / exp009b.FRAME_MANIFEST).read_text())
    plan = exp009b.recorded_plan(root)
    return {
        "experiment_id": EXPERIMENT_ID, "real_training_executed": False,
        "dataset_id_matches": manifest["dataset_version"] == DEFINITION["data"]["dataset_id"],
        "dataset_hash_matches": manifest["content_hash"] == DEFINITION["data"]["dataset_content_hash"],
        "dataset_rows_match": manifest["rows"] == DATASET_ROWS,
        "features": len(FEATURES), "seeds": list(SEEDS), "folds": len(plan.folds),
        "last_validation_date": str(plan.folds[-1].validation_end),
        "holdout_start": str(exp009b.holdout_window(root)[0]),
    }


def _prediction_hash(predictions: pd.DataFrame) -> str:
    ordered = predictions.sort_values(["date", "symbol"])[["date", "symbol", "fold", LABEL, "prediction"]].copy()
    ordered["date"] = ordered["date"].astype(str)
    return hashlib.sha256(pd.util.hash_pandas_object(ordered, index=False).to_numpy().tobytes()).hexdigest()


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, compression="zstd", index=False)
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    os.replace(temporary, path)


def _run_seed(frame: pd.DataFrame, plan: Any, seed: int, *, on_fold: Optional[Callable] = None,
              params: Optional[dict[str, Any]] = None) -> ExperimentResult:
    spec = ModelSpec(f"gradient_boosting_seed_{seed}", "gradient_boosting",
                     tuple((params or HYPERPARAMETERS).items()), seed)
    return run_walk_forward(spec.build, frame, plan, features=FEATURES, label=LABEL,
                            step_sessions=5, on_fold=on_fold)


def _rank_correlation(left: pd.DataFrame, right: pd.DataFrame) -> float:
    joined = left[["date", "symbol", "prediction"]].merge(
        right[["date", "symbol", "prediction"]], on=["date", "symbol"], suffixes=("_left", "_right"))
    values = [spearmanr(group["prediction_left"], group["prediction_right"])[0]
              for _, group in joined.groupby("date") if len(group) >= 20]
    return float(np.nanmean(values))


def _portfolio_overlap(left: pd.DataFrame, right: pd.DataFrame, fraction: float = 0.2) -> float:
    joined = left[["date", "symbol", "prediction"]].merge(
        right[["date", "symbol", "prediction"]], on=["date", "symbol"], suffixes=("_left", "_right"))
    values: list[float] = []
    for _, group in joined.groupby("date"):
        n = max(1, int(round(len(group) * fraction)))
        for ascending in (False, True):
            a = set(group.sort_values("prediction_left", ascending=ascending, kind="stable").head(n)["symbol"])
            b = set(group.sort_values("prediction_right", ascending=ascending, kind="stable").head(n)["symbol"])
            values.append(len(a & b) / n)
    return float(np.mean(values))


def _seed_report(seed: int, predictions: pd.DataFrame, panel: pd.DataFrame,
                 seed_zero: pd.DataFrame) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dated_ic = per_date_ic(predictions, prediction_column="prediction", target_column=LABEL)
    rank = ic_summary(dated_ic, horizon_sessions=21, step_sessions=5)
    folds = []
    for fold, group in predictions.groupby("fold"):
        fold_series = per_date_ic(group, prediction_column="prediction", target_column=LABEL)
        folds.append({"seed": seed, "fold": int(fold), "mean_rank_ic": float(fold_series.mean()),
                      "dates": int(len(fold_series)), "validation_rows": int(len(group))})
    dispersion = predictions.groupby("date")["prediction"].std().mean()
    costs: dict[str, Any] = {}
    for bps in COSTS:
        result = exp009a._backtest(predictions, panel, PORTFOLIO, bps)
        metrics = result.metrics
        costs[f"{int(bps)}bp"] = {
            "gross_sharpe": metrics.get("gross_sharpe"), "net_sharpe": metrics.get("net_sharpe"),
            "annualised_turnover": metrics.get("annualised_turnover"),
            "net_max_drawdown": metrics.get("net_max_drawdown"),
            "cost_share_of_gross": metrics.get("cost_share_of_gross"),
        }
    fold_values = [row["mean_rank_ic"] for row in folds]
    return ({
        "seed": seed, "mean_rank_ic": rank.get("mean_ic"), "hac_t_stat": rank.get("t_stat"),
        "ic_ir": rank.get("ic_ir"), "fold_ic": fold_values,
        "positive_fold_count": int(sum(value > 0 for value in fold_values)),
        "worst_fold_ic": float(min(fold_values)),
        "mean_cross_sectional_prediction_sd": float(dispersion),
        "prediction_rank_correlation_to_seed_0": 1.0 if seed == 0 else _rank_correlation(predictions, seed_zero),
        "portfolio_overlap_to_seed_0": 1.0 if seed == 0 else _portfolio_overlap(predictions, seed_zero),
        "annualised_turnover": costs["10bp"]["annualised_turnover"],
        "gross_sharpe": costs["10bp"]["gross_sharpe"],
        "net_sharpe_10bp": costs["10bp"]["net_sharpe"],
        "costs": costs,
    }, folds)


def _distribution(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)), "sample_std": float(np.std(array, ddof=1)),
        "median": float(np.median(array)), "min": float(np.min(array)), "max": float(np.max(array)),
        "p05": float(np.quantile(array, 0.05)), "p95": float(np.quantile(array, 0.95)),
        "p95_minus_p05": float(np.quantile(array, 0.95) - np.quantile(array, 0.05)),
    }


def summarize_reports(reports: Sequence[dict[str, Any]], fold_rows: Sequence[dict[str, Any]],
                      predictions: dict[int, pd.DataFrame]) -> dict[str, Any]:
    pairwise = []
    for left in SEEDS:
        for right in SEEDS:
            if right <= left:
                continue
            pairwise.append({"seed_left": left, "seed_right": right,
                             "prediction_rank_correlation": _rank_correlation(predictions[left], predictions[right]),
                             "portfolio_overlap": _portfolio_overlap(predictions[left], predictions[right])})
    fold_frame = pd.DataFrame(fold_rows)
    fold_stability = [{"fold": int(fold), **_distribution(group["mean_rank_ic"].tolist())}
                      for fold, group in fold_frame.groupby("fold")]
    return {
        "primary_noise_distributions": {
            key: _distribution([float(report[key]) for report in reports])
            for key in ("mean_rank_ic", "net_sharpe_10bp", "annualised_turnover")
        },
        "pairwise_prediction_rank_correlations": pairwise,
        "pairwise_prediction_rank_correlation_distribution": _distribution([row["prediction_rank_correlation"] for row in pairwise]),
        "pairwise_portfolio_overlap_distribution": _distribution([row["portfolio_overlap"] for row in pairwise]),
        "fold_stability": fold_stability,
        "best_seed_selected": False, "promotion": "NOT ASSESSED",
    }


def run_study(root: Path = Path("."), *, output: Optional[Path] = None) -> dict[str, Any]:
    began = time.perf_counter()
    root = Path(root)
    output = output or root / OUTPUT_DIR
    gate = prereg_gate(root)  # mandatory: before frame or labels are touched
    git_state = exp009a._git_state(root)  # capture the clean start, before outputs exist
    holdout_start, holdout_end = exp009b.arm_firewall(root)
    frame, build = exp009b.load_frame(root)
    panel = frame[["date", "symbol", "dollar_volume", "fwd_ret_5", "fwd_ret_21", "in_universe"]]
    plan = exp009b.recorded_plan(root)
    checks = {
        "dataset_id": build["dataset_version"] == DEFINITION["data"]["dataset_id"],
        "dataset_content_hash": build["content_hash"] == DEFINITION["data"]["dataset_content_hash"],
        "dataset_rows": len(frame) == DATASET_ROWS,
        "returns_panel_hash": exp009a.panel_content_hash(panel) == DEFINITION["data"]["returns_panel_sha256"],
        "features_present": all(feature in frame.columns for feature in FEATURES),
        "folds": len(plan.folds) == 8,
    }
    if not all(checks.values()):
        raise RuntimeError(f"EXP-010A INVALID input: {checks}")

    checkpoint_dir = output / "checkpoints"
    fingerprint = definition_fingerprint(root)
    predictions: dict[int, pd.DataFrame] = {}
    fit_seconds: dict[int, float] = {}
    total_folds = len(SEEDS) * len(plan.folds)
    completed_folds = 0
    for position, seed in enumerate(SEEDS, 1):
        parquet = checkpoint_dir / f"seed_{seed:02d}_predictions.parquet"
        metadata = checkpoint_dir / f"seed_{seed:02d}.json"
        if parquet.exists() and metadata.exists():
            receipt = json.loads(metadata.read_text())
            resumed = pd.read_parquet(parquet)
            resumed["date"] = pd.to_datetime(resumed["date"]).dt.date
            valid = (receipt.get("definition_fingerprint") == fingerprint and
                     receipt.get("dataset_content_hash") == build["content_hash"] and
                     receipt.get("prediction_sha256") == _prediction_hash(resumed))
            if not valid:
                raise RuntimeError(f"checkpoint mismatch for seed {seed}; move the checkpoint aside rather than mixing runs")
            predictions[seed] = resumed
            fit_seconds[seed] = float(receipt.get("fit_seconds", 0.0))
            completed_folds += len(plan.folds)
            print(f"EXP-010A seed {position}/10 ({seed}) resumed; {completed_folds}/{total_folds} folds complete", flush=True)
            continue

        def progress(_model: str, fold: int, mean_ic: Any, _train_ic: Any) -> None:
            nonlocal completed_folds
            completed_folds += 1
            elapsed = time.perf_counter() - began
            eta = elapsed / completed_folds * (total_folds - completed_folds) if completed_folds else 0
            print(f"EXP-010A seed {position}/10 ({seed}) fold {fold + 1}/8 | IC {mean_ic:.4f} | elapsed {elapsed/60:.1f}m | ETA {eta/60:.1f}m", flush=True)

        result = _run_seed(frame, plan, seed, on_fold=progress)
        if result.errors or result.predictions is None or len(result.folds) != 8:
            raise RuntimeError(f"seed {seed} failed: {result.errors}")
        FIREWALL.assert_clear(result.predictions, context=f"EXP-010A seed {seed}")
        _atomic_parquet(parquet, result.predictions)
        receipt = {"seed": seed, "definition_fingerprint": fingerprint,
                   "dataset_content_hash": build["content_hash"], "prediction_sha256": _prediction_hash(result.predictions),
                   "rows": len(result.predictions), "folds": len(result.folds), "fit_seconds": result.seconds}
        _atomic_json(metadata, receipt)
        predictions[seed] = result.predictions
        fit_seconds[seed] = result.seconds

    reports, fold_rows = [], []
    for seed in SEEDS:
        report, rows = _seed_report(seed, predictions[seed], panel, predictions[0])
        report["fit_seconds"] = fit_seconds[seed]
        report["prediction_sha256"] = _prediction_hash(predictions[seed])
        reports.append(report)
        fold_rows.extend(rows)
    summary = summarize_reports(reports, fold_rows, predictions)

    output.mkdir(parents=True, exist_ok=True)
    _atomic_json(output / "definition.json", DEFINITION)
    _atomic_json(output / "config.json", {"features": list(FEATURES), "feature_list_sha256": FEATURE_HASH,
                                          "hyperparameters": HYPERPARAMETERS, "seeds": list(SEEDS),
                                          "folds": [fold.as_dict() for fold in plan.folds], "portfolio": PORTFOLIO, "costs": list(COSTS)})
    pd.json_normalize(reports).drop(columns=[column for column in pd.json_normalize(reports).columns if column.startswith("costs.")]).to_csv(output / "per_seed_metrics.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(output / "fold_metrics.csv", index=False)
    _atomic_json(output / "prediction_hashes.json", {str(report["seed"]): report["prediction_sha256"] for report in reports})
    _atomic_json(output / "metrics.json", {"per_seed": reports, "across_seeds": summary})
    manifest = {
        "experiment_id": EXPERIMENT_ID, "status": DEFINITION["status"], **gate, **git_state,
        "definition_sha256": prereg.sha256_bytes(json.dumps(DEFINITION, sort_keys=True, default=str).encode()),
        "dataset": {"id": build["dataset_version"], "content_hash": build["content_hash"], "rows": len(frame),
                    "feature_list_sha256": FEATURE_HASH},
        "validity_checks": checks, "dependency_versions": dependency_versions(),
        "compute": {"wall_seconds": round(time.perf_counter() - began, 1), "cpu_count": os.cpu_count(),
                    "platform": platform.platform(), "python": platform.python_version()},
        "holdout": {"start": str(holdout_start), "end": str(holdout_end), "touched": False, "firewall": FIREWALL.status()},
        "seeds": list(SEEDS), "best_seed_selected": False, "completion": "COMPLETE",
    }
    manifest["output_sha256"] = {path.name: prereg.sha256_file(path) for path in sorted(output.glob("*")) if path.is_file() and path.name != "manifest.json"}
    _atomic_json(output / "manifest.json", manifest)
    print(f"EXP-010A COMPLETE: 10/10 seeds, 80/80 folds; metrics: {output / 'metrics.json'}", flush=True)
    return {"manifest": manifest, "metrics": {"across_seeds": summary}}


def read_summary(root: Path = Path(".")) -> dict[str, Any]:
    path = Path(root) / OUTPUT_DIR / "metrics.json"
    if not path.exists():
        return {"status": "NOT_RUN", "expected": str(path)}
    payload = json.loads(path.read_text())
    return {"status": "COMPLETE", **payload["across_seeds"]["primary_noise_distributions"],
            "best_seed_selected": payload["across_seeds"]["best_seed_selected"]}
