"""Outer-OOS-only campaign aggregation, economics, cards and diversity.

Nothing in this module fits a base model or selects hyperparameters.  It reads
only COMPLETE outer-evaluation records from one method commit, verifies their
prediction hashes, and refuses partial families before producing scientific
comparisons.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quant.backtest.turnover_diagnostics import breakeven_half_spread
from src.quant.model_lab.ensemble import equal_weight_rank_average, prediction_rank_correlation
from src.quant.model_lab.evaluation import ordering_metrics, prediction_hash
from src.quant.model_lab.registry import TrialRecord, TrialRegistry, TrialStatus
from src.quant.model_lab.robustness import distribution
from src.quant.model_lab.runner import PREDICTION_DIR
from src.quant.model_lab.search_space import family_for
from src.quant.study import exp010b
from src.quant.study.firewall import FIREWALL
from src.quant.validation.metrics import per_date_ic
from src.quant.validation.significance import (
    deflated_sharpe_ratio,
    probability_of_backtest_overfitting,
)

CPU_MODELS = (
    "ridge", "lasso", "elastic_net", "huber", "sgd_huber",
    "pca_ridge", "pls", "random_forest", "extra_trees",
    "hist_gradient_boosting",
)
OUTER_PHASE = "OUTER_EVALUATION"
PRIMARY_COST_BPS = 10.0
REPORT_PATH = Path("data/manifests/model_lab_campaign.json")
CARD_DIR = Path("data/manifests/model_cards")


def complete_outer_records(
    registry: TrialRegistry,
    model_name: str,
    *,
    method_commit: str,
) -> list[TrialRecord]:
    """Exactly one COMPLETE outer record for each frozen fold, or refuse."""
    records = [
        record for record in registry.records()
        if record.model_name == model_name
        and record.phase == OUTER_PHASE
        and record.status is TrialStatus.COMPLETE
        and record.git_commit == method_commit
    ]
    folds = [record.outer_fold for record in records]
    if sorted(folds) != list(range(8)) or len(set(folds)) != 8:
        raise RuntimeError(
            f"{model_name} has outer folds {sorted(folds)} at {method_commit[:8]}; "
            "all eight unique COMPLETE folds are required"
        )
    return sorted(records, key=lambda record: record.outer_fold)


def load_outer_predictions(
    records: list[TrialRecord],
    *,
    root: Path = Path("."),
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for record in records:
        path = root / PREDICTION_DIR / f"{record.trial_id}.parquet"
        if not path.exists():
            raise RuntimeError(f"missing outer prediction artifact {path}")
        frame = pd.read_parquet(path)
        if prediction_hash(frame) != record.prediction_hash:
            raise RuntimeError(f"outer prediction hash mismatch for {record.trial_id}")
        if set(frame["outer_fold"].unique()) != {record.outer_fold}:
            raise RuntimeError(f"outer prediction fold mismatch for {record.trial_id}")
        FIREWALL.assert_clear(frame, context=f"MODEL-LAB aggregate {record.trial_id}")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    if combined.duplicated(["date", "symbol"]).any():
        raise RuntimeError("outer OOS predictions contain duplicate date-symbol rows")
    return combined.sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)


def _runtime(records: list[TrialRecord]) -> dict[str, Any]:
    def total(key: str) -> float:
        return float(sum(float(record.runtime.get(key) or 0.0) for record in records))

    peaks = [float(record.runtime.get("peak_rss_mb") or 0.0) for record in records]
    return {
        "outer_wall_seconds": total("wall_seconds"),
        "outer_fit_seconds": total("fit_seconds"),
        "outer_prediction_seconds": total("prediction_seconds"),
        "peak_rss_mb_max": max(peaks) if peaks else None,
        "device": sorted({record.device for record in records}),
    }


def _ordering(predictions: pd.DataFrame, records: list[TrialRecord]) -> dict[str, Any]:
    pooled = ordering_metrics(predictions)
    fold_ics: list[float] = []
    for fold in range(8):
        series = per_date_ic(
            predictions[predictions["outer_fold"] == fold],
            prediction_column="prediction", target_column="fwd_rank_21",
        )
        fold_ics.append(float(series.mean()))
    train_ics = [record.metrics.get("train_mean_rank_ic") for record in records]
    train = float(np.mean([value for value in train_ics if value is not None]))
    validation = pooled["mean_rank_ic"]
    gap = None if validation is None else train - float(validation)
    return {
        **pooled,
        "median_daily_rank_ic": float(per_date_ic(
            predictions, prediction_column="prediction", target_column="fwd_rank_21",
        ).median()),
        "fold_rank_ic": fold_ics,
        "positive_fold_count": sum(value > 0 for value in fold_ics),
        "worst_fold_rank_ic": min(fold_ics),
        "best_fold_rank_ic": max(fold_ics),
        "fold_rank_ic_std": float(np.std(fold_ics, ddof=1)),
        "train_mean_rank_ic": train,
        "train_validation_ic_gap": gap,
        "overfit_warning": bool(gap is not None and gap > 0.15),
        "overfit_threshold": 0.15,
    }


def _economics(
    predictions: pd.DataFrame,
    panel: pd.DataFrame,
    calendar: Any,
) -> tuple[dict[str, Any], pd.Series]:
    values = predictions[["date", "symbol", "prediction", "outer_fold"]].copy()
    values["date"] = pd.to_datetime(values["date"]).dt.date
    first, last = min(values["date"]), max(values["date"])
    schedule = exp010b.rebalance_schedule(
        calendar, exp010b.ARMS["B1"]["step_sessions"],
        first_prediction=first, last_prediction=last,
    )
    universe = panel[panel["in_universe"]].copy()
    aligned = exp010b.align_signals(values, universe, calendar, schedule)
    fold_by_grid = values.groupby("date")["outer_fold"].first().astype(int).to_dict()
    cost_sweep: dict[str, dict[str, Any]] = {}
    primary = None
    for bps in exp010b.COSTS:
        result, _, _ = exp010b.run_arm(aligned, panel, "B1", bps)
        metrics = result.metrics
        cost_sweep[f"{int(bps)}bp"] = {
            key: metrics.get(key) for key in (
                "gross_sharpe", "net_sharpe", "annualised_turnover",
                "cost_share_of_gross", "net_max_drawdown", "gross_max_drawdown",
                "gross_total_return", "net_total_return", "periods",
            )
        }
        if bps == PRIMARY_COST_BPS:
            primary = result
    if primary is None:
        raise RuntimeError("the frozen cost grid no longer contains the primary 10 bp cell")
    fold_of = exp010b.rebalance_folds(aligned, fold_by_grid)
    return {
        "cadence_sessions": 21,
        "portfolio_rule": dict(exp010b.PORTFOLIO),
        "primary_half_spread_bps": PRIMARY_COST_BPS,
        "cost_sweep": cost_sweep,
        "folds": exp010b.fold_table(primary.periods, fold_of, 252 / 21),
        "breakeven": breakeven_half_spread(primary.periods),
    }, primary.periods.set_index("date")["net_return"]


def _eligibility(ordering: dict[str, Any], complete_folds: bool) -> dict[str, Any]:
    gates = {
        "positive_mean_outer_rank_ic": bool((ordering["mean_rank_ic"] or 0.0) > 0),
        "acceptable_train_validation_gap": bool(
            ordering["train_validation_ic_gap"] is not None
            and ordering["train_validation_ic_gap"] <= 0.15
        ),
        "all_outer_folds_complete": complete_folds,
        "fold_stability": "REPORTED_NOT_NUMERICALLY_PREREGISTERED",
        "seed_stability": "PENDING_FIXED_SEED_ROBUSTNESS",
    }
    return {
        "eligible": False,
        "gates": gates,
        "reason": (
            "Eligibility remains false until the predeclared fold-stability language is "
            "operationalized without looking at outcomes and fixed-seed robustness is complete."
        ),
    }


def build_campaign_report(
    registry: TrialRegistry,
    *,
    method_commit: str,
    root: Path = Path("."),
) -> dict[str, Any]:
    predictions: dict[str, pd.DataFrame] = {}
    records_by_model: dict[str, list[TrialRecord]] = {}
    for model_name in CPU_MODELS:
        records = complete_outer_records(registry, model_name, method_commit=method_commit)
        records_by_model[model_name] = records
        predictions[model_name] = load_outer_predictions(records, root=root)

    expected_keys = None
    for model_name, frame in predictions.items():
        keys = set(map(tuple, frame[["date", "symbol", "outer_fold", "fwd_rank_21"]].itertuples(index=False, name=None)))
        if expected_keys is None:
            expected_keys = keys
        elif keys != expected_keys:
            raise RuntimeError(f"{model_name} outer OOS rows differ from the other families")

    panel, calendar = exp010b.build_daily_panel(root)
    panel_check = exp010b.verify_panel(panel, calendar)
    if not panel_check["passed"]:
        raise RuntimeError(f"frozen 21-session portfolio panel failed integrity: {panel_check['checks']}")

    cards: dict[str, dict[str, Any]] = {}
    net_returns: dict[str, pd.Series] = {}
    for model_name in CPU_MODELS:
        records = records_by_model[model_name]
        ordering = _ordering(predictions[model_name], records)
        economics, net = _economics(predictions[model_name], panel, calendar)
        net_returns[model_name] = net
        family = family_for(model_name)
        cards[model_name] = {
            "research_status": "EXPLORATORY",
            "promotion_status": "NOT_PROMOTED",
            "family": family.family,
            "model": model_name,
            "dataset_id": records[0].dataset_id,
            "dataset_hash": records[0].dataset_hash,
            "feature_set_id": records[0].feature_set_id,
            "feature_hash": records[0].feature_hash,
            "target": records[0].target,
            "search_space": list(family.configurations),
            "inner_cv": records[0].inner_cv_scheme,
            "outer_folds": 8,
            "selected_parameters_by_fold": {
                str(record.outer_fold): record.hyperparameters for record in records
            },
            "ordering": ordering,
            "economics": economics,
            "runtime": _runtime(records),
            "outer_prediction_hashes": {
                str(record.outer_fold): record.prediction_hash for record in records
            },
            "combined_prediction_hash": prediction_hash(predictions[model_name]),
            "method_commit": method_commit,
            "eligibility": _eligibility(ordering, True),
        }

    aligned_returns = pd.concat(net_returns, axis=1, join="inner").dropna()
    trial_sharpes = [
        float(series.mean() / series.std(ddof=1))
        for _, series in aligned_returns.items() if series.std(ddof=1) > 0
    ]
    attempts = len(registry.records())
    for model_name, card in cards.items():
        dsr = deflated_sharpe_ratio(
            aligned_returns[model_name].to_numpy(), trials=attempts,
            periods_per_year=252 / 21, trial_sharpes=trial_sharpes,
        )
        card["multiple_testing"] = dsr.as_dict()

    complete = [record for record in registry.records() if record.status is TrialStatus.COMPLETE]
    inner = [record for record in complete if record.phase == "INNER_SELECTION" and record.git_commit == method_commit]
    outer = [record for record in complete if record.phase == OUTER_PHASE and record.git_commit == method_commit]
    matrix = aligned_returns.to_numpy()
    pbo = probability_of_backtest_overfitting(matrix, blocks=8, seed=0)
    diversity = prediction_rank_correlation(predictions)

    eligible = [name for name, card in cards.items() if card["eligibility"]["eligible"]]
    ensemble: dict[str, Any]
    if len(eligible) >= 2:
        ensemble_predictions = equal_weight_rank_average({name: predictions[name] for name in eligible})
        ensemble = {
            "status": "EXPLORATORY",
            "members": eligible,
            "ordering": ordering_metrics(ensemble_predictions),
            "note": "Equal-weight cross-sectional rank average; no outer-fold weight tuning.",
        }
    else:
        ensemble = {
            "status": "BLOCKED",
            "members": eligible,
            "reason": "Fewer than two families satisfy the predeclared eligibility process.",
        }

    return {
        "campaign_id": "MODEL-LAB-001",
        "research_status": "EXPLORATORY",
        "method_commit": method_commit,
        "outer_oos_only": True,
        "holdout_touched": False,
        "exp012": "BLOCKED_NOT_PREPARED",
        "models": cards,
        "prediction_diversity": diversity.to_dict(orient="index"),
        "ensemble": ensemble,
        "multiple_testing": {
            "total_registry_attempts": attempts,
            "complete_trials_current_method": len(inner) + len(outer),
            "hyperparameter_trials": len(inner),
            "inner_fits": len(inner) * 3,
            "outer_evaluations": len(outer),
            "invalid_trials": sum(record.status is TrialStatus.INVALID for record in registry.records()),
            "failed_trials": sum(record.status is TrialStatus.FAILED for record in registry.records()),
            "pbo_selected_family_returns": pbo,
            "pbo_limit": (
                "PBO uses the ten complete selected-family OOS return series, not every inner "
                "hyperparameter candidate; this limitation prevents overclaiming."
            ),
            "white_reality_check": "NOT_IMPLEMENTED_UNSOUND_WITHOUT_VALIDATED_STATIONARY_BOOTSTRAP",
            "hansen_spa": "NOT_IMPLEMENTED_UNSOUND_WITHOUT_VALIDATED_STATIONARY_BOOTSTRAP",
        },
        "candidate_eligibility": {
            "eligible_models": eligible,
            "count": len(eligible),
            "status": "ZERO_ELIGIBLE_CANDIDATES" if not eligible else "EXPLORATORY_SHORTLIST",
        },
        "portfolio_integrity": panel_check,
    }


def write_campaign_report(
    registry: TrialRegistry,
    *,
    method_commit: str,
    root: Path = Path("."),
) -> Path:
    payload = build_campaign_report(registry, method_commit=method_commit, root=root)
    destination = root / REPORT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    cards = payload["models"]
    card_dir = root / CARD_DIR
    card_dir.mkdir(parents=True, exist_ok=True)
    for model_name, card in cards.items():
        (card_dir / f"{model_name}.json").write_text(
            json.dumps(card, indent=2, sort_keys=True), encoding="utf-8",
        )
    return destination
