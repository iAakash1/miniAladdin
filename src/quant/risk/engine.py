"""
Risk engine — measured risk, with the method attached to every number.

## Why every metric carries its method

"VaR" is not a number, it is a family of numbers. Historical VaR at 95% and
parametric VaR at 95% on the same series routinely differ by 30%, and the
difference is entirely methodological. A risk panel that prints one figure
labelled "VaR" is asserting a false precision, and the reader has no way to
know which assumption they are inheriting.

So every function here returns a `RiskMetric` carrying `method`, and the
aggregate report keys them separately: `var_historical_95` and
`var_parametric_95` are different fields, never averaged, never presented as one
number. Where a method's assumption is known to be violated by the data — a
Gaussian VaR on returns with excess kurtosis of 116, which this project has
actually measured — the metric says so in `caveat`.

## Scope

Everything here is *descriptive*. It measures a return series or a weight
vector; it does not forecast, allocate or score. `src/quant/portfolio/optimizer`
consumes covariance estimates from here; nothing here consumes anything from
there.

## What is deliberately not implemented

* **Monte Carlo VaR** — needs a return-generating process, and choosing one is a
  modelling decision this project has no evidence to make.
* **Factor risk decomposition beyond the six-factor attribution already in
  `backtest/attribution.py`** — that module owns factor exposure; duplicating it
  here would create two answers to the same question.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("omnisignal.quant.risk")

#: Below this many observations a distributional statistic is not reported.
#: A 95% VaR estimated from 30 points is the second-worst observation.
MIN_OBSERVATIONS = 60

#: Excess kurtosis above which a Gaussian assumption is flagged rather than
#: silently used. EXP-005 measured 116.9 on one strategy's returns.
KURTOSIS_WARNING = 3.0


@dataclass(frozen=True)
class RiskMetric:
    """One number, its method, and what would invalidate it."""

    name: str
    value: Optional[float]
    method: str
    observations: int
    caveat: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "value": None if self.value is None else round(self.value, 6),
            "method": self.method,
            "observations": self.observations,
            "caveat": self.caveat,
        }


def _clean(returns: pd.Series) -> pd.Series:
    return pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def _insufficient(name: str, method: str, n: int) -> RiskMetric:
    return RiskMetric(
        name=name, value=None, method=method, observations=n,
        caveat=f"INSUFFICIENT DATA — {n} observations, {MIN_OBSERVATIONS} required",
    )


# ── dispersion ───────────────────────────────────────────────────────────────


def volatility(returns: pd.Series, *, periods_per_year: float = 252.0) -> RiskMetric:
    series = _clean(returns)
    if len(series) < 2:
        return _insufficient("volatility", "sample_std_annualised", len(series))
    return RiskMetric(
        "volatility", float(series.std(ddof=1) * np.sqrt(periods_per_year)),
        "sample_std_annualised", len(series),
    )


def downside_deviation(
    returns: pd.Series, *, threshold: float = 0.0, periods_per_year: float = 252.0
) -> RiskMetric:
    series = _clean(returns)
    if len(series) < 2:
        return _insufficient("downside_deviation", "below_threshold_rms", len(series))
    shortfall = np.minimum(series - threshold, 0.0)
    value = float(np.sqrt((shortfall ** 2).mean()) * np.sqrt(periods_per_year))
    return RiskMetric(
        "downside_deviation", value, f"below_threshold_rms(threshold={threshold})", len(series),
    )


def rolling_volatility(
    returns: pd.Series, *, window: int = 63, periods_per_year: float = 252.0
) -> pd.Series:
    series = _clean(returns)
    return series.rolling(window, min_periods=max(2, window // 2)).std(ddof=1) * np.sqrt(
        periods_per_year
    )


# ── drawdown ─────────────────────────────────────────────────────────────────


def max_drawdown(returns: pd.Series, *, compound: bool = True) -> RiskMetric:
    """Worst peak-to-trough decline.

    `compound=False` accumulates additively, which is correct when the series is
    not a return — this repository's primary target is a cross-sectional rank,
    and compounding it produced a +6,553% "equity curve" once already.
    """
    series = _clean(returns)
    if len(series) < 2:
        return _insufficient("max_drawdown", "peak_to_trough", len(series))
    path = (1.0 + series).cumprod() if compound else series.cumsum()
    peak = path.cummax()
    drawdown = (path / peak - 1.0) if compound else (path - peak)
    return RiskMetric(
        "max_drawdown", float(drawdown.min()),
        "peak_to_trough_compound" if compound else "peak_to_trough_additive",
        len(series),
        caveat=None if compound else "additive accumulation — units are the input's, not %",
    )


def drawdown_series(returns: pd.Series, *, compound: bool = True) -> pd.Series:
    series = _clean(returns)
    path = (1.0 + series).cumprod() if compound else series.cumsum()
    peak = path.cummax()
    return (path / peak - 1.0) if compound else (path - peak)


# ── risk-adjusted performance ────────────────────────────────────────────────
#
# Every ratio here annualises EXACTLY ONCE, and each says how in its `method`.
# Double annualisation is the classic silent error in this family: annualising a
# per-period mean and then dividing by an already-annualised volatility inflates
# a Sharpe by sqrt(periods_per_year), which is 15.9x on daily data. The tests
# pin the arithmetic against hand-computed values for that reason.
#
# `risk_free` is a PER-PERIOD rate, matching the return series. Passing an
# annual rate against daily returns is the other half of the same mistake, so
# the parameter is named and documented rather than inferred.


#: Relative tolerance below which a dispersion counts as zero.
#:
#: `sigma <= 0` is not enough. A series of 120 identical values has a sample
#: standard deviation around 1e-19 rather than exactly zero, so the exact
#: comparison passes and the ratio explodes — a constant series produced a
#: Sharpe of 3.6e16, which would rank first in any leaderboard. The threshold is
#: scaled by the magnitude of what is being divided, because a dispersion of
#: 1e-19 is negligible against a mean of 0.001 and enormous against a mean of
#: 1e-25.
ZERO_DISPERSION_RTOL = 1e-12


def _is_zero_dispersion(dispersion: float, scale: float) -> bool:
    if not np.isfinite(dispersion) or dispersion <= 0:
        return True
    return dispersion <= ZERO_DISPERSION_RTOL * max(1.0, abs(scale))


def _excess(series: pd.Series, risk_free: float) -> pd.Series:
    return series - risk_free if risk_free else series


def sharpe(
    returns: pd.Series, *, periods_per_year: float = 252.0, risk_free: float = 0.0,
) -> RiskMetric:
    """Annualised excess return per unit of total volatility.

    `risk_free` is per period, not annual. A zero-variance series returns None
    rather than infinity: a constant series has no risk-adjusted return, and
    reporting one as unbounded would rank it first in any leaderboard.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("sharpe", "mean_over_std_annualised", len(series))
    excess = _excess(series, risk_free)
    sigma = float(excess.std(ddof=1))
    if _is_zero_dispersion(sigma, float(excess.mean())):
        return RiskMetric(
            "sharpe", None, "mean_over_std_annualised", len(series),
            caveat="zero variance — a constant series has no risk-adjusted return",
        )
    value = float(excess.mean()) / sigma * float(np.sqrt(periods_per_year))
    return RiskMetric("sharpe", value, "mean_over_std_annualised", len(series))


def sortino(
    returns: pd.Series, *, periods_per_year: float = 252.0, risk_free: float = 0.0,
    threshold: float = 0.0,
) -> RiskMetric:
    """Sharpe's numerator over downside deviation only.

    Penalises downside dispersion alone, so a series whose volatility is mostly
    upside scores better than its Sharpe. Undefined when nothing falls below the
    threshold — there is no downside to divide by, and returning infinity would
    make an all-positive sample look infinitely good.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("sortino", "mean_over_downside_deviation_annualised", len(series))
    excess = _excess(series, risk_free)
    shortfall = np.minimum(series - threshold, 0.0)
    downside = float(np.sqrt(np.mean(np.square(shortfall))))
    if _is_zero_dispersion(downside, float(excess.mean())):
        return RiskMetric(
            "sortino", None, "mean_over_downside_deviation_annualised", len(series),
            caveat=f"no observation below the {threshold:g} threshold — downside is undefined",
        )
    value = float(excess.mean()) / downside * float(np.sqrt(periods_per_year))
    return RiskMetric("sortino", value, "mean_over_downside_deviation_annualised", len(series))


def calmar(
    returns: pd.Series, *, periods_per_year: float = 252.0, compound: bool = True,
) -> RiskMetric:
    """Annualised return over the magnitude of the worst drawdown.

    Uses the geometric annualised return when compounding, because Calmar
    compares a growth rate against a peak-to-trough decline and an arithmetic
    mean is not that rate.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("calmar", "annualised_return_over_max_drawdown", len(series))
    worst = max_drawdown(series, compound=compound).value
    if worst is None or worst >= 0:
        return RiskMetric(
            "calmar", None, "annualised_return_over_max_drawdown", len(series),
            caveat="no drawdown in the sample — the ratio has no denominator",
        )
    if compound:
        growth = float((1.0 + series).prod())
        if growth <= 0:
            return RiskMetric(
                "calmar", None, "annualised_return_over_max_drawdown", len(series),
                caveat="cumulative wealth reached zero — no geometric rate exists",
            )
        annualised = growth ** (periods_per_year / len(series)) - 1.0
    else:
        annualised = float(series.mean()) * periods_per_year
    return RiskMetric(
        "calmar", annualised / abs(worst),
        "annualised_return_over_max_drawdown", len(series),
    )


def tracking_error(
    returns: pd.Series, benchmark: pd.Series, *, periods_per_year: float = 252.0,
) -> RiskMetric:
    """Annualised volatility of the active return.

    Aligned on the index before differencing. Subtracting two series of
    different lengths positionally is how a benchmark comparison silently
    becomes a comparison of unrelated dates.
    """
    joined = pd.concat([_clean(returns), _clean(benchmark)], axis=1, join="inner").dropna()
    if len(joined) < MIN_OBSERVATIONS:
        return _insufficient("tracking_error", "active_return_std_annualised", len(joined))
    active = joined.iloc[:, 0] - joined.iloc[:, 1]
    return RiskMetric(
        "tracking_error", float(active.std(ddof=1) * np.sqrt(periods_per_year)),
        "active_return_std_annualised", len(joined),
    )


def information_ratio(
    returns: pd.Series, benchmark: pd.Series, *, periods_per_year: float = 252.0,
) -> RiskMetric:
    """Annualised active return per unit of tracking error."""
    joined = pd.concat([_clean(returns), _clean(benchmark)], axis=1, join="inner").dropna()
    if len(joined) < MIN_OBSERVATIONS:
        return _insufficient("information_ratio", "active_mean_over_tracking_error", len(joined))
    active = joined.iloc[:, 0] - joined.iloc[:, 1]
    sigma = float(active.std(ddof=1))
    if _is_zero_dispersion(sigma, float(active.mean())):
        return RiskMetric(
            "information_ratio", None, "active_mean_over_tracking_error", len(joined),
            caveat="active return has zero variance — the portfolio tracks exactly",
        )
    return RiskMetric(
        "information_ratio", float(active.mean()) / sigma * float(np.sqrt(periods_per_year)),
        "active_mean_over_tracking_error", len(joined),
    )


def capm_alpha(
    returns: pd.Series, benchmark: pd.Series, *, periods_per_year: float = 252.0,
    risk_free: float = 0.0,
) -> RiskMetric:
    """Annualised CAPM intercept — the part beta does not explain.

    A single-factor regression against one benchmark. Named `capm_alpha` rather
    than `alpha` because this repository already reports a six-factor alpha for
    research, and the two are different claims: clearing one says nothing about
    the other. The caveat says so on every result.
    """
    joined = pd.concat([_clean(returns), _clean(benchmark)], axis=1, join="inner").dropna()
    if len(joined) < MIN_OBSERVATIONS:
        return _insufficient("capm_alpha", "single_factor_ols_annualised", len(joined))
    portfolio = joined.iloc[:, 0] - risk_free
    market = joined.iloc[:, 1] - risk_free
    variance = float(market.var(ddof=1))
    if _is_zero_dispersion(variance, float(market.mean() ** 2)):
        return RiskMetric(
            "capm_alpha", None, "single_factor_ols_annualised", len(joined),
            caveat="benchmark has zero variance — beta is undefined",
        )
    slope = float(portfolio.cov(market)) / variance
    intercept = float(portfolio.mean()) - slope * float(market.mean())
    return RiskMetric(
        "capm_alpha", intercept * periods_per_year,
        "single_factor_ols_annualised", len(joined),
        caveat=(
            "single-factor against one benchmark. Not the six-factor alpha the "
            "research surfaces report; clearing one implies nothing about the other."
        ),
    )


def drawdown_profile(returns: pd.Series, *, compound: bool = True) -> dict[str, Any]:
    """How long the worst decline lasted, and whether it recovered.

    Depth alone hides duration, and duration is what a drawdown actually costs.
    `recovered` is False when the series ends still underwater, in which case
    `recovery_periods` is None rather than the length of the sample — an
    unrecovered drawdown has no recovery time, and reporting one would be a
    measurement of when we stopped looking.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return {"observations": len(series), "max_drawdown": None,
                "peak_index": None, "trough_index": None,
                "drawdown_periods": None, "recovery_periods": None,
                "recovered": None, "method": "peak_to_trough",
                "caveat": f"INSUFFICIENT DATA — {len(series)} observations"}

    drawdown = drawdown_series(series, compound=compound)
    trough_pos = int(np.argmin(drawdown.to_numpy()))
    path = (1.0 + series).cumprod() if compound else series.cumsum()
    peak_pos = int(np.argmax(path.to_numpy()[: trough_pos + 1])) if trough_pos > 0 else 0

    after = drawdown.to_numpy()[trough_pos:]
    recovered_offset = next((i for i, v in enumerate(after) if v >= -1e-12), None)
    return {
        "observations": len(series),
        "max_drawdown": round(float(drawdown.min()), 6),
        "peak_index": str(series.index[peak_pos]),
        "trough_index": str(series.index[trough_pos]),
        "drawdown_periods": trough_pos - peak_pos,
        "recovery_periods": None if recovered_offset is None else int(recovered_offset),
        "recovered": recovered_offset is not None,
        "method": "peak_to_trough_compound" if compound else "peak_to_trough_additive",
        "caveat": None if recovered_offset is not None
        else "still underwater at the end of the sample — recovery time is unknown",
    }


def distribution(returns: pd.Series) -> dict[str, Any]:
    """Shape of the return distribution.

    Reported because every Gaussian metric above depends on it. EXP-007's
    selected configuration has skew 3.61 and excess kurtosis 43.28, which is
    why its parametric VaR and its deflated Sharpe disagree so sharply with the
    historical figures.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return {"observations": len(series), "mean": None, "median": None,
                "std": None, "skew": None, "excess_kurtosis": None,
                "gaussian_reasonable": None,
                "caveat": f"INSUFFICIENT DATA — {len(series)} observations"}
    excess_kurtosis = float(series.kurtosis())      # pandas reports EXCESS already
    return {
        "observations": len(series),
        "mean": round(float(series.mean()), 8),
        "median": round(float(series.median()), 8),
        "std": round(float(series.std(ddof=1)), 8),
        "skew": round(float(series.skew()), 4),
        "excess_kurtosis": round(excess_kurtosis, 4),
        "gaussian_reasonable": bool(abs(excess_kurtosis) <= KURTOSIS_WARNING),
        "caveat": None if abs(excess_kurtosis) <= KURTOSIS_WARNING else (
            f"excess kurtosis {excess_kurtosis:.1f} — fat tails. Parametric VaR "
            "and any Gaussian assumption understate the tail."
        ),
    }


# ── drawdown-based risk ──────────────────────────────────────────────────────
#
# `max_drawdown` reports depth and nothing else, so a single catastrophic day
# and a two-year grind to the same trough score identically. These measure the
# drawdown *path*, which is what an investor actually sits through.
#
# The family mirrors the tail family deliberately: DaR is the drawdown analogue
# of VaR, CDaR of CVaR. Same quantile logic, applied to the underwater series
# instead of the return series.


def average_drawdown(returns: pd.Series, *, compound: bool = True) -> RiskMetric:
    """Mean depth across the whole path, including periods at a high-water mark.

    Zeros are included on purpose. Averaging only the underwater periods answers
    "how bad was it while it was bad", which is a different question and reads
    far worse for a strategy that is usually at its peak.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("average_drawdown", "mean_of_drawdown_path", len(series))
    path = drawdown_series(series, compound=compound)
    return RiskMetric(
        "average_drawdown", float(path.mean()),
        "mean_of_drawdown_path_including_zeros", len(series),
    )


def ulcer_index(returns: pd.Series, *, compound: bool = True) -> RiskMetric:
    """Root mean square of the drawdown path.

    Penalises depth and duration together — squaring makes a deep drawdown count
    disproportionately, and averaging over the whole path makes a long one count
    at all. Two strategies with the same maximum drawdown separate here, which
    is the point.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("ulcer_index", "rms_of_drawdown_path", len(series))
    path = drawdown_series(series, compound=compound)
    return RiskMetric(
        "ulcer_index", float(np.sqrt(np.mean(np.square(path.to_numpy())))),
        "rms_of_drawdown_path", len(series),
    )


def drawdown_at_risk(
    returns: pd.Series, *, confidence: float = 0.95, compound: bool = True,
) -> RiskMetric:
    """The drawdown analogue of VaR: the depth exceeded (1-confidence) of the time.

    Reported as a positive magnitude, matching `var_historical`, so the tail
    family reads consistently. Empirical quantile — no distribution assumed.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("drawdown_at_risk", f"empirical_quantile_{confidence:.0%}", len(series))
    path = drawdown_series(series, compound=compound)
    return RiskMetric(
        "drawdown_at_risk", float(-np.quantile(path.to_numpy(), 1.0 - confidence)),
        f"empirical_drawdown_quantile_{confidence:.0%}", len(series),
    )


def conditional_drawdown_at_risk(
    returns: pd.Series, *, confidence: float = 0.95, compound: bool = True,
) -> RiskMetric:
    """Mean depth of the worst (1-confidence) share of the drawdown path — CDaR.

    Stands to DaR as CVaR stands to VaR: it reports the average of the tail
    rather than its boundary, so a path with a few very deep excursions is
    distinguishable from one that merely crosses the threshold often.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("conditional_drawdown_at_risk",
                             f"empirical_es_{confidence:.0%}", len(series))
    path = drawdown_series(series, compound=compound).to_numpy()
    threshold = np.quantile(path, 1.0 - confidence)
    tail = path[path <= threshold]
    if tail.size == 0:
        tail = np.array([threshold])
    return RiskMetric(
        "conditional_drawdown_at_risk", float(-tail.mean()),
        f"empirical_drawdown_es_{confidence:.0%}", len(series),
    )


def ulcer_performance_index(
    returns: pd.Series, *, periods_per_year: float = 252.0, risk_free: float = 0.0,
    compound: bool = True,
) -> RiskMetric:
    """Annualised excess return per unit of ulcer — the Martin ratio.

    A Sharpe that treats drawdown depth-and-duration as the risk rather than
    volatility. Useful precisely when returns are fat-tailed, since it never
    touches a standard deviation.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("ulcer_performance_index",
                             "excess_return_over_ulcer_annualised", len(series))
    ulcer = ulcer_index(series, compound=compound).value
    if ulcer is None or _is_zero_dispersion(ulcer, 1.0):
        return RiskMetric(
            "ulcer_performance_index", None,
            "excess_return_over_ulcer_annualised", len(series),
            caveat="no drawdown in the sample — the ratio has no denominator",
        )
    excess = _excess(series, risk_free)
    return RiskMetric(
        "ulcer_performance_index",
        float(excess.mean()) * periods_per_year / ulcer,
        "excess_return_over_ulcer_annualised", len(series),
    )


# ── robust dispersion ────────────────────────────────────────────────────────
#
# Standard deviation squares every deviation, so one outlier can dominate it.
# On this project's own data that is not hypothetical: EXP-007's selected
# configuration has excess kurtosis of 43.28. These measures are far less
# sensitive to that, and reporting them beside the standard ones shows how much
# of the risk figure is coming from a handful of periods.


def mean_absolute_deviation(returns: pd.Series) -> RiskMetric:
    """Mean absolute deviation from the mean.

    Linear in the deviations rather than quadratic, so a single extreme period
    moves it far less than it moves a standard deviation. A large gap between
    the two is itself the finding.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("mean_absolute_deviation", "mean_abs_deviation_from_mean", len(series))
    values = series.to_numpy()
    return RiskMetric(
        "mean_absolute_deviation", float(np.mean(np.abs(values - values.mean()))),
        "mean_abs_deviation_from_mean", len(series),
    )


def worst_realization(returns: pd.Series) -> RiskMetric:
    """The single worst period, as a positive magnitude.

    No estimation and no assumption — it is an observation. Reported because
    every parametric tail measure should be readable against the worst thing
    that actually happened.
    """
    series = _clean(returns)
    if len(series) < 1:
        return _insufficient("worst_realization", "sample_minimum", len(series))
    return RiskMetric(
        "worst_realization", float(-series.min()), "sample_minimum", len(series),
    )


# ── tail ─────────────────────────────────────────────────────────────────────


def var_historical(returns: pd.Series, *, confidence: float = 0.95) -> RiskMetric:
    """Empirical quantile. Makes no distributional assumption.

    Bounded below by the worst observation, which is its honest limitation: it
    cannot describe a loss larger than one already seen.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("var_historical", f"empirical_quantile_{confidence:.0%}", len(series))
    value = float(np.quantile(series, 1.0 - confidence))
    return RiskMetric(
        "var_historical", abs(value), f"empirical_quantile_{confidence:.0%}", len(series),
        caveat="Cannot exceed the worst observed loss; silent about unseen tails.",
    )


def var_parametric(returns: pd.Series, *, confidence: float = 0.95) -> RiskMetric:
    """Gaussian VaR: μ − zσ.

    Flags itself when the sample is visibly non-Gaussian, because that is
    exactly when it understates risk and exactly when it looks reassuring.
    """
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("var_parametric", f"gaussian_{confidence:.0%}", len(series))

    from scipy import stats

    z = float(stats.norm.ppf(1.0 - confidence))
    value = float(series.mean() + z * series.std(ddof=1))
    excess_kurtosis = float(stats.kurtosis(series, fisher=True))
    caveat = (
        f"Gaussian assumption; sample excess kurtosis {excess_kurtosis:.1f} "
        "exceeds the flagging threshold, so this UNDERSTATES tail risk."
        if excess_kurtosis > KURTOSIS_WARNING
        else "Assumes normality."
    )
    return RiskMetric(
        "var_parametric", abs(value), f"gaussian_{confidence:.0%}", len(series), caveat=caveat,
    )


def cvar_historical(returns: pd.Series, *, confidence: float = 0.95) -> RiskMetric:
    """Mean loss beyond the empirical VaR. Expected shortfall."""
    series = _clean(returns)
    if len(series) < MIN_OBSERVATIONS:
        return _insufficient("cvar_historical", f"empirical_es_{confidence:.0%}", len(series))
    cutoff = float(np.quantile(series, 1.0 - confidence))
    tail = series[series <= cutoff]
    if tail.empty:
        return _insufficient("cvar_historical", f"empirical_es_{confidence:.0%}", len(series))
    return RiskMetric(
        "cvar_historical", abs(float(tail.mean())), f"empirical_es_{confidence:.0%}", len(series),
        caveat=f"Averaged over {len(tail)} tail observations.",
    )


# ── relative ─────────────────────────────────────────────────────────────────


def beta(returns: pd.Series, benchmark: pd.Series) -> RiskMetric:
    joined = pd.concat([_clean(returns), _clean(benchmark)], axis=1, join="inner").dropna()
    joined.columns = ["r", "b"]
    if len(joined) < MIN_OBSERVATIONS:
        return _insufficient("beta", "ols_slope", len(joined))
    variance = float(joined["b"].var(ddof=1))
    if variance <= 0:
        return RiskMetric("beta", None, "ols_slope", len(joined),
                          caveat="benchmark has zero variance")
    value = float(joined.cov().loc["r", "b"] / variance)
    return RiskMetric("beta", value, "ols_slope", len(joined))


def correlation(returns: pd.DataFrame, *, method: str = "pearson") -> pd.DataFrame:
    return returns.corr(method=method)


def covariance_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    from src.quant.portfolio.optimizer import covariance

    return covariance(returns)


# ── risk attribution ─────────────────────────────────────────────────────────


def risk_contributions(weights: pd.Series, cov: pd.DataFrame) -> pd.DataFrame:
    """Marginal and component contribution to portfolio risk.

    Component contributions sum to total portfolio volatility by construction —
    that identity is asserted, because a contribution table that does not add up
    is the usual symptom of a misaligned index.
    """
    aligned = weights.reindex(cov.index).fillna(0.0)
    matrix = cov.to_numpy()
    # numpy 2.2 on Accelerate emits spurious divide/overflow/invalid warnings for
    # matmul on well-formed input. They are suppressed narrowly and the result is
    # checked for finiteness instead — the same pattern `models/base.py` uses,
    # because a warning nobody can act on trains people to ignore warnings.
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        variance = float(aligned @ matrix @ aligned)
        portfolio_vol = float(np.sqrt(max(variance, 0.0)))
        if not np.isfinite(portfolio_vol) or portfolio_vol <= 0:
            return pd.DataFrame(
                {"weight": aligned, "marginal": 0.0, "component": 0.0, "share": 0.0}
            )
        marginal_values = matrix @ aligned.to_numpy() / portfolio_vol

    if not np.all(np.isfinite(marginal_values)):
        return pd.DataFrame(
            {"weight": aligned, "marginal": 0.0, "component": 0.0, "share": 0.0}
        )
    marginal = pd.Series(marginal_values, index=cov.index)
    component = aligned * marginal
    total = float(component.sum())
    assert abs(total - portfolio_vol) < 1e-8 * max(1.0, portfolio_vol), (
        "component contributions must sum to portfolio volatility; "
        f"got {total} vs {portfolio_vol}"
    )
    return pd.DataFrame({
        "weight": aligned,
        "marginal": marginal,
        "component": component,
        "share": component / portfolio_vol,
    }).sort_values("component", ascending=False)


def concentration(weights: pd.Series) -> dict[str, Any]:
    """Herfindahl, effective names, and the top-N shares."""
    w = weights.abs()
    gross = float(w.sum())
    if gross <= 0:
        return {"herfindahl": None, "effective_names": 0.0, "top_1": None,
                "top_5": None, "top_10": None, "names": 0}
    share = (w / gross).sort_values(ascending=False)
    herfindahl = float((share ** 2).sum())
    return {
        "herfindahl": round(herfindahl, 6),
        "effective_names": round(1.0 / max(herfindahl, 1e-12), 2),
        "top_1": round(float(share.iloc[:1].sum()), 6),
        "top_5": round(float(share.iloc[:5].sum()), 6),
        "top_10": round(float(share.iloc[:10].sum()), 6),
        "names": int((w > 1e-12).sum()),
        "method": "inverse_herfindahl_on_gross_weights",
    }


def exposure(weights: pd.Series) -> dict[str, Any]:
    w = weights.dropna()
    longs = float(w[w > 0].sum())
    shorts = float(w[w < 0].sum())
    return {
        "gross": round(float(w.abs().sum()), 6),
        "net": round(float(w.sum()), 6),
        "long": round(longs, 6),
        "short": round(shorts, 6),
        "long_names": int((w > 0).sum()),
        "short_names": int((w < 0).sum()),
    }


def turnover(current: pd.Series, prior: Optional[pd.Series]) -> dict[str, Any]:
    if prior is None or prior.empty:
        return {"one_way": round(float(current.abs().sum()), 6), "method": "initial_build"}
    index = current.index.union(prior.index)
    delta = (current.reindex(index).fillna(0.0) - prior.reindex(index).fillna(0.0)).abs()
    return {
        "one_way": round(float(delta.sum()), 6),
        "names_traded": int((delta > 1e-12).sum()),
        "method": "sum_absolute_weight_change",
    }


# ── report ───────────────────────────────────────────────────────────────────


@dataclass
class RiskReport:
    metrics: dict[str, RiskMetric] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "metrics": {k: v.as_dict() for k, v in self.metrics.items()},
            **self.tables,
            "note": (
                "Every metric carries its method. Historical and parametric "
                "figures are reported separately and are never averaged — they "
                "answer the same question under different assumptions."
            ),
        }


def analyse(
    returns: pd.Series,
    *,
    weights: Optional[pd.Series] = None,
    panel: Optional[pd.DataFrame] = None,
    benchmark: Optional[pd.Series] = None,
    prior_weights: Optional[pd.Series] = None,
    periods_per_year: float = 252.0,
    compound: bool = True,
    risk_free: float = 0.0,
) -> RiskReport:
    """The full report for one strategy's return series and current book.

    `risk_free` is a PER-PERIOD rate, matching the return series. An annual rate
    against daily returns is a common and silent error, so the unit is stated
    here as well as on each function.
    """
    report = RiskReport()
    report.metrics = {
        # dispersion
        "volatility": volatility(returns, periods_per_year=periods_per_year),
        "downside_deviation": downside_deviation(returns, periods_per_year=periods_per_year),
        # risk-adjusted performance
        "sharpe": sharpe(returns, periods_per_year=periods_per_year, risk_free=risk_free),
        "sortino": sortino(returns, periods_per_year=periods_per_year, risk_free=risk_free),
        "calmar": calmar(returns, periods_per_year=periods_per_year, compound=compound),
        "ulcer_performance_index": ulcer_performance_index(
            returns, periods_per_year=periods_per_year, risk_free=risk_free,
            compound=compound),
        # drawdown. Depth alone cannot separate a brief plunge from a long
        # grind to the same trough; the path measures do.
        "max_drawdown": max_drawdown(returns, compound=compound),
        "average_drawdown": average_drawdown(returns, compound=compound),
        "ulcer_index": ulcer_index(returns, compound=compound),
        "drawdown_at_risk_95": drawdown_at_risk(returns, confidence=0.95, compound=compound),
        "conditional_drawdown_at_risk_95": conditional_drawdown_at_risk(
            returns, confidence=0.95, compound=compound),
        # robust dispersion. Reported beside the standard deviation because a
        # large gap between them says how much of the risk figure comes from a
        # handful of periods.
        "mean_absolute_deviation": mean_absolute_deviation(returns),
        "worst_realization": worst_realization(returns),
        # tail. Historical and parametric are kept as separate fields and are
        # never averaged: they answer the same question with different
        # assumptions, and a blend of the two means nothing.
        "var_historical_95": var_historical(returns, confidence=0.95),
        "var_parametric_95": var_parametric(returns, confidence=0.95),
        "cvar_historical_95": cvar_historical(returns, confidence=0.95),
        "var_historical_99": var_historical(returns, confidence=0.99),
        "cvar_historical_99": cvar_historical(returns, confidence=0.99),
    }
    # Shape first: every Gaussian metric above depends on it, and the caveat
    # says so when the tails are fat.
    report.tables["distribution"] = distribution(returns)
    report.tables["drawdown_profile"] = drawdown_profile(returns, compound=compound)

    if benchmark is not None:
        report.metrics["beta"] = beta(returns, benchmark)
        report.metrics["tracking_error"] = tracking_error(
            returns, benchmark, periods_per_year=periods_per_year)
        report.metrics["information_ratio"] = information_ratio(
            returns, benchmark, periods_per_year=periods_per_year)
        report.metrics["capm_alpha"] = capm_alpha(
            returns, benchmark, periods_per_year=periods_per_year, risk_free=risk_free)

    if weights is not None and len(weights):
        report.tables["exposure"] = exposure(weights)
        report.tables["concentration"] = concentration(weights)
        report.tables["turnover"] = turnover(weights, prior_weights)
        if panel is not None and not panel.empty:
            cov = covariance_matrix(panel)
            contributions = risk_contributions(weights, cov)
            report.tables["risk_contributions"] = [
                {
                    "symbol": str(idx),
                    "weight": round(float(row["weight"]), 6),
                    "marginal": round(float(row["marginal"]), 6),
                    "component": round(float(row["component"]), 6),
                    "share": round(float(row["share"]), 6),
                }
                for idx, row in contributions.head(20).iterrows()
            ]
            report.tables["risk_contributions_method"] = (
                "marginal = (Σw)ᵢ / σ_p ; component = wᵢ × marginalᵢ ; "
                "components sum to σ_p by construction"
            )
    return report
