"""One canonical check that a covariance matrix can describe a real book.

A variance is a squared quantity and cannot be negative. When `w' C w` comes
out below zero, the matrix is not a covariance matrix — usually because pandas
estimated each entry on whichever rows that particular pair happened to share,
so the entries are mutually inconsistent.

`sqrt(max(variance, 0))` is the tempting response and the wrong one. It takes
the single piece of evidence that the estimate is invalid and returns the most
reassuring number in the range: zero risk, or a volatility so small that
anything dividing by it explodes. Three modules had written that line
independently, each with a slightly different floor — 0.0, and 1e-24 — and each
producing a different flavour of plausible nonsense downstream.

The distinction this module draws is between:

  * float noise around a genuinely zero variance, which is real and should
    return zero, and
  * a negative beyond that scale, which is proof of an invalid input and must
    be refused.

The tolerance is scale-aware. An absolute threshold is meaningless here: daily
equity variances live around 1e-4, so a fixed 1e-12 is either far too strict on
a levered book or far too loose on a small one.
"""

from __future__ import annotations

import numpy as np

#: Relative tolerance for a negative variance. Below this, the negative is
#: attributable to floating-point accumulation in the quadratic form; above it,
#: the matrix is indefinite by an amount no rounding produced.
VARIANCE_NEGATIVE_RTOL = 1e-12


class NotPositiveSemiDefinite(ValueError):
    """Raised when a covariance matrix cannot describe a real portfolio."""


def quadratic_form(weights: np.ndarray, matrix: np.ndarray, *, context: str) -> float:
    """`w' C w`, or a refusal explaining why no risk number exists.

    Returns the variance — which may be exactly zero for a riskless or empty
    book, because there zero is the true answer. Raises when the inputs cannot
    produce one.
    """
    if not np.all(np.isfinite(matrix)):
        bad = int((~np.isfinite(matrix)).sum())
        raise NotPositiveSemiDefinite(
            f"{context}: covariance matrix has {bad} non-finite entries. A pair "
            "of names with no overlapping history produces one, and no risk "
            "number can be computed from it."
        )
    if not np.all(np.isfinite(weights)):
        raise NotPositiveSemiDefinite(f"{context}: weight vector has non-finite entries")

    variance = float(weights @ matrix @ weights)
    if not np.isfinite(variance):
        raise NotPositiveSemiDefinite(f"{context}: portfolio variance is not finite")

    # Scale of the largest term the quadratic form could have accumulated.
    scale = float(np.max(np.abs(matrix))) * float(np.abs(weights).sum()) ** 2
    if variance < -VARIANCE_NEGATIVE_RTOL * max(scale, 1.0):
        raise NotPositiveSemiDefinite(
            f"{context}: portfolio variance is negative ({variance:.3e}). The "
            "covariance matrix is not positive semi-definite, so it does not "
            "describe any real book. Estimating it on complete rows, or "
            "shrinking it, gives a matrix that does."
        )
    return max(variance, 0.0)


def volatility(weights: np.ndarray, matrix: np.ndarray, *, context: str) -> float:
    """Portfolio standard deviation, or a refusal. Never a clamped stand-in."""
    return float(np.sqrt(quadratic_form(weights, matrix, context=context)))
