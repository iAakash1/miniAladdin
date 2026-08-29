"""
Model registry — what exists, what it was measured at, and what it is allowed to do.

## Promotion is gated, not recorded

The brief's rule is the design constraint: *no model becomes production merely
because it has the highest backtest return.* So the registry does not simply
store a status field for a human to set. `promote()` evaluates
`PROMOTION_GATES` and refuses a transition whose evidence is absent, returning
the specific unmet requirements.

The gates, and the failure each one blocks:

``validated``
    Requires walk-forward folds, a recorded methodology, and a stated
    comparison against a baseline. Blocks "it looked good on the training set".

``production_candidate``
    Additionally requires a cost-aware backtest and factor attribution. Blocks
    a signal with a strong IC and turnover that eats it, and blocks a strategy
    that is momentum in disguise being described as new.

``production``
    Additionally requires holdout metrics and regime-stability evidence. Blocks
    a model selected on the same folds it is reported against, and one that
    worked only in the regime that dominated the sample.

A model can also be `retired` from anywhere, with a reason. Retirement needs no
evidence — stopping is always allowed.

## The experiment count is stored

`ModelEntry.experiments_run` records how many configurations were tried before
this one was registered. The best of forty experiments is an optimistically
biased estimate, and a registry that stores only the winner destroys the
information needed to discount it. The leaderboard renders it.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("omnisignal.quant.models.registry")

REGISTRY_SCHEMA_VERSION = 1
DEFAULT_ROOT = Path("data/research/models")

STATUSES: tuple[str, ...] = (
    "experimental",
    "validated",
    "production_candidate",
    "production",
    "retired",
)

#: Evidence each status requires. Keys are `ModelEntry` attributes that must be
#: present and non-empty; the message is what a caller is told when they are not.
PROMOTION_GATES: dict[str, list[tuple[str, str]]] = {
    "validated": [
        ("walk_forward", "walk-forward fold results"),
        ("validation_methodology", "a written validation methodology"),
        ("baseline_comparison", "a comparison against at least one baseline"),
    ],
    "production_candidate": [
        ("walk_forward", "walk-forward fold results"),
        ("validation_methodology", "a written validation methodology"),
        ("baseline_comparison", "a comparison against at least one baseline"),
        ("backtest", "a transaction-cost-aware backtest"),
        ("factor_attribution", "a factor-model attribution of its returns"),
    ],
    "production": [
        ("walk_forward", "walk-forward fold results"),
        ("validation_methodology", "a written validation methodology"),
        ("baseline_comparison", "a comparison against at least one baseline"),
        ("backtest", "a transaction-cost-aware backtest"),
        ("factor_attribution", "a factor-model attribution of its returns"),
        ("holdout_metrics", "metrics on the untouched holdout period"),
        ("regime_stability", "performance broken out by market regime"),
    ],
}


class PromotionRefused(ValueError):
    """Raised when a status change lacks the evidence that status requires."""


@dataclass
class ModelEntry:
    """One registered model and everything measured about it."""

    model_id: str
    version: str
    task: str
    label: str
    status: str = "experimental"

    features: list[str] = field(default_factory=list)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    fingerprint: str = ""

    dataset_version: str = ""
    dataset_sources: list[dict[str, Any]] = field(default_factory=list)
    training_start: Optional[str] = None
    training_end: Optional[str] = None

    validation_methodology: str = ""
    walk_forward: dict[str, Any] = field(default_factory=dict)
    baseline_comparison: dict[str, Any] = field(default_factory=dict)
    backtest: dict[str, Any] = field(default_factory=dict)
    factor_attribution: dict[str, Any] = field(default_factory=dict)
    holdout_metrics: dict[str, Any] = field(default_factory=dict)
    regime_stability: dict[str, Any] = field(default_factory=dict)

    experiments_run: int = 0
    git_commit: str = ""
    dependency_versions: dict[str, str] = field(default_factory=dict)
    artifact_path: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    status_history: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}; known: {STATUSES}")

    @property
    def key(self) -> str:
        return f"{self.model_id}@{self.version}:{self.label}"

    def missing_for(self, status: str) -> list[str]:
        """Evidence this entry lacks for a target status."""
        return [
            description
            for attribute, description in PROMOTION_GATES.get(status, [])
            if not getattr(self, attribute, None)
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "model_id": self.model_id,
            "version": self.version,
            "task": self.task,
            "label": self.label,
            "status": self.status,
            "features": list(self.features),
            "hyperparameters": dict(self.hyperparameters),
            "seed": self.seed,
            "fingerprint": self.fingerprint,
            "dataset_version": self.dataset_version,
            "dataset_sources": list(self.dataset_sources),
            "training_start": self.training_start,
            "training_end": self.training_end,
            "validation_methodology": self.validation_methodology,
            "walk_forward": dict(self.walk_forward),
            "baseline_comparison": dict(self.baseline_comparison),
            "backtest": dict(self.backtest),
            "factor_attribution": dict(self.factor_attribution),
            "holdout_metrics": dict(self.holdout_metrics),
            "regime_stability": dict(self.regime_stability),
            "experiments_run": self.experiments_run,
            "git_commit": self.git_commit,
            "dependency_versions": dict(self.dependency_versions),
            "artifact_path": self.artifact_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status_history": list(self.status_history),
            "notes": list(self.notes),
            "eligible_for": [
                status for status in ("validated", "production_candidate", "production")
                if not self.missing_for(status)
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ModelEntry":
        data = {k: v for k, v in payload.items() if k not in {"key", "eligible_for"}}
        return cls(**data)


class ModelRegistry:
    """A JSON-backed registry with gated promotion."""

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.path = self.root / "registry.json"
        self._entries: dict[str, ModelEntry] = {}
        self._load()

    # ── persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for item in payload.get("entries", []):
            entry = ModelEntry.from_dict(item)
            self._entries[entry.key] = entry

    def save(self) -> Path:
        """Write atomically — a half-written registry is worse than none."""
        self.root.mkdir(parents=True, exist_ok=True)
        handle, staging = tempfile.mkstemp(dir=self.root, prefix=".registry-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "schema_version": REGISTRY_SCHEMA_VERSION,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "entries": [entry.as_dict() for entry in self._entries.values()],
                    },
                    stream,
                    indent=2,
                    sort_keys=True,
                    default=str,
                )
            os.replace(staging, self.path)
        except BaseException:
            Path(staging).unlink(missing_ok=True)
            raise
        return self.path

    # ── operations ───────────────────────────────────────────────────────

    def register(self, entry: ModelEntry, *, overwrite: bool = True) -> ModelEntry:
        if entry.key in self._entries and not overwrite:
            raise ValueError(f"{entry.key} is already registered")
        entry.git_commit = entry.git_commit or git_commit()
        entry.dependency_versions = entry.dependency_versions or dependency_versions()
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._entries[entry.key] = entry
        return entry

    def get(self, key: str) -> ModelEntry:
        if key not in self._entries:
            raise KeyError(f"unknown model {key!r}")
        return self._entries[key]

    def all(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def by_status(self, status: str) -> list[ModelEntry]:
        return [entry for entry in self._entries.values() if entry.status == status]

    def promote(self, key: str, status: str, *, reason: str = "") -> ModelEntry:
        """Change a model's status, refusing when the evidence is not there."""
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        entry = self.get(key)

        if status != "retired":
            missing = entry.missing_for(status)
            if missing:
                raise PromotionRefused(
                    f"{key} cannot become {status}: missing {', '.join(missing)}. "
                    "A model is promoted on evidence, not on the best backtest number."
                )

        previous = entry.status
        entry.status = status
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        entry.status_history.append(
            {
                "from": previous,
                "to": status,
                "at": entry.updated_at,
                "reason": reason or "(no reason given)",
            }
        )
        logger.info("registry: %s %s -> %s", key, previous, status)
        return entry

    def leaderboard(self, *, label: Optional[str] = None) -> list[dict[str, Any]]:
        """Models ranked, with the numbers that argue against them included.

        Ordering is by out-of-sample mean IC, but every row carries the
        stability, cost and attribution figures that can overturn that ordering.
        A model with a lower IC and a positive-IC rate of 0.9 across folds is
        usually the better choice than one at 0.75, and the table has to make
        that visible rather than sorting it away.
        """
        rows: list[dict[str, Any]] = []
        for entry in self._entries.values():
            if label and entry.label != label:
                continue
            walk = entry.walk_forward or {}
            backtest = entry.backtest or {}
            attribution = entry.factor_attribution or {}
            rows.append(
                {
                    "key": entry.key,
                    "model_id": entry.model_id,
                    "label": entry.label,
                    "status": entry.status,
                    "mean_ic": walk.get("mean_ic"),
                    "ic_t_stat": walk.get("t_stat"),
                    "fold_ic_positive_rate": walk.get("fold_positive_rate"),
                    "net_sharpe": backtest.get("net_sharpe"),
                    "net_cagr": backtest.get("net_cagr"),
                    "max_drawdown": backtest.get("net_max_drawdown"),
                    "annualised_turnover": backtest.get("annualised_turnover"),
                    "cost_share_of_gross": backtest.get("cost_share_of_gross"),
                    "alpha_t_stat": attribution.get("alpha_t_stat"),
                    "alpha_significant": attribution.get("alpha_significant"),
                    "experiments_run": entry.experiments_run,
                    "eligible_for": entry.as_dict()["eligible_for"],
                }
            )
        return sorted(
            rows, key=lambda row: (row.get("mean_ic") is None, -(row.get("mean_ic") or 0.0))
        )

    def summary(self) -> dict[str, Any]:
        return {
            "entries": len(self._entries),
            "by_status": {
                status: len(self.by_status(status)) for status in STATUSES
            },
            "labels": sorted({entry.label for entry in self._entries.values()}),
            "path": str(self.path),
        }


def git_commit() -> str:
    """Best available code identifier, without making the registry need Git."""
    for name in ("RENDER_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA", "GITHUB_SHA"):
        value = os.getenv(name)
        if value:
            return value[:40]
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=2
        ).stdout.strip()[:40] or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def dependency_versions() -> dict[str, str]:
    """Versions of everything that can change a prediction."""
    versions: dict[str, str] = {}
    for module in ("numpy", "pandas", "pyarrow", "sklearn", "scipy"):
        try:
            versions[module] = __import__(module).__version__
        except Exception:  # noqa: BLE001 — an absent optional dependency is data
            versions[module] = "absent"
    import sys

    versions["python"] = sys.version.split()[0]
    return versions
