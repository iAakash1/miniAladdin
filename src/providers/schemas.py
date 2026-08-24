"""
Normalized schemas for the provider layer.

Every provider returns exactly these shapes regardless of which vendor
answered. Vendor-specific field names never escape src/providers/vendors/.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

from src.providers.validation import SeriesQuality, sanitize_bars

logger = logging.getLogger("omnisignal.providers.schemas")

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

    # ── Additive market microstructure (v5.1) ────────────────────────────────
    # Most vendors here return a bare close and leave every field below None,
    # which is the correct answer for them — they genuinely do not know the
    # spread. Only quote-capable vendors populate these, so a null means "this
    # source cannot say", never "the value is zero".
    bid: Optional[float] = None
    ask: Optional[float] = None
    mid: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    day_open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    previous_close: Optional[float] = None
    volume: Optional[float] = None
    # Which field `price` actually came from — "last sale", "bid/ask mid",
    # "previous close". A mid and a stale previous close are not the same
    # claim, and a consumer that cannot tell them apart will treat them alike.
    price_basis: Optional[str] = None

    @property
    def spread_bps(self) -> Optional[float]:
        """Bid-ask spread in basis points of the mid, when both sides exist."""
        if self.bid is None or self.ask is None or not self.mid:
            return None
        return round((self.ask - self.bid) / self.mid * 10_000, 2)


class Fundamentals(BaseModel):
    """Reported statement figures for one period, plus prior periods.

    Every field is Optional and nothing is derived here: a ratio computed
    from two nulls is not zero, and a schema that defaulted to zero would let
    a missing revenue line render as a company with no sales. Ratios are
    computed downstream, only where both inputs are actually present.
    """
    symbol: str
    period: str = ""                        # YYYY-MM-DD of the report
    quarter: Optional[int] = None
    year: Optional[int] = None

    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    eps: Optional[float] = None
    shares_diluted: Optional[float] = None

    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    equity: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None

    free_cash_flow: Optional[float] = None
    operating_cash_flow: Optional[float] = None

    # Prior periods, newest first, carrying only the fields trend detection
    # reads. Travels with the latest statement so a trend needs no second
    # round trip against a tight rate limit.
    history: list[dict[str, Any]] = Field(default_factory=list)


class OHLCVBar(BaseModel):
    date: str                               # YYYY-MM-DD
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class PriceSeries(BaseModel):
    """A price history, validated on construction.

    Validation lives here rather than in each vendor adapter so that no
    vendor — present or future — can route around it. Every adapter already
    returns a `PriceSeries`, so this covers all of them and required no
    adapter changes.

    `quality` records what was dropped. Consumers that care about data
    integrity read it; consumers that do not are simply protected.
    """

    symbol: str
    bars: list[OHLCVBar] = Field(default_factory=list)
    quality: SeriesQuality = Field(default_factory=SeriesQuality)

    def pct_change(self, days: int) -> Optional[float]:
        """Percent change over `days` bars, or None when it is not knowable.

        Canonical: this was reimplemented in three places, and one of those
        copies omitted the zero-base guard the other two had — the same class
        of gap that let a zero close crash four sector rows. Percent change
        belongs to the series, not to whoever happens to be reading it.
        """
        if len(self.bars) <= days:
            return None
        base = self.bars[-1 - days].close
        if not base:
            return None
        return round((self.bars[-1].close / base - 1) * 100, 2)

    @model_validator(mode="after")
    def _reject_impossible_bars(self) -> "PriceSeries":
        # Skip when quality is already populated: re-validating a series that
        # has been round-tripped (cache, tests) would count the same bars
        # twice and report a retention that never happened.
        if self.quality.bars_received:
            return self

        kept, quality = sanitize_bars(self.bars)
        if quality.dropped:
            logger.warning(
                "%s: dropped %d of %d bars — %s",
                self.symbol, quality.dropped, quality.bars_received, quality.summary(),
            )
        object.__setattr__(self, "bars", kept)
        object.__setattr__(self, "quality", quality)
        return self


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
    # Additive (v5.1): vendors that classify their own feed. Empty from
    # vendors that do not, which is different from "no tags apply".
    tags: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    # Set by the aggregator, not by a vendor: which vendors independently
    # carried this same story. One source is a report; four is corroboration.
    corroborated_by: list[str] = Field(default_factory=list)


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
