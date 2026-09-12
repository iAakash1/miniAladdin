"""Cross-sectional stock discovery over the configured universe.

Distinct from `screen_service`, and deliberately not built on it. That module
answers "which securities relate to this phrase" by searching the web and
extracting tickers; ordering there reflects how a search engine ranked pages.
This module answers "of the securities we can score, which rank highest on a
stated quantitative dimension". Merging them would let page-rank leak into
something a reader will read as a financial ordering.

The pipeline is deterministic end to end:

    universe -> shared fetch -> scorecard -> eligibility
             -> cross-sectional normalisation -> category rankings -> cache

No language model runs anywhere in it. Sorting numbers does not need one, and
one narrative call per security would be ~77 model requests per refresh to
produce an ordering that arithmetic already determined. Narrative is generated
when a reader opens a security, not to decide what to list.

The scorecard is the authority. `overall_rank` orders securities; it never
overrides, recomputes or second-guesses a verdict, and a security's
`model_signal` here is the same string the research endpoint returns for it.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, PrivateAttr

from src import providers
from src.providers.parallel import map_concurrent
from src.services import conviction
from src.services import explore_eligibility as eligibility
from src.services import explore_ranking as ranking
from src.services.universe import Constituent, load_universe

logger = logging.getLogger("omnisignal.explore")

SNAPSHOT_TTL_SECONDS = 600.0      # 10 minutes — these are daily-bar rankings
STALE_GRACE_SECONDS = 3600.0      # after which a stale snapshot is withheld
FETCH_WORKERS = 6
SCORING_VERSION = "scoring-v2.1"

_lock = threading.Lock()
_snapshot: Optional["ExploreSnapshot"] = None
_snapshot_at: float = 0.0
_building = False


# ── shapes ───────────────────────────────────────────────────────────────────

class ExploreRow(BaseModel):
    symbol: str
    company_name: str
    sector: str

    price: Optional[float] = None
    price_as_of: Optional[str] = None
    price_age_days: Optional[float] = None
    stale: bool = False

    # Straight from the scorecard — never recomputed here.
    model_signal: Optional[str] = None
    signal_strength: Optional[float] = None      # [-1, 1], the engine's own units
    signal_percentile: Optional[float] = None    # 0-100, cross-sectional
    confidence: Optional[int] = None             # 0-100
    risk_score: Optional[int] = None             # 0-100
    risk_level: Optional[str] = None
    data_completeness: Optional[float] = None    # 0-1 fraction, as the engine reports it

    overall_rank: Optional[float] = None         # 0-100 composite

    # Attention, which is not quality. Carried beside the signal, never instead of it.
    trend_score: Optional[float] = None
    trend_direction: Optional[str] = None

    # Risk-adjusted historical performance. Deliberately separate from
    # `overall_rank` and from `model_signal`: how a security has done and what
    # the model thinks of it now are different questions that often disagree.
    #: Not a stronger buy — a statement that the evidence around a positive
    #: signal is unusually well aligned. See services/conviction.py.
    high_conviction: bool = False
    conviction_met: list[str] = []
    conviction_blocked_by: list[str] = []

    performance_score: Optional[float] = None
    performance_grade: Optional[str] = None
    excess_return_3m: Optional[float] = None
    excess_return_6m: Optional[float] = None
    excess_return_12m: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None

    momentum_percentile: Optional[float] = None
    quality_percentile: Optional[float] = None
    value_percentile: Optional[float] = None
    profitability_percentile: Optional[float] = None
    profitability_sector_percentile: Optional[float] = None
    news_buzz: Optional[float] = None
    analyst_upside: Optional[float] = None
    analyst_count: Optional[int] = None

    # Raw supporting values, so a percentile can be checked against a number.
    operating_margin_ttm: Optional[float] = None
    gross_margin_ttm: Optional[float] = None
    net_margin_ttm: Optional[float] = None
    roe_ttm: Optional[float] = None
    pe_ratio: Optional[float] = None
    forward_pe: Optional[float] = None
    headline_count: Optional[int] = None
    sentiment_avg: Optional[float] = None

    top_positive: Optional[str] = None
    top_caution: Optional[str] = None

    eligible: bool = False
    exclusion_reasons: list[str] = []
    validation_state: str = "PARTIAL"

    #: Working values the ranking pass needs and the API must not return —
    #: the price frame and the scorecard's sleeve scores. Declared rather
    #: than attached ad hoc so it is visibly excluded from serialisation
    #: instead of accidentally excluded.
    _raw: dict[str, Any] = PrivateAttr(default_factory=dict)


class ExploreSnapshot(BaseModel):
    generated_at: str
    data_as_of: Optional[str] = None
    universe_version: str
    scoring_version: str = SCORING_VERSION
    rows: list[ExploreRow]
    eligible_count: int
    evaluated_count: int
    stale: bool = False
    #: Present only when a refresh failed and an older snapshot is being served.
    stale_reason: Optional[str] = None


# ── gathering ────────────────────────────────────────────────────────────────

def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 — one security must never fail the sweep
        return default


def _price_age_days(last_bar_date: Optional[str]) -> Optional[float]:
    if not last_bar_date:
        return None
    try:
        observed = date.fromisoformat(last_bar_date[:10])
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc).date() - observed).days)


def _gather(entry: Constituent, srm: float, spy_frame, stress: dict[str, Any]) -> ExploreRow:
    """Everything one security contributes, or an honest row saying why not."""
    from src.scoring.engine import score_ticker
    from src.services import fundamentals_data

    row = ExploreRow(
        symbol=entry.symbol, company_name=entry.company_name, sector=entry.sector
    )

    series_result = _safe(lambda: providers.market_data.get_series(entry.symbol, "1y"))
    if series_result is None or not series_result.ok or not series_result.data.bars:
        row.exclusion_reasons = ["no_price_series"]
        return row

    bars = series_result.data.bars
    row.stale = bool(series_result.stale)
    row.price = round(bars[-1].close, 2)
    row.price_as_of = bars[-1].date
    row.price_age_days = _price_age_days(bars[-1].date)

    from api.index import _series_to_dataframe

    frame = _safe(lambda: _series_to_dataframe(series_result.data))
    if frame is None or len(frame) < eligibility.MIN_BARS:
        row.exclusion_reasons = ["insufficient_history"]
        return row

    fundamentals = _safe(lambda: providers.fundamentals.get_fundamentals(entry.symbol))
    f = fundamentals.data if fundamentals is not None and fundamentals.ok else None
    if f is not None:
        row.pe_ratio = f.pe_ratio
        row.forward_pe = f.forward_pe
        row.gross_margin_ttm = f.gross_margin_ttm
        row.operating_margin_ttm = f.operating_margin_ttm
        row.net_margin_ttm = f.net_margin_ttm
        row.roe_ttm = f.roe_ttm

    targets = _safe(lambda: providers.fundamentals.get_analyst_targets(entry.symbol))
    t = targets.data if targets is not None and targets.ok else None
    analyst_target = getattr(t, "target_mean", None) if t is not None else None
    row.analyst_count = getattr(t, "analyst_count", None) if t is not None else None

    news = _safe(lambda: providers.news.get_news(entry.symbol, entry.company_name, 12))
    headlines = news.data if news is not None and news.ok and news.data else []
    row.headline_count = len(headlines)
    scores = [
        h.sentiment_score for h in headlines
        if getattr(h, "sentiment_score", None) is not None
        and math.isfinite(h.sentiment_score)
    ]
    row.sentiment_avg = round(sum(scores) / len(scores), 4) if scores else None

    quality = _safe(lambda: fundamentals_data.get_quality_inputs(entry.symbol), {}) or {}

    card = _safe(lambda: score_ticker(
        frame,
        srm=srm,
        price=row.price,
        pe_ratio=row.pe_ratio,
        forward_pe=row.forward_pe,
        analyst_target=analyst_target,
        analyst_count=row.analyst_count,
        beta=getattr(f, "beta", None) if f is not None else None,
        sentiment_avg=row.sentiment_avg,
        headline_count=float(row.headline_count or 0),
        spy_frame=spy_frame,
        gross_profit_over_assets=quality.get("gross_profit_over_assets"),
        net_issuance_yoy=quality.get("net_issuance_yoy"),
        asset_growth_yoy=quality.get("asset_growth_yoy"),
        price_age_days=row.price_age_days,
        nfci=stress.get("nfci"),
        credit_spread_z=stress.get("credit_spread_z"),
        vix_percentile=stress.get("vix_percentile"),
        term_spread=stress.get("term_spread"),
    ))

    if card is not None:
        row.model_signal = card.verdict
        row.signal_strength = ranking.signal_strength(card.raw_score)
        row.confidence = card.confidence
        row.risk_score = card.risk_score
        row.risk_level = ranking.risk_level(card.risk_score)
        row.data_completeness = card.data_completeness
        row.top_positive, row.top_caution = _reasons(card)
        row.validation_state = "VERIFIED" if card.data_completeness >= 0.8 else "PARTIAL"

    row._raw = {
        "frame": frame,
        "momentum_score": getattr(card, "momentum_score", None) if card else None,
        "quality_score": getattr(card, "quality_score", None) if card else None,
        "fundamental_score": getattr(card, "fundamental_score", None) if card else None,
        "analyst_target": analyst_target,
    }

    verdict = eligibility.assess(
        asset_type=entry.asset_type,
        bars=len(frame),
        price=row.price,
        price_age_days=row.price_age_days,
        has_scorecard=card is not None,
        data_completeness=row.data_completeness,
        confidence=row.confidence,
        validation_state=row.validation_state,
    )
    row.eligible = verdict.eligible
    row.exclusion_reasons = verdict.reasons
    return row


def _reasons(card) -> tuple[Optional[str], Optional[str]]:
    """The single strongest supporting and opposing factor, by contribution.

    Derived from what the engine actually weighted, never from a phrase bank.
    A reason a reader cannot trace to a factor row is a reason we invented.
    """
    scored = [
        f for f in card.factors
        if f.score is not None and f.contribution is not None
        and math.isfinite(f.contribution)
    ]
    if not scored:
        return None, None
    positives = [f for f in scored if f.contribution > 0]
    negatives = [f for f in scored if f.contribution < 0]
    best = max(positives, key=lambda f: f.contribution, default=None)
    worst = min(negatives, key=lambda f: f.contribution, default=None)
    return (
        f"{best.name} ({best.family})" if best else None,
        f"{worst.name} ({worst.family})" if worst else None,
    )


# ── trend inputs ─────────────────────────────────────────────────────────────

def _window_return(frame, days: int) -> Optional[float]:
    closes = frame["Close"]
    if len(closes) <= days:
        return None
    base = float(closes.iloc[-1 - days])
    if not math.isfinite(base) or base == 0:
        return None
    value = float(closes.iloc[-1]) / base - 1.0
    return value if math.isfinite(value) else None


def _relative_volume(frame) -> Optional[float]:
    volume = frame["Volume"]
    if len(volume) < 30:
        return None
    recent = float(volume.iloc[-5:].mean())
    baseline = float(volume.iloc[-60:].mean()) if len(volume) >= 60 else float(volume.mean())
    if not math.isfinite(baseline) or baseline <= 0:
        return None
    value = recent / baseline
    return value if math.isfinite(value) else None


def _high_52w_proximity(frame) -> Optional[float]:
    closes = frame["Close"].iloc[-252:] if len(frame) >= 252 else frame["Close"]
    high = float(closes.max())
    if not math.isfinite(high) or high <= 0:
        return None
    value = float(closes.iloc[-1]) / high
    return value if math.isfinite(value) else None


# ── snapshot ─────────────────────────────────────────────────────────────────

def _build_snapshot() -> ExploreSnapshot:
    from api.index import _fetch_macro_safe, _stress_inputs, _series_to_dataframe

    universe = load_universe()
    multiplier, _stats = _fetch_macro_safe()
    # The macro gate is unmeasured, not neutral. 1.0 is the identity — it
    # applies no gating — and the securities are still comparable to each
    # other because every one of them is scored under the same assumption.
    srm = multiplier if isinstance(multiplier, (int, float)) else 1.0
    stress = _safe(_stress_inputs, {}) or {}

    spy_result = _safe(lambda: providers.market_data.get_series("SPY", "1y"))
    spy_frame = (
        _safe(lambda: _series_to_dataframe(spy_result.data))
        if spy_result is not None and spy_result.ok and spy_result.data.bars
        else None
    )

    outcomes = map_concurrent(
        lambda entry: _gather(entry, srm, spy_frame, stress),
        universe.constituents,
        workers=FETCH_WORKERS,
        label="explore.universe",
    )
    rows: list[ExploreRow] = []
    for entry, outcome in zip(universe.constituents, outcomes):
        value = getattr(outcome, "value", None)
        if value is None:
            rows.append(ExploreRow(
                symbol=entry.symbol, company_name=entry.company_name, sector=entry.sector,
                exclusion_reasons=["evaluation_failed"],
            ))
        else:
            rows.append(value)

    _normalise(rows, spy_frame)

    eligible = [r for r in rows if r.eligible]
    observed = [r.price_as_of for r in rows if r.price_as_of]
    return ExploreSnapshot(
        generated_at=datetime.now(timezone.utc).isoformat(),
        data_as_of=max(observed) if observed else None,
        universe_version=universe.universe_version,
        rows=rows,
        eligible_count=len(eligible),
        evaluated_count=len(rows),
    )


def _round(value: Optional[float], digits: int) -> Optional[float]:
    """Round, or keep the absence. `round(None)` raises; `or 0` would lie."""
    return None if value is None else round(value, digits)


def _normalise(rows: list[ExploreRow], benchmark_frame=None) -> None:
    """Percentiles and composites, computed over the eligible set only.

    Eligible-only on purpose: percentile is a statement about a peer group,
    and including securities the policy already refused would let them move
    everyone else's position while never appearing themselves.
    """
    eligible = [r for r in rows if r.eligible]
    if not eligible:
        return

    signals = [r.signal_strength for r in eligible if r.signal_strength is not None]
    for r in eligible:
        r.signal_percentile = ranking.percentile_rank(r.signal_strength, signals)
        r.overall_rank = ranking.overall_rank(
            signal_percentile=r.signal_percentile,
            confidence=float(r.confidence) if r.confidence is not None else None,
            risk_score=float(r.risk_score) if r.risk_score is not None else None,
            data_completeness_pct=(
                r.data_completeness * 100.0 if r.data_completeness is not None else None
            ),
        )

    # Family percentiles, from the scorecard's own sleeve scores.
    for field, key in (
        ("momentum_percentile", "momentum_score"),
        ("quality_percentile", "quality_score"),
        ("value_percentile", "fundamental_score"),
    ):
        population = [
            r._raw[key] for r in eligible
            if r._raw.get(key) is not None
        ]
        for r in eligible:
            raw = r._raw
            setattr(r, field, ranking.percentile_rank(raw.get(key), population))

    # Trend, from price and attention rather than from the verdict.
    m21 = {r.symbol: _window_return(r._raw.get("frame"), 21) for r in eligible}
    m5 = {r.symbol: _window_return(r._raw.get("frame"), 5) for r in eligible}
    rvol = {r.symbol: _relative_volume(r._raw.get("frame")) for r in eligible}
    prox = {r.symbol: _high_52w_proximity(r._raw.get("frame")) for r in eligible}
    news = {r.symbol: float(r.headline_count) if r.headline_count is not None else None
            for r in eligible}

    def pop(d):
        return [v for v in d.values() if v is not None]

    for r in eligible:
        r.trend_score = ranking.trend_score({
            "momentum_21d": ranking.percentile_rank(m21[r.symbol], pop(m21)),
            "momentum_5d": ranking.percentile_rank(m5[r.symbol], pop(m5)),
            "relative_volume": ranking.percentile_rank(rvol[r.symbol], pop(rvol)),
            "news_activity": ranking.percentile_rank(news[r.symbol], pop(news)),
            "high_52w_proximity": ranking.percentile_rank(prox[r.symbol], pop(prox)),
        })
        r.trend_direction = ranking.trend_direction(m21[r.symbol], m5[r.symbol])
        r.news_buzz = ranking.percentile_rank(news[r.symbol], pop(news))

    # Performance: raw measures first, then percentiles, then the composite.
    # Percentiles are taken across the eligible set so every component is on
    # the same scale before the weights combine them.
    bench = benchmark_frame
    raw: dict[str, dict[str, Optional[float]]] = {}
    for r in eligible:
        frame = r._raw.get("frame")
        raw[r.symbol] = {
            "excess_3m": ranking.excess_return(frame, bench, ranking.PERFORMANCE_WINDOWS["excess_3m"]),
            "excess_6m": ranking.excess_return(frame, bench, ranking.PERFORMANCE_WINDOWS["excess_6m"]),
            "excess_12m": ranking.excess_return(frame, bench, ranking.PERFORMANCE_WINDOWS["excess_12m"]),
            "sharpe": ranking.sharpe(frame),
            "sortino": ranking.sortino(frame),
            "drawdown": ranking.max_drawdown(frame),
        }

    def population(key):
        return [v[key] for v in raw.values() if v[key] is not None]

    for r in eligible:
        values = raw[r.symbol]
        r.excess_return_3m = _round(values["excess_3m"], 6)
        r.excess_return_6m = _round(values["excess_6m"], 6)
        r.excess_return_12m = _round(values["excess_12m"], 6)
        r.sharpe_ratio = _round(values["sharpe"], 4)
        r.sortino_ratio = _round(values["sortino"], 4)
        r.max_drawdown = _round(values["drawdown"], 6)

        # Drawdown is negative and a shallower one is better, so the percentile
        # is taken on the value as-is: -0.08 sits above -0.35, which is the
        # ordering we want without inverting anything by hand.
        r.performance_score = ranking.performance_score({
            "excess_3m": ranking.percentile_rank(values["excess_3m"], population("excess_3m")),
            "excess_6m": ranking.percentile_rank(values["excess_6m"], population("excess_6m")),
            "excess_12m": ranking.percentile_rank(values["excess_12m"], population("excess_12m")),
            "sharpe": ranking.percentile_rank(values["sharpe"], population("sharpe")),
            "sortino": ranking.percentile_rank(values["sortino"], population("sortino")),
            "inverse_drawdown": ranking.percentile_rank(values["drawdown"], population("drawdown")),
        })
        r.performance_grade = ranking.performance_grade(r.performance_score)

    # Profitability: absolute percentile plus a sector-relative one, because a
    # software margin and a grocery margin are not the same measurement and
    # ranking them against each other mostly ranks industries.
    margins = {r.symbol: r.operating_margin_ttm for r in eligible}
    for r in eligible:
        r.profitability_percentile = ranking.percentile_rank(margins[r.symbol], pop(margins))
        peers = [
            margins[p.symbol] for p in eligible
            if p.sector == r.sector and margins[p.symbol] is not None
        ]
        r.profitability_sector_percentile = ranking.percentile_rank(margins[r.symbol], peers)

    # Conviction last: it reads the finished rank, performance and validation,
    # so it cannot run before they exist.
    for r in eligible:
        verdict = conviction.assess(
            model_signal=r.model_signal,
            overall_rank=r.overall_rank,
            confidence=r.confidence,
            risk_score=r.risk_score,
            data_completeness=r.data_completeness,
            performance_score=r.performance_score,
            validation_state=r.validation_state,
            price_stale=r.stale,
        )
        r.high_conviction = verdict.qualifies
        r.conviction_met = verdict.met
        r.conviction_blocked_by = verdict.blocked_by

    # Analyst upside, only where both sides of the comparison exist.
    for r in eligible:
        target = r._raw.get("analyst_target")
        if target is None or r.price is None or r.price <= 0 or not math.isfinite(target):
            r.analyst_upside = None
            continue
        upside = target / r.price - 1.0
        r.analyst_upside = round(upside, 4) if math.isfinite(upside) else None


def get_snapshot(force: bool = False) -> ExploreSnapshot:
    """The current snapshot, rebuilding when it has aged past its TTL.

    On a refresh failure the previous snapshot is served with `stale=True` and
    the reason attached, rather than an empty page: "no security qualified"
    and "we could not reach the vendors" look identical once the rows are
    gone, and only one of them is a finding.
    """
    global _snapshot, _snapshot_at, _building
    now = time.time()
    with _lock:
        fresh = _snapshot is not None and (now - _snapshot_at) < SNAPSHOT_TTL_SECONDS
        if fresh and not force:
            return _snapshot
        if _building and _snapshot is not None:
            return _snapshot.model_copy(update={"stale": True, "stale_reason": "a refresh is in progress"})
        _building = True

    try:
        built = _build_snapshot()
        with _lock:
            _snapshot, _snapshot_at = built, time.time()
        return built
    except Exception as exc:  # noqa: BLE001 — a refresh fault must not empty the page
        logger.exception("explore snapshot refresh failed")
        with _lock:
            previous, age = _snapshot, time.time() - _snapshot_at
        if previous is not None and age < STALE_GRACE_SECONDS:
            return previous.model_copy(update={
                "stale": True,
                "stale_reason": f"the last refresh failed ({type(exc).__name__}); showing the previous snapshot",
            })
        raise
    finally:
        with _lock:
            _building = False


def reset_cache_for_testing() -> None:
    global _snapshot, _snapshot_at, _building
    with _lock:
        _snapshot, _snapshot_at, _building = None, 0.0, False


# ── categories ───────────────────────────────────────────────────────────────

class Category(BaseModel):
    key: str
    label: str
    #: The row field this category orders by.
    field: str
    #: True when a *higher* value ranks first.
    descending: bool = True
    blurb: str


#: Only dimensions the current data genuinely supports. Growth is deliberately
#: absent: reconciling TTM against fiscal-year revenue across vendors is not
#: solved here, and a growth tab built on unreconciled periods would rank
#: accounting conventions rather than companies.
CATEGORIES: list[Category] = [
    Category(
        key="overall", label="Overall", field="overall_rank",
        blurb="Signal strength, weighted by how confident, how risky and how complete the evidence is.",
    ),
    Category(
        key="trending", label="Trending", field="trend_score",
        blurb="Recent movement and attention. Not a recommendation — a falling stock can lead this list.",
    ),
    Category(
        key="momentum", label="Momentum", field="momentum_percentile",
        blurb="The scoring engine's momentum sleeve, ranked across the universe.",
    ),
    Category(
        key="quality", label="Quality", field="quality_percentile",
        blurb="Gross profitability, share issuance and asset growth, as the engine scores them.",
    ),
    Category(
        key="value", label="Value", field="value_percentile",
        blurb="The engine's fundamental sleeve: earnings yield, forward valuation and analyst target.",
    ),
    Category(
        key="profitability", label="Profitability", field="profitability_sector_percentile",
        blurb="Operating margin against sector peers, because margins differ structurally by industry.",
    ),
    Category(
        key="performance", label="Performance", field="performance_score",
        blurb="Risk-adjusted history against the benchmark. Not a forecast, and not the model's view.",
    ),
    Category(
        key="low_risk", label="Low Risk", field="risk_score", descending=False,
        blurb="Lowest measured risk first. A security whose risk could not be measured does not appear.",
    ),
    Category(
        key="news_buzz", label="News Buzz", field="news_buzz",
        blurb="How much is being written. Volume of coverage, not its tone — sentiment is shown separately.",
    ),
    Category(
        key="analyst_upside", label="Analyst Upside", field="analyst_upside",
        blurb="Distance from the current price to the mean analyst target, where both exist.",
    ),
]

_BY_KEY = {c.key: c for c in CATEGORIES}


class ExploreFilters(BaseModel):
    sector: Optional[str] = None
    model_signal: Optional[str] = None
    max_risk: Optional[int] = None
    min_confidence: Optional[int] = None
    min_data_completeness: Optional[float] = None   # 0-1, matching the engine
    min_price: Optional[float] = None
    max_price: Optional[float] = None


def _passes(row: ExploreRow, f: ExploreFilters) -> bool:
    if f.sector and row.sector.lower() != f.sector.lower():
        return False
    if f.model_signal and (row.model_signal or "").lower() != f.model_signal.lower():
        return False
    # `is None` throughout: a filter compares against a measurement, and a row
    # missing the measurement fails the filter rather than passing it by
    # default. "Show me risk under 40" must not return unmeasured risk.
    if f.max_risk is not None and (row.risk_score is None or row.risk_score > f.max_risk):
        return False
    if f.min_confidence is not None and (row.confidence is None or row.confidence < f.min_confidence):
        return False
    if f.min_data_completeness is not None and (
        row.data_completeness is None or row.data_completeness < f.min_data_completeness
    ):
        return False
    if f.min_price is not None and (row.price is None or row.price < f.min_price):
        return False
    if f.max_price is not None and (row.price is None or row.price > f.max_price):
        return False
    return True


def rank(
    snapshot: ExploreSnapshot,
    category_key: str = "overall",
    filters: Optional[ExploreFilters] = None,
    limit: int = 25,
) -> list[ExploreRow]:
    """Eligible rows ordered by one category, filtered, truncated.

    A row missing the category's own measure is dropped rather than sorted to
    the bottom. Appearing last in "Low Risk" still reads as a risk statement,
    and we do not have one to make.
    """
    category = _BY_KEY.get(category_key)
    if category is None:
        raise KeyError(category_key)
    f = filters or ExploreFilters()
    candidates = [
        r for r in snapshot.rows
        if r.eligible and getattr(r, category.field) is not None and _passes(r, f)
    ]
    candidates.sort(key=lambda r: getattr(r, category.field), reverse=category.descending)
    return candidates[: max(1, min(limit, 200))]


def recommendations(snapshot: ExploreSnapshot, limit: int = 5) -> list[ExploreRow]:
    """Top Ranked Ideas: the overall ordering, nothing hard-coded.

    Which securities may be considered is configuration; which of them rank
    highest is model output. No symbol is named anywhere in this path.
    """
    return rank(snapshot, "overall", None, limit)


def high_conviction(snapshot: ExploreSnapshot, limit: int = 5) -> list[ExploreRow]:
    """Securities where every condition agrees at once.

    Frequently empty, and that is the feature working. A tier that always has
    entries is a ranking wearing a threshold's name.
    """
    rows = [r for r in snapshot.rows if r.eligible and r.high_conviction]
    rows.sort(key=lambda r: (-(r.overall_rank or 0.0), r.symbol))
    return rows[: max(1, min(limit, 50))]


def near_conviction(snapshot: ExploreSnapshot, limit: int = 5) -> list[ExploreRow]:
    """The securities that came closest without qualifying.

    High conviction is empty most days, and an empty panel that says only
    "nothing qualifies" teaches a reader nothing about the policy it is
    enforcing. This answers the question they actually have — how close did
    anything get, and on what — from the same assessment that produced the
    tier, so the two can never disagree about what blocked a name.

    Ordered by how many conditions are unmet, then by rank. That ordering is
    presentation: it is not a second scoring path, and a security appearing
    first here is not a recommendation, it is the one with the shortest list of
    reasons it is not in the tier above.
    """
    rows = [
        r for r in snapshot.rows
        if r.eligible and not r.high_conviction and r.conviction_blocked_by
    ]
    rows.sort(key=lambda r: (len(r.conviction_blocked_by), -(r.overall_rank or 0.0), r.symbol))
    return rows[: max(1, min(limit, 50))]


def performance_leaders(snapshot: ExploreSnapshot, limit: int = 5) -> list[ExploreRow]:
    """Strongest risk-adjusted history, whatever the model currently thinks.

    A separate list from `recommendations` on purpose. A security can have
    compounded beautifully and still carry a HOLD because it is expensive
    today, and merging the two would quietly turn the product into a momentum
    chaser wearing a model's name.
    """
    return rank(snapshot, "performance", None, limit)


def categories_payload() -> list[dict[str, Any]]:
    return [c.model_dump() for c in CATEGORIES]
