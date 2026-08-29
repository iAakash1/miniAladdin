"""
Leakage guards — the checks that run before a dataset is allowed to be trained on.

## Why guards and not discipline

`src/panel/builder.py` states the principle this module generalises:

    Look-ahead bias is normally a discipline: remember not to peek. Discipline
    fails silently and the failure is invisible in the output.

The panel makes peeking structurally impossible for *its* factors by handing
the engine a truncated window. That works because there is one computation path.
A machine-learning dataset has many — features, labels, cross-sectional
normalisation, macro joins, universe membership, train/test splits — and each
is a separate opportunity. So the property is asserted here instead, on the
assembled matrix, where it can be checked whatever produced it.

## The four failures these catch

**Temporal leakage.** A row whose feature depends on data after its
observation date. Detected by `assert_no_future_dependence`, which perturbs
the source *after* a cutoff and asserts nothing before the cutoff moves. This
is a genuine test, not an inspection: it fails when the property is violated
and cannot pass vacuously, because it also verifies the perturbation changed
*something*.

**Target leakage.** A label, or a transform of one, present among the features.
Detected structurally by name and numerically by near-perfect correlation with
the target — the second catches a label that was renamed.

**Split leakage.** A training window that overlaps its validation window once
label horizons are accounted for. A 21-session label observed on the last
training day is realised 21 sessions into validation, so the training set
knows part of the validation outcome unless those rows are purged.

**Survivorship leakage.** A universe whose membership was decided using data
from after the date it claims to describe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as Date
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd


class LeakageError(AssertionError):
    """Raised when a dataset is shown to contain information it could not have had.

    An `AssertionError` on purpose: this is a violated invariant, not a
    recoverable condition, and nothing downstream should be catching it.
    """


@dataclass
class GuardReport:
    """The outcome of every guard, passing or not."""

    checks: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str, **extra: Any) -> None:
        self.checks.append({"check": name, "passed": passed, "detail": detail, **extra})

    @property
    def passed(self) -> bool:
        return all(check["passed"] for check in self.checks)

    def failures(self) -> list[dict[str, Any]]:
        return [check for check in self.checks if not check["passed"]]

    def raise_for_status(self) -> None:
        if not self.passed:
            lines = "; ".join(f"{c['check']}: {c['detail']}" for c in self.failures())
            raise LeakageError(f"dataset failed {len(self.failures())} leakage guard(s) — {lines}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": list(self.checks),
            "failed": len(self.failures()),
            "total": len(self.checks),
        }


def assert_no_future_dependence(
    build: Callable[[pd.DataFrame], pd.DataFrame],
    source: pd.DataFrame,
    *,
    cutoff: Date,
    perturb_columns: Sequence[str],
    compare_columns: Sequence[str],
    date_column: str = "date",
    scale: float | dict[str, float] = 3.0,
    report: Optional[GuardReport] = None,
) -> GuardReport:
    """Build twice, perturbing only the future, and assert the past is identical.

    This is the strongest available test of point-in-time correctness, and the
    reason it is strong is that it makes no assumption about *how* the builder
    works. Any path from a post-cutoff value to a pre-cutoff output — a rolling
    window without `min_periods`, a centred mean, a `shift(-1)`, a
    cross-sectional statistic computed over the whole sample, a fitted scaler —
    changes a pre-cutoff number and is caught.

    The perturbation is multiplicative and large (`scale=3.0`) rather than
    additive noise: it must be big enough that any real dependence produces a
    difference above floating-point tolerance, and multiplicative keeps signs
    and zeros intact so the builder does not fail for an unrelated reason.

    `scale` may be a **mapping** of column to factor, and for any feature that
    is a ratio of two perturbed columns it must be. Scaling both numerator and
    denominator by the same factor cancels exactly — `amihud_21` is
    `|return| / dollar_volume`, so a uniform 3x perturbation leaves it bit-identical
    and the guard would report "the future changed nothing", which is true and
    proves nothing. Distinct per-column factors make the perturbation visible
    through a ratio. The `guard_is_live` check exists precisely to catch this
    case rather than let it pass as a success.

    The guard also asserts the perturbation **changed something after the
    cutoff**. Without that, a builder that returned a constant frame would pass
    — and a leakage test that cannot fail is decoration.
    """
    report = report or GuardReport()

    baseline = build(source.copy())
    mutated_source = source.copy()
    future_mask = mutated_source[date_column] > cutoff
    if not future_mask.any():
        report.record(
            "no_future_dependence", False,
            f"no rows after {cutoff} — the guard had nothing to perturb, so it proves nothing",
        )
        return report

    scales = (
        dict(scale) if isinstance(scale, dict)
        else {column: float(scale) for column in perturb_columns}
    )
    for column in perturb_columns:
        if column in mutated_source.columns:
            factor = scales.get(column, 3.0)
            mutated_source.loc[future_mask, column] = (
                pd.to_numeric(mutated_source.loc[future_mask, column], errors="coerce") * factor
            )
    mutated = build(mutated_source)

    past_a = baseline[baseline[date_column] <= cutoff].reset_index(drop=True)
    past_b = mutated[mutated[date_column] <= cutoff].reset_index(drop=True)

    if len(past_a) != len(past_b):
        report.record(
            "no_future_dependence", False,
            f"row count before {cutoff} changed: {len(past_a)} -> {len(past_b)}",
        )
        return report

    offenders: list[dict[str, Any]] = []
    for column in compare_columns:
        if column not in past_a.columns or column not in past_b.columns:
            continue
        left = pd.to_numeric(past_a[column], errors="coerce").to_numpy(dtype=float)
        right = pd.to_numeric(past_b[column], errors="coerce").to_numpy(dtype=float)
        if not np.array_equal(np.isnan(left), np.isnan(right)):
            offenders.append({"column": column, "reason": "null pattern changed"})
            continue
        both = ~np.isnan(left)
        if both.any() and not np.allclose(left[both], right[both], rtol=1e-9, atol=1e-12):
            worst = float(np.nanmax(np.abs(left[both] - right[both])))
            offenders.append({"column": column, "reason": "values changed", "max_abs_diff": worst})

    # The guard must be capable of failing: prove the perturbation was felt.
    future_a = baseline[baseline[date_column] > cutoff]
    future_b = mutated[mutated[date_column] > cutoff]
    moved = False
    for column in compare_columns:
        if column in future_a.columns and column in future_b.columns:
            left = pd.to_numeric(future_a[column], errors="coerce").to_numpy(dtype=float)
            right = pd.to_numeric(future_b[column], errors="coerce").to_numpy(dtype=float)
            both = ~np.isnan(left) & ~np.isnan(right)
            if both.any() and not np.allclose(left[both], right[both], rtol=1e-9):
                moved = True
                break
    if not moved:
        report.record(
            "guard_is_live", False,
            "perturbing the future changed no output at all — this guard would pass "
            "on a builder that ignores its input, so it is not evidence of anything",
        )
    else:
        report.record("guard_is_live", True, "perturbation was observable after the cutoff")

    if offenders:
        report.record(
            "no_future_dependence", False,
            f"{len(offenders)} column(s) before {cutoff} moved when only the future changed",
            offenders=offenders[:10],
        )
    else:
        report.record(
            "no_future_dependence", True,
            f"{len(compare_columns)} column(s) unchanged before {cutoff} under a "
            f"{scales} future perturbation",
        )
    return report


def assert_no_target_leakage(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    label_columns: Sequence[str],
    *,
    correlation_threshold: float = 0.999,
    report: Optional[GuardReport] = None,
) -> GuardReport:
    """Assert no label — or a rename of one — sits in the feature matrix.

    Two checks, because each catches what the other misses. The name check
    catches the ordinary mistake of forgetting to drop a column. The
    correlation check catches the subtle one: a label copied under a different
    name, or a feature that is an invertible transform of the target.

    The threshold is 0.999, not 1.0. A label that has been scaled, rounded or
    passed through a monotone transform will not correlate at exactly 1, and a
    feature that legitimately correlates at 0.999 with its own target does not
    exist in financial data.
    """
    report = report or GuardReport()

    overlap = sorted(set(feature_columns) & set(label_columns))
    report.record(
        "no_label_in_features", not overlap,
        f"label column(s) present as features: {overlap}" if overlap else "no shared column names",
    )

    suspicious: list[dict[str, Any]] = []
    for label in label_columns:
        if label not in frame.columns:
            continue
        target = pd.to_numeric(frame[label], errors="coerce")
        for feature in feature_columns:
            if feature not in frame.columns:
                continue
            values = pd.to_numeric(frame[feature], errors="coerce")
            both = target.notna() & values.notna()
            if both.sum() < 30 or values[both].std(ddof=1) == 0:
                continue
            correlation = float(np.corrcoef(values[both], target[both])[0, 1])
            if abs(correlation) >= correlation_threshold:
                suspicious.append(
                    {"feature": feature, "label": label, "correlation": round(correlation, 6)}
                )

    report.record(
        "no_target_correlation", not suspicious,
        (
            f"{len(suspicious)} feature/label pair(s) correlate at or above "
            f"{correlation_threshold} — a renamed label or an invertible transform of one"
        )
        if suspicious
        else f"no feature correlates with any label above {correlation_threshold}",
        pairs=suspicious[:10],
    )
    return report


def assert_split_is_purged(
    train_end: Date,
    validation_start: Date,
    *,
    label_horizon_sessions: int,
    embargo_sessions: int,
    calendar,
    report: Optional[GuardReport] = None,
) -> GuardReport:
    """Assert the gap between training and validation covers the label horizon.

    A label observed on the last training day is realised `horizon` sessions
    later. If validation begins before that, the training set contains partial
    knowledge of validation outcomes — which inflates measured performance in
    a way that survives every other check, because nothing about the feature
    matrix is wrong.

    The required gap is `horizon + embargo`. The embargo is separate and serves
    a different purpose: it covers *serial correlation* between adjacent
    observations, which persists past the horizon itself. Naming them
    separately keeps the two reasons distinguishable.
    """
    report = report or GuardReport()
    required = int(label_horizon_sessions) + int(embargo_sessions)
    try:
        actual = calendar.count_between(train_end, validation_start) - 1
    except Exception as error:  # noqa: BLE001 — reported, never swallowed
        report.record("split_purged", False, f"calendar could not measure the gap: {error}")
        return report

    report.record(
        "split_purged", actual >= required,
        (
            f"only {actual} session(s) between train_end {train_end} and validation_start "
            f"{validation_start}; {required} required (horizon {label_horizon_sessions} + "
            f"embargo {embargo_sessions})"
        )
        if actual < required
        else f"{actual} session gap covers the required {required}",
        gap_sessions=actual,
        required_sessions=required,
    )
    return report


def assert_universe_is_point_in_time(
    universe_history, *, report: Optional[GuardReport] = None
) -> GuardReport:
    """Assert membership was decided from data available at each rebalance."""
    report = report or GuardReport()

    report.record(
        "universe_declares_pit", bool(getattr(universe_history, "point_in_time", False)),
        "universe does not declare point-in-time membership — any study over it is "
        "survivorship-biased and must be labelled so",
    )

    snapshots = getattr(universe_history, "snapshots", [])
    monotone = all(
        snapshots[i].as_of < snapshots[i + 1].as_of for i in range(len(snapshots) - 1)
    )
    report.record(
        "universe_dates_monotone", monotone,
        "rebalance dates are not strictly increasing" if not monotone else
        f"{len(snapshots)} rebalance dates strictly increasing",
    )

    # A survivorship-free universe must contain names that stop appearing. One
    # whose membership only ever grows is a survivor list wearing a date column.
    exits = 0
    previous: set[str] = set()
    for snapshot in snapshots:
        current = set(snapshot.symbols)
        exits += len(previous - current)
        previous = current
    report.record(
        "universe_has_exits", exits > 0,
        (
            "no symbol ever left the universe — membership that only grows is a "
            "survivor list with a date column attached"
        )
        if exits == 0
        else f"{exits} membership exits recorded across {len(snapshots)} rebalances",
        exits=exits,
    )
    return report


def assert_features_declared_safe(registry, feature_names: Sequence[str],
                                  *, report: Optional[GuardReport] = None) -> GuardReport:
    """Assert every requested feature declared itself point-in-time safe."""
    report = report or GuardReport()
    unsafe: list[str] = []
    unknown: list[str] = []
    for name in feature_names:
        try:
            definition = registry.get(name)
        except KeyError:
            unknown.append(name)
            continue
        if not definition.point_in_time_safe:
            unsafe.append(name)

    report.record(
        "features_registered", not unknown,
        f"undeclared feature(s): {unknown}" if unknown else f"{len(feature_names)} features declared",
    )
    report.record(
        "features_pit_safe", not unsafe,
        f"feature(s) declared NOT point-in-time safe: {unsafe}" if unsafe else
        "every feature declares point-in-time safety",
    )
    return report
