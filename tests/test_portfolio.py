"""Factor portfolio simulation tests."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.research.portfolio import MIN_NAMES, simulate


def _panel(dates: int, names: int, signal: float, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for step in range(dates):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        scores = rng.normal(size=names)
        noise = rng.normal(size=names)
        returns = (signal * scores + math.sqrt(max(0.0, 1 - signal**2)) * noise) * 0.02
        for index in range(names):
            rows.append({
                "symbol": f"S{index:02d}", "date": day,
                "factor": float(scores[index]),
                "period_return": float(returns[index]),
            })
    return pd.DataFrame(rows)


def test_a_predictive_factor_makes_money():
    result = simulate(_panel(80, 30, signal=0.7), "factor")
    assert result is not None
    assert result.total_return > 0
    assert result.sharpe > 0
    assert result.beat_benchmark


def test_an_inverted_factor_loses_money():
    panel = _panel(80, 30, signal=0.7)
    panel["factor"] = -panel["factor"]
    result = simulate(panel, "factor")
    assert result.total_return < 0
    assert "lost money" in result.assessment


def test_a_worthless_factor_earns_roughly_nothing():
    result = simulate(_panel(80, 30, signal=0.0, seed=7), "factor")
    assert abs(result.total_return) < 0.5


def test_long_and_short_legs_are_reported_separately():
    """A long/short result that is really just a market bet must be visible."""
    result = simulate(_panel(60, 30, signal=0.6), "factor")
    assert result.long_leg_return > result.short_leg_return


def test_equity_curve_compounds_and_aligns_with_total_return():
    result = simulate(_panel(60, 30, signal=0.5), "factor")
    assert len(result.equity_curve) == result.rebalances
    assert result.equity_curve[-1]["strategy"] == pytest.approx(
        1 + result.total_return, rel=1e-6
    )


def test_max_drawdown_is_non_positive():
    result = simulate(_panel(80, 30, signal=0.3), "factor")
    assert result.max_drawdown <= 0


def test_turnover_is_zero_for_a_static_ranking():
    """Same ordering every date means nothing is traded after the first fill."""
    rows = []
    for step in range(30):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        for index in range(30):
            rows.append({
                "symbol": f"S{index:02d}", "date": day,
                "factor": float(index),                 # identical every date
                "period_return": 0.001 * ((index % 3) - 1),
            })
    result = simulate(pd.DataFrame(rows), "factor")
    assert result.turnover == pytest.approx(0.0)


def test_turnover_is_high_for_a_random_ranking():
    result = simulate(_panel(60, 30, signal=0.0, seed=3), "factor")
    assert result.turnover > 0.5


def test_sharpe_is_zero_when_returns_are_constant():
    rows = []
    for step in range(40):
        day = date(2024, 1, 1) + timedelta(days=7 * step)
        for index in range(20):
            rows.append({
                "symbol": f"S{index:02d}", "date": day,
                "factor": float(index), "period_return": 0.001,
            })
    result = simulate(pd.DataFrame(rows), "factor")
    assert result.sharpe == 0.0        # zero volatility, not infinite Sharpe


def test_thin_cross_sections_are_skipped():
    panel = _panel(40, MIN_NAMES - 1, signal=0.5)
    assert simulate(panel, "factor") is None


def test_missing_columns_return_none():
    panel = _panel(40, 30, signal=0.5)
    assert simulate(panel, "absent") is None
    assert simulate(panel.drop(columns=["period_return"]), "factor") is None


def test_too_few_rebalances_returns_none():
    assert simulate(_panel(3, 30, signal=0.5), "factor") is None


def test_short_history_is_flagged_rather_than_judged():
    result = simulate(_panel(10, 30, signal=0.8), "factor")
    assert "too few rebalances" in result.assessment


def test_benchmark_is_the_equal_weight_universe():
    panel = _panel(50, 30, signal=0.0, seed=11)
    result = simulate(panel, "factor")
    expected = np.cumprod(
        1 + panel.groupby("date")["period_return"].mean().to_numpy()
    )[-1] - 1
    assert result.benchmark_return == pytest.approx(expected, rel=1e-6)


def test_bucket_count_changes_concentration():
    panel = _panel(60, 40, signal=0.6)
    wide = simulate(panel, "factor", buckets=2)
    narrow = simulate(panel, "factor", buckets=10)
    assert narrow.total_return != wide.total_return
