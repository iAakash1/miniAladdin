"""
OmniSignal Async Data Pipeline
Concurrent data fetching from FRED, Yahoo Finance, and news sources.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.decision import compute_decision
from src.models import (
    AggregateSentiment,
    OmniSignalReport,
    RiskAssessment,
    SignalVerdict,
    TechnicalAnalysis,
)
from src.prediction_agent import RiskAwarePredictionAgent
from src.risk_analysis import OmniSignalRiskEngine
from src.sentiment_edge import SentimentAnalyzer

logger = logging.getLogger(__name__)


class AsyncDataPipeline:
    """
    Orchestrates concurrent data fetching from multiple financial data sources
    and assembles a unified OmniSignalReport.
    """

    def __init__(self, fred_api_key: Optional[str] = None):
        self.risk_engine = OmniSignalRiskEngine(api_key=fred_api_key)
        self.sentiment_analyzer = SentimentAnalyzer(max_headlines=5)

    async def _fetch_macro(self) -> RiskAssessment:
        """Fetch macro indicators (runs in thread pool since fredapi is sync)."""
        loop = asyncio.get_event_loop()
        indicators = await loop.run_in_executor(
            None, self.risk_engine.get_macro_indicators
        )
        return self.risk_engine.calculate_multiplier(indicators)

    async def _fetch_technicals(
        self, ticker: str, risk_multiplier: float
    ) -> TechnicalAnalysis:
        """Fetch technical analysis (runs in thread pool since yfinance is sync)."""
        loop = asyncio.get_event_loop()
        agent = RiskAwarePredictionAgent(ticker=ticker)

        def _run():
            return agent.predict(risk_multiplier=risk_multiplier)

        return await loop.run_in_executor(None, _run)

    async def _fetch_sentiment(self, ticker: str) -> AggregateSentiment:
        """Fetch sentiment analysis (runs in thread pool since requests is sync)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.sentiment_analyzer.analyze_ticker, ticker
        )

    def _compute_verdict(
        self,
        macro: RiskAssessment,
        technicals: TechnicalAnalysis,
        sentiment: AggregateSentiment,
    ) -> tuple[SignalVerdict, float, str]:
        """
        Compute the final OmniSignal verdict by synthesizing all three factors.

        Returns (verdict, confidence, rationale).

        The implementation lives in src/decision.py so the HTTP API and this
        pipeline share a single source of truth.
        """
        return compute_decision(macro, technicals, sentiment)

    async def run(self, ticker: str) -> OmniSignalReport:
        """
        Execute the full pipeline concurrently and return a complete report.
        """
        # Step 1: Macro first (needed for dampening)
        try:
            macro = await self._fetch_macro()
        except Exception as e:
            logger.exception("Macro fetch failed — falling back to neutral SRM (%s)", e)
            macro = RiskAssessment(risk_multiplier=1.0)

        # Step 2: Technicals + Sentiment in parallel
        tech_task = asyncio.create_task(
            self._fetch_technicals(ticker, macro.risk_multiplier)
        )
        sentiment_task = asyncio.create_task(self._fetch_sentiment(ticker))

        technicals = await tech_task
        sentiment = await sentiment_task

        # Step 3: Compute final verdict
        verdict, confidence, rationale = self._compute_verdict(
            macro, technicals, sentiment
        )

        return OmniSignalReport(
            ticker=ticker.upper(),
            macro=macro,
            technicals=technicals,
            sentiment=sentiment,
            omnisignal_verdict=verdict,
            confidence=confidence,
            rationale=rationale,
        )

    async def run_fast(self, ticker: str) -> OmniSignalReport:
        """
        Fast-track pipeline for Vercel's 10s timeout.
        Returns macro risk + technicals only, skipping sentiment.
        Designed to complete in ~3-4 seconds.
        """
        # Step 1: Macro
        try:
            macro = await self._fetch_macro()
        except Exception as e:
            logger.exception("Macro fetch failed — falling back to neutral SRM (%s)", e)
            macro = RiskAssessment(risk_multiplier=1.0)

        # Step 2: Technicals only (no sentiment)
        try:
            technicals = await self._fetch_technicals(ticker, macro.risk_multiplier)
        except Exception as e:
            logger.exception("Technical fetch failed for %s (%s)", ticker, e)
            technicals = TechnicalAnalysis(ticker=ticker.upper())

        # Compute verdict without sentiment
        empty_sentiment = AggregateSentiment()
        verdict, confidence, rationale = self._compute_verdict(
            macro, technicals, empty_sentiment
        )

        return OmniSignalReport(
            ticker=ticker.upper(),
            macro=macro,
            technicals=technicals,
            sentiment=empty_sentiment,
            omnisignal_verdict=verdict,
            confidence=confidence,
            rationale=f"[FAST MODE] {rationale}",
        )

    def run_sync(self, ticker: str) -> OmniSignalReport:
        """Synchronous wrapper for environments without an event loop."""
        return asyncio.run(self.run(ticker))

    def run_fast_sync(self, ticker: str) -> OmniSignalReport:
        """Synchronous fast-track wrapper."""
        return asyncio.run(self.run_fast(ticker))
