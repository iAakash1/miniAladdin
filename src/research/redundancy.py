"""
Factor redundancy — how many independent signals are actually here?

The engine exposes seven price factors and the screen averages their
percentiles as though each contributed something new. That assumption is
worth testing rather than trusting: `r12_1`, `r63` and `r21` are the same
statistic over three horizons, and if they move together the composite is
momentum wearing three hats, its "agreement" column is measuring an identity
rather than a consensus, and equal weighting silently triples momentum's vote.

## What it measures

**Cross-sectional correlation.** On each date, the Spearman correlation
between two factors' rankings across the universe, averaged over dates. Rank
correlation for the same reason `evaluate_factor` uses it: the scores are
`tanh`-squashed and the claim is about ordering.

Averaging per-date correlations rather than pooling all (symbol, date) pairs
into one correlation is deliberate — pooling would let cross-date variation
in factor levels masquerade as cross-sectional agreement.

**Effective factor count.** The participation ratio of the correlation
matrix's eigenvalues:

    N_eff = (Σλ)² / Σλ²

For perfectly independent factors this equals the factor count; for perfectly
redundant ones it equals 1. It is the honest answer to "how many bets is this
composite really making", and it is usually smaller than anyone expects.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_NAMES = 10

#: Above this, two factors are telling you substantially the same thing.
#: Below this share of factor pairs actually observed together, the
#: independence verdict is withheld rather than computed from the fill.
MIN_PAIR_COVERAGE = 0.75

REDUNDANT_ABOVE = 0.7


@dataclass(frozen=True)
class Redundancy:
    factors: list[str]
    matrix: list[list[float]]
    effective_factors: float
    redundant_pairs: list[tuple[str, str, float]]
    dates: int
    #: Factor pairs that were actually observed together. Every unobserved pair
    #: enters the eigenvalue calculation as zero correlation, which inflates
    #: `effective_factors` toward a claim of independence.
    measured_pairs: int = 0
    total_pairs: int = 0

    @property
    def pair_coverage(self) -> float | None:
        if self.total_pairs <= 0:
            return None
        return self.measured_pairs / self.total_pairs

    @property
    def assessment(self) -> str:
        count = len(self.factors)
        ratio = self.effective_factors / count if count else 0.0
        coverage = self.pair_coverage
        # A breadth claim built mostly on pairs that were never observed together
        # is a claim about the fill, not about the factors.
        if coverage is not None and coverage < MIN_PAIR_COVERAGE:
            return (
                f"{count} factors, but only {self.measured_pairs} of "
                f"{self.total_pairs} pairs were ever observed together — too "
                "little overlap to say whether they are independent"
            )
        if ratio > 0.85:
            shape = "largely independent"
        elif ratio > 0.6:
            shape = "partly overlapping"
        else:
            shape = "heavily overlapping"
        suffix = (
            ""
            if coverage is None or coverage >= 1.0
            else f" (on {self.measured_pairs} of {self.total_pairs} observed pairs)"
        )
        return (
            f"{count} factors behave like {self.effective_factors:.1f} independent "
            f"ones — {shape}{suffix}"
        )


def analyse(panel: pd.DataFrame, factors: tuple[str, ...]) -> Redundancy | None:
    """Average cross-sectional rank correlation between every factor pair."""
    present = [f for f in factors if f in panel.columns]
    if len(present) < 2:
        return None

    accumulated = np.zeros((len(present), len(present)))
    counts = np.zeros((len(present), len(present)))

    for _, group in panel.groupby("date", sort=True):
        usable = group[present]
        if usable.dropna(how="all").shape[0] < MIN_NAMES:
            continue
        ranked = usable.rank()
        correlation = ranked.corr(method="pearson").to_numpy()  # ranks → Spearman
        mask = ~np.isnan(correlation)
        accumulated[mask] += correlation[mask]
        counts[mask] += 1

    if counts.max() == 0:
        return None

    with np.errstate(invalid="ignore"):
        mean = np.divide(accumulated, counts, out=np.full_like(accumulated, np.nan),
                         where=counts > 0)
    np.fill_diagonal(mean, 1.0)

    # Eigenvalues need a complete matrix, and an unmeasured pair has no value to
    # supply, so it is filled with zero — treated as uncorrelated.
    #
    # That fill is NOT conservative, which this comment previously claimed. It
    # understates redundancy, and understating redundancy overstates
    # independence, which is the direction this metric's own verdict flatters:
    # `assessment` reports "largely independent" above a ratio of 0.85. Six
    # factors correlated 0.9 with each other have 1.19 effective factors; blank
    # out twelve of the fifteen pairs and the same six report 3.31, a 2.8x
    # inflation toward a breadth claim the data does not support.
    #
    # There is no better fill — a correlation that was never observed cannot be
    # invented — so the fill stays and the coverage is published beside the
    # result instead, and the verdict is withheld when coverage is too thin to
    # support a claim about independence.
    filled = np.nan_to_num(mean, nan=0.0)
    eigenvalues = np.linalg.eigvalsh(filled)
    eigenvalues = np.clip(eigenvalues, 0.0, None)
    total = eigenvalues.sum()
    effective = float(total**2 / np.square(eigenvalues).sum()) if total > 0 else 0.0

    pairs = [
        (present[i], present[j], round(float(mean[i, j]), 3))
        for i in range(len(present))
        for j in range(i + 1, len(present))
        if not np.isnan(mean[i, j]) and abs(mean[i, j]) >= REDUNDANT_ABOVE
    ]
    pairs.sort(key=lambda row: -abs(row[2]))

    off_diagonal = [
        mean[i, j] for i in range(len(present)) for j in range(i + 1, len(present))
    ]
    measured = sum(1 for v in off_diagonal if not np.isnan(v))
    return Redundancy(
        factors=present,
        matrix=[[None if np.isnan(v) else round(float(v), 3) for v in row] for row in mean],
        effective_factors=round(effective, 2),
        redundant_pairs=pairs,
        dates=int(counts.max()),
        measured_pairs=measured,
        total_pairs=len(off_diagonal),
    )
