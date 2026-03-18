"""Tests for the Risk-Aware Prediction Agent."""

from unittest.mock import PropertyMock, patch

import pandas as pd
import pytest

from src.models import SignalVerdict
from src.prediction_agent import RiskAwarePredictionAgent


class TestDampeningLogic:
    """Test signal dampening based on risk multiplier."""

    def setup_method(self):
        self.agent = RiskAwarePredictionAgent(ticker="TEST")

    def test_no_dampening_neutral(self):
        """Multiplier 1.0 should not change the signal."""
        result = self.agent._apply_dampening(SignalVerdict.BUY, 1.0)
        assert result == SignalVerdict.BUY

    def test_moderate_dampening(self):
        """Multiplier > 1.2 should downgrade by 1 level."""
        result = self.agent._apply_dampening(SignalVerdict.STRONG_BUY, 1.25)
        assert result == SignalVerdict.BUY

    def test_critical_dampening(self):
        """Multiplier > 1.3 should downgrade by 2 levels."""
        result = self.agent._apply_dampening(SignalVerdict.STRONG_BUY, 1.4)
        assert result == SignalVerdict.HOLD

    def test_critical_dampening_buy_to_sell(self):
        """Multiplier > 1.3 on BUY should go to SELL."""
        result = self.agent._apply_dampening(SignalVerdict.BUY, 1.5)
        assert result == SignalVerdict.SELL

    def test_boost_low_risk(self):
        """Multiplier < 0.9 should boost by 1 level."""
        result = self.agent._apply_dampening(SignalVerdict.HOLD, 0.8)
        assert result == SignalVerdict.BUY

    def test_dampening_floor(self):
        """Cannot dampen below STRONG_SELL."""
        result = self.agent._apply_dampening(SignalVerdict.STRONG_SELL, 1.5)
        assert result == SignalVerdict.STRONG_SELL

    def test_boost_ceiling(self):
        """Cannot boost above STRONG_BUY."""
        result = self.agent._apply_dampening(SignalVerdict.STRONG_BUY, 0.7)
        assert result == SignalVerdict.STRONG_BUY


class TestRawSignal:
    """Test the raw signal generation logic."""

    def setup_method(self):
        self.agent = RiskAwarePredictionAgent(ticker="TEST")

    def test_strong_buy_conditions(self):
        """High RSI momentum, strong sharpe, positive return."""
        signal = self.agent._raw_signal(rsi=58.0, sharpe=2.0, return_21d=0.15)
        assert signal in (SignalVerdict.STRONG_BUY, SignalVerdict.BUY)

    def test_sell_conditions(self):
        """Overbought RSI, negative sharpe, negative return."""
        signal = self.agent._raw_signal(rsi=75.0, sharpe=-1.0, return_21d=-0.12)
        assert signal in (SignalVerdict.STRONG_SELL, SignalVerdict.SELL)

    def test_hold_neutral(self):
        """Neutral conditions should produce HOLD."""
        signal = self.agent._raw_signal(rsi=50.0, sharpe=0.2, return_21d=0.01)
        assert signal == SignalVerdict.HOLD

    def test_none_inputs(self):
        """All None inputs should produce HOLD."""
        signal = self.agent._raw_signal(rsi=None, sharpe=None, return_21d=None)
        assert signal == SignalVerdict.HOLD


class TestPrediction:
    """Test full prediction pipeline with mocked price data."""

    def test_predict_with_mock_data(self, mock_price_data):
        agent = RiskAwarePredictionAgent(ticker="TEST")
        # Inject mock data
        agent._data = mock_price_data

        result = agent.predict(risk_multiplier=1.0)
        assert result.ticker == "TEST"
        assert result.current_price is not None
        assert result.raw_signal is not None
        assert result.risk_adjusted_signal is not None

    def test_predict_with_dampening(self, mock_price_data):
        agent = RiskAwarePredictionAgent(ticker="TEST")
        agent._data = mock_price_data

        normal = agent.predict(risk_multiplier=1.0)
        dampened = agent.predict(risk_multiplier=1.5)

        # Dampened signal should be same or more conservative
        signal_order = [
            SignalVerdict.STRONG_SELL,
            SignalVerdict.SELL,
            SignalVerdict.HOLD,
            SignalVerdict.BUY,
            SignalVerdict.STRONG_BUY,
        ]
        normal_idx = signal_order.index(normal.risk_adjusted_signal)
        dampened_idx = signal_order.index(dampened.risk_adjusted_signal)
        assert dampened_idx <= normal_idx
