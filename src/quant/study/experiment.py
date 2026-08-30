"""
Experiment definition — frozen before the run, hashed, and recorded.

An experiment is a *declaration*, not a set of arguments. It names the models,
the targets, the folds, the costs and the seed before anything executes, and
`fingerprint()` hashes the whole thing so a result can be tied to the exact
configuration that produced it. Changing a field changes the fingerprint, so a
report cannot be silently re-attributed to a different setup.

## Trial accounting is part of the declaration

`declared_evaluations` is `len(models) × len(targets)`, computed from the
definition rather than counted afterwards. `prior_evaluations` carries forward
the cumulative exposure from `docs/RESEARCH_LEDGER.md`, because significance
must be discounted against everything ever run on these folds — not against one
study's own count. Resetting that number when the code changes is how
multiple-testing bias gets laundered.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any, Optional

from src.quant.models.factory import ModelSpec, default_specs


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def git_dirty() -> bool:
    try:
        return bool(subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return True


@dataclass(frozen=True)
class ExperimentDefinition:
    """Everything frozen before a study runs."""

    experiment_id: str
    objective: str
    start: Date
    end: Optional[Date]
    step_sessions: int
    targets: tuple[str, ...]
    primary_target: str
    models: tuple[ModelSpec, ...]
    seed: int

    universe_name: str = "liquid"
    universe_size: int = 250
    execution_lag_periods: int = 1
    cost_half_spreads_bps: tuple[float, ...] = (1.0, 3.0, 5.0, 10.0, 20.0)
    primary_half_spread_bps: float = 10.0
    validation_sessions: int = 252
    min_train_sessions: int = 756
    holdout_sessions: int = 252
    embargo_sessions: int = 5

    #: Cumulative evaluations already run on these folds, from the ledger.
    prior_evaluations: int = 0
    run_negative_controls: bool = True
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.primary_target not in self.targets:
            raise ValueError(
                f"primary_target {self.primary_target!r} is not among targets {self.targets}. "
                "The primary must be declared before results are seen."
            )
        if self.execution_lag_periods < 1:
            raise ValueError(
                "execution_lag_periods must be >= 1. A lag of 0 forms a position at "
                "the close the signal was computed from, which is not achievable."
            )
        names = [spec.name for spec in self.models]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate model names: {names}")

    @property
    def declared_evaluations(self) -> int:
        return len(self.models) * len(self.targets)

    @property
    def cumulative_evaluations(self) -> int:
        """Exposure a significance claim must be discounted against."""
        return self.prior_evaluations + self.declared_evaluations

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "objective": self.objective,
            "start": str(self.start),
            "end": str(self.end) if self.end else None,
            "step_sessions": self.step_sessions,
            "targets": list(self.targets),
            "primary_target": self.primary_target,
            "models": [spec.as_dict() for spec in self.models],
            "model_count": len(self.models),
            "seed": self.seed,
            "universe_name": self.universe_name,
            "universe_size": self.universe_size,
            "execution_lag_periods": self.execution_lag_periods,
            "cost_half_spreads_bps": list(self.cost_half_spreads_bps),
            "primary_half_spread_bps": self.primary_half_spread_bps,
            "validation_sessions": self.validation_sessions,
            "min_train_sessions": self.min_train_sessions,
            "holdout_sessions": self.holdout_sessions,
            "embargo_sessions": self.embargo_sessions,
            "declared_evaluations": self.declared_evaluations,
            "prior_evaluations": self.prior_evaluations,
            "cumulative_evaluations": self.cumulative_evaluations,
            "run_negative_controls": self.run_negative_controls,
            "notes": list(self.notes),
        }

    def fingerprint(self) -> str:
        encoded = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def exp_004(seed: int = 0) -> ExperimentDefinition:
    """EXP-004 — a clean re-establishment of validation evidence.

    Deliberately **the same model ladder and targets as the voided EXP-002**.
    This is not an optimisation pass: changing the design at the same time as
    fixing the pipeline would leave it impossible to say whether a difference in
    results came from the fix or from the change. One variable moves.

    Two things do change, and both are corrections rather than choices:

    * `execution_lag_periods = 1` — EXP-002 formed positions at the close its
      signal was computed from, which is not achievable.
    * `prior_evaluations = 46` — the cumulative exposure recorded in the ledger.
      EXP-002 discounted against its own 17 and therefore understated the
      correction it needed.
    """
    return ExperimentDefinition(
        experiment_id="EXP-004",
        objective=(
            "Re-establish validation evidence on the corrected pipeline after the "
            "as-of join defect that voided EXP-002. Determine whether any learned "
            "model shows incremental predictive information over free factor "
            "baselines that survives transaction costs, a realistic execution lag, "
            "and correction for cumulative multiple testing."
        ),
        start=Date(2014, 4, 1),
        end=None,
        step_sessions=5,
        targets=("fwd_rank_21", "fwd_ret_21"),
        primary_target="fwd_rank_21",
        models=tuple(default_specs(seed)),
        seed=seed,
        execution_lag_periods=1,
        prior_evaluations=46,
        notes=(
            "Model ladder and targets are unchanged from EXP-002 on purpose: with "
            "the pipeline fix as the only moving part, a difference in results is "
            "attributable to the fix.",
            "The primary target is declared here, before any result is seen.",
            "Negative controls run alongside the real targets. A control that finds "
            "signal invalidates the study rather than the control.",
            "The 252-session holdout is not read, scored, or used for selection.",
        ),
    )


EXPERIMENTS: dict[str, Any] = {"EXP-004": exp_004}


def get_experiment(experiment_id: str, seed: int = 0) -> ExperimentDefinition:
    if experiment_id not in EXPERIMENTS:
        raise KeyError(f"unknown experiment {experiment_id!r}; known: {sorted(EXPERIMENTS)}")
    return EXPERIMENTS[experiment_id](seed)
