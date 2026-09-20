"""Crash-safe SQLite ledger for every Model Lab trial, including failures."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TrialStatus(str, Enum):
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    PRUNED = "PRUNED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    BLOCKED = "BLOCKED"


class TrialRecord(BaseModel):
    trial_id: str
    campaign_id: str = "MODEL-LAB-001"
    phase: str
    model_family: str
    model_name: str
    dataset_id: str
    dataset_hash: str
    data_integrity_status: str
    feature_set_id: str
    feature_hash: str
    target: str = "fwd_rank_21"
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    seed: int
    outer_fold: int
    inner_cv_scheme: str
    git_commit: str
    dependency_versions: dict[str, str | None] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    device: str
    prediction_hash: str | None = None
    status: TrialStatus
    error: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def identity(cls, **parts: Any) -> str:
        encoded = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
        return "MLT-" + hashlib.sha256(encoded.encode()).hexdigest()[:16].upper()


class TrialRegistry:
    """One transaction per trial; interruption cannot erase finished work."""

    def __init__(self, path: Path | str = "data/research/model_lab/registry.sqlite") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS trials (
                    trial_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    model_family TEXT NOT NULL,
                    outer_fold INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS trial_family_status ON trials(model_family, status)"
            )

    def put(self, record: TrialRecord) -> None:
        payload = record.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO trials(trial_id,status,campaign_id,model_family,outer_fold,payload,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(trial_id) DO UPDATE SET
                     status=excluded.status, payload=excluded.payload, updated_at=excluded.updated_at""",
                (record.trial_id, record.status.value, record.campaign_id,
                 record.model_family, record.outer_fold, payload, now),
            )

    def get(self, trial_id: str) -> TrialRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM trials WHERE trial_id=?", (trial_id,),
            ).fetchone()
        return TrialRecord.model_validate_json(row["payload"]) if row else None

    def completed(self, trial_id: str) -> bool:
        record = self.get(trial_id)
        return record is not None and record.status is TrialStatus.COMPLETE

    def records(self, *, campaign_id: str = "MODEL-LAB-001") -> list[TrialRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM trials WHERE campaign_id=? ORDER BY updated_at, trial_id",
                (campaign_id,),
            ).fetchall()
        return [TrialRecord.model_validate_json(row["payload"]) for row in rows]

    def summary(self, *, campaign_id: str = "MODEL-LAB-001") -> dict[str, Any]:
        records = self.records(campaign_id=campaign_id)
        statuses = {status.value: 0 for status in TrialStatus}
        families: dict[str, dict[str, Any]] = {}
        for record in records:
            statuses[record.status.value] += 1
            family = families.setdefault(record.model_family, {"trials": 0, "complete": 0, "failed": 0})
            family["trials"] += 1
            family["complete"] += int(record.status is TrialStatus.COMPLETE)
            family["failed"] += int(record.status in {TrialStatus.FAILED, TrialStatus.INVALID, TrialStatus.RESOURCE_LIMIT})
        return {
            "campaign_id": campaign_id,
            "research_status": "EXPLORATORY",
            "trials": len(records),
            "statuses": statuses,
            "families": families,
        }
