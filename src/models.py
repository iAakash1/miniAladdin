"""
OmniSignal Data Models
Pydantic models for the multi-factor risk engine data layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────────────────────────

class MacroStatus(str, Enum):
    """Overall macro-economic environment status."""
    STABLE = "STABLE"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"
    DATA_ERROR = "DATA_ERROR"


class SignalVerdict(str, Enum):
    """Final OmniSignal recommendation."""
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


class SentimentLabel(str, Enum):
    """Sentiment classification for a single headline."""
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


# ── Macro Models ─────────────────────────────────────────────────────────────

class MacroIndicators(BaseModel):
    """Raw macro-economic indicators from FRED."""
    yield_spread: float = Field(
        ..., description="10Y minus 2Y Treasury yield spread (T10Y2Y)"
    )
    inflation_rate: float = Field(
        ..., description="Year-over-year CPI inflation rate (%)"
    )
    fed_funds_rate: Optional[float] = Field(
        None, description="Effective Federal Funds Rate (%)"
    )
    timestamp: datetime = Field(default_factory=datetime.now)


class RiskAssessment(BaseModel):
    """Computed systemic risk assessment."""
    risk_multiplier: float = Field(
        ..., ge=0.5, le=1.6, description="Systemic Risk Multiplier (0.5–1.6)"
    )
    yield_curve_inverted: bool = Field(
        False, description="True if yield curve is inverted (recession signal)"
    )
    status: MacroStatus = Field(
        MacroStatus.STABLE, description="Overall macro status"
    )
    indicators: Optional[MacroIndicators] = None
    recession_warning: bool = False


# ── Sentiment Models ─────────────────────────────────────────────────────────

class SentimentResult(BaseModel):
    """Sentiment analysis for a single news headline."""
    headline: str = Field(..., min_length=1)
    score: float = Field(
        ..., ge=-1.0, le=1.0, description="Sentiment score: -1 (bearish) to +1 (bullish)"
    )
    label: SentimentLabel
    source: str = Field("unknown", description="Source of the headline")


class AggregateSentiment(BaseModel):
    """Aggregated sentiment across multiple headlines."""
    headlines: list[SentimentResult] = Field(default_factory=list)
    average_score: float = Field(0.0, ge=-1.0, le=1.0)
    dominant_label: SentimentLabel = SentimentLabel.NEUTRAL
    headline_count: int = 0

    @field_validator("average_score", mode="before")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 4)


# ── Technical Analysis Models ────────────────────────────────────────────────

class TechnicalAnalysis(BaseModel):
    """Technical analysis output for a ticker."""
    ticker: str
    current_price: Optional[float] = None
    price_target: Optional[float] = None
    return_21d: Optional[float] = Field(None, description="21-day return")
    return_5d: Optional[float] = Field(None, description="5-day return")
    volatility: Optional[float] = Field(None, description="Annualized volatility")
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    rsi_14: Optional[float] = Field(None, ge=0, le=100)
    max_drawdown: Optional[float] = None
    beta: Optional[float] = None
    alpha: Optional[float] = None
    momentum: Optional[float] = None
    raw_signal: Optional[SignalVerdict] = None
    risk_adjusted_signal: Optional[SignalVerdict] = None


# ── Report Model ─────────────────────────────────────────────────────────────

class OmniSignalReport(BaseModel):
    """Complete OmniSignal research report for a ticker."""
    ticker: str
    generated_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0.0"

    # Components
    macro: Optional[RiskAssessment] = None
    technicals: Optional[TechnicalAnalysis] = None
    sentiment: Optional[AggregateSentiment] = None

    # Final verdict
    omnisignal_verdict: SignalVerdict = SignalVerdict.HOLD
    confidence: float = Field(
        0.5, ge=0.0, le=1.0, description="Confidence level 0–1"
    )
    rationale: str = ""
