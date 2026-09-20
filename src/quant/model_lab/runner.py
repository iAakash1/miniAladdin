"""Resumable nested temporal CV for the locally executable Model Lab families."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.quant.model_lab.compute import ComputeProbe
from src.quant.model_lab.evaluation import ordering_metrics, prediction_hash
from src.quant.model_lab.inner_cv import assert_outer_isolation, build_inner_plan
from src.quant.model_lab.registry import TrialRecord, TrialRegistry, TrialStatus
from src.quant.model_lab.report import write_summary
from src.quant.model_lab.search_space import build_spec, family_for
from src.quant.models.base import FoldImputer
from src.quant.models.registry import dependency_versions
from src.quant.pit import rich_panel as R
from src.quant.study import exp009b
from src.quant.study.firewall import FIREWALL

CAMPAIGN_ID = "MODEL-LAB-001"
DATASET_ID = "ds-richpit2-6368cccdb94c62d0"
DATASET_HASH = "6368cccdb94c62d09dd048b972ae75272721f4f6cc56f246ccf36cff63319d8e"
F0_CONTENT_HASH = "3141e8d2a6635c66def0d20dbef0f4dd6bebd88b5d828f48f204b3ccea1a6e15"
PANEL = Path("data/research/derived/rich_pit_v2_panel.parquet")
MANIFEST = Path("data/manifests/rich_pit_v2_manifest.json")
REVENUE_AUDIT = Path("data/manifests/exp011_revenue_mapping_impact.json")
FEATURE_SET_ID = "F0_UNAFFECTED_BASELINE_26"
TARGET = "fwd_rank_21"
INNER_SCHEME = "expanding-3-split-65-session-validation-purged-21-plus-5-sessions-v2"
PREDICTION_DIR = Path("data/research/model_lab/predictions")


def _git_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, timeout=2, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def feature_hash(features: Iterable[str]) -> str:
    payload = json.dumps(list(features), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def load_dataset(root: Path = Path(".")) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load only the revenue-unaffected F0 block and enforce every data gate."""
    root = Path(root)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    revenue = json.loads((root / REVENUE_AUDIT).read_text(encoding="utf-8"))
    if manifest.get("dataset_id") != DATASET_ID or manifest.get("content_hash") != DATASET_HASH:
        raise RuntimeError("MODEL-LAB dataset identity does not match the declared campaign")
    if revenue.get("classification") != "UNRESOLVED_MAPPING_IMPACT":
        raise RuntimeError("revenue integrity status changed; re-review feature-set eligibility before fitting")
    affected = set(revenue["feature_impact"]["by_feature"])
    overlap = affected.intersection(R.BASELINE_FEATURES)
    if overlap:
        raise RuntimeError(f"F0 is no longer revenue-unaffected: {sorted(overlap)}")
    old = manifest.get("old_block_invariance", {})
    if old.get("changed_cells") != 0:
        raise RuntimeError("the frozen feature block changed in Rich PIT v2")

    exp009b.arm_firewall(root)
    frame = pd.read_parquet(root / PANEL)
    frame["date"] = pd.to_datetime(frame["date"])
    required = {"date", "symbol", "in_universe", TARGET, *R.BASELINE_FEATURES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise RuntimeError(f"MODEL-LAB panel is missing {missing}")
    if len(frame) != int(manifest["rows"]):
        raise RuntimeError("MODEL-LAB panel row count differs from its manifest")
    if frame["date"].max().date().isoformat() != manifest["date_max"]:
        raise RuntimeError("MODEL-LAB panel maximum date differs from its manifest")
    observed_f0_hash = R.content_hash(frame, ["date", "symbol", TARGET, *R.BASELINE_FEATURES])
    if observed_f0_hash != F0_CONTENT_HASH:
        raise RuntimeError("MODEL-LAB F0 values differ from the declared unaffected block")
    FIREWALL.assert_clear(frame, context="MODEL-LAB-001 dataset")
    # The repository's recorded Fold contract uses datetime.date. Normalise
    # only after hashing so representation cannot change the pinned content.
    frame["date"] = frame["date"].dt.date
    return frame, {
        "dataset_id": DATASET_ID,
        "dataset_hash": DATASET_HASH,
        "feature_set_id": FEATURE_SET_ID,
        "feature_hash": feature_hash(R.BASELINE_FEATURES),
        "block_content_hash": F0_CONTENT_HASH,
        "features": list(R.BASELINE_FEATURES),
        "integrity_status": "VALIDATED_UNAFFECTED_BLOCK",
        "revenue_affected_feature_sets": "BLOCKED",
        "holdout_touched": False,
    }


def _fit_predict(
    model_name: str,
    params: dict[str, Any],
    seed: int,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    train = train.dropna(subset=[TARGET])
    validation = validation.dropna(subset=[TARGET])
    FIREWALL.assert_clear(train, context=f"MODEL-LAB {model_name} TRAIN")
    FIREWALL.assert_clear(validation, context=f"MODEL-LAB {model_name} VALIDATION")
    spec = build_spec(model_name, params, seed, suffix="nested")
    model = spec.build()
    imputer = FoldImputer(standardise=model.requires_scaling)
    X_train = imputer.fit_transform(train[features].to_numpy(float), feature_names=features)
    X_validation = imputer.transform(validation[features].to_numpy(float))
    groups = train["date"].to_numpy() if getattr(model, "requires_groups", False) else None

    caught: list[warnings.WarningMessage]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        fit_started = time.perf_counter()
        model.fit(X_train, train[TARGET].to_numpy(float), feature_names=features, groups=groups)
        fit_seconds = time.perf_counter() - fit_started
        predict_started = time.perf_counter()
        values = model.predict(X_validation)
        prediction_seconds = time.perf_counter() - predict_started
    if not np.isfinite(values).all():
        raise RuntimeError("validation predictions contain non-finite values")

    scored = validation[["date", "symbol", TARGET]].copy()
    scored["prediction"] = values
    train_scored = train[["date", "symbol", TARGET]].copy()
    with warnings.catch_warnings(record=True) as train_caught:
        warnings.simplefilter("always", RuntimeWarning)
        train_values = model.predict(X_train)
    caught.extend(train_caught)
    if not np.isfinite(train_values).all():
        raise RuntimeError("training predictions contain non-finite values")
    train_scored["prediction"] = train_values
    return scored, ordering_metrics(scored), {
        "train": ordering_metrics(train_scored),
        "fit_seconds": fit_seconds,
        "prediction_seconds": prediction_seconds,
        "runtime_warnings": sorted({f"{type(item.message).__name__}: {item.message}" for item in caught}),
    }


def _record(
    *, registry: TrialRegistry, identity: dict[str, Any], metadata: dict[str, Any],
    params: dict[str, Any], phase: str, family: str, model_name: str, seed: int,
    outer_fold: int, status: TrialStatus, runtime: dict[str, Any],
    metrics: dict[str, Any] | None = None, prediction_sha: str | None = None,
    error: str | None = None,
) -> TrialRecord:
    trial_id = TrialRecord.identity(**identity)
    record = TrialRecord(
        trial_id=trial_id, phase=phase, model_family=family, model_name=model_name,
        dataset_id=metadata["dataset_id"], dataset_hash=metadata["dataset_hash"],
        data_integrity_status=metadata["integrity_status"],
        feature_set_id=metadata["feature_set_id"], feature_hash=metadata["feature_hash"],
        hyperparameters=params, seed=seed, outer_fold=outer_fold,
        inner_cv_scheme=INNER_SCHEME, git_commit=identity["git_commit"],
        dependency_versions=dependency_versions(), runtime=runtime, device="MAC_CPU",
        prediction_hash=prediction_sha, status=status, error=error,
        metrics=metrics or {},
    )
    registry.put(record)
    return record


def run_family(
    model_name: str,
    *,
    registry: TrialRegistry,
    root: Path = Path("."),
    outer_folds: Iterable[int] = range(8),
    max_configs: int | None = None,
    seed: int = 0,
    evaluate_outer: bool = True,
) -> list[TrialRecord]:
    """Nested selection per outer fold; outer validation is never used to tune."""
    root = Path(root)
    family = family_for(model_name)
    available = family.availability()
    if available["status"] != "READY" or family.route != "MAC_CPU":
        raise RuntimeError(available["reason"] if available["status"] != "READY" else f"{model_name} is routed to {family.route}")
    frame, metadata = load_dataset(root)
    plan = exp009b.recorded_plan(root)
    features = metadata["features"]
    commit = _git_commit(root)
    configs = list(family.configurations)[:max_configs]
    output: list[TrialRecord] = []

    for outer_index in outer_folds:
        outer = plan.folds[outer_index]
        outer_train, outer_validation = outer.split(frame)
        outer_train = outer_train[outer_train["in_universe"]].reset_index(drop=True)
        outer_validation = outer_validation[outer_validation["in_universe"]].reset_index(drop=True)
        inner_plan = build_inner_plan(outer_train)
        if len(inner_plan.splits) != 3:
            raise RuntimeError(
                f"outer fold {outer_index} produced {len(inner_plan.splits)} inner splits; exactly 3 are required"
            )
        assert_outer_isolation(inner_plan, outer_validation)
        candidates: list[tuple[float, dict[str, Any], str]] = []

        for config_index, params in enumerate(configs):
            identity = {
                "campaign": CAMPAIGN_ID, "phase": "INNER_SELECTION",
                "model": model_name, "params": params, "seed": seed,
                "outer_fold": outer_index, "git_commit": commit,
                "dataset_hash": DATASET_HASH, "feature_set": FEATURE_SET_ID,
                "inner_cv_scheme": INNER_SCHEME,
            }
            trial_id = TrialRecord.identity(**identity)
            existing = registry.get(trial_id)
            if existing and existing.status is TrialStatus.COMPLETE:
                value = existing.metrics.get("mean_inner_rank_ic")
                if value is not None:
                    candidates.append((float(value), params, trial_id))
                output.append(existing)
                continue
            probe = ComputeProbe()
            scores: list[float] = []
            split_metrics: list[dict[str, Any]] = []
            try:
                for inner in inner_plan:
                    train, validation = inner.split(outer_train)
                    predictions, metrics, timing = _fit_predict(
                        model_name, params, seed, train, validation, features,
                    )
                    probe.fit_seconds += timing["fit_seconds"]
                    probe.prediction_seconds += timing["prediction_seconds"]
                    if metrics["mean_rank_ic"] is None:
                        raise RuntimeError(f"inner split {inner.index} produced no Rank IC")
                    scores.append(float(metrics["mean_rank_ic"]))
                    split_metrics.append({
                        "inner_split": inner.index, **metrics,
                        "runtime_warnings": timing["runtime_warnings"],
                    })
                aggregate = float(np.mean(scores))
                metrics = {"mean_inner_rank_ic": aggregate, "inner_splits": split_metrics}
                record = _record(
                    registry=registry, identity=identity, metadata=metadata, params=params,
                    phase="INNER_SELECTION", family=family.family, model_name=model_name,
                    seed=seed, outer_fold=outer_index, status=TrialStatus.COMPLETE,
                    runtime=probe.finish(), metrics=metrics,
                )
                candidates.append((aggregate, params, record.trial_id))
            except Exception as error:  # every failure is a retained result
                record = _record(
                    registry=registry, identity=identity, metadata=metadata, params=params,
                    phase="INNER_SELECTION", family=family.family, model_name=model_name,
                    seed=seed, outer_fold=outer_index, status=TrialStatus.FAILED,
                    runtime=probe.finish(), error=f"{type(error).__name__}: {error}",
                )
            output.append(record)

        if not candidates or not evaluate_outer:
            continue
        # Selection sees INNER metrics only. Outer validation has not been fit,
        # transformed, predicted or scored above this line.
        _, selected, source_trial = max(candidates, key=lambda row: (row[0], json.dumps(row[1], sort_keys=True)))
        identity = {
            "campaign": CAMPAIGN_ID, "phase": "OUTER_EVALUATION",
            "model": model_name, "params": selected, "seed": seed,
            "outer_fold": outer_index, "git_commit": commit,
            "dataset_hash": DATASET_HASH, "feature_set": FEATURE_SET_ID,
            "inner_cv_scheme": INNER_SCHEME,
        }
        trial_id = TrialRecord.identity(**identity)
        existing = registry.get(trial_id)
        if existing and existing.status is TrialStatus.COMPLETE:
            output.append(existing)
            continue
        probe = ComputeProbe()
        try:
            predictions, metrics, timing = _fit_predict(
                model_name, selected, seed, outer_train, outer_validation, features,
            )
            predictions["outer_fold"] = outer_index
            PREDICTION_DIR.mkdir(parents=True, exist_ok=True)
            predictions.to_parquet(PREDICTION_DIR / f"{trial_id}.parquet", index=False)
            probe.fit_seconds += timing["fit_seconds"]
            probe.prediction_seconds += timing["prediction_seconds"]
            train_ic = timing["train"].get("mean_rank_ic")
            validation_ic = metrics.get("mean_rank_ic")
            metrics.update({
                "train_mean_rank_ic": train_ic,
                "train_validation_ic_gap": (
                    None if train_ic is None or validation_ic is None
                    else float(train_ic - validation_ic)
                ),
                "selected_by_inner_trial": source_trial,
                "selected_hyperparameters": selected,
                "runtime_warnings": timing["runtime_warnings"],
            })
            record = _record(
                registry=registry, identity=identity, metadata=metadata, params=selected,
                phase="OUTER_EVALUATION", family=family.family, model_name=model_name,
                seed=seed, outer_fold=outer_index, status=TrialStatus.COMPLETE,
                runtime=probe.finish(), metrics=metrics,
                prediction_sha=prediction_hash(predictions),
            )
        except Exception as error:
            record = _record(
                registry=registry, identity=identity, metadata=metadata, params=selected,
                phase="OUTER_EVALUATION", family=family.family, model_name=model_name,
                seed=seed, outer_fold=outer_index, status=TrialStatus.FAILED,
                runtime=probe.finish(), error=f"{type(error).__name__}: {error}",
            )
        output.append(record)
        write_summary(registry, root / "data/manifests/model_lab_summary.json")
    return output
