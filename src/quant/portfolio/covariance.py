"""Named covariance estimators. The empirical one remains the default.

`optimizer.covariance` calls pandas `.cov()`, which estimates every entry on
whichever rows that particular pair happens to share. On names with staggered
listing dates that produces a matrix which is not positive semi-definite — a
real universe of fifteen names on a common factor reaches a most-negative
eigenvalue four orders of magnitude past the ridge — and the portfolio variance
of a real book comes out below zero.

The engine refuses such a matrix rather than clamping it. That is correct and it
is not a fix: refusing tells the caller there is no risk number, without giving
them one. These estimators are the fix, and they are offered by name.

Nothing here changes an existing result. `optimizer.covariance` is untouched and
still the default, because its docstring's argument holds — swapping the
estimator silently would move every historical risk number and break every
comparison against a recorded one. An estimator that is chosen is a different
thing from an estimator that is substituted.

Each returns a matrix that is positive semi-definite by construction, which the
empirical one is not, so the quadratic form cannot go negative and a book that
had no computable risk acquires one honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CovarianceEstimate:
    """A covariance matrix and how it was produced."""

    matrix: pd.DataFrame
    estimator: str
    observations: int
    #: Complete rows used. Every estimator here uses complete-case deletion, so
    #: this is the honest sample size rather than a per-pair maximum.
    complete_rows: int
    names: int
    shrinkage: Optional[float] = None
    note: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimator": self.estimator,
            "observations": self.observations,
            "complete_rows": self.complete_rows,
            "names": self.names,
            "shrinkage": None if self.shrinkage is None else round(self.shrinkage, 6),
            "note": self.note,
        }

    @property
    def is_psd(self) -> bool:
        eigenvalues = np.linalg.eigvalsh(self.matrix.to_numpy())
        return bool(eigenvalues.min() >= -1e-12 * max(1.0, abs(eigenvalues.max())))


def _complete(returns: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Complete-case rows, and how many were available before and after.

    Complete-case rather than pairwise. Pairwise keeps more data and produces a
    matrix whose entries were measured on different populations, which is what
    makes it indefinite. Dropping rows costs sample size and returns a matrix
    that is internally consistent.
    """
    frame = returns.dropna(axis=1, how="all")
    complete = frame.dropna(axis=0, how="any")
    return complete, len(frame), len(complete)


def empirical(returns: pd.DataFrame) -> CovarianceEstimate:
    """Sample covariance on complete rows only.

    Differs from `optimizer.covariance` in exactly one way — that one uses
    pandas' pairwise deletion — and that one difference is what makes this
    positive semi-definite.
    """
    complete, total, rows = _complete(returns)
    matrix = complete.cov()
    return CovarianceEstimate(
        matrix=matrix, estimator="empirical_complete_case",
        observations=total, complete_rows=rows, names=matrix.shape[0],
        note=(
            None if rows == total
            else f"{total - rows} of {total} rows dropped for incompleteness"
        ),
    )


def ledoit_wolf(returns: pd.DataFrame) -> CovarianceEstimate:
    """Sample covariance shrunk toward a constant-correlation target.

    The sample covariance of N names on T periods is a poor estimator when T is
    not much larger than N, and its worst errors are in the extreme eigenvalues
    — precisely the directions an optimiser leans on hardest. Shrinking toward a
    structured target trades a little bias for a large variance reduction, and
    the optimal intensity is estimable from the data rather than tuned.

    The target is the constant-correlation matrix: each name keeps its own
    sample variance, and every pair takes the average sample correlation. It
    preserves the one thing the sample estimates well and replaces the one it
    does not.

    The intensity is Ledoit and Wolf's analytic estimate, clipped to [0, 1] —
    the formula can leave that interval on small samples, and an intensity
    outside it is not a shrinkage.
    """
    complete, total, rows = _complete(returns)
    values = complete.to_numpy(dtype=float)
    n, k = values.shape
    names = list(complete.columns)
    if n < 2 or k < 2:
        matrix = complete.cov()
        return CovarianceEstimate(
            matrix=matrix, estimator="ledoit_wolf", observations=total,
            complete_rows=rows, names=len(names), shrinkage=None,
            note="too few complete rows or names to shrink",
        )

    # numpy on Accelerate emits spurious divide/overflow/invalid warnings for
    # matmul on well-formed input. Suppressed narrowly and the result checked for
    # finiteness instead — the pattern models/base.py and risk/engine.py use,
    # because a warning nobody can act on trains people to ignore warnings.
    with np.errstate(all="ignore"):
        centred = values - values.mean(axis=0)
        sample = centred.T @ centred / n       # MLE scaling, as the derivation assumes
        variances = np.diag(sample)
        stds = np.sqrt(variances)
        outer = np.outer(stds, stds)
        correlation = np.where(outer > 0, sample / outer, 0.0)
        off = ~np.eye(k, dtype=bool)
        mean_correlation = float(correlation[off].mean()) if k > 1 else 0.0

        target = mean_correlation * outer
        np.fill_diagonal(target, variances)

        # pi: summed variance of the sample covariance entries.
        squared = centred**2
        pi_matrix = (
            (squared.T @ squared) / n - 2.0 * sample * (centred.T @ centred / n) + sample**2
        )
        pi = float(pi_matrix.sum())

        # rho: covariance between the sample entries and the target's entries.
        term = (centred**3).T @ centred / n - variances[:, None] * sample
        ratio = np.where(outer > 0, stds[None, :] / stds[:, None], 0.0)
        rho_off = mean_correlation / 2.0 * (ratio * term + ratio.T * term.T)
        rho = float(np.diag(pi_matrix).sum() + rho_off[off].sum())

        gamma = float(np.sum((target - sample) ** 2))
        intensity = 0.0 if gamma <= 0 else (pi - rho) / gamma / n
        intensity = float(min(1.0, max(0.0, intensity)))

        shrunk = intensity * target + (1.0 - intensity) * sample

    if not np.all(np.isfinite(shrunk)):
        matrix = complete.cov()
        return CovarianceEstimate(
            matrix=matrix, estimator="ledoit_wolf", observations=total,
            complete_rows=rows, names=len(names), shrinkage=None,
            note="shrinkage arithmetic was not finite; returned the sample estimate",
        )
    # Back to the unbiased scaling the rest of the repository uses.
    shrunk = shrunk * n / max(1, n - 1)
    matrix = pd.DataFrame(shrunk, index=names, columns=names)
    return CovarianceEstimate(
        matrix=matrix, estimator="ledoit_wolf", observations=total,
        complete_rows=rows, names=len(names), shrinkage=intensity,
        note=f"shrunk {intensity:.1%} toward constant correlation {mean_correlation:.3f}",
    )


def exponentially_weighted(
    returns: pd.DataFrame, *, halflife: float = 63.0
) -> CovarianceEstimate:
    """Covariance with geometrically decaying weights.

    An equally weighted estimate says a return from three years ago describes
    today's risk as well as yesterday's. It does not. The halflife is in
    observations and is explicit, because the number chosen is the whole content
    of the estimate: 63 sessions is a quarter, and a different choice is a
    different claim about how fast risk decays.

    Weights are normalised so the result is an unbiased-style estimate under the
    effective sample size implied by the decay, not the raw row count.
    """
    complete, total, rows = _complete(returns)
    values = complete.to_numpy(dtype=float)
    n, k = values.shape
    names = list(complete.columns)
    if n < 2 or k < 1 or halflife <= 0:
        matrix = complete.cov()
        return CovarianceEstimate(
            matrix=matrix, estimator="exponentially_weighted", observations=total,
            complete_rows=rows, names=len(names),
            note="too few complete rows to weight",
        )

    decay = 0.5 ** (1.0 / halflife)
    ages = np.arange(n - 1, -1, -1, dtype=float)      # oldest row has the largest age
    weights = decay**ages
    weights /= weights.sum()

    with np.errstate(all="ignore"):
        mean = weights @ values
        centred = values - mean
        weighted = (centred * weights[:, None]).T @ centred
    if not np.all(np.isfinite(weighted)):
        matrix = complete.cov()
        return CovarianceEstimate(
            matrix=matrix, estimator="exponentially_weighted", observations=total,
            complete_rows=rows, names=len(names),
            note="weighted arithmetic was not finite; returned the sample estimate",
        )

    # Effective sample size under these weights; the bias correction that
    # matches ddof=1 for equal weights.
    effective = 1.0 / float(np.sum(weights**2))
    matrix = pd.DataFrame(
        weighted * effective / max(1.0, effective - 1.0), index=names, columns=names
    )
    return CovarianceEstimate(
        matrix=matrix, estimator="exponentially_weighted", observations=total,
        complete_rows=rows, names=len(names),
        note=f"halflife {halflife:g} observations, effective sample {effective:.1f}",
    )


ESTIMATORS = {
    "empirical": empirical,
    "ledoit_wolf": ledoit_wolf,
    "exponentially_weighted": exponentially_weighted,
}


def estimate(returns: pd.DataFrame, *, estimator: str = "empirical") -> CovarianceEstimate:
    """Dispatch by name. Unknown names raise rather than falling back."""
    if estimator not in ESTIMATORS:
        raise ValueError(
            f"unknown covariance estimator {estimator!r}; "
            f"available: {', '.join(sorted(ESTIMATORS))}"
        )
    return ESTIMATORS[estimator](returns)
