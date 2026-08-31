"""
Staged model search — the heavy overnight run.

## What this is, and what it deliberately is not

It is a controlled, four-stage search over model families, hyperparameters,
feature sets and targets, with every configuration logged and counted against
the cumulative multiple-testing budget.

It is **not** a way to find a better number. A larger search does not improve
the chance of finding a real effect; it raises the bar a real effect must clear.
`search.multiple_testing_cost` reports that bar *before* the run so the tradeoff
is a decision rather than a discovery: the `overnight` budget takes the expected
maximum |t| of a zero-skill population from 3.09 to 3.39.

## Stages

    1 SCREEN      every family, few configurations, on the reference context
    2 TUNE        the competitive families, deeply
    3 CONTEXT     finalists across feature arms x targets
    4 ROBUSTNESS  neighbours of each finalist — is the winner a point or a region?

Stage 1 decides where Stage 2's budget goes. Spending it flat would tune
families the screen already showed are not competitive.

## Crash safety

An overnight run that loses six hours to a failed worker is worse than one that
never started. Every completed configuration is appended to a JSONL checkpoint
immediately, `--resume` skips what is already recorded, and the checkpoint is
append-only so a crash mid-write costs one line rather than the file.

A configuration that fails is recorded as failed and the search continues; the
run is only reported COMPLETE when every planned configuration has a result.

## What it does not touch

The holdout. `build_plan` reserves it and the firewall refuses holdout-dated
rows at every fit. Nothing here can arm the contract, and selection uses
validation folds only.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date as Date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from src.quant.study import search as search_space
from src.quant.study.families import FeatureArm, arm_features

logger = logging.getLogger("omnisignal.quant.heavy")

STAGES = ("screen", "tune", "context", "robustness")


@dataclass
class ConfigResult:
    """One configuration's outcome. The unit of the checkpoint."""

    config_id: str
    stage: str
    family: str
    params: dict[str, Any]
    arm: str
    target: str
    feature_count: int
    ok: bool
    mean_ic: Optional[float] = None
    ic_t_stat: Optional[float] = None
    train_mean_ic: Optional[float] = None
    train_ic_gap: Optional[float] = None
    fold_ic_positive_rate: Optional[float] = None
    ic_ir: Optional[float] = None
    folds: int = 0
    seconds: float = 0.0
    error: Optional[str] = None
    completed_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "config_id": self.config_id, "stage": self.stage, "family": self.family,
            "params": self.params, "arm": self.arm, "target": self.target,
            "feature_count": self.feature_count, "ok": self.ok,
            "mean_ic": self.mean_ic, "ic_t_stat": self.ic_t_stat,
            "train_mean_ic": self.train_mean_ic, "train_ic_gap": self.train_ic_gap,
            "fold_ic_positive_rate": self.fold_ic_positive_rate, "ic_ir": self.ic_ir,
            "folds": self.folds, "seconds": round(self.seconds, 2),
            "error": self.error, "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ConfigResult":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})


class Checkpoint:
    """Append-only JSONL of completed configurations.

    Append-only on purpose: a crash during a write costs the last line, which
    the reader skips, rather than truncating a rewritten file. There is no
    scenario in which a half-finished overnight run should lose the six hours
    that already succeeded.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, ConfigResult]:
        if not self.path.exists():
            return {}
        done: dict[str, ConfigResult] = {}
        skipped = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1          # a torn final line from a crash
                continue
            result = ConfigResult.from_dict(payload)
            done[result.config_id] = result
        if skipped:
            logger.warning("checkpoint: skipped %d unreadable line(s)", skipped)
        return done

    def append(self, result: ConfigResult) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result.as_dict(), default=str) + "\n")
            handle.flush()


@dataclass
class SearchContext:
    """Everything the stages need, built once."""

    frame: pd.DataFrame
    manifest: Any
    calendar: Any
    available_features: list[str]
    plans: dict[str, Any] = field(default_factory=dict)
    arm_cache: dict[str, list[str]] = field(default_factory=dict)

    def features_for(self, arm: str) -> list[str]:
        if arm not in self.arm_cache:
            from src.quant.study.families import DEFAULT_ARMS

            definition = next((a for a in DEFAULT_ARMS if a.name == arm), None)
            if definition is None:
                raise KeyError(f"unknown arm {arm!r}")
            self.arm_cache[arm] = arm_features(definition, self.available_features)
        return self.arm_cache[arm]


def _walk_forward_plan(context: SearchContext, target: str, definition: Any) -> Any:
    """One plan per target, cached. Reserves the holdout and arms the firewall."""
    if target not in context.plans:
        from src.quant.validation.walkforward import build_plan

        horizon = int(target.rsplit("_", 1)[-1]) if target.rsplit("_", 1)[-1].isdigit() else 21
        context.plans[target] = build_plan(
            context.calendar,
            start=definition.start,
            end=max(context.frame["date"]),
            label_horizon_sessions=horizon,
            validation_sessions=definition.validation_sessions,
            min_train_sessions=definition.min_train_sessions,
            embargo_sessions=definition.embargo_sessions,
            holdout_sessions=definition.holdout_sessions,
        )
    return context.plans[target]


def evaluate_batch(
    specs: list[tuple[str, str, dict[str, Any], str, str]],
    context: SearchContext,
    definition: Any,
    *,
    workers: int,
    stage: str,
    checkpoint: Checkpoint,
    on_result: Optional[Callable[[ConfigResult], None]] = None,
) -> list[ConfigResult]:
    """Evaluate a batch of (config_id, family, params, arm, target) tuples.

    Batched per (arm, target) because `evaluate_specs` takes one feature list and
    one label. Within a batch the existing runner handles parallelism, ordering
    and per-model failure isolation — none of that is reimplemented here.
    """
    from src.quant.study.search import to_spec
    from src.quant.validation.parallel import evaluate_specs

    grouped: dict[tuple[str, str], list[tuple[str, str, dict[str, Any]]]] = {}
    for config_id, family, params, arm, target in specs:
        grouped.setdefault((arm, target), []).append((config_id, family, params))

    results: list[ConfigResult] = []
    for (arm, target), items in grouped.items():
        features = context.features_for(arm)
        if not features:
            for config_id, family, params in items:
                result = ConfigResult(
                    config_id=config_id, stage=stage, family=family, params=params,
                    arm=arm, target=target, feature_count=0, ok=False,
                    error=f"arm {arm} has no features in this panel",
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                checkpoint.append(result)
                results.append(result)
                if on_result:
                    on_result(result)
            continue

        plan = _walk_forward_plan(context, target, definition)
        # The spec name carries the config id so the leaderboard row, the
        # checkpoint entry and the artifact all refer to the same object.
        model_specs = [
            to_spec(family, params, name=f"{family}::{config_id}", seed=definition.seed)
            for config_id, family, params in items
        ]
        lookup = {f"{family}::{cid}": (cid, family, params) for cid, family, params in items}

        began = time.perf_counter()
        outcomes, failures, _timing = evaluate_specs(
            model_specs, context.frame, plan,
            features=features, label=target,
            step_sessions=definition.step_sessions, workers=workers,
        )
        elapsed = time.perf_counter() - began
        per_config = elapsed / max(len(items), 1)

        seen: set[str] = set()
        for outcome in outcomes:
            cid, family, params = lookup[outcome.model_id]
            seen.add(outcome.model_id)
            result = ConfigResult(
                config_id=cid, stage=stage, family=family, params=params,
                arm=arm, target=target, feature_count=len(features), ok=True,
                mean_ic=outcome.pooled_ic.get("mean_ic"),
                ic_t_stat=outcome.pooled_ic.get("t_stat"),
                ic_ir=outcome.pooled_ic.get("ic_ir"),
                train_mean_ic=outcome.stability("train_mean_ic").get("mean"),
                train_ic_gap=_gap(outcome),
                fold_ic_positive_rate=outcome.stability("spearman").get("fold_positive_rate"),
                folds=len(outcome.folds),
                seconds=round(outcome.seconds or per_config, 2),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            checkpoint.append(result)
            results.append(result)
            if on_result:
                on_result(result)

        for failure in failures:
            name = failure.get("model")
            if name in seen or name not in lookup:
                continue
            cid, family, params = lookup[name]
            result = ConfigResult(
                config_id=cid, stage=stage, family=family, params=params,
                arm=arm, target=target, feature_count=len(features), ok=False,
                error=str(failure.get("error", ""))[:500], seconds=per_config,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            checkpoint.append(result)
            results.append(result)
            if on_result:
                on_result(result)

    return results


def _gap(outcome: Any) -> Optional[float]:
    train = outcome.stability("train_mean_ic").get("mean")
    validation = outcome.pooled_ic.get("mean_ic")
    if train is None or validation is None:
        return None
    return train - validation


# ── selection ────────────────────────────────────────────────────────────────

#: Train-minus-validation IC above which a configuration is OVERFIT and excluded
#: from advancing, whatever its validation IC. Matches `quant_service.OVERFIT_GAP`.
OVERFIT_GAP = 0.15


def rank_candidates(results: list[ConfigResult]) -> list[ConfigResult]:
    """Order by validation IC, with overfit configurations pushed out.

    Deliberately not a weighted score. A composite invites tuning the weights
    until the preferred model wins; the gates in `screen_finalists` are explicit
    pass/fail instead, and this ordering only decides what gets *examined*.
    """
    usable = [r for r in results if r.ok and r.mean_ic is not None]
    return sorted(
        usable,
        key=lambda r: (
            (r.train_ic_gap or 0.0) > OVERFIT_GAP,   # overfit sinks
            -(r.mean_ic or 0.0),
        ),
    )


def competitive_families(
    results: list[ConfigResult], *, keep: int
) -> list[str]:
    """Families that earned Stage 2's budget.

    Ranked by each family's best NON-OVERFIT screen configuration. A family
    whose only good number comes from a memorising configuration has not shown
    it competes.
    """
    best: dict[str, float] = {}
    for result in results:
        if not result.ok or result.mean_ic is None:
            continue
        if (result.train_ic_gap or 0.0) > OVERFIT_GAP:
            continue
        best[result.family] = max(best.get(result.family, -1e9), result.mean_ic)
    ordered = sorted(best.items(), key=lambda kv: -kv[1])
    return [family for family, _ in ordered[:keep]]


@dataclass
class Gate:
    name: str
    passed: bool
    observed: Any
    required: str


def evaluate_gates(
    candidate: dict[str, Any],
    *,
    best_baseline_ic: Optional[float],
    cumulative_trials: int,
    expected_max_t: float,
) -> list[Gate]:
    """The predeclared development gates. None of them move.

    These are the same bars `ModelRegistry.CANDIDATE_THRESHOLDS` enforces, plus
    the search-specific ones: a candidate selected from N configurations must
    clear the |t| a zero-skill population of N would be expected to produce, and
    must not be an overfit configuration.
    """
    ic = candidate.get("mean_ic")
    t = candidate.get("ic_t_stat")
    gap = candidate.get("train_ic_gap")
    gross = candidate.get("gross_sharpe")
    net = candidate.get("net_sharpe")
    alpha_t = candidate.get("alpha_t_stat")
    turnover = candidate.get("annualised_turnover")

    return [
        Gate("ic_t_stat", t is not None and abs(t) >= 2.0, t, ">= 2.0 (absolute)"),
        Gate("gross_sharpe", gross is not None and gross > 0, gross, "> 0"),
        Gate("net_sharpe", net is not None and net > 0, net, "> 0 at the declared 10 bp"),
        Gate(
            "beats_best_baseline",
            ic is not None and best_baseline_ic is not None and ic > best_baseline_ic,
            None if ic is None or best_baseline_ic is None else round(ic - best_baseline_ic, 6),
            f"IC above the best baseline ({best_baseline_ic})",
        ),
        Gate("not_overfit", gap is not None and gap <= OVERFIT_GAP, gap, f"<= {OVERFIT_GAP}"),
        Gate(
            "survives_search_size",
            t is not None and abs(t) > expected_max_t,
            t,
            f"> {expected_max_t:.2f}, the expected max |t| of {cumulative_trials} "
            "zero-skill configurations",
        ),
        Gate("alpha_credible", alpha_t is not None and alpha_t > 0, alpha_t,
             "> 0 against the six-factor model"),
        Gate("turnover_tolerable", turnover is not None and turnover <= 30.0, turnover,
             "<= 30x annualised"),
    ]


def selection_verdict(gates: list[Gate]) -> dict[str, Any]:
    failed = [g.name for g in gates if not g.passed]
    return {
        "passed": not failed,
        "status": "DEVELOPMENT CANDIDATE" if not failed else "NO PRODUCTION CANDIDATE",
        "gates": [
            {"gate": g.name, "passed": g.passed, "observed": g.observed, "required": g.required}
            for g in gates
        ],
        "failed": failed,
        "note": (
            "Passing every gate makes this a DEVELOPMENT candidate only. The holdout "
            "is untouched and promotion remains blocked until it is spent under the "
            "contract."
        ),
    }
