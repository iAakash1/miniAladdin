"""
OmniSignal Prediction Agent
Risk-aware prediction with optional Alpha Vantage fundamental enrichment.

Signal scoring layers:
  Layer 1: RSI momentum
  Layer 2: Sharpe ratio (risk-adjusted return quality)
  Layer 3: 21-day return momentum
  Layer 4: MACD crossover (Alpha Vantage)
  Layer 5: Analyst target vs current price (Alpha Vantage)
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import yfinance as yf
import numpy as np
import pandas as pd

from src.models import SignalVerdict, TechnicalAnalysis

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.alpha_vantage import AlphaVantageClient, FundamentalData, MacdSignal


class RiskAwarePredictionAgent:
    """
    Multi-layer technical analysis with macro risk dampening.

    Base layer: yfinance price data + manual indicator calculation
    Enrichment: Alpha Vantage fundamentals + MACD (when key available)
    """

    # Signal dampening thresholds
    DAMPEN_THRESHOLD  = 1.2
    BOOST_THRESHOLD   = 0.9
    CRITICAL_THRESHOLD = 1.3

    # Lookback
    SHORT_WINDOW  = 5
    MEDIUM_WINDOW = 21
    RSI_WINDOW    = 14

    def __init__(
        self,
        ticker: str,
        period: str = "3mo",
        av_client: Optional["AlphaVantageClient"] = None,
    ):
        self.ticker    = ticker.upper()
        self.period    = period
        self.av_client = av_client
        self._data: Optional[pd.DataFrame] = None

    @property
    def data(self) -> pd.DataFrame:
        if self._data is None:
            stock = yf.Ticker(self.ticker)
            self._data = stock.history(period=self.period)
            if self._data.empty:
                raise ValueError(f"No price data found for {self.ticker}")
        return self._data

    # ── Technical indicators (yfinance) ──────────────────────────────────────

    def _compute_returns(self) -> dict:
        closes = self.data["Close"]
        return {
            "return_5d":  float(closes.iloc[-1] / closes.iloc[-self.SHORT_WINDOW] - 1)
                          if len(closes) >= self.SHORT_WINDOW else None,
            "return_21d": float(closes.iloc[-1] / closes.iloc[-self.MEDIUM_WINDOW] - 1)
                          if len(closes) >= self.MEDIUM_WINDOW else None,
        }

    def _compute_volatility(self) -> Optional[float]:
        daily = self.data["Close"].pct_change().dropna()
        if len(daily) < 2:
            return None
        return float(daily.std() * np.sqrt(252))

    def _compute_sharpe(self) -> Optional[float]:
        daily = self.data["Close"].pct_change().dropna()
        if len(daily) < 2 or daily.std() == 0:
            return None
        return float(round((daily.mean() * 252) / (daily.std() * np.sqrt(252)), 4))

    def _compute_sortino(self) -> Optional[float]:
        daily    = self.data["Close"].pct_change().dropna()
        downside = daily[daily < 0]
        if len(downside) < 2 or downside.std() == 0:
            return None
        return float(round(daily.mean() / downside.std(), 4))

    def _compute_rsi(self) -> Optional[float]:
        closes = self.data["Close"]
        if len(closes) < self.RSI_WINDOW + 1:
            return None
        delta  = closes.diff()
        gain   = delta.where(delta > 0, 0.0).rolling(window=self.RSI_WINDOW).mean()
        loss   = (-delta.where(delta < 0, 0.0)).rolling(window=self.RSI_WINDOW).mean()
        rs     = gain / loss
        return float(round((100 - 100 / (1 + rs)).iloc[-1], 2))

    def _compute_max_drawdown(self) -> Optional[float]:
        closes = self.data["Close"]
        if len(closes) < 2:
            return None
        peak = closes.cummax()
        return float(round(((closes - peak) / peak).min(), 4))

    def _compute_momentum(self) -> Optional[float]:
        closes = self.data["Close"]
        if len(closes) < self.MEDIUM_WINDOW:
            return None
        return float(round(closes.iloc[-1] - closes.iloc[-self.MEDIUM_WINDOW], 2))

    # ── Signal scoring ────────────────────────────────────────────────────────

    def _raw_signal(
        self,
        rsi: Optional[float],
        sharpe: Optional[float],
        return_21d: Optional[float],
        macd: Optional["MacdSignal"] = None,
        fundamentals: Optional["FundamentalData"] = None,
        current_price: Optional[float] = None,
    ) -> SignalVerdict:
        """
        Multi-layer scoring.
        Max possible: ±10 → maps to Strong Buy / Strong Sell at ±4.
        """
        score = 0

        # Layer 1: RSI
        if rsi is not None:
            if rsi > 70:    score -= 2   # overbought
            elif rsi < 30:  score += 2   # oversold — buying opportunity
            elif rsi > 55:  score += 1
            elif rsi < 45:  score -= 1

        # Layer 2: Sharpe ratio
        if sharpe is not None:
            if sharpe > 1.5:    score += 2
            elif sharpe > 0.5:  score += 1
            elif sharpe < -0.5: score -= 2
            elif sharpe < 0:    score -= 1

        # Layer 3: 21-day return momentum
        if return_21d is not None:
            if return_21d > 0.10:   score += 2
            elif return_21d > 0.03: score += 1
            elif return_21d < -0.10: score -= 2
            elif return_21d < -0.03: score -= 1

        # Layer 4: MACD crossover (Alpha Vantage)
        if macd is not None and not macd.error:
            if macd.crossover == "bullish":   score += 1
            elif macd.crossover == "bearish": score -= 1

        # Layer 5: Analyst target vs current price (Alpha Vantage)
        if (
            fundamentals is not None
            and not fundamentals.error
            and fundamentals.analyst_target
            and current_price
            and current_price > 0
        ):
            upside = (fundamentals.analyst_target - current_price) / current_price
            if upside > 0.20:     score += 2   # >20% upside: strong buy signal
            elif upside > 0.10:   score += 1   # >10% upside
            elif upside < -0.10:  score -= 1   # analyst below market
            elif upside < -0.20:  score -= 2   # analysts think it's 20%+ overvalued

        # Map to verdict
        if score >= 5:    return SignalVerdict.STRONG_BUY
        elif score >= 2:  return SignalVerdict.BUY
        elif score <= -5: return SignalVerdict.STRONG_SELL
        elif score <= -2: return SignalVerdict.SELL
        return SignalVerdict.HOLD

    @classmethod
    def apply_dampening(cls, raw: SignalVerdict, risk_multiplier: float) -> SignalVerdict:
        """
        Macro risk dampening / boosting.

        Public and stateless so callers that fetch macro data concurrently with
        price data can apply the final adjustment once both are available,
        without re-running the technical pipeline.
        """
        order = [
            SignalVerdict.STRONG_SELL,
            SignalVerdict.SELL,
            SignalVerdict.HOLD,
            SignalVerdict.BUY,
            SignalVerdict.STRONG_BUY,
        ]
        idx = order.index(raw)
        if risk_multiplier >= cls.CRITICAL_THRESHOLD:
            idx = max(0, idx - 2)
        elif risk_multiplier >= cls.DAMPEN_THRESHOLD:
            idx = max(0, idx - 1)
        elif risk_multiplier <= cls.BOOST_THRESHOLD:
            idx = min(len(order) - 1, idx + 1)
        return order[idx]

    # Backwards-compatible alias (older call sites/tests use the underscore name)
    _apply_dampening = apply_dampening

    # ── Main entry point ──────────────────────────────────────────────────────

    def predict(self, risk_multiplier: float = 1.0) -> TechnicalAnalysis:
        """
        Run full technical analysis.

        If AlphaVantageClient is provided, enriches with:
        - MACD crossover signal
        - Analyst consensus price target
        - Company fundamentals (P/E, EPS, 52-week range, beta)
        """
        # Base indicators
        returns       = self._compute_returns()
        volatility    = self._compute_volatility()
        sharpe        = self._compute_sharpe()
        sortino       = self._compute_sortino()
        rsi           = self._compute_rsi()
        max_drawdown  = self._compute_max_drawdown()
        momentum      = self._compute_momentum()
        current_price = float(self.data["Close"].iloc[-1])

        # Alpha Vantage enrichment
        fundamentals = None
        macd         = None

        if self.av_client and self.av_client.available:
            try:
                fundamentals = self.av_client.get_fundamentals(self.ticker)
            except Exception:
                logger.exception("Alpha Vantage fundamentals failed for %s", self.ticker)

            try:
                macd = self.av_client.get_macd(self.ticker)
            except Exception:
                logger.exception("Alpha Vantage MACD failed for %s", self.ticker)

        # Build signal
        raw_signal = self._raw_signal(
            rsi=rsi,
            sharpe=sharpe,
            return_21d=returns.get("return_21d"),
            macd=macd,
            fundamentals=fundamentals,
            current_price=current_price,
        )
        adjusted_signal = self._apply_dampening(raw_signal, risk_multiplier)

        # Build output
        result = TechnicalAnalysis(
            ticker=self.ticker,
            current_price=round(current_price, 2),
            return_21d=returns.get("return_21d"),
            return_5d=returns.get("return_5d"),
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            rsi_14=rsi,
            max_drawdown=round(max_drawdown, 4) if max_drawdown else None,
            momentum=momentum,
            raw_signal=raw_signal,
            risk_adjusted_signal=adjusted_signal,
        )

        # Attach fundamentals if available
        if fundamentals and not fundamentals.error:
            result.pe_ratio       = fundamentals.pe_ratio
            result.forward_pe     = fundamentals.forward_pe
            result.eps            = fundamentals.eps
            result.analyst_target = fundamentals.analyst_target
            result.week_52_high   = fundamentals.week_52_high
            result.week_52_low    = fundamentals.week_52_low
            result.beta           = fundamentals.beta
            result.market_cap     = fundamentals.market_cap
            result.sector         = fundamentals.sector
            result.company_name   = fundamentals.name

        # Attach MACD if available
        if macd and not macd.error:
            result.macd_crossover = macd.crossover
            result.macd_histogram = macd.histogram

        return result
