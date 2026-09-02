"""Backtest: position timing, cost accounting, and terminology discipline."""

from __future__ import annotations

from datetime import date as Date
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from src.quant.backtest.attribution import attribute_returns, compound_factor_returns
from src.quant.backtest.costs import SimpleCostModel, sensitivity_grid
from src.quant.backtest.engine import BacktestConfig, _quantile_weights, run_backtest


# ── costs ───────────────────────────────────────────────────────────────────


def test_no_trade_costs_nothing():
    breakdown = SimpleCostModel().charge(pd.Series({"A": 0.0, "B": 0.0}), capital=1e6)
    assert breakdown.total == 0.0


def test_cost_is_charged_on_traded_notional_not_on_holdings():
    """A position held unchanged across a rebalance must be free."""
    model = SimpleCostModel(commission_bps=1.0, half_spread_bps=5.0, impact_coefficient=0.0)
    traded = model.charge(pd.Series({"A": 0.10}), capital=1e6)
    assert traded.total == pytest.approx(1e6 * 0.10 * 6.0 / 10000.0)
    assert model.charge(pd.Series({"A": 0.0}), capital=1e6).total == 0.0


def test_impact_grows_sublinearly_with_size():
    """The square-root law: doubling size must less than double impact per dollar."""
    model = SimpleCostModel(commission_bps=0, half_spread_bps=0, impact_coefficient=0.1)
    volume = pd.Series({"A": 1e9})
    small = model.charge(pd.Series({"A": 0.01}), capital=1e6, dollar_volume=volume)
    large = model.charge(pd.Series({"A": 0.01}), capital=4e6, dollar_volume=volume)
    assert large.impact < small.impact * 4 * 2.001
    assert large.impact > small.impact


def test_impact_is_zero_without_volume_rather_than_invented():
    model = SimpleCostModel(impact_coefficient=0.1)
    assert model.charge(pd.Series({"A": 0.1}), capital=1e6).impact == 0.0


def test_spread_assumption_is_declared_as_assumed():
    assumptions = SimpleCostModel().assumptions()
    assert "ASSUMED" in assumptions["spread_source"]
    assert "not simulated fills" in assumptions["execution"] or "not simulated" in assumptions["execution"]


def test_sensitivity_grid_sweeps_the_spread():
    assert [m.half_spread_bps for m in sensitivity_grid()] == [1.0, 5.0, 10.0, 20.0]


# ── weights ─────────────────────────────────────────────────────────────────


def test_long_short_book_is_dollar_neutral():
    predictions = pd.Series({f"S{i}": float(i) for i in range(20)})
    weights = _quantile_weights(predictions, quantiles=5, long_short=True, max_weight=1.0)
    assert weights.sum() == pytest.approx(0.0, abs=1e-12)
    assert weights.abs().sum() == pytest.approx(1.0, abs=1e-12)


def test_long_only_book_is_fully_invested():
    predictions = pd.Series({f"S{i}": float(i) for i in range(20)})
    weights = _quantile_weights(predictions, quantiles=5, long_short=False, max_weight=1.0)
    assert weights.sum() == pytest.approx(1.0, abs=1e-12)
    assert (weights >= 0).all()


def test_top_bucket_is_long_and_bottom_is_short():
    predictions = pd.Series({f"S{i}": float(i) for i in range(20)})
    weights = _quantile_weights(predictions, quantiles=5, long_short=True, max_weight=1.0)
    assert weights.get("S19", 0) > 0
    assert weights.get("S0", 0) < 0


def test_max_weight_is_enforced():
    predictions = pd.Series({f"S{i}": float(i) for i in range(10)})
    weights = _quantile_weights(predictions, quantiles=5, long_short=True, max_weight=0.2)
    assert weights.abs().max() <= 0.2 + 1e-12


def test_thin_cross_section_returns_no_weights():
    assert _quantile_weights(pd.Series({"A": 1.0}), quantiles=5, long_short=True, max_weight=1.0) is None


# ── engine ──────────────────────────────────────────────────────────────────


def _panel(periods: int = 60, names: int = 30, seed: int = 5):
    rng = np.random.default_rng(seed)
    dates = [Date(2020, 1, 6) + timedelta(days=7 * i) for i in range(periods)]
    rows = []
    for day in dates:
        signal = rng.normal(size=names)
        forward = signal * 0.01 + rng.normal(scale=0.02, size=names)
        for index in range(names):
            rows.append(
                {
                    "date": day, "symbol": f"S{index:02d}",
                    "prediction": float(signal[index]),
                    "fwd_ret_5": float(forward[index]),
                    "dollar_volume": 5e8,
                }
            )
    frame = pd.DataFrame(rows)
    return frame[["date", "symbol", "prediction"]], frame[["date", "symbol", "fwd_ret_5", "dollar_volume"]]


def test_backtest_is_deterministic():
    predictions, returns = _panel()
    first = run_backtest(predictions, returns, forward_return_column="fwd_ret_5")
    second = run_backtest(predictions, returns, forward_return_column="fwd_ret_5")
    pd.testing.assert_frame_equal(first.periods, second.periods)


def test_net_return_is_gross_minus_cost_every_period():
    predictions, returns = _panel()
    result = run_backtest(predictions, returns, forward_return_column="fwd_ret_5")
    computed = result.periods["gross_return"] - result.periods["cost_return"]
    pd.testing.assert_series_equal(result.periods["net_return"], computed, check_names=False)


def test_costs_reduce_returns_monotonically_in_the_spread():
    predictions, returns = _panel()
    sharpes = []
    for spread in (1.0, 5.0, 20.0, 50.0):
        result = run_backtest(
            predictions, returns,
            config=BacktestConfig(cost_model=SimpleCostModel(half_spread_bps=spread)),
            forward_return_column="fwd_ret_5",
        )
        sharpes.append(result.metrics["net_cagr"])
    assert sharpes == sorted(sharpes, reverse=True)


def test_a_missing_forward_return_column_is_refused_not_derived():
    """Deriving the horizon here would let it silently disagree with the rebalance."""
    predictions, returns = _panel()
    with pytest.raises(ValueError, match="fwd_ret_21"):
        run_backtest(predictions, returns, forward_return_column="fwd_ret_21")


def test_turnover_is_reported_and_positive_for_a_changing_signal():
    predictions, returns = _panel()
    result = run_backtest(predictions, returns, forward_return_column="fwd_ret_5")
    assert result.metrics["mean_turnover"] > 0
    assert result.metrics["annualised_turnover"] > result.metrics["mean_turnover"]


def test_a_signal_with_no_information_does_not_produce_a_positive_result():
    """A pure-noise prediction must not systematically make money.

    The check is on the mean of many independent draws, not one: a single seed
    can be positive by chance, and asserting on it would make this test pass or
    fail for the wrong reason.
    """
    outcomes = []
    for seed in range(12):
        rng = np.random.default_rng(seed)
        dates = [Date(2020, 1, 6) + timedelta(days=7 * i) for i in range(60)]
        rows = []
        for day in dates:
            for index in range(30):
                rows.append(
                    {"date": day, "symbol": f"S{index:02d}",
                     "prediction": float(rng.normal()),
                     "fwd_ret_5": float(rng.normal(scale=0.02)),
                     "dollar_volume": 5e8}
                )
        frame = pd.DataFrame(rows)
        result = run_backtest(
            frame[["date", "symbol", "prediction"]],
            frame[["date", "symbol", "fwd_ret_5", "dollar_volume"]],
            forward_return_column="fwd_ret_5",
        )
        outcomes.append(result.metrics["net_cagr"])
    assert np.mean(outcomes) < 0.02


def test_no_metric_is_named_alpha():
    """Terminology discipline: the engine reports return differences, never alpha."""
    predictions, returns = _panel()
    result = run_backtest(predictions, returns, forward_return_column="fwd_ret_5")
    assert not any("alpha" in key.lower() for key in result.metrics)


# ── attribution ─────────────────────────────────────────────────────────────


def _factors(n: int = 900, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n).date
    return pd.DataFrame(
        {
            "date": dates,
            "mkt_rf": rng.normal(0.0003, 0.01, n),
            "smb": rng.normal(0, 0.005, n),
            "hml": rng.normal(0, 0.005, n),
            "rmw": rng.normal(0, 0.004, n),
            "cma": rng.normal(0, 0.004, n),
            "rf": np.full(n, 0.00008),
            "mom": rng.normal(0, 0.006, n),
        }
    )


def test_a_pure_factor_bet_shows_the_exposure_and_no_alpha():
    """A strategy that IS momentum must load on MOM and show a zero intercept."""
    factors = _factors()
    weekly = sorted({d for d in factors["date"] if d.weekday() == 4})
    compounded = compound_factor_returns(factors, weekly)
    series = pd.Series(
        (compounded["mom"] * 0.9).to_numpy(), index=compounded["date"].to_numpy()
    )
    result = attribute_returns(series, factors, periods_per_year=52, holding_periods=4)
    assert result.betas["mom"] == pytest.approx(0.9, abs=0.05)
    assert abs(result.alpha_t_stat) < 2.0
    assert result.alpha_significant is False
    assert "return difference, not alpha" in result.verdict()


def test_a_genuine_intercept_is_detected():
    factors = _factors()
    weekly = sorted({d for d in factors["date"] if d.weekday() == 4})
    compounded = compound_factor_returns(factors, weekly)
    series = pd.Series(
        (compounded["mom"] * 0.3 + 0.004).to_numpy(), index=compounded["date"].to_numpy()
    )
    result = attribute_returns(series, factors, periods_per_year=52, holding_periods=4)
    assert result.alpha_per_period == pytest.approx(0.004, abs=0.001)
    assert result.alpha_significant is True


def test_too_few_observations_reports_nothing_rather_than_a_number():
    factors = _factors(n=60)
    weekly = sorted({d for d in factors["date"] if d.weekday() == 4})[:8]
    series = pd.Series(np.random.default_rng(0).normal(size=len(weekly)), index=weekly)
    result = attribute_returns(series, factors, periods_per_year=52, holding_periods=4)
    assert result.alpha_t_stat is None
    assert "below" in result.note or "overlapping" in result.note


def test_factor_compounding_is_geometric_and_drops_the_first_boundary():
    factors = pd.DataFrame(
        {"date": pd.bdate_range("2024-01-01", periods=10).date, "mkt_rf": [0.01] * 10,
         "rf": [0.0] * 10}
    )
    boundaries = [factors["date"].iloc[4], factors["date"].iloc[9]]
    out = compound_factor_returns(factors, boundaries, columns=["mkt_rf"])
    # First boundary is dropped; the second compounds the 5 days after it.
    assert len(out) == 1
    assert out["mkt_rf"].iloc[0] == pytest.approx(1.01**5 - 1, rel=1e-9)


# ── execution lag ───────────────────────────────────────────────────────────
#
# EXP-002 formed positions at the close its signal was computed from. These
# tests exist so that reverting to same-period execution fails loudly rather
# than silently improving every number.


def test_execution_lag_defaults_to_one_period():
    """The default must never drift back to 0.

    A lag of 0 means the signal computed from date t's close is traded at that
    same close, which is not achievable. If a future change makes 0 the default
    again, this fails.
    """
    assert BacktestConfig().execution_lag_periods == 1


def test_execution_lag_is_recorded_in_the_config_payload():
    """A backtest's assumptions must travel with its result."""
    payload = BacktestConfig().as_dict()
    assert payload["execution_lag_periods"] == 1
    assert "not achievable" in payload["execution_lag_note"]


def test_zero_lag_produces_a_different_and_better_looking_result():
    """Demonstrates why the lag matters rather than asserting that it does.

    Same predictions, same returns; only the execution assumption changes. If
    lag 0 and lag 1 gave the same answer the parameter would be cosmetic.
    """
    predictions, returns = _panel(periods=80, names=30, seed=3)
    optimistic = run_backtest(
        predictions, returns,
        config=BacktestConfig(execution_lag_periods=0), forward_return_column="fwd_ret_5",
    )
    realistic = run_backtest(
        predictions, returns,
        config=BacktestConfig(execution_lag_periods=1), forward_return_column="fwd_ret_5",
    )
    assert optimistic.metrics["net_cagr"] != realistic.metrics["net_cagr"]
    # The synthetic panel has a real contemporaneous signal, so removing the
    # same-period advantage must cost performance.
    assert realistic.metrics["net_cagr"] < optimistic.metrics["net_cagr"]


def test_lagged_backtest_never_uses_a_prediction_from_the_period_it_trades():
    """The invariant, checked on the joined frame rather than inferred."""
    from src.quant.backtest.engine import _apply_execution_lag

    predictions, _ = _panel(periods=20, names=5, seed=1)
    original = predictions.set_index(["symbol", "date"])["prediction"]
    lagged = _apply_execution_lag(
        predictions, 1, prediction_column="prediction",
        date_column="date", symbol_column="symbol",
    ).set_index(["symbol", "date"])["prediction"]

    for (symbol, date_), value in lagged.items():
        same_period = original.loc[(symbol, date_)]
        # The value carried into this period must not be this period's own
        # signal (the synthetic panel gives every row a distinct prediction).
        assert value != same_period
