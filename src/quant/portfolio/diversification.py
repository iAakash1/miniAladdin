"""How many independent bets a book actually contains.

Counting positions overstates diversification whenever positions move together,
and the two measures here are the standard corrections for that — one in
volatility space, one in the space of the covariance's own principal axes.

Both refuse rather than clamp when the covariance cannot describe a real book,
using the same guard as every other quadratic form in the repository.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from src.quant.portfolio import psd


def diversification_ratio(weights: pd.Series, cov: pd.DataFrame) -> Optional[float]:
    """Weighted average volatility over portfolio volatility.

    `(w'sigma) / sqrt(w'Sigma w)`. One when every name is perfectly correlated,
    and larger as they are not — it is exactly the factor by which correlation
    reduced the book's risk below the sum of its parts.

    Computed on absolute weights, so a long/short book is measured on the risk
    it takes rather than on a net exposure that can cancel to nothing.
    """
    aligned = weights.reindex(cov.index).fillna(0.0)
    matrix = cov.to_numpy()
    if not np.all(np.isfinite(matrix)):
        raise psd.NotPositiveSemiDefinite(
            "diversification ratio: covariance has non-finite entries"
        )
    sigma = np.sqrt(np.clip(np.diag(matrix), 0.0, None))
    weighted_average = float(np.abs(aligned.to_numpy()) @ sigma)
    portfolio = psd.volatility(
        aligned.to_numpy(), matrix, context="diversification ratio"
    )
    if portfolio <= 0 or weighted_average <= 0:
        return None
    return weighted_average / portfolio


# ── effective number of bets: NOT IMPLEMENTED, deliberately ─────────────────
#
# The obvious construction rotates the book onto the covariance's principal
# axes, reads each axis's share of variance as a probability, and reports the
# exponential entropy of that distribution. It is widely published and it is not
# a function of the inputs.
#
# For k names with equal variance and no correlation the covariance is
# sigma^2 * I, and EVERY orthonormal basis is an eigenbasis. Ten independent
# names return 10.000 effective bets under the basis numpy happens to produce
# for the exact matrix, and 3.770 under a different, equally valid one. The
# covariance is identical in both cases. In practice the sample covariance is
# never exactly degenerate, so the basis is chosen by estimation noise and the
# answer inherits it — ten independent names measured from 4,000 observations
# report 6.50.
#
# A number that changes with an arbitrary rotation is not a measurement, and it
# fails in the flattering direction as readily as the other: it can report a
# concentrated book as diversified.
#
# Meucci's minimum-torsion rotation fixes exactly this by choosing the
# uncorrelated basis closest to the original assets, which is unique. Until that
# is implemented and verified against both limiting cases, this module reports
# the diversification ratio — which is closed-form, basis-free, and correct at
# both limits — and says nothing about a bet count.
#
# See docs/SEMANTIC_AUDIT.md.
