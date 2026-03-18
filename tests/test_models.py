"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from src.models import (
    AggregateSentiment,
    MacroIndicators,
    MacroStatus,
    OmniSignalReport,
    RiskAssessment,
    SentimentLabel,
    SentimentResult,
    SignalVerdict,
    TechnicalAnalysis,
)


class TestMacroIndicators:
    def test_valid_creation(self):
        m = MacroIndicators(yield_spread=1.5, inflation_rate=3.0)
        assert m.yield_spread == 1.5
        assert m.inflation_rate == 3.0
        assert m.fed_funds_rate is None

    def test_with_fed_funds(self):
        m = MacroIndicators(yield_spread=0.5, inflation_rate=2.0, fed_funds_rate=4.5)
        assert m.fed_funds_rate == 4.5

    def test_negative_yield_spread(self):
        m = MacroIndicators(yield_spread=-1.0, inflation_rate=3.0)
        assert m.yield_spread == -1.0


class TestRiskAssessment:
    def test_valid_creation(self):
        r = RiskAssessment(risk_multiplier=1.0)
        assert r.risk_multiplier == 1.0
        assert r.status == MacroStatus.STABLE
        assert not r.recession_warning

    def test_multiplier_bounds_min(self):
        with pytest.raises(ValidationError):
            RiskAssessment(risk_multiplier=0.3)

    def test_multiplier_bounds_max(self):
        with pytest.raises(ValidationError):
            RiskAssessment(risk_multiplier=2.0)

    def test_critical_status(self):
        r = RiskAssessment(
            risk_multiplier=1.5,
            status=MacroStatus.CRITICAL,
            yield_curve_inverted=True,
            recession_warning=True,
        )
        assert r.status == MacroStatus.CRITICAL
        assert r.recession_warning


class TestSentimentResult:
    def test_valid_creation(self):
        s = SentimentResult(
            headline="Stock surges", score=0.8, label=SentimentLabel.BULLISH
        )
        assert s.score == 0.8
        assert s.label == SentimentLabel.BULLISH

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            SentimentResult(headline="test", score=1.5, label=SentimentLabel.NEUTRAL)

    def test_empty_headline_rejected(self):
        with pytest.raises(ValidationError):
            SentimentResult(headline="", score=0.0, label=SentimentLabel.NEUTRAL)


class TestAggregateSentiment:
    def test_empty_default(self):
        a = AggregateSentiment()
        assert a.headline_count == 0
        assert a.average_score == 0.0

    def test_score_rounding(self):
        a = AggregateSentiment(average_score=0.33333333)
        assert a.average_score == 0.3333


class TestTechnicalAnalysis:
    def test_valid_creation(self):
        t = TechnicalAnalysis(ticker="NVDA", current_price=950.0)
        assert t.ticker == "NVDA"
        assert t.current_price == 950.0

    def test_rsi_bounds(self):
        with pytest.raises(ValidationError):
            TechnicalAnalysis(ticker="NVDA", rsi_14=150.0)


class TestOmniSignalReport:
    def test_default_report(self):
        r = OmniSignalReport(ticker="AAPL")
        assert r.ticker == "AAPL"
        assert r.omnisignal_verdict == SignalVerdict.HOLD
        assert r.confidence == 0.5

    def test_full_report(self):
        r = OmniSignalReport(
            ticker="NVDA",
            omnisignal_verdict=SignalVerdict.STRONG_BUY,
            confidence=0.85,
            rationale="All signals align bullish",
        )
        assert r.omnisignal_verdict == SignalVerdict.STRONG_BUY
        assert r.confidence == 0.85


class TestSignalVerdict:
    def test_all_verdicts_exist(self):
        assert SignalVerdict.STRONG_BUY.value == "Strong Buy"
        assert SignalVerdict.BUY.value == "Buy"
        assert SignalVerdict.HOLD.value == "Hold"
        assert SignalVerdict.SELL.value == "Sell"
        assert SignalVerdict.STRONG_SELL.value == "Strong Sell"
