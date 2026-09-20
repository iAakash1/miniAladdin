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
        "completed_trials": [record.model_dump(mode="json") for record in completed],
        # Failure, invalidation and resource-limit records are first-class
        # evidence. Keep their complete provenance in the published read model
        # rather than reducing them to a counter that cannot be audited.
        "retained_noncomplete_trials": [
            record.model_dump(mode="json") for record in retained_noncomplete
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


def write_summary(registry: TrialRegistry, path: Path | str = "data/manifests/model_lab_summary.json") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build_summary(registry), indent=2, sort_keys=True), encoding="utf-8")
    return destination
