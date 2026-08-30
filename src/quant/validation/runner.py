"""
Walk-forward driver — fit, predict, score, and record what happened.

## Every model, every fold, one code path

The driver is deliberately dumb. It fits a `Model` on a fold's training rows,
predicts its validation rows, computes the same metrics, and appends a record.
`ZeroBaseline` and a gradient-boosted forest travel identical code, which is
what makes their numbers comparable — a baseline evaluated by different code is
a rhetorical device, not a control.

## What is recorded, and why all of it

Every experiment, not only the ones that worked. `ExperimentLog` holds the full
set and `leaderboard()` sorts it, but `distribution()` reports the whole
population — because the maximum of forty experiments is a biased estimate of
the best model's true performance, and reporting the maximum alone is how
multiple-comparison bias enters a research record silently.

## The imputer is refitted every fold

`FoldImputer` is constructed inside the fold loop and fitted on training rows
only. Hoisting it out — computing medians and scales once over the whole
sample — is a small, real leak: the validation fold's distribution informs the
transform applied to it. It is easy to introduce, it improves results slightly,
and nothing downstream reveals it. So it is structurally impossible here: the
imputer does not exist outside the loop.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd

from src.quant.models.base import FoldImputer, Model
from src.quant.validation.metrics import (
    calibration_bins,
    classification_metrics,
    expected_calibration_error,
    ic_summary,
    per_date_ic,
    regression_metrics,
)
from src.quant.validation.walkforward import WalkForwardPlan

from src.quant.study.firewall import FIREWALL

logger = logging.getLogger("omnisignal.quant.validation.runner")


@dataclass
class FoldResult:
    """One model on one fold."""

    fold_index: int
    train_rows: int
    validation_rows: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    metrics: dict[str, Any]
    ic: dict[str, Any]
    fit_seconds: float
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "train_rows": self.train_rows,
            "validation_rows": self.validation_rows,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "metrics": dict(self.metrics),
            "ic": dict(self.ic),
            "fit_seconds": round(self.fit_seconds, 3),
            "warnings": list(self.warnings),
        }


@dataclass
class ExperimentResult:
    """One model against one label over the whole plan."""

    model_id: str
    model_version: str
    label: str
    task: str
    fingerprint: str
    features: list[str]
    folds: list[FoldResult]
    pooled_metrics: dict[str, Any]
    pooled_ic: dict[str, Any]
    calibration: list[dict[str, Any]]
    explanation: dict[str, Any]
    predictions: Optional[pd.DataFrame] = None
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.errors) and not self.folds

    def fold_metric(self, name: str) -> list[float]:
        out = []
        for fold in self.folds:
            value = fold.metrics.get(name)
            if isinstance(value, (int, float)) and np.isfinite(value):
                out.append(float(value))
        return out

    def stability(self, name: str) -> dict[str, Any]:
        """Spread of a metric across folds.

        A model whose IC is 0.05 in every fold and one whose IC averages 0.05
        from +0.20 and -0.10 are entirely different propositions, and the mean
        alone cannot tell them apart. `fold_positive_rate` is the more
        informative half.
        """
        values = self.fold_metric(name)
        if len(values) < 2:
            return {"folds": len(values), "mean": None, "std": None, "min": None, "max": None}
        return {
            "folds": len(values),
            "mean": float(np.mean(values)),
            "std": float(np.std(values, ddof=1)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "fold_positive_rate": float(np.mean(np.asarray(values) > 0)),
        }

    def as_dict(self, *, include_folds: bool = True) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "label": self.label,
            "task": self.task,
            "fingerprint": self.fingerprint,
            "features": list(self.features),
            "fold_count": len(self.folds),
            "pooled_metrics": dict(self.pooled_metrics),
            "pooled_ic": dict(self.pooled_ic),
            "calibration": list(self.calibration),
            "explanation": dict(self.explanation),
            "stability_ic": self.stability("spearman"),
            "seconds": round(self.seconds, 2),
            "errors": list(self.errors),
            "folds": [fold.as_dict() for fold in self.folds] if include_folds else [],
        }


def run_walk_forward(
    model_factory: Callable[[], Model],
    dataset_frame: pd.DataFrame,
    plan: WalkForwardPlan,
    *,
    features: Sequence[str],
    label: str,
    step_sessions: int,
    date_column: str = "date",
    symbol_column: str = "symbol",
    keep_predictions: bool = True,
    universe_only: bool = True,
    on_fold: Optional[Any] = None,
) -> ExperimentResult:
    """Fit and score one model across every fold.

    `model_factory` rather than a model instance, because a fitted model must
    not carry state between folds. Reusing one object would let fold 3's
    coefficients initialise fold 4 — a subtle information path from the past
    that is not the training data.
    """
    began = time.perf_counter()
    probe = model_factory()
    feature_list = list(features)

    frame = dataset_frame
    if universe_only and "in_universe" in frame.columns:
        # Restrict to point-in-time universe members. A cross-sectional metric
        # over names that were not investable on the date measures nothing
        # anyone could have traded.
        frame = frame[frame["in_universe"]]

    usable = frame.dropna(subset=[label])
    fold_results: list[FoldResult] = []
    collected: list[pd.DataFrame] = []
    errors: list[str] = []
    explanation: dict[str, Any] = {}

    for fold in plan.folds:
        train, validation = fold.split(usable, date_column=date_column)
        if train.empty or validation.empty:
            errors.append(f"fold {fold.index}: empty train or validation split")
            continue

        # The firewall, at the only place that matters: immediately before rows
        # become a fit. A plan that reserved the holdout correctly cannot reach
        # here with holdout rows, so this is a guard against the plan being
        # wrong — which is exactly the case a fold-level assertion cannot make.
        FIREWALL.assert_clear(
            train, context=f"walk-forward fold {fold.index} TRAIN", date_column=date_column
        )
        FIREWALL.assert_clear(
            validation, context=f"walk-forward fold {fold.index} VALIDATION",
            date_column=date_column,
        )

        X_train = train[feature_list].to_numpy(dtype=float)
        y_train = train[label].to_numpy(dtype=float)
        X_validation = validation[feature_list].to_numpy(dtype=float)
        y_validation = validation[label].to_numpy(dtype=float)

        # Fitted here, inside the loop, on training rows only. See the module
        # docstring — hoisting this out is the leak.
        imputer = FoldImputer(standardise=probe.requires_scaling)
        X_train_ready = imputer.fit_transform(X_train, feature_names=feature_list)
        X_validation_ready = imputer.transform(X_validation)

        model = model_factory()
        fold_started = time.perf_counter()
        try:
            model.fit(X_train_ready, y_train, feature_names=feature_list)
            predictions = model.predict(X_validation_ready)
        except Exception as error:  # noqa: BLE001 — recorded, never hidden
            errors.append(f"fold {fold.index}: {type(error).__name__}: {error}")
            logger.warning("walk-forward %s fold %d failed: %s", probe.model_id, fold.index, error)
            continue
        fit_seconds = time.perf_counter() - fold_started

        scale_free = bool(getattr(model, "scale_free", False))
        if probe.task == "classification":
            metrics = classification_metrics(y_validation, predictions)
        else:
            metrics = regression_metrics(y_validation, predictions, scale_free=scale_free)

        # In-sample metrics on the training fold. Reported, never used for
        # selection: the gap between them and the validation metrics is the
        # overfitting signal, and a study that computes only the validation
        # side cannot show it. `train_ic_gap` is the number to watch — a model
        # with train IC 0.30 and validation IC 0.02 has memorised the fold.
        train_metrics = {}
        try:
            in_sample = model.predict(X_train_ready)
            train_scored = train[[date_column, symbol_column, label]].copy()
            train_scored["prediction"] = in_sample
            train_ic = ic_summary(
                per_date_ic(
                    train_scored, prediction_column="prediction",
                    target_column=label, date_column=date_column,
                ),
                horizon_sessions=plan.label_horizon_sessions,
                step_sessions=step_sessions,
            )
            train_metrics = {
                "train_mean_ic": train_ic.get("mean_ic"),
                "train_spearman": (
                    regression_metrics(y_train, in_sample, scale_free=scale_free)
                    .values.get("spearman")
                ),
            }
        except Exception as error:  # noqa: BLE001 — an absent gap is not a failed fold
            logger.debug("in-sample metrics unavailable for %s: %s", probe.model_id, error)

        scored = validation[[date_column, symbol_column, label]].copy()
        scored["prediction"] = predictions
        scored["fold"] = fold.index
        ic = ic_summary(
            per_date_ic(
                scored, prediction_column="prediction", target_column=label,
                date_column=date_column,
            ),
            horizon_sessions=plan.label_horizon_sessions,
            step_sessions=step_sessions,
        )

        fold_results.append(
            FoldResult(
                fold_index=fold.index,
                train_rows=len(train),
                validation_rows=len(validation),
                train_start=str(fold.train_start),
                train_end=str(fold.train_end),
                validation_start=str(fold.validation_start),
                validation_end=str(fold.validation_end),
                metrics={**metrics.as_dict(), **train_metrics},
                ic=ic,
                fit_seconds=fit_seconds,
                warnings=list(metrics.notes),
            )
        )
        if keep_predictions:
            collected.append(scored)
        explanation = model.explain().as_dict()
        if on_fold is not None:
            on_fold(probe.model_id, fold.index, ic.get("mean_ic"), train_metrics.get("train_mean_ic"))

    predictions_frame = (
        pd.concat(collected, ignore_index=True) if collected else None
    )

    # Pooled metrics come from concatenated OUT-OF-SAMPLE predictions across
    # every fold. Not an average of fold metrics: folds differ in size, and
    # averaging their scores weights a thin fold equally with a full one.
    pooled_metrics: dict[str, Any] = {}
    pooled_ic: dict[str, Any] = {}
    calibration: list[dict[str, Any]] = []
    if predictions_frame is not None and not predictions_frame.empty:
        truth = predictions_frame[label].to_numpy(dtype=float)
        predicted = predictions_frame["prediction"].to_numpy(dtype=float)
        scale_free = bool(getattr(probe, "scale_free", False))
        if probe.task == "classification":
            pooled = classification_metrics(truth, predicted)
            calibration = calibration_bins(truth, predicted)
            pooled.values["expected_calibration_error"] = expected_calibration_error(
                truth, predicted
            )
        else:
            pooled = regression_metrics(truth, predicted, scale_free=scale_free)
        pooled_metrics = pooled.as_dict()
        pooled_ic = ic_summary(
            per_date_ic(
                predictions_frame, prediction_column="prediction",
                target_column=label, date_column=date_column,
            ),
            horizon_sessions=plan.label_horizon_sessions,
            step_sessions=step_sessions,
        )

    result = ExperimentResult(
        model_id=probe.model_id,
        model_version=probe.version,
        label=label,
        task=probe.task,
        fingerprint=probe.fingerprint(),
        features=feature_list,
        folds=fold_results,
        pooled_metrics=pooled_metrics,
        pooled_ic=pooled_ic,
        calibration=calibration,
        explanation=explanation,
        predictions=predictions_frame,
        seconds=time.perf_counter() - began,
        errors=errors,
    )
    logger.info(
        "walk-forward %s/%s: %d folds, mean IC %s, %.1fs",
        probe.model_id, label, len(fold_results),
        _fmt(pooled_ic.get("mean_ic")), result.seconds,
    )
    return result


@dataclass
class ExperimentLog:
    """Every experiment run, winners and failures alike.

    The population matters as much as the maximum. Forty experiments produce a
    best result that is optimistically biased by selection alone, and the only
    defence is to report how many were run and what the whole distribution
    looked like. `distribution()` does that; `leaderboard()` is for reading.
    """

    results: list[ExperimentResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, result: ExperimentResult) -> None:
        self.results.append(result)

    def leaderboard(
        self, *, label: Optional[str] = None, metric: str = "mean_ic"
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in self.results:
            if label and result.label != label:
                continue
            pooled = result.pooled_metrics
            rows.append(
                {
                    "model_id": result.model_id,
                    "label": result.label,
                    "folds": len(result.folds),
                    "mean_ic": result.pooled_ic.get("mean_ic"),
                    "ic_t_stat": result.pooled_ic.get("t_stat"),
                    "ic_ir": result.pooled_ic.get("ic_ir"),
                    "rmse_vs_zero": pooled.get("rmse_vs_zero"),
                    "directional_edge": pooled.get("directional_edge"),
                    "spearman": pooled.get("spearman"),
                    "fold_ic_positive_rate": result.stability("spearman").get(
                        "fold_positive_rate"
                    ),
                    "train_mean_ic": result.stability("train_mean_ic").get("mean"),
                    "train_ic_gap": _gap(result),
                    "seconds": round(result.seconds, 2),
                    "errors": len(result.errors),
                }
            )
        return sorted(
            rows,
            key=lambda row: (row.get(metric) is None, -(row.get(metric) or 0.0)),
        )

    def distribution(self, *, label: Optional[str] = None, metric: str = "mean_ic") -> dict[str, Any]:
        """The whole population of results, so the winner can be read in context."""
        values = [
            row[metric]
            for row in self.leaderboard(label=label, metric=metric)
            if isinstance(row.get(metric), (int, float))
        ]
        if not values:
            return {"experiments": 0}
        array = np.asarray(values, dtype=float)
        return {
            "experiments": len(array),
            "metric": metric,
            "best": float(np.max(array)),
            "median": float(np.median(array)),
            "worst": float(np.min(array)),
            "mean": float(np.mean(array)),
            "std": float(np.std(array, ddof=1)) if len(array) > 1 else None,
            "above_zero": int(np.sum(array > 0)),
            "note": (
                "The best of N experiments is an optimistically biased estimate of that "
                "model's true performance. Read `best` against `median` and `experiments`, "
                "and against the deflated Sharpe ratio in the backtest report."
            ),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiments": len(self.results),
            "failed": sum(1 for result in self.results if result.failed),
            "labels": sorted({result.label for result in self.results}),
            "models": sorted({result.model_id for result in self.results}),
            "results": [result.as_dict(include_folds=False) for result in self.results],
            "notes": list(self.notes),
        }


def _gap(result: "ExperimentResult") -> Optional[float]:
    """Mean train IC minus mean validation IC across folds.

    The overfitting number. A large positive gap says the model fits its
    training fold and does not carry that to the next period, which is the
    single most useful diagnostic in the whole table and the one a
    validation-only report cannot produce.
    """
    train = result.fold_metric("train_mean_ic")
    validation = [
        fold.ic.get("mean_ic") for fold in result.folds
        if isinstance(fold.ic.get("mean_ic"), (int, float))
    ]
    if not train or not validation:
        return None
    return float(np.mean(train) - np.mean(validation))


def _fmt(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.4f}"
