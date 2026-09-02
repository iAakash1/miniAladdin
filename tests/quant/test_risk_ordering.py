"""
Path-dependent risk metrics must refuse a series that is not in date order.

`cumprod` and `cummax` walk a series as given. On a date-indexed series that is
not sorted, the wealth path is wrong and so is everything read off it — and the
output is a different plausible number rather than an error. Measured on 200
observations, shuffling moved maximum drawdown from -0.0959 to -0.1185, the
ulcer index from 0.0462 to 0.0509 and Calmar from 1.75 to 1.42, while
`drawdown_profile` reported a trough date that meant nothing.

Ordinary tests miss this because every fixture is built sorted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.quant.risk import engine

PATH_DEPENDENT = [
    engine.max_drawdown, engine.average_drawdown, engine.ulcer_index,
    engine.drawdown_at_risk, engine.conditional_drawdown_at_risk,
    engine.ulcer_performance_index, engine.calmar,
]
ORDER_INDEPENDENT = [
    engine.volatility, engine.sharpe, engine.mean_absolute_deviation,
    engine.var_historical, engine.worst_realization,
]


@pytest.fixture()
def ordered() -> pd.Series:
    rng = np.random.default_rng(0)
    return pd.Series(rng.normal(0.0005, 0.012, 200),
                     index=pd.bdate_range("2024-01-01", periods=200))


@pytest.fixture()
def shuffled(ordered) -> pd.Series:
    return ordered.sample(frac=1.0, random_state=1)


@pytest.mark.parametrize("fn", PATH_DEPENDENT, ids=lambda f: f.__name__)
def test_path_dependent_metrics_refuse_unordered_dates(fn, shuffled):
    with pytest.raises(engine.UnorderedSeries, match="date order"):
        fn(shuffled)


def test_drawdown_series_and_profile_refuse_too(shuffled):
    with pytest.raises(engine.UnorderedSeries):
        engine.drawdown_series(shuffled)
    with pytest.raises(engine.UnorderedSeries):
        engine.drawdown_profile(shuffled)


@pytest.mark.parametrize("fn", ORDER_INDEPENDENT, ids=lambda f: f.__name__)
def test_order_independent_metrics_are_unaffected(fn, ordered, shuffled):
    """The guard must be scoped. Volatility does not care about order."""
    assert fn(ordered).value == pytest.approx(fn(shuffled).value)


def test_a_positional_index_is_allowed(ordered):
    """With a RangeIndex, row order IS the intended order — nothing to violate."""
    positional = pd.Series(ordered.to_numpy())
    assert engine.max_drawdown(positional).value == pytest.approx(
        engine.max_drawdown(ordered).value
    )


def test_the_shuffle_genuinely_changed_the_answer(ordered, shuffled):
    """Proof the guard is not theoretical.

    Computed on the raw arrays so the guard cannot intervene: the same
    observations in a different order produce a different drawdown.
    """
    def depth(values: np.ndarray) -> float:
        path = np.cumprod(1.0 + values)
        return float((path / np.maximum.accumulate(path) - 1.0).min())

    assert depth(ordered.to_numpy()) != pytest.approx(depth(shuffled.to_numpy()))


def test_a_descending_date_index_is_refused(ordered):
    """Reverse-chronological is the most likely real-world violation."""
    with pytest.raises(engine.UnorderedSeries):
        engine.max_drawdown(ordered.iloc[::-1])


def test_a_single_observation_is_not_treated_as_unordered(ordered):
    """One row cannot be out of order; it must fail on sample size instead."""
    one = ordered.iloc[:1]
    result = engine.max_drawdown(one)
    assert result.value is None
    assert "INSUFFICIENT DATA" in result.caveat
