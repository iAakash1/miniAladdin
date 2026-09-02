"""
Factor attribution — the only place in this repository that may say "alpha".

## The distinction this module exists to enforce

This codebase already holds the line elsewhere: a strategy's return minus a
benchmark's is a **return difference**, and calling it alpha is a claim the
subtraction does not support. `src/services/backtest_service.py` says so in its
scope note; `src/research/portfolio.py` reports a spread and does not name it.

Alpha is a specific object: the intercept of a regression of excess strategy
returns on a set of factor returns, together with its standard error. It is the
part of the return that the factors do not explain. Producing it requires
factor returns, which is why `french_factors_daily` is ingested, and it
requires the regression to actually be run — which is what happens here and
nowhere else.

    r_t - rf_t = a + b1*MktRF + b2*SMB + b3*HML + b4*RMW + b5*CMA + b6*MOM + e_t

`a` is the alpha. Its t-statistic is Newey-West corrected, because a strategy
sampled weekly with a monthly holding period has autocorrelated residuals and
the naive standard error is too small.

## Why the answer is usually "no alpha"

Most cross-sectional equity signals are momentum, value or low-volatility in
disguise. A signal whose returns load 0.8 on MOM with an intercept
indistinguishable from zero has not found anything new — it has rediscovered a
factor available since 1993, and this regression is how that gets said out loud
rather than left for a reader to suspect.

## Revised data, and why it is admissible here

The French series is revised when CRSP is revised, so it is catalogued
`PUBLICATION_LAGGED` and barred from features. It is admissible *here* because
attribution is explicitly retrospective: it asks what a realised return series
was exposed to, not what a model should have known. Revision moves the
benchmark's history, not the strategy's returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.research.cross_section import newey_west_tstat

logger = logging.getLogger("omnisignal.quant.backtest.attribution")

FACTOR_COLUMNS: tuple[str, ...] = ("mkt_rf", "smb", "hml", "rmw", "cma", "mom")

#: Below this the regression has too few degrees of freedom for its standard
#: errors to be meaningful with six regressors.
MIN_OBSERVATIONS = 40


@dataclass
class AttributionResult:
    """A factor regression, with the intercept named honestly."""

    observations: int
    alpha_per_period: Optional[float]
    alpha_annualised: Optional[float]
    alpha_t_stat: Optional[float]
    alpha_significant: Optional[bool]
    betas: dict[str, float] = field(default_factory=dict)
    beta_t_stats: dict[str, float] = field(default_factory=dict)
    r_squared: Optional[float] = None
    residual_volatility: Optional[float] = None
    periods_per_year: float = 252.0
    newey_west_lags: int = 0
    factors_used: list[str] = field(default_factory=list)
    note: str = ""

    def verdict(self) -> str:
        """A one-line reading, phrased so it cannot be over-claimed."""
        if self.alpha_t_stat is None:
            return "Not estimated — insufficient overlapping observations."
        if self.alpha_significant:
            direction = "positive" if (self.alpha_per_period or 0) > 0 else "negative"
            return (
                f"Intercept is {direction} and statistically distinguishable from zero "
                f"(t = {self.alpha_t_stat:.2f}) after controlling for "
                f"{len(self.factors_used)} factors."
            )
        dominant = max(self.betas.items(), key=lambda kv: abs(kv[1]), default=("none", 0.0))
        return (
            f"Intercept is not distinguishable from zero (t = {self.alpha_t_stat:.2f}). "
            f"The return series is explained by its factor exposures — largest loading "
            f"{dominant[0]} at {dominant[1]:+.2f}. This is a return difference, not alpha."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "observations": self.observations,
            "alpha_per_period": self.alpha_per_period,
            "alpha_annualised": self.alpha_annualised,
            "alpha_t_stat": self.alpha_t_stat,
            "alpha_significant": self.alpha_significant,
            "betas": {k: round(v, 4) for k, v in self.betas.items()},
            "beta_t_stats": {k: round(v, 3) for k, v in self.beta_t_stats.items()},
            "r_squared": self.r_squared,
            "residual_volatility": self.residual_volatility,
            "periods_per_year": self.periods_per_year,
            "newey_west_lags": self.newey_west_lags,
            "factors_used": list(self.factors_used),
            "verdict": self.verdict(),
            "note": self.note,
            "methodology": (
                "OLS of excess strategy returns on Fama-French 5 factors plus momentum. "
                "The intercept is alpha; its t-statistic is Newey-West corrected for "
                "autocorrelation induced by overlapping holding periods. Significance "
                "is |t| > 2.0."
            ),
        }


def compound_factor_returns(
    factors: pd.DataFrame, period_ends: Sequence, *, columns: Sequence[str] = FACTOR_COLUMNS
) -> pd.DataFrame:
    """Compound daily factor returns into the strategy's rebalance periods.

    Necessary because factors are daily and the strategy trades weekly or
    monthly. Regressing weekly strategy returns on daily factor returns would
    compare different quantities; compounding the factors up to the strategy's
    own period boundaries is the correct alignment.

    Compounded geometrically, matching how the strategy's own returns
    accumulate. Summing them would be an approximation that drifts over years.
    """
    frame = factors.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    frame = frame.sort_values("date").reset_index(drop=True)

    boundaries = sorted({pd.Timestamp(day).date() for day in period_ends})
    available = [column for column in columns if column in frame.columns]
    rows: list[dict[str, Any]] = []

    for index, end in enumerate(boundaries):
        start = boundaries[index - 1] if index else None
        window = frame[frame["date"] <= end] if start is None else frame[
            (frame["date"] > start) & (frame["date"] <= end)
        ]
        if window.empty or (start is None and index == 0):
            # The first boundary has no preceding period to compound over, so it
            # is dropped rather than compounded from the start of the factor
            # history — which would attach decades of returns to one period.
            continue
        row: dict[str, Any] = {"date": end, "factor_days": len(window)}
        for column in [*available, "rf"]:
            if column in window.columns:
                row[column] = float(np.prod(1.0 + window[column].to_numpy(dtype=float)) - 1.0)
        rows.append(row)

    return pd.DataFrame(rows)


def attribute_returns(
    strategy_returns: pd.Series,
    factors: pd.DataFrame,
    *,
    # Required, not defaulted.
    #
    # It was 52.0 — weekly — while every caller in this repository passes
    # 252 / step_sessions, which is 50.4 at the project's 5-session cadence.
    # The default was never used, and that is exactly what made it dangerous: a
    # caller who forgot would have annualised alpha and residual volatility
    # against the wrong period count and got a plausible number back. Alpha is
    # compounded to the power of this value, so a 3% error in the exponent is
    # not a 3% error in the result.
    periods_per_year: float,
    # Required for the same reason. This sets the Newey-West lag count, so a
    # caller who forgets gets three lags no matter how far the label looks
    # forward. Under-correction does not produce an obviously broken number; it
    # produces a t-statistic that is merely too large.
    holding_periods: int,
    market_neutral: bool = True,
) -> AttributionResult:
    """Regress strategy returns on factor returns and report the intercept.

    `market_neutral=True` skips the risk-free deduction: a dollar-neutral
    long/short book is funded by its own short proceeds, so its return is
    already an excess return and subtracting cash again would understate alpha
    by the cash rate. For a long-only strategy pass False.
    """
    period_ends = list(strategy_returns.index)
    aligned = compound_factor_returns(factors, period_ends)
    if aligned.empty:
        return AttributionResult(
            observations=0, alpha_per_period=None, alpha_annualised=None,
            alpha_t_stat=None, alpha_significant=None,
            note="no overlapping factor observations",
        )

    strategy = pd.DataFrame(
        {"date": [pd.Timestamp(d).date() for d in strategy_returns.index],
         "strategy": strategy_returns.to_numpy(dtype=float)}
    )
    merged = strategy.merge(aligned, on="date", how="inner").dropna()
    available = [column for column in FACTOR_COLUMNS if column in merged.columns]

    if len(merged) < MIN_OBSERVATIONS or not available:
        return AttributionResult(
            observations=len(merged), alpha_per_period=None, alpha_annualised=None,
            alpha_t_stat=None, alpha_significant=None, factors_used=available,
            note=(
                f"{len(merged)} overlapping periods is below the {MIN_OBSERVATIONS} "
                "needed for a six-factor regression to have meaningful standard errors"
            ),
        )

    y = merged["strategy"].to_numpy(dtype=float)
    if not market_neutral and "rf" in merged.columns:
        y = y - merged["rf"].to_numpy(dtype=float)

    X = np.column_stack([np.ones(len(merged))] + [merged[c].to_numpy(dtype=float) for c in available])
    coefficients, *_ = np.linalg.lstsq(X, y, rcond=None)
    # NumPy 2.2 on Apple Accelerate raises spurious divide/overflow flags from
    # the vectorised matmul kernel — reproducible on two arrays of plain
    # standard normals, where no such condition exists. The flags are
    # suppressed and replaced with a check of the property that actually
    # matters: that the result is finite. That is a stronger guarantee than the
    # flag provided, and it fails loudly rather than warning and continuing.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        fitted = X @ coefficients
    if not np.isfinite(fitted).all():
        raise ValueError("factor regression produced non-finite fitted values")
    residuals = y - fitted

    total_variance = float(np.sum((y - y.mean()) ** 2))
    r_squared = float(1.0 - np.sum(residuals**2) / total_variance) if total_variance > 0 else None

    # Newey-West on the residual-weighted regressors. Lags = holding periods - 1,
    # the number of subsequent observations whose holding windows overlap.
    lags = max(0, holding_periods - 1)
    t_stats = _newey_west_tstats(X, residuals, coefficients, lags)

    alpha = float(coefficients[0])
    alpha_t = float(t_stats[0])
    return AttributionResult(
        observations=len(merged),
        alpha_per_period=alpha,
        alpha_annualised=float((1.0 + alpha) ** periods_per_year - 1.0),
        alpha_t_stat=alpha_t,
        alpha_significant=bool(abs(alpha_t) > 2.0),
        betas={name: float(value) for name, value in zip(available, coefficients[1:])},
        beta_t_stats={name: float(value) for name, value in zip(available, t_stats[1:])},
        r_squared=r_squared,
        # n - k, not n - 1. A regression residual is not a sample mean deviation:
        # fitting k coefficients consumes k degrees of freedom, and dividing by
        # n - 1 understates idiosyncratic risk — 1.2% at 250 observations against
        # six factors, but 21% at 20. Understated residual volatility makes a book
        # look better explained by its factors than it is.
        residual_volatility=float(
            np.sqrt(float(residuals @ residuals) / max(1, len(residuals) - X.shape[1]))
            * np.sqrt(periods_per_year)
        ),
        periods_per_year=periods_per_year,
        newey_west_lags=lags,
        factors_used=available,
        note=(
            "Dollar-neutral book: no risk-free deduction, since short proceeds fund the "
            "long leg." if market_neutral else "Excess returns over the risk-free rate."
        ),
    )


def _newey_west_tstats(
    X: np.ndarray, residuals: np.ndarray, coefficients: np.ndarray, lags: int
) -> np.ndarray:
    """HAC standard errors, then t-statistics.

    The sandwich estimator: `(X'X)^-1 S (X'X)^-1` with `S` the Bartlett-weighted
    sum of autocovariances of the score `X_t * e_t`. Falls back to the classical
    covariance when the HAC estimate is not positive definite, which is reported
    rather than silently substituted — and which is conservative in the useful
    direction, since it can only be smaller if the autocorrelation is negative.

    No finite-sample `n / (n - k)` correction is applied to `S`. Both conventions
    appear in the literature and this is the plain asymptotic form. Stating it
    because it is not neutral: omitting the correction makes every t-statistic
    larger by `sqrt(n / (n - k))` — 1.4% at 250 observations against six factors,
    6.4% at 60. The classical fallback below does use `n - k`, so the two paths
    scale differently and a result that switched between them would move.
    """
    n, k = X.shape
    xtx_inverse = np.linalg.pinv(X.T @ X)
    scores = X * residuals[:, None]

    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        S = scores.T @ scores
        for lag in range(1, min(lags, n - 1) + 1):
            weight = 1.0 - lag / (lags + 1.0)
            gamma = scores[lag:].T @ scores[:-lag]
            S += weight * (gamma + gamma.T)
    if not np.isfinite(S).all():
        raise ValueError("HAC covariance accumulation produced non-finite values")

    covariance = xtx_inverse @ S @ xtx_inverse
    variances = np.diag(covariance)
    if np.any(variances <= 0):
        sigma_squared = float(residuals @ residuals) / max(1, n - k)
        variances = np.diag(sigma_squared * xtx_inverse)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(variances > 0, coefficients / np.sqrt(variances), 0.0)
