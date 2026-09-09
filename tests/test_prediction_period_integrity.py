"""Period endpoints and undefined ratios on the live technical-analysis path."""
import numpy as np
import pandas as pd
import pytest

from src.prediction_agent import RiskAwarePredictionAgent
from src.providers.schemas import OHLCVBar, PriceSeries


def _agent(closes):
    frame = pd.DataFrame({'Close': closes}, index=pd.bdate_range('2026-01-01', periods=len(closes)))
    return RiskAwarePredictionAgent('AAPL', price_data=frame)


@pytest.mark.parametrize('horizon,field', [(5, 'return_5d'), (21, 'return_21d')])
def test_named_return_has_exactly_that_many_session_intervals(horizon, field):
    closes = [80.0] + [100.0] * horizon
    actual = _agent(closes)._compute_returns()[field]
    assert actual == pytest.approx(0.25)
    series = PriceSeries(symbol='AAPL', bars=[
        OHLCVBar(date=str(i), close=close) for i, close in enumerate(closes)
    ])
    assert actual == pytest.approx(series.pct_change(horizon) / 100)


@pytest.mark.parametrize('horizon,field', [(5, 'return_5d'), (21, 'return_21d')])
def test_horizon_requires_the_baseline_close(horizon, field):
    assert _agent([100.0] * horizon)._compute_returns()[field] is None


@pytest.mark.parametrize('daily_return', [0.001, -0.001])
def test_constant_nonzero_returns_have_no_sharpe(daily_return):
    closes = [100.0 * (1 + daily_return) ** i for i in range(63)]
    assert _agent(closes)._compute_sharpe() is None


def test_constant_negative_returns_have_no_downside_dispersion_ratio():
    closes = [100.0 * 0.999 ** i for i in range(63)]
    assert _agent(closes)._compute_sortino() is None


def test_nonconstant_returns_keep_the_measured_sharpe():
    daily = np.array([0.002, -0.001, 0.004, -0.003] * 16)
    closes = np.concatenate([[100.0], 100 * np.cumprod(1 + daily)])
    expected = daily.mean() / daily.std(ddof=1) * np.sqrt(252)
    assert _agent(closes)._compute_sharpe() == pytest.approx(expected, abs=0.00005)


def test_flat_price_volatility_remains_a_measured_zero():
    assert _agent([100.0] * 63)._compute_volatility() == 0.0
