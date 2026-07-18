"""
Normalized schemas for the provider layer.

Every provider returns exactly these shapes regardless of which vendor
answered. Vendor-specific field names never escape src/providers/vendors/.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# ── Envelope ──────────────────────────────────────────────────────────────────

class SourceReading(BaseModel):
    """One vendor's answer for a cross-validated field (used in confidence)."""

    vendor: str
    value: float
    latency_ms: float = 0.0


class ProviderResult(BaseModel, Generic[T]):
    """
    Uniform envelope for every provider call.

    confidence ∈ [0, 1]:
        1.00  multiple vendors agree tightly
        0.85  single healthy primary source
        0.70  fallback source (primary unavailable)
        0.50  sources disagree materially (disagreement=True)
        0.30  stale cache served because every vendor failed
    """

    data: Optional[T] = None
    source: str = ""                       # vendor that produced `data`
    sources_consulted: list[str] = Field(default_factory=list)
    readings: list[SourceReading] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    disagreement: bool = False
    cached: bool = False
    stale: bool = False
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None            # set only when data is None

    @property
    def ok(self) -> bool:
        return self.data is not None


# ── Market data ───────────────────────────────────────────────────────────────

class PriceQuote(BaseModel):
    symbol: str
    price: float
    currency: str = "USD"
    as_of: Optional[str] = None            # ISO timestamp when vendor supplies it


class OHLCVBar(BaseModel):
    date: str                               # YYYY-MM-DD
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class PriceSeries(BaseModel):
    symbol: str
    bars: list[OHLCVBar] = Field(default_factory=list)


# ── Fundamentals ──────────────────────────────────────────────────────────────

class CompanyProfile(BaseModel):
    symbol: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    market_cap: Optional[float] = None      # raw USD
    currency: str = "USD"
    exchange: str = ""


class FundamentalsData(BaseModel):
    symbol: str
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    eps: Optional[float] = None
    beta: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    dividend_yield: Optional[float] = None
    profit_margin: Optional[float] = None
    profile: Optional[CompanyProfile] = None


class AnalystTargets(BaseModel):
    symbol: str
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    analyst_count: Optional[int] = None


# ── Street data (v4.5: analyst recommendations, surprises, insiders) ─────────

class RecommendationMonth(BaseModel):
    period: str  # YYYY-MM-01
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0


class EarningsSurprise(BaseModel):
    period: str
    actual: Optional[float] = None
    estimate: Optional[float] = None
    surprise_pct: Optional[float] = None


class StreetData(BaseModel):
    symbol: str
    recommendations: list[RecommendationMonth] = []  # newest first
    surprises: list[EarningsSurprise] = []           # newest first
    insider_mspr: Optional[float] = None             # monthly share purchase ratio, −100…100
    insider_net_shares: Optional[float] = None       # net insider share change, same window


# ── News ──────────────────────────────────────────────────────────────────────

class NewsHeadline(BaseModel):
    title: str
    source: str = "unknown"
    url: str = ""
    published_at: str = ""                  # ISO or vendor string, best effort
    summary: str = ""


# ── Macro ─────────────────────────────────────────────────────────────────────

class MacroSnapshot(BaseModel):
    yield_spread: Optional[float] = None    # 10Y − 2Y, percent
    inflation_rate: Optional[float] = None  # YoY CPI, percent
    fed_funds_rate: Optional[float] = None  # percent


# ── Search ────────────────────────────────────────────────────────────────────

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: str = ""
    score: Optional[float] = None
