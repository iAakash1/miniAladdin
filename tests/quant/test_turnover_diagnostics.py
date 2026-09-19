"""Turnover forensics: the decomposition must add up and must not read a return."""

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.engine import BacktestConfig, run_backtest
from src.quant.backtest.turnover_diagnostics import (
    breakeven_half_spread,
    decompose_turnover,
    independent_turnover,
    lagged_frame,
)
from tests.quant.test_weight_rules import panel


def _frames(n_symbols=100, n_dates=50, rho=0.7, seed=5):
    pred, ret = panel(n_symbols=n_symbols, n_dates=n_dates, rho=rho, seed=seed)
    return pred, ret, lagged_frame(pred, ret, lag=1)


def test_independent_turnover_equals_the_engine_exactly():
    pred, ret, lag = _frames()
    engine = run_backtest(pred, ret, config=BacktestConfig())
    indep = independent_turnover(lag)
    assert indep["mean_one_way_turnover"] == pytest.approx(engine.metrics["mean_turnover"], rel=1e-12)
    assert indep["annualised_one_way_turnover"] == pytest.approx(engine.metrics["annualised_turnover"], rel=1e-12)
    assert indep["dates_with_different_book_than_qcut"] == 0


def test_independent_turnover_includes_the_max_weight_cap_on_a_thin_date():
    pred, ret = panel(n_symbols=30, n_dates=12, seed=8)
    keep = pred.groupby("date").head(30)
    thin = keep[keep["date"] == sorted(keep["date"].unique())[6]].head(14)      # 14 names -> 3/leg -> capped
    pred2 = pd.concat([keep[keep["date"] != thin["date"].iloc[0]], thin], ignore_index=True)
    lag = lagged_frame(pred2, ret, lag=1)
    engine = run_backtest(pred2, ret, config=BacktestConfig())
    assert independent_turnover(lag)["mean_one_way_turnover"] == pytest.approx(
        engine.metrics["mean_turnover"], rel=1e-12)


def test_decomposition_shares_sum_to_one_and_are_non_negative():
    _, _, lag = _frames()
    out = decompose_turnover(lag)
    shares = out["share_of_turnover"]
    assert shares["check_sums_to_one"] == pytest.approx(1.0)
    assert all(v >= 0 for v in shares["exits"].values())
    assert all(v >= 0 for v in shares["entries"].values())
    assert 0.0 < out["names_replaced_per_rebalance"]["retention_rate"] < 1.0


def test_exits_and_entries_carry_equal_turnover_on_a_stable_universe():
    _, _, lag = _frames()
    out = decompose_turnover(lag)
    exits = sum(out["share_of_turnover"]["exits"].values())
    entries = sum(out["share_of_turnover"]["entries"].values())
    assert exits == pytest.approx(entries, abs=0.02)


def test_a_persistent_signal_has_more_adjacent_band_churn_than_reversal():
    _, _, lag = _frames(rho=0.9)
    out = decompose_turnover(lag)["share_of_turnover"]["exits"]
    assert out["adjacent_band"] > out["full_reversal"]


def test_a_static_signal_has_no_turnover_after_the_first_period():
    pred, ret = panel(n_symbols=60, n_dates=20, seed=2)
    static = pred.copy()
    first = static.groupby("symbol")["prediction"].transform("first")
    static["prediction"] = first
    lag = lagged_frame(static, ret, lag=1)
    assert decompose_turnover(lag)["mean_one_way_turnover"] == pytest.approx(0.0, abs=1e-12)


def test_decomposition_does_not_depend_on_forward_returns():
    pred, ret = panel()
    shuffled = ret.copy()
    shuffled["fwd_ret_5"] = np.random.default_rng(1).permutation(shuffled["fwd_ret_5"].to_numpy())
    a = decompose_turnover(lagged_frame(pred, ret, lag=1))
    b = decompose_turnover(lagged_frame(pred, shuffled, lag=1))
    assert a == b


def test_breakeven_half_spread_zeroes_the_mean_net_return():
    pred, ret, _ = _frames()
    result = run_backtest(pred, ret, config=BacktestConfig())
    out = breakeven_half_spread(result.periods)
    h = out["breakeven_half_spread_bp"]
    p = result.periods
    net = p["gross_return"].mean() - p["turnover_round_trip"].mean() * (1.0 + h) / 1e4 - p["impact"].mean() / 1e6
    assert net == pytest.approx(0.0, abs=1e-12)
    shares = out["cost_components_share"]
    assert sum(shares.values()) == pytest.approx(1.0)
