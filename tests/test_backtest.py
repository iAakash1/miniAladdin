"""Tests for the walk-forward validation service (mocked provider data)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pytest

from src.providers.schemas import OHLCVBar, PriceSeries, ProviderResult
from src.services import backtest_service as bt


def _to_result(closes: np.ndarray, rng) -> ProviderResult[PriceSeries]:
    bars = []
    day = date(2021, 1, 4)
    for close in closes:
        while day.weekday() >= 5:
            day = date.fromordinal(day.toordinal() + 1)
        bars.append(OHLCVBar(date=day.isoformat(), open=close, high=close * 1.01,
                             low=close * 0.99, close=float(close),
                             volume=int(rng.integers(1_000_000, 2_000_000))))
        day = date.fromordinal(day.toordinal() + 1)
    return ProviderResult(data=PriceSeries(symbol="X", bars=bars), source="test", confidence=0.85)


def make_series(days: int, drift: float, vol: float, seed: int = 11) -> ProviderResult[PriceSeries]:
    """Constant-drift GBM — memoryless returns, i.e. NO momentum by construction."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, days)
    closes = 100 * np.cumprod(1 + returns)
    return _to_result(closes, rng)


def make_regime_series(days: int, seed: int = 11) -> ProviderResult[PriceSeries]:
    """Regime-switching drift (±0.2%/day) with ~18-month regimes — matching
    the 6-12+ month trend persistence that makes 12-1 momentum work
    empirically (Jegadeesh–Titman). Regimes shorter than the momentum
    lookback would make ANY long-window momentum anti-predictive by
    construction (the factor would measure the previous regime)."""
    rng = np.random.default_rng(seed)
    returns = np.empty(days)
    drift = 0.002
    for i in range(days):
        if i % 378 == 0 and i > 0:
            drift = -drift
        returns[i] = rng.normal(drift, 0.008)
    closes = 100 * np.cumprod(1 + returns)
    return _to_result(closes, rng)


@pytest.fixture(autouse=True)
def clean():
    bt.reset_for_tests()
    yield
    bt.reset_for_tests()


class TestBacktest:
    def test_ic_discriminates_signal_from_noise_and_full_shape(self):
        # The scientifically meaningful property: the engine finds MORE
        # rank-signal where returns are serially correlated (regime drift)
        # than on a memoryless GBM, and stays positive where momentum exists.
        # (The composite blends trend + contrarian factors, so absolute IC
        # on synthetic data is modest by design.)
        regimes = make_regime_series(900)
        with patch.object(bt.providers.market_data, "get_series", return_value=regimes):
            result = bt.run_backtest("TREND")

        gbm = make_series(800, drift=0.0005, vol=0.012, seed=23)
        with patch.object(bt.providers.market_data, "get_series", return_value=gbm):
            noise_result = bt.run_backtest("NOISE")

        assert "error" not in result and "error" not in noise_result
        assert result["samples"] >= 50
        assert result["ic"] is not None and result["ic"] > 0
        assert noise_result["ic"] is not None and abs(noise_result["ic"]) < 0.35
        assert result["ic"] > noise_result["ic"]
        assert result["hit_rate"] is None or result["hit_rate"] >= 0

        # Shape: every promised section present
        for key in ("rolling_ic", "confusion_matrix", "calibration", "strategy",
                     "buy_hold", "equity_curve", "monthly_strategy_returns",
                     "score_distribution", "verdict_distribution", "scope_note"):
            assert key in result, f"missing {key}"

        matrix = result["confusion_matrix"]
        assert set(matrix) == {"long", "flat", "short"}
        assert all(set(row) == {"up", "down"} for row in matrix.values())

        total_cells = sum(cell for row in matrix.values() for cell in row.values())
        assert total_cells == result["samples"]

        assert result["strategy"]["sharpe"] is None or isinstance(result["strategy"]["sharpe"], float)
        assert result["equity_curve"][0]["strategy"] == pytest.approx(1.0, abs=0.1)

    def test_insufficient_history_returns_explicit_error(self):
        short = make_series(120, drift=0.001, vol=0.01)
        with patch.object(bt.providers.market_data, "get_series", return_value=short):
            result = bt.run_backtest("SHORT")
        assert "error" in result

    def test_result_is_cached(self):
        trending = make_series(700, drift=0.001, vol=0.012)
        with patch.object(bt.providers.market_data, "get_series", return_value=trending) as mocked:
            first = bt.run_backtest("CACHE")
            second = bt.run_backtest("CACHE")
        assert first["cached"] is False
        assert second["cached"] is True
        assert mocked.call_count == 1

    def test_calibration_bins_are_bounded(self):
        trending = make_series(800, drift=0.0012, vol=0.012, seed=5)
        with patch.object(bt.providers.market_data, "get_series", return_value=trending):
            result = bt.run_backtest("CAL")
        for bin_row in result["calibration"]:
            assert 0 <= bin_row["actual"] <= 100
            assert bin_row["n"] >= 3
