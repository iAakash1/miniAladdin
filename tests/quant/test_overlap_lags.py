"""Newey-West lag counts must follow the label, not a constant.

Under-correcting for label overlap does not produce a broken number. It
produces a t-statistic that is merely too large, sitting next to a
`newey_west_lags` field that makes it look accounted for. These tests pin the
three places where the lag count was taken from something other than the label
in hand.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from src.quant.backtest.attribution import attribute_returns
from src.quant.labels.geometry import LabelGeometry
from src.quant.regime import performance_by_regime
from src.quant.validation.metrics import ic_summary
from src.research.cross_section import newey_west_tstat


def _overlapping_noise(n: int, overlap: int, seed: int = 7) -> np.ndarray:
    """Pure noise carrying exactly the dependence an overlapped label imposes."""
    rng = np.random.default_rng(seed)
    raw = rng.normal(0, 1, n + overlap)
    return np.array([raw[i : i + overlap + 1].mean() for i in range(n)]) * 0.02


# --- the lag count must track the horizon -----------------------------------

@pytest.mark.parametrize(
    "horizon, step, expected_lags",
    [(21, 5, 4), (63, 5, 12), (63, 21, 2), (5, 5, 0), (1, 1, 0)],
)
def test_lags_follow_the_label(horizon: int, step: int, expected_lags: int) -> None:
    import pandas as pd

    series = pd.Series(
        _overlapping_noise(200, max(1, horizon // max(1, step))),
        index=pd.bdate_range("2022-01-03", periods=200),
    )
    out = ic_summary(series, horizon_sessions=horizon, step_sessions=step)
    assert out["newey_west_lags"] == expected_lags


def test_a_longer_horizon_is_not_given_the_21_session_lag_count() -> None:
    """The hardcoded value. fwd_ret_63 needs 12 lags and was getting 4."""
    assert LabelGeometry("fwd_ret_63", 63, 5, 0).block_length - 1 == 12
    assert LabelGeometry("fwd_rank_21", 21, 5, 0).block_length - 1 == 4


# --- under-correction inflates, and inflation is the flattering direction ----

def test_too_few_lags_inflates_the_t_statistic() -> None:
    ic = _overlapping_noise(400, overlap=12)
    t_under = abs(newey_west_tstat(ic, 4))
    t_correct = abs(newey_west_tstat(ic, 12))
    assert t_under > t_correct, "fewer lags must not make a signal look weaker"
    assert t_under / t_correct > 1.2


def test_under_correction_can_flip_the_significance_gate_on_noise() -> None:
    """13% of pure-noise draws cleared |t| >= 2.0 at 4 lags but not at 12."""
    flips = 0
    for seed in range(300):
        ic = _overlapping_noise(400, overlap=12, seed=seed)
        if abs(newey_west_tstat(ic, 4)) >= 2.0 > abs(newey_west_tstat(ic, 12)):
            flips += 1
    assert flips > 20, f"expected a material false-pass rate, saw {flips}/300"


def test_block_length_rounds_up_not_down() -> None:
    """floor(21/5) = 4 leaves one overlapping observation uncorrected."""
    assert LabelGeometry("fwd_rank_21", 21, 5, 0).block_length == 5
    assert 21 // 5 == 4


# --- the geometry cannot be omitted ------------------------------------------

def test_performance_by_regime_requires_the_label_geometry() -> None:
    params = inspect.signature(performance_by_regime).parameters
    for name in ("horizon_sessions", "step_sessions"):
        assert params[name].default is inspect.Parameter.empty, (
            f"{name} must not carry a default; a wrong lag count is invisible"
        )


def test_attribute_returns_requires_holding_periods() -> None:
    params = inspect.signature(attribute_returns).parameters
    assert params["holding_periods"].default is inspect.Parameter.empty
    assert params["periods_per_year"].default is inspect.Parameter.empty


def test_omitting_holding_periods_raises_rather_than_assuming_four() -> None:
    import pandas as pd

    dates = pd.bdate_range("2022-01-03", periods=60)
    series = pd.Series(np.random.default_rng(0).normal(size=60), index=dates)
    factors = pd.DataFrame({"date": dates, "mkt": 0.001, "rf": 0.0})
    with pytest.raises(TypeError):
        attribute_returns(series, factors, periods_per_year=252)  # type: ignore[call-arg]
