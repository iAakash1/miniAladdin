"""Risk measures the engine did not have: entropic, Gini, Omega, partial moments.

Every function here is a deterministic transformation of one return series. No
new data is required and nothing is estimated from a model, which is why these
could be added honestly where a factor requiring point-in-time fundamentals
could not.

The entropic measures are the reason this module exists. EVaR is the tightest
upper bound on VaR obtainable from the Chernoff inequality, and unlike VaR it is
coherent — it cannot reward splitting a position across two books. It sits above
CVaR by construction, so where a report shows CVaR alone the tail is being
described by its average rather than its worst credible shape.

    VaR_a  <=  CVaR_a  <=  EVaR_a

That ordering is an identity, not an empirical tendency, and the tests assert it
on every distribution they can construct — including ones with no upper tail at
all, where the three collapse together.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar


def _losses(returns: pd.Series) -> np.ndarray:
    """Returns as positive losses. A +2% return is a loss of -0.02."""
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    return -values


def entropic_value_at_risk(
    returns: pd.Series, *, confidence: float = 0.95
) -> Optional[float]:
    """EVaR: the tightest Chernoff bound on VaR. Reported as a positive loss.

    EVaR_a = inf_{z>0} z * ln( E[exp(L/z)] / (1-a) ) over losses L = -returns.

    The objective is convex in z, so a bounded scalar minimisation finds the
    global optimum. It is evaluated in log space — `logsumexp` rather than
    `mean(exp(...))` — because L/z overflows for the small z the optimiser
    probes, and an overflow there returns `inf`, which looks like a legitimately
    unbounded tail rather than the arithmetic failure it is.
    """
    losses = _losses(returns)
    n = len(losses)
    if n < 2 or not 0.0 < confidence < 1.0:
        return None
    if not np.all(np.isfinite(losses)):
        return None

    log_alpha = math.log(1.0 - confidence)

    def objective(log_z: float) -> float:
        z = math.exp(log_z)
        scaled = losses / z
        shift = float(np.max(scaled))
        # log(mean(exp(s))) computed stably.
        log_mean = shift + math.log(float(np.mean(np.exp(scaled - shift))))
        return z * (log_mean - log_alpha)

    # z is searched in log space so the bracket spans many orders of magnitude
    # without the optimiser having to step across them linearly.
    spread = float(np.std(losses)) or 1.0
    result = minimize_scalar(
        objective,
        bounds=(math.log(spread * 1e-4), math.log(spread * 1e4)),
        method="bounded",
        options={"xatol": 1e-10},
    )
    if not result.success or not np.isfinite(result.fun):
        return None
    return float(result.fun)


def entropic_drawdown_at_risk(
    drawdowns: pd.Series, *, confidence: float = 0.95
) -> Optional[float]:
    """EDaR: EVaR applied to the drawdown path. Reported as a positive loss.

    Takes an already-computed drawdown series rather than a return series, so
    the ordering guard that produces it is applied once, by its caller, instead
    of being duplicated and possibly diverging here.
    """
    values = pd.to_numeric(drawdowns, errors="coerce").dropna()
    if values.empty:
        return None
    # Drawdowns are non-positive; EVaR expects the same sign convention as
    # returns, so they are passed through unchanged and come back positive.
    return entropic_value_at_risk(values, confidence=confidence)


def gini_mean_difference(returns: pd.Series) -> Optional[float]:
    """Expected absolute difference between two independent draws.

    A dispersion measure that assumes nothing about the shape of the
    distribution — unlike standard deviation, which is only a complete
    description when returns are normal, and unlike a quantile measure, which
    ignores everything between the quantiles.

    Computed from the sorted sample in O(n log n) using the rank identity
    rather than the O(n^2) double sum, which is unusable on a long series.
    """
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    n = len(values)
    if n < 2:
        return None
    ordered = np.sort(values)
    ranks = np.arange(1, n + 1, dtype=float)
    weighted = float(np.sum((2.0 * ranks - n - 1.0) * ordered))
    return 2.0 * weighted / (n * (n - 1))


def lower_partial_moment(
    returns: pd.Series, *, threshold: float = 0.0, order: int = 2
) -> Optional[float]:
    """`E[max(threshold - r, 0) ** order]`.

    Order 1 is the expected shortfall below the threshold; order 2 is the
    semi-variance about it. The threshold is explicit because "downside" means
    nothing until someone says below what — zero and the mean give different
    answers, and a measure that silently picked one would be describing a
    different question than the reader asked.
    """
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) == 0 or order < 1:
        return None
    shortfall = np.maximum(threshold - values, 0.0)
    return float(np.mean(shortfall**order))


def omega_ratio(returns: pd.Series, *, threshold: float = 0.0) -> Optional[float]:
    """Probability-weighted gains over losses, relative to a threshold.

    `E[(r - t)+] / E[(t - r)+]`. Uses the whole distribution rather than its
    first two moments, so it separates two series that share a mean and variance
    but differ in shape — which is the case a Sharpe ratio cannot see.

    Returns None when nothing falls below the threshold. The ratio is unbounded
    there, and reporting a huge number would read as an extraordinary result
    rather than as an absent denominator.
    """
    values = pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return None
    gain = float(np.mean(np.maximum(values - threshold, 0.0)))
    loss = float(np.mean(np.maximum(threshold - values, 0.0)))
    if loss <= 0.0:
        return None
    return gain / loss
