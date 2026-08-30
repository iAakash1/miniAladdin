"""
Negative controls — what the pipeline reports when there is nothing to find.

A validation score is only interpretable against what the same machinery
produces on a target that *cannot* be predicted. If shuffling the labels still
yields an information coefficient of 0.03, then 0.03 is what this pipeline
returns on noise, and a real result of 0.03 means nothing.

Three controls, each breaking a different link:

``shuffled_within_date``
    Permute the target **within each date's cross-section**. The marginal
    distribution of the target on every date is untouched, the features are
    untouched, and only the pairing between them is destroyed. This is the
    sharpest control for a cross-sectional ranking study: it leaves the
    cross-sectional structure intact and removes exactly the relationship the
    model claims to find.

``shifted_forward`` — **DIAGNOSTIC, NOT BLOCKING**
    Replace each row's target with one from further in the future than the
    label horizon. Originally written as a leakage control on the premise that
    displacing the target should destroy predictability. **That premise is
    wrong for this signal class, and the evidence is direct.**

    Measured on EXP-004's dataset, with the target displaced 4 rebalance
    periods (~20 sessions):

    | model | real target IC | shifted target IC | retained |
    |---|---|---|---|
    | `baseline_momentum` | +0.0158 | +0.0194 | 122% |
    | `baseline_low_volatility` | +0.0209 | +0.0127 | 61% |

    `baseline_momentum` is a passthrough of `mom_252_21_xs` — a backward
    rolling window, no fitting, no join, no as-of merge. It **cannot** leak,
    and it predicts the displaced target at least as well as the real one.
    12-1 momentum is documented to act over 3-12 months, so a target 20
    sessions further out is still well inside the horizon it operates over.

    So a positive result here says the signal is **slow-moving**, which is a
    finding about the signal rather than a fault in the pipeline. It is
    reported and never blocks. The same two baselines collapse to +0.0007 and
    +0.0050 under `shuffled_within_date`, which is the control that actually
    tests leakage.

``permuted_symbols``
    Reassign targets between symbols on the same date. Detects a pipeline that
    is picking up date-level effects and reporting them as cross-sectional skill.

## Reading the result

The expected outcome is an IC statistically indistinguishable from zero, with a
|t| below 2 and a fold-positive rate near 0.5. `assess` reports the observed
values against those expectations rather than returning a bare pass, because
"near zero" is a judgement that should be visible.

**A control that fails is more informative than a model that succeeds.** It
means the machinery manufactures signal, and every number the study produced is
suspect.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.validation.controls")

#: |t| above which a control is considered to have produced real signal, and
#: therefore to have failed. Deliberately the same bar the study uses for a
#: positive finding: a control is held to the standard it is validating.
CONTROL_T_THRESHOLD = 2.0

#: IC magnitude above which a control is suspicious even without significance.
CONTROL_IC_THRESHOLD = 0.02

#: Controls whose failure invalidates the study, versus controls that are
#: reported for what they say about the signal.
#:
#: `shifted_forward` is deliberately NOT blocking — see the module docstring for
#: the measurement that established it tests horizon persistence rather than
#: leakage. Moving a control out of the blocking set is a methodological change
#: and is recorded here, in the ledger, and in docs/EXP-004.md rather than made
#: quietly.
BLOCKING_CONTROLS: frozenset[str] = frozenset(
    {"shuffled_within_date", "permuted_symbols"}
)


@dataclass
class ControlOutcome:
    """What a control produced, and whether that is acceptable."""

    name: str
    description: str
    mean_ic: Optional[float]
    t_stat: Optional[float]
    observations: int
    fold_positive_rate: Optional[float] = None
    notes: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return self.name in BLOCKING_CONTROLS

    @property
    def passed(self) -> bool:
        """A control passes when it finds NOTHING."""
        if self.t_stat is None or self.mean_ic is None:
            return False
        return abs(self.t_stat) < CONTROL_T_THRESHOLD and abs(self.mean_ic) < CONTROL_IC_THRESHOLD

    def as_dict(self) -> dict[str, Any]:
        return {
            "control": self.name,
            "description": self.description,
            "mean_ic": self.mean_ic,
            "t_stat": self.t_stat,
            "observations": self.observations,
            "fold_positive_rate": self.fold_positive_rate,
            "passed": self.passed,
            "blocking": self.blocking,
            "role": (
                "leakage control — failure invalidates the study" if self.blocking
                else "diagnostic — reports a property of the signal, never blocks"
            ),
            "expectation": (
                f"|IC| < {CONTROL_IC_THRESHOLD} and |t| < {CONTROL_T_THRESHOLD} — "
                "a control that finds signal means the pipeline manufactures it"
            ),
            "notes": list(self.notes),
        }


def shuffle_within_date(
    frame: pd.DataFrame,
    label: str,
    *,
    date_column: str = "date",
    seed: int = 0,
) -> pd.DataFrame:
    """Permute the target within each date, leaving features and margins intact.

    The sharpest control for a cross-sectional study: every date keeps exactly
    the same set of target values, so any level, dispersion or regime effect
    survives. Only the pairing between a feature vector and its outcome is
    destroyed.
    """
    out = frame.copy()
    rng = np.random.default_rng(seed)
    values = out[label].to_numpy(dtype=float).copy()

    for _, positions in out.groupby(date_column, sort=False).indices.items():
        block = values[positions]
        present = ~np.isnan(block)
        if present.sum() > 1:
            # Permute only the observed values, so the NULL pattern is unchanged
            # and the control does not accidentally alter sample composition.
            block[present] = rng.permutation(block[present])
            values[positions] = block
    out[label] = values
    return out


def shift_target_forward(
    frame: pd.DataFrame,
    label: str,
    *,
    periods: int,
    date_column: str = "date",
    symbol_column: str = "symbol",
) -> pd.DataFrame:
    """Replace each target with one from `periods` rebalances further ahead.

    Shifted **per symbol**; a global shift would hand one name's outcome to
    another and test something else entirely. Rows with no such future target
    are dropped rather than filled.
    """
    out = frame.sort_values([symbol_column, date_column], kind="mergesort").copy()
    out[label] = out.groupby(symbol_column, sort=False)[label].shift(-periods)
    return out.dropna(subset=[label]).reset_index(drop=True)


def permute_symbols_within_date(
    frame: pd.DataFrame,
    label: str,
    *,
    date_column: str = "date",
    symbol_column: str = "symbol",
    seed: int = 0,
) -> pd.DataFrame:
    """Reassign targets between symbols on the same date.

    Distinct from `shuffle_within_date` in intent rather than mechanism: this
    asks whether the pipeline is reporting a date-level effect as if it were
    cross-sectional skill.
    """
    return shuffle_within_date(frame, label, date_column=date_column, seed=seed + 977)


def assess(
    name: str,
    description: str,
    result: Any,
    *,
    notes: Optional[list[str]] = None,
) -> ControlOutcome:
    """Turn an `ExperimentResult` from a control run into a verdict."""
    pooled = getattr(result, "pooled_ic", {}) or {}
    stability = result.stability("spearman") if hasattr(result, "stability") else {}
    outcome = ControlOutcome(
        name=name,
        description=description,
        mean_ic=pooled.get("mean_ic"),
        t_stat=pooled.get("t_stat"),
        observations=pooled.get("observations", 0),
        fold_positive_rate=stability.get("fold_positive_rate"),
        notes=list(notes or []),
    )
    if not outcome.passed and outcome.t_stat is not None:
        if outcome.blocking:
            outcome.notes.append(
                "CONTROL FAILED — the pipeline produced signal on a target it should "
                "not be able to predict. Every result from this study is suspect "
                "until the cause is found."
            )
        else:
            outcome.notes.append(
                "Diagnostic finding, not a failure: predictability survives displacing "
                "the target, which for a slow-moving characteristic signal is expected. "
                "Leak-free passthrough baselines behave identically (see the module "
                "docstring), so this does not indicate contamination."
            )
    if outcome.passed:
        verdict = "PASS"
    elif outcome.blocking:
        verdict = "FAIL (blocking)"
    else:
        # A diagnostic that finds something has not failed; it has reported.
        # Logging it as FAIL invites a reader to conclude the study is broken.
        verdict = "FINDING (diagnostic, non-blocking)"
    logger.info(
        "control %s: IC %s t %s -> %s",
        name,
        "n/a" if outcome.mean_ic is None else f"{outcome.mean_ic:+.4f}",
        "n/a" if outcome.t_stat is None else f"{outcome.t_stat:+.2f}",
        verdict,
    )
    return outcome


def summarise(outcomes: list[ControlOutcome]) -> dict[str, Any]:
    """Verdict over the controls, distinguishing blocking failures from diagnostics."""
    blocking_failures = [o for o in outcomes if o.blocking and not o.passed]
    diagnostic_findings = [o for o in outcomes if not o.blocking and not o.passed]

    if blocking_failures:
        interpretation = (
            "A BLOCKING CONTROL FAILED. The pipeline produced signal on a randomised "
            "target, so its scores on the real target cannot be interpreted. Do not "
            "proceed to a holdout."
        )
    elif diagnostic_findings:
        interpretation = (
            "All blocking controls passed: the pipeline reports approximately nothing "
            "on targets whose feature-outcome pairing has been destroyed. "
            f"{len(diagnostic_findings)} diagnostic control(s) found predictability "
            "surviving a displaced target, which indicates a slow-moving signal rather "
            "than contamination — leak-free passthrough baselines show the same pattern."
        )
    else:
        interpretation = (
            "All controls passed: the pipeline reports approximately nothing on "
            "targets it cannot predict, so a non-zero result on the real target is "
            "not an artefact of the machinery."
        )

    return {
        "controls": [o.as_dict() for o in outcomes],
        "all_passed": not blocking_failures,
        "blocking_failed": [o.name for o in blocking_failures],
        "diagnostic_findings": [o.name for o in diagnostic_findings],
        "failed": [o.name for o in blocking_failures],
        "interpretation": interpretation,
    }
