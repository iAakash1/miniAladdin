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
    return {
        **registry.summary(),
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
        "promotion": "NOT_ASSESSED",
        "interpretation": "Exploratory validation evidence; requires separately preregistered replication.",
    }


def write_summary(registry: TrialRegistry, path: Path | str = "data/manifests/model_lab_summary.json") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(build_summary(registry), indent=2, sort_keys=True), encoding="utf-8")
    return destination
