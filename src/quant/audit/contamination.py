"""
Contamination probes — does appending future data change the past?

Two independent probes, because they fail for different reasons.

**Truncation invariance.** Build the feature matrix over a full range and again
truncated at `T`, then compare every overlapping observation. Any path from a
post-`T` row to a pre-`T` value shows up as a changed number. This is the probe
that found the `merge_asof` alignment defect, and it makes no assumption about
how a feature is computed — which is precisely why it caught something reading
the code had not.

**Adversarial injection.** Append future rows carrying absurd values — prices
1,000x larger, impossible volumes, extreme IV, extreme surprises — and rebuild.
Historical values must be bit-identical. Truncation invariance can in principle
be satisfied by a leak that happens to be numerically small on real data;
injection makes any leak enormous and therefore visible.

Both run over multiple truncation points and multiple input orderings, because
a single fixture proves a single case. The original defect was invisible under
single-symbol, date-ordered input and obvious under symbol-major input.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import timedelta
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.audit.contamination")

#: Multiplier for injected future values. Large enough that any leak dominates
#: whatever it contaminates, so a small numeric difference cannot hide.
ABSURD_SCALE = 1_000.0


@dataclass
class ComparisonResult:
    """Per-column verdict for one comparison."""

    label: str
    rows_compared: int
    columns_compared: int
    differing: list[dict[str, Any]] = field(default_factory=list)
    row_set_changed: bool = False

    @property
    def clean(self) -> bool:
        return not self.differing and not self.row_set_changed

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "rows_compared": self.rows_compared,
            "columns_compared": self.columns_compared,
            "row_set_changed": self.row_set_changed,
            "clean": self.clean,
            "differing": self.differing[:20],
            "differing_count": len(self.differing),
        }


def compare_overlapping(
    baseline: pd.DataFrame,
    candidate: pd.DataFrame,
    columns: Sequence[str],
    *,
    label: str,
    key: Sequence[str] = ("symbol", "date"),
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> ComparisonResult:
    """Compare two frames on their shared keys, column by column.

    NULL **pattern** is compared before values. A feature that becomes
    computable only because later data arrived is a leak even when the values it
    then produces look reasonable — that was the signature of the original
    defect, and a values-only comparison would have missed it.
    """
    keys = list(key)
    left = baseline.set_index(keys).sort_index()
    right = candidate.set_index(keys).sort_index()
    shared = left.index.intersection(right.index)

    result = ComparisonResult(
        label=label,
        rows_compared=len(shared),
        columns_compared=0,
        row_set_changed=not left.index.equals(right.index),
    )

    for column in columns:
        if column not in left.columns or column not in right.columns:
            continue
        result.columns_compared += 1
        a = pd.to_numeric(left.loc[shared, column], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(right.loc[shared, column], errors="coerce").to_numpy(dtype=float)

        if not np.array_equal(np.isnan(a), np.isnan(b)):
            result.differing.append({
                "column": column, "kind": "null_pattern",
                "rows": int((np.isnan(a) != np.isnan(b)).sum()),
            })
            continue
        both = ~np.isnan(a)
        if both.any() and not np.allclose(a[both], b[both], rtol=rtol, atol=atol):
            result.differing.append({
                "column": column, "kind": "values",
                "max_abs_diff": float(np.nanmax(np.abs(a[both] - b[both]))),
                "rows": int((~np.isclose(a[both], b[both], rtol=rtol, atol=atol)).sum()),
            })
    return result


def truncation_invariance(
    build: Callable[[Optional[Date]], pd.DataFrame],
    cutoffs: Sequence[Date],
    columns: Sequence[str],
    *,
    key: Sequence[str] = ("symbol", "date"),
    date_column: str = "date",
) -> list[ComparisonResult]:
    """For each cutoff `T`: rows before `T` must not depend on rows after it.

    `build(None)` produces the full matrix; `build(T)` produces one from data
    ending at `T`. Several cutoffs, because a leak with a bounded reach — a
    252-session window, say — only shows at cutoffs inside its span.
    """
    full = build(None)
    results: list[ComparisonResult] = []
    for cutoff in cutoffs:
        truncated = build(cutoff)
        results.append(
            compare_overlapping(
                full[full[date_column] <= cutoff],
                truncated[truncated[date_column] <= cutoff],
                columns, label=f"truncate@{cutoff}", key=key,
            )
        )
    return results


def ordering_invariance(
    build: Callable[[pd.DataFrame], pd.DataFrame],
    source: pd.DataFrame,
    columns: Sequence[str],
    *,
    key: Sequence[str] = ("symbol", "date"),
    seed: int = 0,
) -> list[ComparisonResult]:
    """The same input in four row orders must produce the same output.

    Symbol-major is the order the builder actually receives, and it is the order
    under which the original defect appeared; date-major is the order that hid
    it. Shuffled is the general case. A builder whose output depends on input
    order is doing something positional.
    """
    baseline = build(source.copy())
    orderings = {
        "symbol_major": source.sort_values(["symbol", "date"], kind="mergesort"),
        "date_major": source.sort_values(["date", "symbol"], kind="mergesort"),
        "reversed": source.iloc[::-1],
        "shuffled": source.sample(frac=1.0, random_state=seed),
    }
    return [
        compare_overlapping(
            baseline, build(frame.reset_index(drop=True)), columns,
            label=f"order:{name}", key=key,
        )
        for name, frame in orderings.items()
    ]


def inject_absurd_future(
    source: pd.DataFrame,
    *,
    after: Date,
    date_column: str = "date",
    scale: float = ABSURD_SCALE,
    numeric_columns: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Multiply every numeric value dated after `after` by an absurd factor.

    Not additive noise and not a small perturbation: the point is that any leak
    becomes numerically overwhelming, so it cannot hide inside a tolerance.
    Multiplicative preserves signs and zeros, so a builder does not fail for an
    unrelated reason.
    """
    frame = source.copy()
    mask = pd.to_datetime(frame[date_column]) > pd.Timestamp(after)
    if not mask.any():
        raise ValueError(f"nothing after {after} to inject into")

    targets = list(numeric_columns) if numeric_columns else [
        column for column in frame.columns
        if column != date_column and pd.api.types.is_numeric_dtype(frame[column])
    ]
    for column in targets:
        frame.loc[mask, column] = pd.to_numeric(
            frame.loc[mask, column], errors="coerce"
        ) * scale
    return frame


def adversarial_invariance(
    build: Callable[[pd.DataFrame], pd.DataFrame],
    source: pd.DataFrame,
    columns: Sequence[str],
    *,
    cutoff: Date,
    key: Sequence[str] = ("symbol", "date"),
    date_column: str = "date",
    scale: float = ABSURD_SCALE,
) -> ComparisonResult:
    """Historical output must be identical after absurd future values are injected."""
    baseline = build(source.copy())
    injected = build(inject_absurd_future(source, after=cutoff, date_column=date_column, scale=scale))

    result = compare_overlapping(
        baseline[baseline[date_column] <= cutoff],
        injected[injected[date_column] <= cutoff],
        columns, label=f"adversarial@{cutoff}x{scale:g}", key=key,
    )

    # A probe that changes nothing anywhere proves nothing: it would pass on a
    # builder that ignores its input entirely.
    after = compare_overlapping(
        baseline[baseline[date_column] > cutoff],
        injected[injected[date_column] > cutoff],
        columns, label="post-cutoff sanity", key=key,
    )
    if after.clean:
        result.differing.append({
            "column": "__probe_liveness__", "kind": "probe_not_live",
            "note": "injecting absurd values changed nothing after the cutoff either; "
                    "this probe cannot detect anything and its pass is meaningless",
        })
    return result


def summarise(results: Sequence[ComparisonResult]) -> dict[str, Any]:
    failures = [r for r in results if not r.clean]
    return {
        "comparisons": len(results),
        "clean": not failures,
        "failed": [r.as_dict() for r in failures],
        "rows_compared": sum(r.rows_compared for r in results),
        "columns_compared": max((r.columns_compared for r in results), default=0),
    }
