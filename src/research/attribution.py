"""
Return attribution — was this name's move explained by the factors, or not?

The engine scores a name and, when it later moves, offers no way to ask
whether the move was the kind of thing it was tracking. That gap matters more
than it sounds: a portfolio that made money for reasons its factors never
mentioned did not work, it got lucky, and nothing in the product could tell
the two apart.

For each date, this regresses the cross-section of forward returns on the
cross-section of factor exposures:

    r_i = α + Σ_k β_k · f_ki + ε_i

**Cross-sectionally, one date at a time** — the Fama–MacBeth arrangement.
Each date yields its own coefficients, and the reported values are their
means. That ordering matters: pooling every (name, date) pair into one
regression would let market-wide moves that lift every name masquerade as
factor returns, which is the exact error this is meant to detect.

The residual is the point. `unexplained_share` is the fraction of
cross-sectional return variance the factors did not account for, and on a
weak factor set it is close to one. Reporting it prominently is the honest
alternative to presenting an R² nobody looks at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

MIN_NAMES = 12


@dataclass(frozen=True)
class Attribution:
    """Mean factor returns and how much of the cross-section they explain."""

    factors: list[str]
    factor_returns: dict[str, float]     # mean cross-sectional coefficient
    t_stats: dict[str, float]
    mean_r_squared: float
    mean_adjusted_r_squared: float
    unexplained_share: float
    names_median: int
    dates: int

    @property
    def overfit_gap(self) -> float:
        """Raw R² minus adjusted. How much of the fit is free parameters."""
        return self.mean_r_squared - self.mean_adjusted_r_squared

    @property
    def assessment(self) -> str:
        if self.unexplained_share > 0.9:
            return (
                f"the factors explain almost none of the cross-section — "
                f"{self.unexplained_share:.0%} of return variance is unexplained"
            )
        if self.unexplained_share > 0.7:
            return (
                f"the factors explain a small share of the cross-section "
                f"({1 - self.unexplained_share:.0%}); most of what moves these "
                f"names is not in the model"
            )
        return (
            f"the factors explain {1 - self.unexplained_share:.0%} of "
            f"cross-sectional return variance after adjusting for "
            f"{len(self.factors)} predictors on {self.names_median} names"
        )


def _standardise(frame: pd.DataFrame) -> np.ndarray:
    """Z-score each factor within the date so coefficients are comparable."""
    values = frame.to_numpy(dtype=float)
    centre = np.nanmean(values, axis=0)
    spread = np.nanstd(values, axis=0)
    spread[spread == 0] = np.nan
    return (values - centre) / spread


def attribute(
    panel: pd.DataFrame, factors: tuple[str, ...], return_column: str = "forward_return"
) -> Optional[Attribution]:
    """Fama–MacBeth cross-sectional attribution. None when unestimable."""
    present = [f for f in factors if f in panel.columns]
    if not present or return_column not in panel.columns:
        return None

    coefficients: list[np.ndarray] = []
    r_squareds: list[float] = []
    adjusted: list[float] = []
    name_counts: list[int] = []

    for _, group in panel.groupby("date", sort=True):
        usable = group[present + [return_column]].dropna()
        if len(usable) < MIN_NAMES:
            continue

        exposures = _standardise(usable[present])
        if np.isnan(exposures).any():
            continue
        outcomes = usable[return_column].to_numpy(dtype=float)

        design = np.column_stack([np.ones(len(usable)), exposures])
        try:
            beta, *_ = np.linalg.lstsq(design, outcomes, rcond=None)
        except np.linalg.LinAlgError:
            continue

        fitted = design @ beta
        residual = outcomes - fitted
        total = float(((outcomes - outcomes.mean()) ** 2).sum())
        if total <= 0:
            continue

        coefficients.append(beta[1:])          # drop the intercept
        raw = 1.0 - float((residual**2).sum()) / total
        r_squareds.append(raw)
        name_counts.append(len(usable))

        # Adjusted R², because raw R² is badly inflated here: seven predictors
        # on ~25 names produces roughly 0.29 of fit from chance alone. Reporting
        # the raw figure would overstate the factors' explanatory power by
        # nearly a factor of two.
        degrees = len(usable) - len(present) - 1
        adjusted.append(
            1.0 - (1.0 - raw) * (len(usable) - 1) / degrees if degrees > 0 else np.nan
        )

    if len(coefficients) < 12:
        return None

    stacked = np.vstack(coefficients)
    means = stacked.mean(axis=0)
    # Fama-MacBeth standard errors: the time-series variation of the
    # per-date coefficients, which is what makes them comparable across
    # factors with different cross-sectional dispersion.
    errors = stacked.std(axis=0, ddof=1) / np.sqrt(len(stacked))
    with np.errstate(invalid="ignore", divide="ignore"):
        t_values = np.where(errors > 0, means / errors, 0.0)

    mean_r2 = float(np.mean(r_squareds))
    mean_adjusted = float(np.nanmean(adjusted)) if adjusted else mean_r2
    return Attribution(
        factors=present,
        factor_returns={f: float(m) for f, m in zip(present, means)},
        t_stats={f: float(t) for f, t in zip(present, t_values)},
        mean_r_squared=mean_r2,
        mean_adjusted_r_squared=mean_adjusted,
        # Unexplained is stated against the *adjusted* figure. The raw one
        # flatters a seven-predictor model on a thirty-name cross-section.
        unexplained_share=float(min(1.0, max(0.0, 1.0 - mean_adjusted))),
        names_median=int(np.median(name_counts)) if name_counts else 0,
        dates=len(stacked),
    )
