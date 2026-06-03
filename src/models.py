"""
OmniSignal Data Models
Pydantic models for the multi-factor risk engine data layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MacroStatus(str, Enum):
    STABLE     = "STABLE"
    ELEVATED   = "ELEVATED"
    CRITICAL   = "CRITICAL"
    DATA_ERROR = "DATA_ERROR"


class SignalVerdict(str, Enum):
    STRONG_BUY  = "Strong Buy"
    BUY         = "Buy"
    HOLD        = "Hold"
    SELL        = "Sell"
    STRONG_SELL = "Strong Sell"


class SentimentLabel(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


# ── Macro ─────────────────────────────────────────────────────────────────────

class MacroIndicators(BaseModel):
    yield_spread:   float
    inflation_rate: float
    fed_funds_rate: Optional[float] = None
    timestamp:      datetime = Field(default_factory=datetime.now)


class RiskAssessment(BaseModel):
    risk_multiplier:     float = Field(..., ge=0.5, le=1.6)
    yield_curve_inverted: bool = False
    status:              MacroStatus = MacroStatus.STABLE
    indicators:          Optional[MacroIndicators] = None
    recession_warning:   bool = False


# ── Sentiment ─────────────────────────────────────────────────────────────────

class SentimentResult(BaseModel):
    headline: str = Field(..., min_length=1)
    score:    float = Field(..., ge=-1.0, le=1.0)
    label:    SentimentLabel
    source:   str = "unknown"


class AggregateSentiment(BaseModel):
    headlines:      list[SentimentResult] = Field(default_factory=list)
    average_score:  float = Field(0.0, ge=-1.0, le=1.0)
    dominant_label: SentimentLabel = SentimentLabel.NEUTRAL
    headline_count: int = 0

    @field_validator("average_score", mode="before")
    @classmethod
    def round_score(cls, v: float) -> float:
        return round(v, 4)


# ── Technical ─────────────────────────────────────────────────────────────────

class TechnicalAnalysis(BaseModel):
    ticker:       str
    current_price: Optional[float] = None

    # Returns & risk metrics
    return_21d:   Optional[float] = None
    return_5d:    Optional[float] = None
    volatility:   Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    rsi_14:       Optional[float] = Field(None, ge=0, le=100)
    max_drawdown: Optional[float] = None
    momentum:     Optional[float] = None

    # Alpha Vantage MACD
    macd_crossover: Optional[str]   = None   # "bullish" | "bearish" | "neutral"
    macd_histogram: Optional[float] = None

    # Alpha Vantage fundamentals
    pe_ratio:       Optional[float] = None
    forward_pe:     Optional[float] = None
    eps:            Optional[float] = None
    analyst_target: Optional[float] = None
    week_52_high:   Optional[float] = None
    week_52_low:    Optional[float] = None
    beta:           Optional[float] = None
    market_cap:     Optional[float] = None   # raw USD
    sector:         Optional[str]   = None
    company_name:   Optional[str]   = None

    # Signals
    raw_signal:           Optional[SignalVerdict] = None
    risk_adjusted_signal: Optional[SignalVerdict] = None


# ── Report ─────────────────────────────────────────────────────────────────────

class OmniSignalReport(BaseModel):
    ticker:       str
    generated_at: datetime = Field(default_factory=datetime.now)
    version:      str = "1.0.0"
    macro:        Optional[RiskAssessment] = None
    technicals:   Optional[TechnicalAnalysis] = None
    sentiment:    Optional[AggregateSentiment] = None
    omnisignal_verdict: SignalVerdict = SignalVerdict.HOLD
    confidence:   float = Field(0.5, ge=0.0, le=1.0)
    rationale:    str = ""
