"""Small committed summary derived from the local trial database."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.quant.model_lab.registry import TrialRegistry, TrialStatus
from src.quant.model_lab.search_space import families


def build_summary(registry: TrialRegistry) -> dict[str, Any]:
    records = registry.records()
    completed = [record for record in records if record.status is TrialStatus.COMPLETE]
    retained_noncomplete = [record for record in records if record.status is not TrialStatus.COMPLETE]
    outer = [record for record in completed if record.phase == "OUTER_EVALUATION"]
    outer_ics = [record.metrics.get("mean_rank_ic") for record in outer]
    finite_outer_ics = [float(value) for value in outer_ics if value is not None]
    return {
        **registry.summary(),
        "campaign_stage": "SMOKE_COMPLETE" if outer else "INFRASTRUCTURE_ONLY",
        "declared_families": families(),
        "dataset": {
            "dataset_id": "ds-richpit2-6368cccdb94c62d0",
            "feature_set_id": "F0_UNAFFECTED_BASELINE_26",
            "integrity_status": "VALIDATED_UNAFFECTED_BLOCK",
            "revenue_affected_feature_sets": "BLOCKED",
        },
        "holdout": {"start": "2025-08-26", "end": "2026-08-28", "touched": False},
        "exp012": {"status": "BLOCKED_NOT_PREPARED"},
        # Only outer evaluations are needed by the production UI. Inner-fit
        # provenance remains complete in the crash-safe local SQLite ledger;
        # serialising hundreds of full records into one API response created a
        # 1.4 MB payload and a measured ~25 MB request RSS increase.
        "completed_trials": [
            _published_trial(record) for record in outer
        ],
        "completed_inner_trial_count": len(completed) - len(outer),
        # Non-complete evidence stays individually inspectable because the
        # reason a trial was refused is part of the research record.
        "retained_noncomplete_trials": [
            _published_trial(record, include_error=True) for record in retained_noncomplete
        ],
        "smoke_outcome": {
            "outer_evaluations": len(outer),
            "positive_outer_rank_ic": sum(value > 0 for value in finite_outer_ics),
            "negative_outer_rank_ic": sum(value < 0 for value in finite_outer_ics),
            "candidate_eligible": False,
            "reason": (
                "Smoke evidence cannot establish eligibility; the complete eight-fold campaign "
                "and preregistered confirmation remain required."
            ),
        },
        "promotion": "NOT_ASSESSED",
        "interpretation": "Exploratory validation evidence; requires separately preregistered replication.",
    }


def _published_trial(record, *, include_error: bool = False) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    metrics = payload.get("metrics") or {}
    runtime = payload.get("runtime") or {}
    result = {key: payload.get(key) for key in (
        "trial_id", "phase", "model_family", "model_name", "outer_fold",
        "status", "hyperparameters", "git_commit",
    )}
    result["metrics"] = {key: metrics.get(key) for key in (
        "mean_rank_ic", "hac_t_stat", "train_validation_ic_gap", "runtime_warnings",
    )}
    result["runtime"] = {"wall_seconds": runtime.get("wall_seconds")}
    if include_error:
        result["error"] = payload.get("error")
    return result


def write_summary(registry: TrialRegistry, path: Path | str = "data/manifests/model_lab_summary.json") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build_summary(registry), indent=2, sort_keys=True), encoding="utf-8")
    return destination
