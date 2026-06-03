"""Tests for the OmniSignal Risk Analysis Engine."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import MacroIndicators, MacroStatus
from src.risk_analysis import OmniSignalRiskEngine


class TestCalculateMultiplier:
    """Tests for the multiplier calculation logic (no FRED calls)."""

    def setup_method(self):
        self.engine = OmniSignalRiskEngine(api_key="test_key")

    def test_stable_conditions(self, normal_indicators):
        result = self.engine.calculate_multiplier(normal_indicators)
        assert result.risk_multiplier == 1.0
        assert result.status == MacroStatus.STABLE
        assert not result.yield_curve_inverted
        assert not result.recession_warning

    def test_inverted_yield_curve(self, inverted_yield_indicators):
        result = self.engine.calculate_multiplier(inverted_yield_indicators)
        assert result.risk_multiplier == 1.3
        assert result.yield_curve_inverted is True
        assert result.recession_warning is True

    def test_high_inflation(self, high_inflation_indicators):
        result = self.engine.calculate_multiplier(high_inflation_indicators)
        assert result.risk_multiplier == 1.2
        assert result.status == MacroStatus.ELEVATED

    def test_crisis_conditions(self, crisis_indicators):
        result = self.engine.calculate_multiplier(crisis_indicators)
        # inverted (0.3) + inflation (0.2) + fed rate (0.1) = 1.6
        assert result.risk_multiplier == 1.6
        assert result.status == MacroStatus.CRITICAL
        assert result.recession_warning is True

    def test_multiplier_clamped_min(self):
        """Multiplier should never go below 0.5."""
        # Normal conditions → 1.0, which is above min
        indicators = MacroIndicators(
            yield_spread=3.0, inflation_rate=1.0, fed_funds_rate=1.0
        )
        result = self.engine.calculate_multiplier(indicators)
        assert result.risk_multiplier >= 0.5

    def test_no_fed_funds_rate(self):
        """Fed funds rate being None should not cause errors."""
        indicators = MacroIndicators(
            yield_spread=-0.5, inflation_rate=5.0, fed_funds_rate=None
        )
        result = self.engine.calculate_multiplier(indicators)
        # inverted (0.3) + inflation (0.2) = 1.5
        assert result.risk_multiplier == 1.5


class TestFetchMacroData:
    """Tests for FRED data fetching (mocked)."""

    def setup_method(self):
        self.engine = OmniSignalRiskEngine(api_key="test_key")

    @patch.object(OmniSignalRiskEngine, "_fetch_yield_spread", return_value=1.5)
    @patch.object(OmniSignalRiskEngine, "_fetch_inflation_rate", return_value=2.5)
    @patch.object(OmniSignalRiskEngine, "_fetch_fed_funds_rate", return_value=3.0)
    def test_get_macro_indicators(self, mock_ff, mock_inf, mock_yield):
        indicators = self.engine.get_macro_indicators()
        assert indicators.yield_spread == 1.5
        assert indicators.inflation_rate == 2.5
        assert indicators.fed_funds_rate == 3.0

    @patch.object(OmniSignalRiskEngine, "_fetch_yield_spread", return_value=-0.5)
    @patch.object(OmniSignalRiskEngine, "_fetch_inflation_rate", return_value=5.0)
    @patch.object(OmniSignalRiskEngine, "_fetch_fed_funds_rate", return_value=5.5)
    def test_get_systemic_risk_multiplier_crisis(self, mock_ff, mock_inf, mock_yield):
        multiplier, stats = self.engine.get_systemic_risk_multiplier()
        assert multiplier == 1.6
        assert stats["status"] == "CRITICAL"
        assert stats["yield_curve_inverted"] is True
        assert stats["recession_warning"] is True

    @patch.object(OmniSignalRiskEngine, "_fetch_yield_spread", return_value=2.0)
    @patch.object(OmniSignalRiskEngine, "_fetch_inflation_rate", return_value=2.0)
    @patch.object(OmniSignalRiskEngine, "_fetch_fed_funds_rate", return_value=3.0)
    def test_get_systemic_risk_multiplier_stable(self, mock_ff, mock_inf, mock_yield):
        multiplier, stats = self.engine.get_systemic_risk_multiplier()
        assert multiplier == 1.0
        assert stats["status"] == "STABLE"

    def test_error_fallback(self):
        """On error, should return default multiplier 1.0."""
        with patch.object(
            self.engine, "get_macro_indicators", side_effect=Exception("API Error")
        ):
            multiplier, stats = self.engine.get_systemic_risk_multiplier()
            assert multiplier == 1.0
            assert stats["status"] == "DATA_ERROR"
