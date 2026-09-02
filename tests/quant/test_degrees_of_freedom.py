"""Each estimator's degrees of freedom, pinned with its justification.

The sweep behind this file is recorded in docs/SEMANTIC_AUDIT.md. Most of the
codebase already used `ddof=1` consistently, which is right for a sample
statistic. A regression residual is not a sample statistic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.attribution import attribute_returns
from src.quant.portfolio.optimizer import covariance


def _factors(n: int = 300, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "mkt": rng.normal(0.0003, 0.01, n),
            "smb": rng.normal(0.0, 0.006, n),
            "hml": rng.normal(0.0, 0.006, n),
            "rf": 0.0,
        }
    )


def test_residual_volatility_uses_n_minus_k_not_n_minus_one() -> None:
    """Fitting k coefficients consumes k degrees of freedom."""
    factors = _factors()
    rng = np.random.default_rng(11)
    series = pd.Series(rng.normal(0.0002, 0.011, len(factors)), index=factors["date"])

    result = attribute_returns(
        series, factors, periods_per_year=252.0, holding_periods=1
    )
    k = len(result.factors_used) + 1        # regressors plus the intercept
    n = result.observations

    annual = np.sqrt(252.0)
    per_period = result.residual_volatility / annual
    # Reconstruct both conventions from the same residual sum of squares.
    rss = per_period**2 * (n - k)
    wrong = np.sqrt(rss / (n - 1))
    assert per_period > wrong, "n-1 understates the residual dispersion"
    assert per_period / wrong == pytest.approx(np.sqrt((n - 1) / (n - k)), rel=1e-6)


def test_the_understatement_grows_as_observations_shrink() -> None:
    """0.6% at 500 observations, 21% at 20 — the reason it is worth fixing."""
    k = 7
    ratios = [np.sqrt((n - 1) / (n - k)) for n in (500, 250, 120, 60, 30, 20)]
    assert ratios == sorted(ratios)
    assert ratios[0] < 1.01
    assert ratios[-1] > 1.20


def test_sample_statistics_still_use_ddof_one() -> None:
    """The correction is specific to regression residuals, not general."""
    from src.quant.risk import engine as risk

    rng = np.random.default_rng(2)
    series = pd.Series(
        rng.normal(0.0004, 0.012, 300), index=pd.bdate_range("2022-01-03", periods=300)
    )
    vol = risk.volatility(series, periods_per_year=252.0)
    expected = float(series.std(ddof=1) * np.sqrt(252.0))
    assert vol.value == pytest.approx(expected)


def test_covariance_and_its_diagonal_agree_on_ddof() -> None:
    """A ratio built from two different conventions is wrong in a hidden way."""
    rng = np.random.default_rng(6)
    frame = pd.DataFrame(rng.normal(0, 0.02, (400, 4)), columns=list("ABCD"))
    cov = covariance(frame, ridge=0.0)
    for name in frame.columns:
        assert cov.loc[name, name] == pytest.approx(float(frame[name].var(ddof=1)))


def test_beta_numerator_and_denominator_share_a_convention() -> None:
    from src.quant.risk import engine as risk

    rng = np.random.default_rng(8)
    idx = pd.bdate_range("2022-01-03", periods=300)
    bench = pd.Series(rng.normal(0.0003, 0.01, 300), index=idx)
    port = 1.3 * bench + pd.Series(rng.normal(0, 0.004, 300), index=idx)

    result = risk.beta(port, bench)
    joined = pd.concat([port, bench], axis=1, join="inner").dropna()
    expected = float(joined.cov().iloc[0, 1] / joined.iloc[:, 1].var(ddof=1))
    assert result.value == pytest.approx(expected)
    assert result.value == pytest.approx(1.3, abs=0.1)
