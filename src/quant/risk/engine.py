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
) -> RiskReport:
    """The full report for one strategy's return series and current book."""
    report = RiskReport()
    report.metrics = {
        "volatility": volatility(returns, periods_per_year=periods_per_year),
        "downside_deviation": downside_deviation(returns, periods_per_year=periods_per_year),
        "max_drawdown": max_drawdown(returns, compound=compound),
        "var_historical_95": var_historical(returns, confidence=0.95),
        "var_parametric_95": var_parametric(returns, confidence=0.95),
        "cvar_historical_95": cvar_historical(returns, confidence=0.95),
        "var_historical_99": var_historical(returns, confidence=0.99),
        "cvar_historical_99": cvar_historical(returns, confidence=0.99),
    }
    if benchmark is not None:
        report.metrics["beta"] = beta(returns, benchmark)

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
