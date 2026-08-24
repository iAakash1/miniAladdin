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
    #: 52-week range, when the quote endpoint carries it. Distinct from the
    #: same figures on FundamentalsData: this one is a *quote* observation
    #: with the quote's timestamp, not a fundamentals snapshot.
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None

    # ── Session context (v5.4) ───────────────────────────────────────────────
    # Three quote adapters were returning the close and discarding everything
    # else in a response the request had already paid for. These are all
    # observations from the same quote tick, so they share its timestamp and
    # must not be mixed with figures from a fundamentals snapshot.
    #: Absolute and percentage move on the session, as the *vendor* computed
    #: them. Kept rather than derived from `price - previous_close` because a
    #: vendor computing against its own official close is more authoritative
    #: than our subtraction across two possibly-different sources.
    change: Optional[float] = None
    change_pct: Optional[float] = None
    #: Volume-weighted average price for the session, where the vendor has it.
    #: A different statistic from `price` — the average a share actually
    #: traded at, not the last print.
    vwap: Optional[float] = None
    #: Trades executed in the session. Liquidity context, not a price.
    trade_count: Optional[int] = None
    #: Average daily volume over the vendor's own window. The window differs
    #: per vendor, which is why it is never compared across them.
    avg_volume: Optional[float] = None
    #: Moving averages the vendor already computed. Recomputing these locally
    #: from our own series would be cheap, but the vendor's values carry the
    #: vendor's own adjustment and calendar conventions.
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    #: Market capitalisation as of this quote. Distinct from the profile's
    #: market cap, which is a slower-moving reference figure.
    market_cap: Optional[float] = None
    exchange: str = ""
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

    # ── Additive identity & narrative (v5.2) ─────────────────────────────────
    # FMP's /profile already returned every field below on every call; the
    # adapter kept six and discarded the rest, so the product had no company
    # description, no domain to resolve a logo from, and no headcount — all of
    # which were arriving in the same response the market cap came from.
    website: str = ""
    # The registrable domain, derived from `website`. This is what the logo
    # provider is keyed on, so it is stored rather than re-parsed at each use.
    domain: str = ""
    description: str = ""
    ceo: str = ""
    employees: Optional[int] = None
    country: str = ""
    ipo_date: str = ""
    beta: Optional[float] = None
    # Vendor-hosted logo, when the vendor has one. A second opinion to the
    # dedicated logo provider, never a replacement for it.
    vendor_image: str = ""


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

    # ── Additive ratio surface (v5.3) ────────────────────────────────────────
    # Finnhub's /stock/metric returns 133 figures for one request; the adapter
    # kept seven. The rest were not redundant — margins, returns, leverage and
    # growth are exactly what a fundamentals panel is for, and they were being
    # fetched and thrown away on every research run.
    #
    # Every field below carries its period in its NAME, because that is the
    # only thing that makes these comparable: a TTM margin and a 5-year
    # average margin are different measurements, and a schema that called
    # both `margin` would invite a reconciler to average them.
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    ev_to_ebitda: Optional[float] = None
    ev_to_revenue: Optional[float] = None

    gross_margin_ttm: Optional[float] = None
    operating_margin_ttm: Optional[float] = None
    net_margin_ttm: Optional[float] = None
    net_margin_5y: Optional[float] = None

    roe_ttm: Optional[float] = None
    roa_ttm: Optional[float] = None
    roi_ttm: Optional[float] = None

    revenue_growth_ttm_yoy: Optional[float] = None
    revenue_growth_3y: Optional[float] = None
    eps_growth_ttm_yoy: Optional[float] = None
    eps_growth_3y: Optional[float] = None

    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    long_term_debt_to_equity: Optional[float] = None

    payout_ratio_ttm: Optional[float] = None

    #: Vendor-native figures that do not map onto the named fields above.
    #: Preserved rather than dropped so a later feature does not need a new
    #: round trip to recover something the response already contained.
    vendor_metrics: dict[str, Any] = Field(default_factory=dict)


class OwnershipData(BaseModel):
    """Who holds the shares, and how many are sold short.

    A separate model from `FundamentalsData` because these are *positions*,
    not performance: insider and institutional holdings and short interest
    answer "who is on the other side of this" rather than "how did the
    business do". Merging them would put a settlement-lagged short figure
    next to a trailing margin and invite them to be read as equally current.

    Percentages are stored as the fractions the vendor supplies (0.664, not
    66.4) and formatted at the edge — one convention, converted once.
    """
    symbol: str
    shares_outstanding: Optional[float] = None
    float_shares: Optional[float] = None
    held_percent_insiders: Optional[float] = None
    held_percent_institutions: Optional[float] = None

    #: Short interest. `as_of` matters more here than anywhere else in the
    #: system: exchanges publish this twice a month, so a figure without its
    #: settlement date is close to meaningless.
    shares_short: Optional[float] = None
    short_percent_of_float: Optional[float] = None
    short_ratio: Optional[float] = None          # days to cover
    short_interest_date: Optional[str] = None

    source: str = ""


class AnalystConsensus(BaseModel):
    """Sell-side price targets and the rating distribution.

    The distribution is kept whole rather than collapsed into one score. A
    mean of 2.18 on a five-point scale hides whether that is forty analysts
    clustered on "buy" or a split between "strong buy" and "sell", and those
    are opposite situations for anyone sizing a position.

    `target_mean` is the vendor's own consensus of *their* contributing
    analysts — not something this system computes, and explicitly not
    something to reconcile across vendors, since each covers a different
    analyst set.
    """
    symbol: str
    target_mean: Optional[float] = None
    target_high: Optional[float] = None
    target_low: Optional[float] = None
    analyst_count: Optional[int] = None
    #: Vendor's own label ("buy", "hold"). Kept verbatim — normalising it
    #: across vendors would imply a shared scale that does not exist.
    recommendation: Optional[str] = None
    #: Vendor's mean on its own scale. Meaningless without the scale, so the
    #: label above travels with it.
    recommendation_mean: Optional[float] = None
    source: str = ""


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
    #: The publisher's own image for this article. Preserved because it is
    #: the article's actual photograph — editorial imagery from a stock
    #: library is a different thing and must never overwrite it.
    image_url: str = ""
    #: Byline, where the vendor supplies one. Empty from vendors that do not,
    #: which is different from an unattributed article.
    author: str = ""

    # ── Vendor-scored sentiment (v5.2) ───────────────────────────────────────
    # Only some vendors score their feed. These stay None elsewhere, which is
    # meaningfully different from a score of 0.0 — "not measured" is not
    # "neutral". `sentiment_source` names who scored it, so nothing downstream
    # can present a vendor's tone estimate as the product's own judgement.
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    #: How much this article is *about* the ticker asked for, per the vendor
    #: that scored its sentiment.
    sentiment_relevance: Optional[float] = None
    sentiment_source: Optional[str] = None

    #: Topical relevance from a search vendor. Deliberately a separate field
    #: from `sentiment_relevance`: one is a search engine's match score for a
    #: query and the other is a sentiment model's judgement of how much an
    #: article concerns a ticker. They answer similar-sounding questions on
    #: incomparable scales, and merging them would let a search rank be read
    #: as an analytical weight.
    relevance: Optional[float] = None
    relevance_source: Optional[str] = None
    # Set by the aggregator, not by a vendor: which vendors independently
    # carried this same story. One source is a report; four is corroboration.
    corroborated_by: list[str] = Field(default_factory=list)


# ── Macro ─────────────────────────────────────────────────────────────────────

# ── Visual identity & imagery ─────────────────────────────────────────────────

class BrandMark(BaseModel):
    """A company's actual logo. Identity, never decoration.

    Kept structurally separate from `VisualAsset` on purpose: a brand mark is
    a claim about *who a company is*, and a stock photograph is a claim about
    what an industry looks like. Merging them into one type is what would
    eventually let a photo of an orchard render where Apple's logo belongs.
    """
    symbol: str
    domain: str = ""
    logo_url: str = ""
    #: Second URL to try when the first 404s — usually domain when the primary
    #: was resolved by ticker. Handed to the client so a miss costs no round trip.
    alternate_url: str = ""
    resolved_by: str = ""                   # "ticker" | "domain"
    provider: str = ""


class VisualAsset(BaseModel):
    """One editorial photograph. Context, never identity.

    Carries its own attribution because both libraries require credit, and a
    renderer that had to remember which provider needs it would eventually
    forget. `provider_metadata` keeps whatever is vendor-specific — Unsplash's
    download-tracking endpoint, Pexels' average colour — rather than dropping
    fields that do not fit a shared shape.
    """
    provider: str
    provider_asset_id: str = ""

    image_url: str
    thumbnail_url: str = ""
    source_url: str = ""                    # the photo's page on the provider

    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None

    alt_text: str = ""
    photographer: str = ""
    photographer_url: str = ""

    query: str = ""
    #: Deterministic, explainable score — see visual_intelligence.rank().
    relevance: float = 0.0
    attribution_required: bool = True

    provider_metadata: dict[str, Any] = Field(default_factory=dict)


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
