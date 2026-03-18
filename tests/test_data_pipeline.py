"""Tests for the Async Data Pipeline."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.data_pipeline import AsyncDataPipeline
from src.models import (
    AggregateSentiment,
    MacroStatus,
    RiskAssessment,
    SentimentLabel,
    SignalVerdict,
    TechnicalAnalysis,
)


@pytest.fixture
def mock_risk_assessment() -> RiskAssessment:
    return RiskAssessment(
        risk_multiplier=1.0,
        status=MacroStatus.STABLE,
    )


@pytest.fixture
def mock_technicals() -> TechnicalAnalysis:
    return TechnicalAnalysis(
        ticker="NVDA",
        current_price=950.0,
        return_21d=0.05,
        sharpe_ratio=1.2,
        rsi_14=55.0,
        raw_signal=SignalVerdict.BUY,
        risk_adjusted_signal=SignalVerdict.BUY,
    )


@pytest.fixture
def mock_sentiment() -> AggregateSentiment:
    return AggregateSentiment(
        average_score=0.5,
        dominant_label=SentimentLabel.BULLISH,
        headline_count=3,
    )


class TestComputeVerdict:
    """Test the verdict synthesis logic."""

    def setup_method(self):
        self.pipeline = AsyncDataPipeline(fred_api_key="test")

    def test_bullish_all_aligned(
        self, mock_risk_assessment, mock_technicals, mock_sentiment
    ):
        verdict, confidence, rationale = self.pipeline._compute_verdict(
            mock_risk_assessment, mock_technicals, mock_sentiment
        )
        # BUY + bullish sentiment should boost to STRONG_BUY
        assert verdict in (SignalVerdict.BUY, SignalVerdict.STRONG_BUY)
        assert confidence > 0.5

    def test_dampened_by_negative_sentiment(
        self, mock_risk_assessment, mock_technicals
    ):
        bearish_sentiment = AggregateSentiment(
            average_score=-0.5,
            dominant_label=SentimentLabel.BEARISH,
            headline_count=3,
        )
        verdict, confidence, rationale = self.pipeline._compute_verdict(
            mock_risk_assessment, mock_technicals, bearish_sentiment
        )
        # BUY dampened by bearish sentiment → HOLD
        assert verdict == SignalVerdict.HOLD

    def test_recession_warning_in_rationale(self, mock_technicals, mock_sentiment):
        crisis_macro = RiskAssessment(
            risk_multiplier=1.5,
            status=MacroStatus.CRITICAL,
            yield_curve_inverted=True,
            recession_warning=True,
        )
        _, _, rationale = self.pipeline._compute_verdict(
            crisis_macro, mock_technicals, mock_sentiment
        )
        assert "Recession warning" in rationale or "CRITICAL" in rationale

    def test_no_sentiment_data(self, mock_risk_assessment, mock_technicals):
        empty_sentiment = AggregateSentiment()
        verdict, confidence, rationale = self.pipeline._compute_verdict(
            mock_risk_assessment, mock_technicals, empty_sentiment
        )
        assert "No sentiment data" in rationale
        assert verdict is not None


class TestPipelineExecution:
    """Test the async pipeline execution."""

    @pytest.mark.asyncio
    async def test_run_with_mocked_components(
        self, mock_risk_assessment, mock_technicals, mock_sentiment
    ):
        pipeline = AsyncDataPipeline(fred_api_key="test")

        with patch.object(
            pipeline, "_fetch_macro", return_value=mock_risk_assessment
        ), patch.object(
            pipeline, "_fetch_technicals", return_value=mock_technicals
        ), patch.object(
            pipeline, "_fetch_sentiment", return_value=mock_sentiment
        ):
            report = await pipeline.run("NVDA")

        assert report.ticker == "NVDA"
        assert report.macro is not None
        assert report.technicals is not None
        assert report.sentiment is not None
        assert report.omnisignal_verdict is not None
        assert 0.0 <= report.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_macro_failure_fallback(self, mock_technicals, mock_sentiment):
        pipeline = AsyncDataPipeline(fred_api_key="test")

        with patch.object(
            pipeline, "_fetch_macro", side_effect=Exception("FRED down")
        ), patch.object(
            pipeline, "_fetch_technicals", return_value=mock_technicals
        ), patch.object(
            pipeline, "_fetch_sentiment", return_value=mock_sentiment
        ):
            report = await pipeline.run("NVDA")

        # Should still produce a report with default macro
        assert report.ticker == "NVDA"
        assert report.macro.risk_multiplier == 1.0
