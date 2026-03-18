"""
OmniSignal Prediction Agent
Risk-aware prediction wrapper that dampens/boosts signals based on the SRM.
"""

from __future__ import annotations

from typing import Optional

import yfinance as yf
import numpy as np
import pandas as pd

from src.models import SignalVerdict, TechnicalAnalysis


class RiskAwarePredictionAgent:
    """
    Wraps MASFIN-style technical analysis with systemic risk dampening.

    When macro risk is elevated (multiplier > 1.2), optimistic signals
    are downgraded. When risk is low (< 0.9), modest boosts are applied.
    """

    # Signal dampening thresholds
    DAMPEN_THRESHOLD = 1.2
    BOOST_THRESHOLD = 0.9
    CRITICAL_THRESHOLD = 1.3

    # Lookback periods
    SHORT_WINDOW = 5
    MEDIUM_WINDOW = 21
    RSI_WINDOW = 14

    def __init__(self, ticker: str, period: str = "3mo"):
        self.ticker = ticker.upper()
        self.period = period
        self._data: Optional[pd.DataFrame] = None

    @property
    def data(self) -> pd.DataFrame:
        """Lazy-fetch price data via yfinance."""
        if self._data is None:
            stock = yf.Ticker(self.ticker)
            self._data = stock.history(period=self.period)
            if self._data.empty:
                raise ValueError(f"No price data found for {self.ticker}")
        return self._data

    def _compute_returns(self) -> dict:
        """Compute short-term and medium-term returns."""
        closes = self.data["Close"]
        return {
            "return_5d": float((closes.iloc[-1] / closes.iloc[-self.SHORT_WINDOW] - 1))
            if len(closes) >= self.SHORT_WINDOW
            else None,
            "return_21d": float((closes.iloc[-1] / closes.iloc[-self.MEDIUM_WINDOW] - 1))
            if len(closes) >= self.MEDIUM_WINDOW
            else None,
        }

    def _compute_volatility(self) -> Optional[float]:
        """Annualized volatility from daily returns."""
        daily_returns = self.data["Close"].pct_change().dropna()
        if len(daily_returns) < 2:
            return None
        return float(daily_returns.std() * np.sqrt(252))

    def _compute_sharpe(self) -> Optional[float]:
        """Sharpe ratio (risk-free rate assumed 0)."""
        daily_returns = self.data["Close"].pct_change().dropna()
        if len(daily_returns) < 2 or daily_returns.std() == 0:
            return None
        mean_return = daily_returns.mean() * 252
        vol = daily_returns.std() * np.sqrt(252)
        return float(round(mean_return / vol, 4))

    def _compute_sortino(self) -> Optional[float]:
        """Sortino ratio (downside deviation only)."""
        daily_returns = self.data["Close"].pct_change().dropna()
        downside = daily_returns[daily_returns < 0]
        if len(downside) < 2 or downside.std() == 0:
            return None
        mean_return = daily_returns.mean()
        downside_dev = downside.std()
        return float(round(mean_return / downside_dev, 4))

    def _compute_rsi(self) -> Optional[float]:
        """RSI-14 momentum indicator."""
        closes = self.data["Close"]
        if len(closes) < self.RSI_WINDOW + 1:
            return None
        delta = closes.diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=self.RSI_WINDOW).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=self.RSI_WINDOW).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(round(rsi.iloc[-1], 2))

    def _compute_max_drawdown(self) -> Optional[float]:
        """Maximum drawdown from peak to trough."""
        closes = self.data["Close"]
        if len(closes) < 2:
            return None
        peak = closes.cummax()
        drawdown = (closes - peak) / peak
        return float(round(drawdown.min(), 4))

    def _compute_momentum(self) -> Optional[float]:
        """21-day price momentum (absolute change)."""
        closes = self.data["Close"]
        if len(closes) < self.MEDIUM_WINDOW:
            return None
        return float(round(closes.iloc[-1] - closes.iloc[-self.MEDIUM_WINDOW], 2))

    def _raw_signal(self, rsi: Optional[float], sharpe: Optional[float],
                    return_21d: Optional[float]) -> SignalVerdict:
        """Generate a raw signal before risk adjustment."""
        score = 0

        # RSI scoring
        if rsi is not None:
            if rsi > 70:
                score -= 2  # Overbought
            elif rsi < 30:
                score += 2  # Oversold (buy opportunity)
            elif rsi > 55:
                score += 1
            elif rsi < 45:
                score -= 1

        # Sharpe scoring
        if sharpe is not None:
            if sharpe > 1.5:
                score += 2
            elif sharpe > 0.5:
                score += 1
            elif sharpe < -0.5:
                score -= 2
            elif sharpe < 0:
                score -= 1

        # Momentum scoring
        if return_21d is not None:
            if return_21d > 0.10:
                score += 2
            elif return_21d > 0.03:
                score += 1
            elif return_21d < -0.10:
                score -= 2
            elif return_21d < -0.03:
                score -= 1

        # Map score to verdict
        if score >= 4:
            return SignalVerdict.STRONG_BUY
        elif score >= 2:
            return SignalVerdict.BUY
        elif score <= -4:
            return SignalVerdict.STRONG_SELL
        elif score <= -2:
            return SignalVerdict.SELL
        return SignalVerdict.HOLD

    def _apply_dampening(self, raw: SignalVerdict, risk_multiplier: float) -> SignalVerdict:
        """
        Apply macro risk dampening to the raw signal.

        - Multiplier > 1.3 (CRITICAL): Strong Buy → Hold, Buy → Hold
        - Multiplier > 1.2 (ELEVATED): Strong Buy → Buy
        - Multiplier < 0.9 (LOW RISK): Hold → Buy (boost)
        """
        signal_order = [
            SignalVerdict.STRONG_SELL,
            SignalVerdict.SELL,
            SignalVerdict.HOLD,
            SignalVerdict.BUY,
            SignalVerdict.STRONG_BUY,
        ]
        idx = signal_order.index(raw)

        if risk_multiplier >= self.CRITICAL_THRESHOLD:
            # Aggressive dampening: shift down by 2
            idx = max(0, idx - 2)
        elif risk_multiplier >= self.DAMPEN_THRESHOLD:
            # Moderate dampening: shift down by 1
            idx = max(0, idx - 1)
        elif risk_multiplier <= self.BOOST_THRESHOLD:
            # Mild boost: shift up by 1
            idx = min(len(signal_order) - 1, idx + 1)

        return signal_order[idx]

    def predict(self, risk_multiplier: float = 1.0) -> TechnicalAnalysis:
        """
        Run full technical analysis with risk-aware dampening.

        Args:
            risk_multiplier: Systemic Risk Multiplier from OmniSignalRiskEngine
        """
        returns = self._compute_returns()
        volatility = self._compute_volatility()
        sharpe = self._compute_sharpe()
        sortino = self._compute_sortino()
        rsi = self._compute_rsi()
        max_drawdown = self._compute_max_drawdown()
        momentum = self._compute_momentum()

        current_price = float(self.data["Close"].iloc[-1])

        raw_signal = self._raw_signal(rsi, sharpe, returns.get("return_21d"))
        adjusted_signal = self._apply_dampening(raw_signal, risk_multiplier)

        return TechnicalAnalysis(
            ticker=self.ticker,
            current_price=round(current_price, 2),
            return_21d=returns.get("return_21d"),
            return_5d=returns.get("return_5d"),
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            rsi_14=rsi,
            max_drawdown=max_drawdown,
            momentum=momentum,
            raw_signal=raw_signal,
            risk_adjusted_signal=adjusted_signal,
        )
