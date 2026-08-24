"""
OmniSignal API — FastAPI Backend
Multi-factor risk intelligence: FRED macro + yfinance technicals + Alpha Vantage
fundamentals + NewsAPI sentiment, with an optional LLM explanation layer.

Handlers are deliberately *synchronous* (`def`, not `async def`): every data
source here is blocking (fredapi / yfinance / requests), and FastAPI runs sync
handlers in its threadpool — so one slow upstream can no longer stall the
event loop for every concurrent request (see docs/AUDIT.md H3).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.decision import (
    compute_decision,
    confidence_breakdown,
    derive_risk_level,
    verdict_to_recommendation,
)
from src.services import llm_service
from src.models import (
    AggregateSentiment,
    MacroStatus,
    RiskAssessment,
    SignalVerdict,
    TechnicalAnalysis,
)
from src.risk_analysis import OmniSignalRiskEngine
from src.prediction_agent import RiskAwarePredictionAgent
from src.sentiment_edge import SentimentAnalyzer
from src.alpha_vantage import AlphaVantageClient
from src.news_api import NewsAPIClient
from src.models import MacroIndicators
from src import observability, providers
from src.providers import fabric
from src.providers.schemas import PriceSeries
from src.scoring import score_ticker
from src.scoring import technical_intelligence
from src.services import (
    analyst_store, database, factor_lab_service, fundamentals_data,
    news_scoring, research_prefetch, street_intelligence,
)
from src.services.backtest_service import peek_cached as peek_backtest
from src.services.clerk_auth import optional_clerk_user
from src.services.database.repositories import AnalysisRepository
from src.services.provenance import Ledger
from src.services import visual_intelligence

# ── Logging ───────────────────────────────────────────────────────────────────
# Railway captures stdout; structured single-line records with timestamps.

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("omnisignal.api")

DISCLAIMER = "Research and education only — not investment advice."

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniSignal API",
    description="Multi-Factor Risk & Prediction Engine",
    version="5.0.0",
)

# Explicit origin allowlist (comma-separated env var). Wildcard + credentials
# is invalid per the CORS spec; nothing cookie-based crosses this boundary,
# so credentials stay off.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://mini-aladding.vercel.app,http://localhost:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Persistence REST API (watchlists, portfolio, history, saved reports,
# preferences) — Clerk-authenticated, Supabase-backed, optional at runtime.
from api.persistence import router as persistence_router  # noqa: E402

app.include_router(persistence_router)


@app.middleware("http")
async def request_logging(request, call_next):
    """One structured line per request: id, method, path, user, status, duration.

    The request id is generated here and echoed as X-Request-Id so a client
    error report can be matched to its server log line. The Clerk user id is
    attached by the auth dependency (request.state.clerk_user) when a valid
    token was presented — never any token contents.
    """
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    # Profile every request. Attribution is per-label and lock-guarded, and
    # measured at 0.19 µs per record (benchmarks/observability.py), so this
    # stays on in production rather than behind a flag nobody enables before
    # the incident they needed it for.
    profile = observability.begin(f"{request.method} {request.url.path}")
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "rid=%s unhandled error %s %s", request_id, request.method, request.url.path
        )
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    user = getattr(request.state, "clerk_user", None)
    report = profile.report()
    observability.registry.observe(
        "http.request", duration_ms,
        method=request.method, path=_metrics_path(request.url.path),
    )
    logger.info(
        "rid=%s %s %s%s -> %d in %.0fms (work %.0fms, %.1fx parallel, %.0fms unattributed)",
        request_id, request.method, request.url.path,
        f" user={user}" if user else "",
        response.status_code, duration_ms,
        report["work_ms"], report["parallelism"], report["unattributed_ms"],
    )
    observability.clear()
    response.headers["X-Request-Id"] = request_id
    return response


def _metrics_path(path: str) -> str:
    """Collapse path parameters so metric labels stay bounded.

    `/api/research/AAPL` and `/api/research/MSFT` are the same endpoint. Left
    raw, a ticker in the label is unbounded cardinality — the exact leak the
    registry's series cap exists to catch.
    """
    parts = path.strip("/").split("/")
    collapsed = [
        part if index < 2 or not part or part.islower() else ":param"
        for index, part in enumerate(parts)
    ]
    return "/" + "/".join(collapsed)

# ── Shared instances ──────────────────────────────────────────────────────────

risk_engine        = OmniSignalRiskEngine()
sentiment_analyzer = SentimentAnalyzer(max_headlines=12)
av_client          = AlphaVantageClient()

DEMO_MACRO_MULTIPLIER = 1.15


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_market_cap(v: Optional[float]) -> Optional[str]:
    """Format raw market cap to readable string e.g. '$2.34T'."""
    if v is None:
        return None
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"


def _demo_macro_stats() -> dict[str, Any]:
    """Fallback macro payload when FRED is unreachable. Loud in logs, harmless to clients."""
    return {
        "status":               "DEMO_MODE",
        "error":                "FRED API unavailable - using demo data",
        "yield_curve_inverted": False,
        "inflation_rate":       3.2,
        "fed_funds_rate":       5.25,
        "note":                 "Get a free FRED API key at fred.stlouisfed.org",
    }



# FRED series update at most daily; a short TTL cache removes 1-2s of latency
# from every research call and keeps free-tier quota usage flat.
MACRO_CACHE_TTL_SECONDS = float(os.getenv("MACRO_CACHE_TTL", "300"))
_macro_cache: dict[str, tuple[float, tuple[float, dict[str, Any]]]] = {}
_macro_lock = threading.Lock()


def _fetch_macro_safe() -> tuple[float, dict[str, Any]]:
    """
    SRM + stats, sourced through the MacroProvider (FRED behind cache,
    retries and health tracking); SRM math stays in the risk engine.
    Demo fallback preserved. Never raises.
    """
    now = time.time()
    with _macro_lock:
        entry = _macro_cache.get("srm")
        if entry and entry[0] > now:
            return entry[1]
    try:
        snapshot_result = providers.macro.get_macro()
        if not snapshot_result.ok:
            raise RuntimeError(snapshot_result.error or "macro provider returned no data")
        snap = snapshot_result.data
        indicators = MacroIndicators(
            yield_spread=snap.yield_spread if snap.yield_spread is not None else 0.0,
            inflation_rate=snap.inflation_rate if snap.inflation_rate is not None else 0.0,
            fed_funds_rate=snap.fed_funds_rate,
        )
        assessment = risk_engine.calculate_multiplier(indicators)
        stats: dict[str, Any] = {
            "yield_spread": indicators.yield_spread,
            "inflation_rate": f"{indicators.inflation_rate:.2f}%",
            "fed_funds_rate": (
                f"{indicators.fed_funds_rate:.2f}%"
                if indicators.fed_funds_rate is not None else "N/A"
            ),
            "yield_curve_inverted": assessment.yield_curve_inverted,
            "status": assessment.status.value,
            "recession_warning": assessment.recession_warning,
        }
        result = (assessment.risk_multiplier, stats)
        with _macro_lock:
            _macro_cache["srm"] = (now + MACRO_CACHE_TTL_SECONDS, result)
        return result
    except Exception:
        logger.exception("Macro fetch failed — serving DEMO_MODE fallback")
        return DEMO_MACRO_MULTIPLIER, _demo_macro_stats()


# ── Fast macro stress inputs (engine v2.1 probabilistic gate) ────────────────
# NFCI (weekly), Moody's BAA−10Y credit spread z, T10Y2Y term spread, VIX
# percentile. Cached 15 min; every input optional — the gate degrades to the
# term-only Estrella–Mishkin reduced model, then to the legacy SRM curve.
STRESS_CACHE_TTL = 900.0
_stress_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _stress_inputs() -> dict[str, Any]:
    now = time.time()
    with _macro_lock:
        entry = _stress_cache.get("v1")
        if entry and entry[0] > now:
            return entry[1]

    out: dict[str, Any] = {"term_spread": None, "nfci": None,
                           "credit_spread_z": None, "vix_percentile": None}
    try:
        term = providers.macro.get_series_snapshot("T10Y2Y", count=5)
        if term.ok and term.data:
            out["term_spread"] = float(term.data[-1][1])
    except Exception:  # noqa: BLE001
        logger.exception("term spread fetch failed")
    try:
        nfci = providers.macro.get_series_snapshot("NFCI", count=5)
        if nfci.ok and nfci.data:
            out["nfci"] = float(nfci.data[-1][1])  # NFCI is standardized at source
    except Exception:  # noqa: BLE001
        logger.exception("NFCI fetch failed")
    try:
        credit = providers.macro.get_series_snapshot("BAA10Y", count=260)
        if credit.ok and credit.data and len(credit.data) >= 60:
            values = [v for _, v in credit.data]
            median = sorted(values)[len(values) // 2]
            mad = sorted(abs(v - median) for v in values)[len(values) // 2]
            if mad > 1e-9:
                out["credit_spread_z"] = round((values[-1] - median) / (1.4826 * mad), 3)
    except Exception:  # noqa: BLE001
        logger.exception("credit spread fetch failed")
    try:
        vix = providers.market_data.get_series("^VIX", "1y")
        if vix.ok and len(vix.data.bars) >= 60:
            closes = [bar.close for bar in vix.data.bars]
            latest = closes[-1]
            out["vix_percentile"] = round(sum(1 for c in closes if c <= latest) / len(closes), 3)
    except Exception:  # noqa: BLE001
        logger.exception("VIX percentile fetch failed")

    with _macro_lock:
        _stress_cache["v1"] = (now + STRESS_CACHE_TTL, out)
    return out


def _series_to_dataframe(series: PriceSeries):
    """Convert normalized OHLCV bars to the DataFrame shape the agent expects."""
    import pandas as pd

    frame = pd.DataFrame(
        {
            "Open": [bar.open for bar in series.bars],
            "High": [bar.high for bar in series.bars],
            "Low": [bar.low for bar in series.bars],
            "Close": [bar.close for bar in series.bars],
            "Volume": [bar.volume if bar.volume is not None else 0 for bar in series.bars],
        },
        index=pd.to_datetime([bar.date for bar in series.bars]),
    )
    return frame


def _macro_assessment(multiplier: float, stats: dict[str, Any]) -> RiskAssessment:
    """Rebuild a RiskAssessment object from the stats dict for decision logic."""
    status_raw = str(stats.get("status", "STABLE"))
    try:
        status = MacroStatus(status_raw)
    except ValueError:  # e.g. "DEMO_MODE"
        status = MacroStatus.DATA_ERROR
    return RiskAssessment(
        risk_multiplier=max(0.5, min(1.6, multiplier)),
        yield_curve_inverted=bool(stats.get("yield_curve_inverted", False)),
        status=status,
        recession_warning=bool(stats.get("recession_warning", False)),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _build_commit() -> str:
    """The revision this process is running, or "unknown".

    Hosts inject their own name for this; Render uses RENDER_GIT_COMMIT.
    Falls back to asking git, which only works in a checkout — deliberately
    returning "unknown" rather than raising, because a health endpoint that
    can fail is worse than one that admits ignorance.
    """
    for name in ("RENDER_GIT_COMMIT", "VERCEL_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION"):
        value = os.getenv(name)
        if value:
            return value[:12]
    try:
        import subprocess

        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=2, check=True,
        ).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 — health must never fail
        return "unknown"


@app.get("/api/health")
def health():
    """Health check — reports which API keys are configured."""
    environment = (
        "production"
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENV") == "production"
        else "development"
    )
    missing_persistence = [
        name
        for name in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "CLERK_JWKS_URL", "CLERK_ISSUER")
        if not os.getenv(name)
    ]
    return {
        "status":  "ok",
        "service": "OmniSignal API",
        "version": "5.0.0",
        # ── Deploy identity ──────────────────────────────────────────────
        # `version` is hand-maintained and was identical on a local tree and
        # a production service running six-day-old code, which is exactly how
        # a stale backend went unnoticed until the browser 404'd on
        # /api/factors. These two fields make "is production running my
        # code?" a single curl:
        #
        #   commit       the deployed revision. Render injects
        #                RENDER_GIT_COMMIT; other hosts set their own, and
        #                locally we fall back to reading git directly.
        #   capabilities the route families this build actually serves, so a
        #                client can ask what exists instead of discovering
        #                absence through a 404.
        "commit": _build_commit(),
        "capabilities": sorted(
            {
                route.path.split("/")[2]
                for route in app.routes
                if getattr(route, "path", "").startswith("/api/")
                and len(route.path.split("/")) > 2
            }
        ),
        "data_sources": {
            "fred":          bool(os.getenv("FRED_API_KEY")),
            "alpha_vantage": av_client.available,
            "news_api":      NewsAPIClient().available,
            "llm":           bool(os.getenv("GROQ_API_KEY")),
            "yfinance":      True,
            "yahoo_scraper": True,
        },
        # Presence booleans only — names, never values. Lets a release engineer
        # confirm from outside that the deployed build reads its env correctly.
        "persistence": {
            "database_configured": database.is_configured(),
            "auth_configured": bool(os.getenv("CLERK_JWKS_URL")),
            "missing_env": missing_persistence,
        },
        "environment": environment,
    }


@app.get("/api/macro")
def get_macro():
    """Systemic Risk Multiplier + FRED macro indicators."""
    start = time.time()
    multiplier, stats = _fetch_macro_safe()
    return JSONResponse(
        status_code=200,
        content={
            "risk_multiplier": multiplier,
            "stats":           stats,
            "elapsed_seconds": round(time.time() - start, 2),
        },
    )


# Deterministic event taxonomy. Keyword matching over the headline and its
# summary — not a second model. The existing LLM layer already receives the
# headlines and narrates them; classifying them here gives it structure to
# reason over and gives the UI counts that do not depend on a model being up.
NEWS_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Earnings": ("earnings", "eps", "quarterly result", "q1 ", "q2 ", "q3 ", "q4 ",
                 "beats estimate", "misses estimate", "guidance", "revenue"),
    "M&A": ("acquisition", "acquires", "merger", "takeover", "buyout", "stake in",
            "divest", "spin-off", "spinoff"),
    "Product": ("launch", "unveil", "announce", "release", "new model", "rollout",
                "next-generation", "update"),
    "Regulatory": ("regulator", "antitrust", "sec ", "ftc", "doj", "probe",
                   "investigation", "compliance", "fine", "sanction"),
    "Management": ("ceo", "cfo", "chief executive", "resign", "appoint", "steps down",
                   "board of directors", "succession"),
    "Analyst": ("upgrade", "downgrade", "price target", "initiates coverage",
                "outperform", "underperform", "reiterates", "rating"),
    "Legal": ("lawsuit", "sues", "settlement", "court", "litigation", "patent"),
    "Supply chain": ("supply chain", "shortage", "factory", "production", "supplier",
                     "capacity", "fab "),
    "Macro": ("fed ", "inflation", "rate cut", "rate hike", "tariff", "recession",
              "jobs report", "gdp"),
}


def _xbrl_trends(facts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Year-over-year change per concept, from the company's own tagged figures.

    Only consecutive fiscal years of the *same* concept are compared, so no
    two periods are ever crossed between different line items. A concept with
    one year of data yields no trend rather than a zero — a single
    observation is not a direction.

    The prior year's value travels with the percentage so the arithmetic is
    checkable against the rows rendered beside it.
    """
    out: list[dict[str, Any]] = []
    for concept, series in facts.items():
        usable = [row for row in series if isinstance(row.get("value"), (int, float))]
        if len(usable) < 2:
            continue
        latest, prior = usable[0], usable[1]
        # Guard the ratio: a prior year of zero has no defined growth rate,
        # and a sign flip makes the percentage meaningless rather than large.
        if not prior["value"] or (latest["value"] < 0) != (prior["value"] < 0):
            continue
        change = (latest["value"] / prior["value"] - 1) * 100
        out.append({
            "concept": concept,
            "latest_year": latest.get("fiscal_year"),
            "latest_value": latest["value"],
            "prior_year": prior.get("fiscal_year"),
            "prior_value": prior["value"],
            "change_pct": round(change, 2),
            "unit": latest.get("unit"),
            "form": latest.get("form"),
            "filed": latest.get("filed"),
        })
    out.sort(key=lambda r: abs(r["change_pct"]), reverse=True)
    return out


def _categorise_news(headlines: list) -> dict[str, int]:
    """Counts per event type, deterministically.

    A headline can hit several categories — an earnings beat that triggers an
    upgrade is genuinely both — so counts sum to more than the article total.
    That is reported as counts per category rather than as a partition, since
    forcing a single label would discard the second fact.
    """
    counts: dict[str, int] = {}
    for item in headlines:
        text = f"{getattr(item, 'title', '')} {getattr(item, 'summary', '')}".lower()
        matched = False
        for label, keywords in NEWS_CATEGORIES.items():
            if any(k in text for k in keywords):
                counts[label] = counts.get(label, 0) + 1
                matched = True
        if not matched:
            counts["Other"] = counts.get("Other", 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def _as_result(headlines: list, providers_used: list[str]):
    """Wrap merged headlines in the envelope the rest of the handler expects.

    The sentiment path downstream consumes a `ProviderResult`; the fabric
    returns a plain merge. Adapting here keeps that path untouched rather
    than rewriting a working scorer around a new shape.
    """
    from src.providers.schemas import ProviderResult
    return ProviderResult(
        data=headlines or None,
        source=", ".join(providers_used),
        sources_consulted=list(providers_used),
        confidence=0.85 if headlines else 0.0,
        error=None if headlines else "no vendor returned headlines",
    )


@app.get("/api/research/{ticker}")
def research_ticker(
    ticker: str,
    fast: bool = Query(False, description="Skip sentiment and LLM analysis for speed"),
    clerk_user: Optional[str] = Depends(optional_clerk_user),
):
    """
    Full OmniSignal research pipeline:
      1. FRED macro risk (SRM)          ┐ fetched concurrently —
      2. yfinance + Alpha Vantage       ┘ independent upstreams
      3. NewsAPI / Yahoo sentiment       (unless fast=true; needs company name)
      4. Deterministic decision synthesis (verdict / confidence / risk level)
      5. LLM explanation layer           (unless fast=true; optional, never fatal)
    """
    start  = time.time()
    ticker = ticker.upper().strip()

    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    # Chain of custody for this run. Every provider call below already returns
    # which vendor answered, which were tried, and how degraded the answer
    # was; until this ledger existed all of it went to a log line and the
    # response carried the conclusion without the evidence behind it.
    ledger = Ledger(ticker)

    news_stream: Optional[dict[str, Any]] = None
    news_categories: dict[str, int] = {}
    # Company identity & narrative, from whichever vendor answered. Fetched
    # for the news query anyway; previously six of its fields were used and
    # the description, domain, headcount and IPO date were thrown away.
    profile_block: Optional[dict[str, Any]] = None
    # Valuation, margin, return, growth and leverage ratios. 133 figures come
    # back from one vendor request; seven were being kept.
    ratios_block: Optional[dict[str, Any]] = None

    # ── Step 0: warm the seven independent upstreams concurrently. ──────────
    # Purely a latency measure. Every fetch below is cache-first and
    # single-flight wrapped, so a warmed key returns instantly and a call
    # that races the warm joins it instead of duplicating it. Nothing here
    # changes what the handler computes — if the warm fails entirely, each
    # call below simply fetches as it always did.
    research_prefetch.warm(ticker)

    # ── Steps 1+2 concurrently: macro and technicals are independent. ────────
    # predict() is run with a neutral multiplier, then the real dampening is
    # applied once the SRM is known — apply_dampening is stateless, so the
    # arithmetic is identical to the sequential version.
    prediction = None
    technicals: dict[str, Any] = {}
    tech_error: Optional[str] = None

    def _days_to_earnings() -> Optional[int]:
        """Best-effort business days to the next confirmed earnings date."""
        try:
            import pandas as pd
            import yfinance as yf

            calendar = yf.Ticker(ticker).calendar
            dates = calendar.get("Earnings Date") if isinstance(calendar, dict) else None
            if not dates:
                return None
            next_date = min(d for d in dates if d is not None)
            days = len(pd.bdate_range(start=pd.Timestamp.utcnow().date(), end=next_date)) - 1
            return max(0, days)
        except Exception:  # noqa: BLE001 — calendar is a nice-to-have
            return None

    def _run_technicals():
        # One year of history through the MarketDataProvider fallback chain
        # (Polygon → TwelveData → FMP → MarketStack → yfinance → stale cache).
        # The scoring engine consumes the full year (rolling distributions);
        # the legacy agent gets the trailing quarter so its reported metrics
        # (volatility, Sharpe, drawdown windows) stay unchanged.
        series_result = providers.market_data.get_series(ticker, "1y")
        full_frame = (
            _series_to_dataframe(series_result.data)
            if series_result.ok and series_result.data.bars
            else None
        )
        if full_frame is not None:
            logger.info(
                "technicals %s: %d bars via %s (confidence %.2f%s)",
                ticker, len(full_frame), series_result.source, series_result.confidence,
                ", stale" if series_result.stale else "",
            )
        quarter = full_frame.iloc[-63:] if full_frame is not None and len(full_frame) > 63 else full_frame
        agent = RiskAwarePredictionAgent(
            ticker, period="3mo", av_client=av_client, price_data=quarter
        )
        prediction_result = agent.predict(risk_multiplier=1.0)
        # Slow inputs for the v2.1 quality/PEAD sleeves (6h-cached, optional)
        quality_inputs = fundamentals_data.get_quality_inputs(ticker)
        pead_inputs = fundamentals_data.get_pead_inputs(ticker)
        return (prediction_result, full_frame, series_result,
                _days_to_earnings(), quality_inputs, pead_inputs)

    scoring_frame = None
    series_result = None
    series_confidence = 1.0
    days_to_earnings: Optional[int] = None
    quality_inputs: dict[str, Any] = {}
    pead_inputs: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="research") as pool:
        macro_future = pool.submit(_fetch_macro_safe)
        tech_future = pool.submit(_run_technicals)
        multiplier, macro_stats = macro_future.result()
        ledger.note(
            f"Macro regime gate applied at SRM {multiplier:.2f}"
            if isinstance(multiplier, (int, float)) else "Macro regime gate applied"
        )
        try:
            (prediction, scoring_frame, series_result,
             days_to_earnings, quality_inputs, pead_inputs) = tech_future.result()
            series_confidence = series_result.confidence
            bars = len(scoring_frame) if scoring_frame is not None else 0
            ledger.record(
                label="Daily price history",
                kind="market",
                result=series_result,
                detail=f"{bars} daily bars, 1y window",
                used_for=["momentum factors", "volatility", "technical intelligence",
                          "risk score"],
            )
        except Exception:
            logger.exception("Technical analysis failed for %s", ticker)
            tech_error = "Technical analysis failed — check that the ticker symbol is valid"
            ledger.record(
                label="Daily price history", kind="market",
                missing_reason="every price vendor failed for this symbol",
                used_for=["momentum factors", "volatility", "risk score"],
            )

    if prediction is not None:
        risk_adjusted = RiskAwarePredictionAgent.apply_dampening(
            prediction.raw_signal, multiplier
        ) if prediction.raw_signal else None
        prediction.risk_adjusted_signal = risk_adjusted or prediction.risk_adjusted_signal

        technicals = {
            "ticker":        prediction.ticker,
            "current_price": prediction.current_price,
            "return_5d":     round(prediction.return_5d, 4)    if prediction.return_5d    else None,
            "return_21d":    round(prediction.return_21d, 4)   if prediction.return_21d   else None,
            "volatility":    round(prediction.volatility, 4)   if prediction.volatility   else None,
            "sharpe_ratio":  prediction.sharpe_ratio,
            "sortino_ratio": prediction.sortino_ratio,
            "rsi_14":        prediction.rsi_14,
            "max_drawdown":  prediction.max_drawdown,
            "momentum":      prediction.momentum,
            "raw_signal":    prediction.raw_signal.value             if prediction.raw_signal             else None,
            "risk_adjusted_signal": prediction.risk_adjusted_signal.value if prediction.risk_adjusted_signal else None,

            # Alpha Vantage MACD
            "macd_crossover": prediction.macd_crossover,
            "macd_histogram": round(prediction.macd_histogram, 4) if prediction.macd_histogram else None,

            # Alpha Vantage fundamentals
            "pe_ratio":       prediction.pe_ratio,
            "forward_pe":     prediction.forward_pe,
            "eps":            prediction.eps,
            "analyst_target": prediction.analyst_target,
            "week_52_high":   prediction.week_52_high,
            "week_52_low":    prediction.week_52_low,
            "beta":           prediction.beta,
            "market_cap":     _fmt_market_cap(prediction.market_cap),
            "sector":         prediction.sector,
            "company_name":   prediction.company_name,
        }
    else:
        technicals = {"error": tech_error, "note": "Technical analysis failed — check ticker"}

    # ── Step 2b: fill fundamentals gaps through the FundamentalsProvider chain
    # (Alpha Vantage → Finnhub → FMP). Only missing fields are filled; the
    # agent's own enrichment always wins when present.
    # Unconditional now. It was gated on a missing company name, so a ticker
    # whose name arrived from the price vendor never fetched a profile — and
    # therefore never got a sector, a domain, or a description, all of which
    # ride in the same response.
    if prediction is not None:
        try:
            # Every profile-capable vendor, in parallel. No single vendor
            # carries a complete profile — Finnhub has the domain and IPO
            # date, Polygon the headcount and SIC description, yfinance the
            # GICS sector and business summary — so this is a union, and the
            # per-field provenance records which vendor each value came from.
            profile_ev = providers.fundamentals.profile_evidence(ticker)
            merged_profile = fabric.merge_profile(profile_ev)
            if merged_profile:
                profile_block = {
                    **merged_profile["resolved"],
                    "symbol": ticker,
                    "providers": merged_profile["providers"],
                    "conflicts": merged_profile["conflicts"],
                    "field_sources": {
                        name: entry.get("providers", [])
                        for name, entry in merged_profile["fields"].items()
                    },
                }
            ledger.record_fabric(
                label="Company profile",
                kind="fundamental",
                evidence=profile_ev,
                detail=(f"{len(merged_profile['fields'])} fields from "
                        f"{len(merged_profile['providers'])} vendors"
                        + (f" · {len(merged_profile['conflicts'])} disputed"
                           if merged_profile["conflicts"] else "")
                        if merged_profile else "no vendor answered"),
                used_for=["sector identity", "news query", "logo domain"],
            )
            # The chain result still feeds the legacy enrichment below, which
            # expects a single profile object rather than a union.
            company_result = providers.fundamentals.get_company(ticker)
            if company_result.ok:
                profile = company_result.data
                technicals["company_name"] = technicals.get("company_name") or profile.name or None
                technicals["sector"] = technicals.get("sector") or (profile.sector or None)
                if technicals.get("market_cap") is None and profile.market_cap:
                    technicals["market_cap"] = _fmt_market_cap(profile.market_cap)
        except Exception:  # noqa: BLE001 — enrichment is never fatal
            logger.exception("Fundamentals enrichment failed for %s", ticker)
    if prediction is not None and technicals.get("pe_ratio") is None:
        try:
            fund_result = providers.fundamentals.get_fundamentals(ticker)
            if fund_result.ok and fund_result.data:
                # The ratio surface the vendor already returned. Named with
                # their periods intact so nothing downstream can average a
                # TTM figure against a 5-year average.
                ratios_block = {
                    k: v for k, v in fund_result.data.model_dump().items()
                    if k not in ("symbol", "profile", "vendor_metrics") and v is not None
                }
                ratios_block["source"] = fund_result.source
            ledger.record(
                label="Valuation fundamentals",
                kind="fundamental",
                result=fund_result,
                detail="P/E, forward P/E, EPS, beta, 52-week range",
                used_for=["value factors", "analyst-target upside", "beta risk"],
            )
            if fund_result.ok:
                fund = fund_result.data
                for field, value in (
                    ("pe_ratio", fund.pe_ratio), ("forward_pe", fund.forward_pe),
                    ("eps", fund.eps), ("beta", fund.beta),
                    ("week_52_high", fund.week_52_high), ("week_52_low", fund.week_52_low),
                ):
                    if technicals.get(field) is None and value is not None:
                        technicals[field] = value
        except Exception:  # noqa: BLE001
            logger.exception("Fundamentals metrics enrichment failed for %s", ticker)

    # ── Step 2c: multi-source consensus quote and statement union ───────────
    # Both are parallel fan-outs over every capable vendor, not fallback
    # chains: the useful output is not the value but the *agreement*, and a
    # chain that stops at the first answer can never report it. Additive —
    # neither feeds the scoring engine, so a total failure here costs the
    # response two presentation blocks and nothing else.
    consensus = None
    statements = None
    if prediction is not None:
        try:
            quote_ev = providers.market_data.quote_evidence(ticker)
            consensus = fabric.reconcile_price(quote_ev)
            ledger.record_fabric(
                label="Consensus quote",
                kind="market",
                evidence=quote_ev,
                detail=(f"{consensus['agreement']} vendors agree · "
                        f"{consensus['dispersion_pct']:.3f}% spread"
                        if consensus else "no vendor quoted this symbol"),
                used_for=["price consensus", "cross-vendor agreement"],
            )
        except Exception:  # noqa: BLE001 — additive block, never fatal
            logger.exception("consensus quote failed for %s", ticker)

        try:
            stmt_ev = providers.fundamentals.statement_evidence(ticker)
            statements = fabric.merge_fundamentals(stmt_ev)
            if stmt_ev:
                ledger.record_fabric(
                    label="Reported statements",
                    kind="fundamental",
                    evidence=stmt_ev,
                    detail=(f"{len(statements['fields'])} line items from "
                            f"{len(statements['providers'])} vendors"
                            if statements else "no vendor is entitled for this symbol"),
                    used_for=["valuation ratios", "fundamental trend"],
                )
        except Exception:  # noqa: BLE001
            logger.exception("statement union failed for %s", ticker)

    # ── Step 2c-bis: ownership and sell-side positioning ────────────────────
    # Both keyless, both previously unreachable. Ownership answers "who is on
    # the other side of this" and the analyst block answers "what does the
    # street expect" — neither is performance data, which is why they are
    # separate blocks rather than more fields on the fundamentals object.
    ownership_block = None
    analyst_block = None
    if prediction is not None:
        try:
            own_ev = providers.fundamentals.ownership_evidence(ticker)
            row = next((e.data for e in own_ev if e.ok and e.data), None)
            if row is not None:
                ownership_block = row.model_dump()
            if own_ev:
                ledger.record_fabric(
                    label="Ownership & short interest",
                    kind="fundamental",
                    evidence=own_ev,
                    detail=(f"short interest as of {ownership_block['short_interest_date']}"
                            if ownership_block and ownership_block.get("short_interest_date")
                            else "float, holdings and short interest"),
                    used_for=["presentation only — never a scoring input"],
                )
        except Exception:  # noqa: BLE001 — additive, never fatal
            logger.exception("ownership lookup failed for %s", ticker)

        try:
            analyst_ev = providers.fundamentals.analyst_evidence(ticker)
            readings = [e.data.model_dump() for e in analyst_ev if e.ok and e.data]
            if readings:
                # Every vendor's reading, side by side. Deliberately not
                # reduced to one number: each polls a different analyst set,
                # so a median across vendors is a consensus of no actual
                # group of people.
                analyst_block = {"readings": readings, "vendor_count": len(readings)}
            if analyst_ev:
                ledger.record_fabric(
                    label="Analyst targets",
                    kind="fundamental",
                    evidence=analyst_ev,
                    detail=(f"{len(readings)} vendor consensus reading"
                            f"{'' if len(readings) == 1 else 's'}"),
                    used_for=["presentation only — not reconciled across vendors"],
                )
        except Exception:  # noqa: BLE001
            logger.exception("analyst lookup failed for %s", ticker)

    # ── Step 2d: primary-source regulatory evidence ─────────────────────────
    # SEC EDGAR is keyless and is not another vendor's reading of a filing —
    # it is the filing, with the date it was actually filed. That makes it a
    # different *kind* of evidence rather than a cheaper copy of the same
    # kind, which is why it is recorded as its own input and never merged
    # into the fundamentals union.
    filings_block = None
    if prediction is not None:
        try:
            filings_ev = providers.filings.filings_evidence(ticker, limit=10)
            rows = next((e.data for e in filings_ev if e.ok and e.data), None)
            if rows:
                filings_block = {
                    "filings": rows,
                    # Counts by form, so a reader sees the shape of recent
                    # activity before reading any single row.
                    "by_form": {
                        form: sum(1 for r in rows if r["form"] == form)
                        for form in sorted({r["form"] for r in rows})
                    },
                    "latest": rows[0] if rows else None,
                    "source": "SEC EDGAR",
                }
            ledger.record_fabric(
                label="SEC filings",
                kind="fundamental",
                evidence=filings_ev,
                detail=(f"{len(rows)} recent filings" if rows else "no filings resolved"),
                used_for=["primary-source evidence", "filing recency"],
            )

            # XBRL company facts: the numbers as the company itself tagged
            # them, with the fiscal year, the unit, the form and the filing
            # date attached. This is the one place in the product where a
            # figure can be traced to a specific document rather than to a
            # vendor's extraction of one — which is exactly what makes it
            # worth a separate capability from `statements`.
            facts_ev = providers.filings.facts_evidence(ticker)
            facts = next((e.data for e in facts_ev if e.ok and e.data), None)
            if facts:
                # Trimmed to the most recent years per concept. The full
                # history is available from the same call, but a research
                # page wants a trend, not a decade of rows.
                filings_block = filings_block or {"source": "SEC EDGAR"}
                filings_block["xbrl"] = {
                    concept: series[:6]
                    for concept, series in facts.items() if series
                }
                # A trend the reader can check against the rows beside it —
                # computed from consecutive fiscal years of the *same*
                # concept, so no two periods are ever compared across
                # different line items.
                filings_block["xbrl_trend"] = _xbrl_trends(facts)
            if facts_ev:
                ledger.record_fabric(
                    label="XBRL reported facts",
                    kind="fundamental",
                    evidence=facts_ev,
                    detail=(f"{len(facts)} tagged concepts" if facts
                            else "no XBRL facts for this filer"),
                    used_for=["primary-source figures", "multi-year trend"],
                )
        except Exception:  # noqa: BLE001 — additive block, never fatal
            logger.exception("filings lookup failed for %s", ticker)

    # ── Step 3: Sentiment (after technicals — reuses the resolved company name)
    sentiment_data: Optional[dict[str, Any]] = None
    sentiment_obj = AggregateSentiment()
    if fast:
        ledger.record(
            label="News & headlines", kind="evidence",
            missing_reason="fast mode — evidence gathering and the narrative layer are skipped",
            used_for=["news factor", "evidence weighting", "sentiment"],
        )
    if not fast:
        company_name = technicals.get("company_name", "") or ""
        try:
            # Headlines through the NewsProvider chain (NewsAPI → GNews →
            # Yahoo RSS → Tavily → stale cache); the keyword scorer is unchanged.
            # Every news vendor, concurrently. News is the clearest case
            # against a fallback chain: vendors do not carry the same
            # stories, so stopping at the first success returns a *smaller*
            # answer rather than a faster one. Merged by URL then canonical
            # title, with corroboration recorded.
            news_ev = providers.news.news_evidence(ticker, company_name, limit=12)
            merged_news = fabric.merge_news(news_ev)
            news_stream = merged_news
            ledger.record_fabric(
                label="News & headlines",
                kind="evidence",
                evidence=news_ev,
                detail=(f"{merged_news['unique']} unique of {merged_news['collected']} collected · "
                        f"{merged_news['corroborated']} corroborated"),
                used_for=["news factor", "evidence weighting", "sentiment"],
            )
            news_categories = _categorise_news(merged_news["headlines"])
            news_result = _as_result(merged_news["headlines"], merged_news["providers"])
            if news_result.ok and news_result.data:
                headline_dicts = [
                    {
                        "title": h.title,
                        "source": h.source,
                        "url": h.url,
                        "published": h.published_at,
                        "is_breaking": sentiment_analyzer._detect_breaking(h.title),
                    }
                    for h in news_result.data
                ]
                sentiment_obj = sentiment_analyzer.analyze_headlines(headline_dicts)
                logger.info(
                    "sentiment %s: %d headlines via %s",
                    ticker, len(headline_dicts), news_result.source,
                )
            else:
                sentiment_obj = sentiment_analyzer.analyze_ticker(ticker, company_name=company_name)
            sentiment_data = {
                "headline_count": sentiment_obj.headline_count,
                "average_score":  sentiment_obj.average_score,
                "dominant_label": sentiment_obj.dominant_label.value,
                "headlines": [
                    {
                        "title":        h.headline,
                        "score":        h.score,
                        "label":        h.label.value,
                        "source":       h.source,
                        "url":          h.url,
                        "published_at": h.published_at,
                    }
                    for h in sentiment_obj.headlines
                ],
            }
        except Exception:
            logger.exception("Sentiment analysis failed for %s", ticker)
            ledger.record(
                label="News & headlines", kind="evidence",
                missing_reason="every news vendor failed",
                used_for=["news factor", "evidence weighting", "sentiment"],
            )
            sentiment_data = {
                "error":          "Sentiment sources unavailable",
                "headline_count": 0,
                "note":           "Sentiment analysis failed",
            }

    # ── Step 3b: News evidence methodology (v2.1 §7) — decay, novelty,
    # clustering, confirmation → effective evidence for the engine. The raw
    # sentiment block keeps its contract; additive fields report the method.
    news_evidence = None
    if sentiment_obj.headline_count:
        try:
            news_evidence = news_scoring.score_headlines([
                {
                    "title": h.headline, "score": h.score, "source": h.source,
                    "url": h.url, "published_at": h.published_at,
                }
                for h in sentiment_obj.headlines
            ])
            if sentiment_data is not None:
                sentiment_data["n_eff"] = news_evidence.n_eff
                sentiment_data["s_eff"] = news_evidence.s_eff
                sentiment_data["clusters"] = news_evidence.clusters
                sentiment_data["method_note"] = news_evidence.note
                for row, scored in zip(sentiment_data.get("headlines", []), news_evidence.headlines):
                    row["event_type"] = scored.event_type
                    row["evidence_weight"] = scored.weight

            # Re-attach what the fan-out learned that the keyword scorer does
            # not model: which vendors independently carried each story, the
            # publisher's own image, and any vendor-scored sentiment. The
            # scorer consumes only title/score/source, so without this the
            # merge's whole advantage would be discarded at serialisation.
            if news_stream and sentiment_data:
                by_title = {
                    (h.title or "").strip().lower(): h
                    for h in news_stream["headlines"]
                }
                for row in sentiment_data.get("headlines", []):
                    merged = by_title.get((row.get("title") or "").strip().lower())
                    if not merged:
                        continue
                    row["corroborated_by"] = merged.corroborated_by
                    row["image_url"] = merged.image_url
                    row["sentiment_score"] = merged.sentiment_score
                    row["sentiment_label"] = merged.sentiment_label
        except Exception:  # noqa: BLE001 — methodology layer must never break research
            logger.exception("News scoring failed for %s", ticker)

    # ── Step 4: Quantitative scoring (docs/SCORING.md v2.1). The engine is
    # the primary verdict source; the v1 point system remains solely as the
    # fallback for short price histories (< 60 bars) or scoring failures.
    # v4.5: deterministic technical intelligence from the frame we already hold.
    tech_intel = None
    if scoring_frame is not None:
        try:
            tech_intel = technical_intelligence.build(scoring_frame)
        except Exception:  # noqa: BLE001 — presentation layer must never break research
            logger.exception("technical intelligence failed for %s", ticker)

    # v4.5 P0-B: street & insider intelligence (Finnhub free tier, 6h cache).
    street_intel = None
    if prediction is not None:
        try:
            street_result = providers.fundamentals.get_street(ticker)
            ledger.record(
                label="Street & insider activity",
                kind="fundamental",
                result=street_result,
                detail="analyst ratings, price targets, insider transactions",
                used_for=["presentation only — never a scoring input"],
            )
            if street_result.ok:
                street_intel = street_intelligence.build(street_result.data)
        except Exception:  # noqa: BLE001 — additive block, never fatal
            logger.exception("street intelligence failed for %s", ticker)

    scorecard = None
    if prediction is not None and scoring_frame is not None:
        try:
            spy_result = providers.market_data.get_series("SPY", "1y")
            ledger.record(
                label="SPY benchmark series",
                kind="market",
                result=spy_result,
                detail="1y daily bars",
                used_for=["relative strength vs benchmark"],
            )
            spy_frame = (
                _series_to_dataframe(spy_result.data)
                if spy_result.ok and spy_result.data.bars else None
            )
            stress = _stress_inputs()
            backtest_recent = (peek_backtest(ticker) or {}).get("recent", {})
            last_bar_age_days = max(
                0.0,
                (datetime.now(timezone.utc).date()
                 - date.fromisoformat(scoring_frame.index[-1].strftime("%Y-%m-%d"))).days,
            ) if len(scoring_frame) else None
            scorecard = score_ticker(
                scoring_frame,
                srm=multiplier,
                price=prediction.current_price,
                pe_ratio=prediction.pe_ratio,
                forward_pe=prediction.forward_pe,
                analyst_target=prediction.analyst_target,
                beta=prediction.beta,
                sentiment_avg=(news_evidence.s_eff if news_evidence
                               else (sentiment_obj.average_score if sentiment_obj.headline_count else None)),
                headline_count=(news_evidence.n_eff if news_evidence
                                else float(sentiment_obj.headline_count)),
                spy_frame=spy_frame,
                days_to_earnings=days_to_earnings,
                data_confidence=series_confidence,
                gross_profit_over_assets=quality_inputs.get("gross_profit_over_assets"),
                net_issuance_yoy=quality_inputs.get("net_issuance_yoy"),
                asset_growth_yoy=quality_inputs.get("asset_growth_yoy"),
                earnings_surprise_pct=pead_inputs.get("surprise_pct"),
                days_since_earnings=pead_inputs.get("days_since"),
                nfci=stress.get("nfci"),
                credit_spread_z=stress.get("credit_spread_z"),
                vix_percentile=stress.get("vix_percentile"),
                term_spread=stress.get("term_spread"),
                price_age_days=last_bar_age_days,
                news_age_hours=news_evidence.median_age_hours if news_evidence else None,
                model_rolling_ic=backtest_recent.get("rolling_ic_last"),
                recent_verdict_flips=backtest_recent.get("verdict_flips_last6"),
            )
        except Exception:  # noqa: BLE001 — scoring must never take down research
            logger.exception("Scoring engine failed for %s — using legacy verdict", ticker)

    # ── Step 4b: analyst snapshot persistence (plan item 10 — stored, not scored)
    if prediction is not None:
        analyst_store.record_snapshot(
            ticker,
            price=prediction.current_price,
            analyst_target=prediction.analyst_target,
            pe_ratio=prediction.pe_ratio,
            forward_pe=prediction.forward_pe,
            eps=prediction.eps,
        )

    if scorecard is not None:
        # The engine's verdicts replace the legacy signal fields (same field
        # names and value vocabulary — contract shape unchanged).
        technicals["raw_signal"] = scorecard.raw_verdict
        technicals["risk_adjusted_signal"] = scorecard.verdict
        prediction.raw_signal = SignalVerdict(scorecard.raw_verdict)
        prediction.risk_adjusted_signal = SignalVerdict(scorecard.verdict)

    # ── Step 5: Decision synthesis (rationale text; confidence source depends
    # on path: scorecard when available, legacy agreement formula otherwise)
    verdict = technicals.get("risk_adjusted_signal") or "Hold"

    macro_obj = _macro_assessment(multiplier, macro_stats)
    tech_obj = prediction if prediction is not None else TechnicalAnalysis(ticker=ticker)
    decision_verdict, confidence, rationale = compute_decision(macro_obj, tech_obj, sentiment_obj)
    breakdown = confidence_breakdown(macro_obj, tech_obj, sentiment_obj, decision_verdict)
    risk_level = derive_risk_level(
        volatility=tech_obj.volatility,
        risk_multiplier=multiplier,
        max_drawdown=tech_obj.max_drawdown,
        beta=tech_obj.beta,
    )

    confidence_pct = round(confidence * 100)
    if scorecard is not None:
        confidence_pct = scorecard.confidence
        rationale = (
            f"Composite score {scorecard.raw_score:+.2f} "
            f"(momentum {scorecard.momentum_score if scorecard.momentum_score is not None else 'n/a'}, "
            f"fundamental {scorecard.fundamental_score if scorecard.fundamental_score is not None else 'n/a'}, "
            f"news {scorecard.news_score if scorecard.news_score is not None else 'n/a'}; "
            f"macro gate {scorecard.macro_gate}); {rationale}"
        )
        breakdown = [{"component": "Model confidence base", "points": 100}] + [
            {"component": f"Less: {loss.component}", "points": -loss.points}
            for loss in scorecard.confidence_losses
        ]

    # ── Step 5: LLM explanation layer (optional; never fatal; fast mode skips)
    ai: Optional[dict[str, Any]] = None
    if not fast and prediction is not None:
        try:
            ai = llm_service.explain_recommendation(
                llm_service.build_payload(
                    ticker=ticker,
                    recommendation=verdict_to_recommendation(SignalVerdict(verdict)),
                    confidence=confidence_pct,
                    risk=risk_level,
                    verdict=verdict,
                    rationale=rationale,
                    macro={"risk_multiplier": multiplier, **macro_stats},
                    technicals=technicals,
                    sentiment=sentiment_data,
                    confidence_breakdown=breakdown,
                    quant=(
                        {
                            "raw_score": scorecard.raw_score,
                            "ungated_score": scorecard.ungated_score,
                            "momentum_score": scorecard.momentum_score,
                            "fundamental_score": scorecard.fundamental_score,
                            "quality_score": scorecard.quality_score,
                            "news_score": scorecard.news_score,
                            "macro_gate": scorecard.macro_gate,
                            "conflict_index": scorecard.conflict_index,
                            "uncertainty": scorecard.uncertainty,
                            "risk_score": scorecard.risk_score,
                            "weights_used": scorecard.weights_used,
                            "regimes": scorecard.regimes,
                            # Full per-factor list (name/family/contribution) —
                            # llm_service._group_factor_impacts sums this into
                            # the momentum/quality/value/pead/news subtotals.
                            "factors": [
                                {"name": row.name, "family": row.family, "contribution": row.contribution}
                                for row in scorecard.factors
                                if row.score is not None
                            ],
                            "top_contributions": sorted(
                                (
                                    {"factor": row.name, "contribution": row.contribution}
                                    for row in scorecard.factors
                                    if row.score is not None
                                ),
                                key=lambda item: abs(item["contribution"]),
                                reverse=True,
                            )[:6],
                            "top_positive": sorted(
                                (
                                    {"factor": row.name, "contribution": row.contribution}
                                    for row in scorecard.factors
                                    if row.score is not None and row.contribution > 0
                                ),
                                key=lambda item: item["contribution"],
                                reverse=True,
                            )[:5],
                            "top_negative": sorted(
                                (
                                    {"factor": row.name, "contribution": row.contribution}
                                    for row in scorecard.factors
                                    if row.score is not None and row.contribution < 0
                                ),
                                key=lambda item: item["contribution"],
                            )[:5],
                        }
                        if scorecard is not None else None
                    ),
                )
            )
        except Exception:  # belt and braces — the service already never raises
            logger.exception("LLM layer raised unexpectedly for %s", ticker)
            ai = None

    # Inputs the engine wanted but did not get. Recorded as explicitly absent
    # rather than left out, because a factor that is missing and a factor that
    # scored neutral look identical in a decomposition otherwise.
    if not quality_inputs:
        ledger.record(
            label="Quality fundamentals", kind="fundamental",
            missing_reason="gross profitability / issuance / asset growth unavailable for this symbol",
            used_for=["quality factors"],
        )
    if not pead_inputs:
        ledger.record(
            label="Earnings surprise history", kind="fundamental",
            missing_reason="no recent reported surprise available",
            used_for=["post-earnings-drift factor"],
        )

    elapsed = round(time.time() - start, 2)
    logger.info(
        "research %s: verdict=%s confidence=%d risk=%s ai=%s mode=%s elapsed=%.2fs",
        ticker, verdict, confidence_pct, risk_level,
        (ai or {}).get("generated"), "fast" if fast else "full", elapsed,
    )

    response = {
        "ticker":  ticker,
        "macro":   {"risk_multiplier": multiplier, **macro_stats},
        "technicals": technicals,
        "sentiment":  sentiment_data,
        "verdict":    verdict,
        # Additive fields (v1.1): deterministic synthesis shared with the CLI pipeline.
        "confidence":  confidence_pct,
        "confidence_breakdown": breakdown,
        "risk_level":  risk_level,
        "rationale":   rationale,
        "quant":       scorecard.model_dump() if scorecard is not None else None,
        # v4.5 additive: deterministic technical read of the same OHLCV frame
        # the engine scored. Presentation intelligence only — never a scoring
        # input, never fatal, absent when history is too thin.
        # Multi-source blocks (v5.1). Additive and presentation-only: the
        # scoring engine is untouched by them, so a vendor outage here costs
        # a panel and never a verdict.
        "profile": profile_block,
        "filings": filings_block,
        "ratios": ratios_block,
        "ownership": ownership_block,
        "analyst": analyst_block,
        "consensus_price": consensus,
        "statements": statements,
        "news_stream": {
            "collected": news_stream["collected"],
            "unique": news_stream["unique"],
            "providers": news_stream["providers"],
            "corroborated": news_stream["corroborated"],
            "with_image": news_stream.get("with_image", 0),
            "sentiment": news_stream.get("sentiment"),
            "categories": news_categories,
        } if news_stream else None,
        "technical_intelligence": tech_intel,
        "street_intelligence": street_intel,
        "ai":          ai,
        "disclaimer":  DISCLAIMER,
        "elapsed_seconds": elapsed,
        "mode":  "fast" if fast else "full",
        # Chain of custody: every input this verdict was computed from, which
        # vendor answered, how degraded it was and what it fed. Assembled from
        # the same ProviderResults the analysis consumed, so it cannot drift
        # from the analysis it describes.
        "provenance": ledger.build(
            engine_version=(scorecard.model_version if scorecard is not None else None),
            elapsed_seconds=elapsed,
            confidence_losses=(
                [{"component": loss.component, "points": loss.points}
                 for loss in scorecard.confidence_losses]
                if scorecard is not None else []
            ),
            ai_generated=(ai or {}).get("generated"),
            ai_model=(ai or {}).get("model"),
        ),
    }

    # ── Automatic history persistence (v3.5, additive) ───────────────────────
    # Every completed run is recorded for the authenticated user without any
    # frontend action. Failures here must never fail the analysis: the whole
    # step is best-effort, logged, and skipped entirely when Supabase or Clerk
    # verification is not configured.
    response["history_id"] = None
    if clerk_user is not None and prediction is not None:
        db = database.get_client()
        if db is not None:
            try:
                response["history_id"] = AnalysisRepository(db).record(clerk_user, response)
            except Exception:  # noqa: BLE001 — persistence must never break research
                logger.exception("history persistence failed for %s", ticker)

    return response


@app.get("/api/chart/{ticker}")
def get_chart(ticker: str, period: str = "3mo"):
    """Daily close + volume series through the MarketDataProvider chain."""
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    try:
        result = providers.market_data.get_series(ticker, period)
        if not result.ok or not result.data.bars:
            return {"ticker": ticker, "prices": [], "error": "No data"}

        prices = [
            {
                "date": bar.date,
                "close": round(bar.close, 2),
                "volume": bar.volume,
            }
            for bar in result.data.bars
        ]
        logger.info(
            "chart %s %s: %d bars via %s%s",
            ticker, period, len(prices), result.source, " (stale)" if result.stale else "",
        )
        return {"ticker": ticker, "prices": prices}
    except Exception:
        logger.exception("Chart fetch failed for %s period=%s", ticker, period)
        return {"ticker": ticker, "prices": [], "error": "Price history unavailable"}


@app.get("/api/knowledge/{ticker}")
def knowledge(ticker: str):
    """Company ecosystem: merged knowledge graph, timeline and SEC-grounded
    findings. Additive and independent of /api/research — a failure here
    never affects analysis."""
    from src.services import company_intelligence

    symbol = ticker.upper().strip()
    if not symbol or len(symbol) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    return company_intelligence.build(symbol)


@app.get("/api/research/providers/health")
def research_provider_health():
    """Per-provider research status: configured, available, capabilities.
    Names and booleans only — never key material."""
    from src.services.research import health as research_health

    return {"providers": research_health(), "order": os.getenv("RESEARCH_PROVIDER_ORDER", "default")}


@app.get("/api/graph/expand")
def graph_expand(node: str = Query(..., max_length=120), label: str = Query(default="", max_length=120)):
    """Expand any knowledge-graph node into its neighbours — the traversal
    behind the Knowledge Graph Explorer. Every node type is a valid entry
    point, so exploration is continuous."""
    from src.services import graph_service

    return graph_service.expand(node, label)


@app.get("/api/graph/workspace")
def graph_workspace(
    symbols: str = Query(..., max_length=60, description="Comma-separated tickers"),
    hops: int = Query(default=2, ge=0, le=3),
    node_types: str = Query(default=""),
    edge_types: str = Query(default=""),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    before: str = Query(default=""),
):
    """The Knowledge Graph Workspace payload: a bounded, filtered working
    graph over one or more companies, with analytics and (for multi-select)
    shared neighbours. `before` reconstructs the graph as of a date."""
    from src.services import graph_service

    return graph_service.workspace(
        symbols.split(","),
        hops=hops,
        node_types={t.strip() for t in node_types.split(",") if t.strip()} or None,
        edge_types={t.strip() for t in edge_types.split(",") if t.strip()} or None,
        min_confidence=min_confidence,
        before=before or None,
    )


@app.get("/api/graph/path")
def graph_path(
    symbols: str = Query(..., max_length=60),
    source: str = Query(..., max_length=120),
    target: str = Query(..., max_length=120),
):
    """Shortest deterministic path between two entities, edge by edge."""
    from src.services import graph_service

    return {"path": graph_service.path_between(symbols.split(","), source, target)}


@app.get("/api/factors", tags=["research"])
def get_factor_lab(
    universe: str = Query("mega30", description="named universe to evaluate"),
    years: float = Query(2.5, ge=0.5, le=10.0),
    horizon: int = Query(21, ge=5, le=126, description="forward-return horizon in trading days"),
):
    """Cross-sectional evidence for every factor in the scoring engine.

    Answers the question single-ticker views structurally cannot: does this
    factor rank names correctly? Rank IC per observation date, Newey-West
    corrected for the overlap that inflates naive t-statistics, plus the
    quantile spread and the full ranked cross-section on the latest date.

    Slow and honest on a cold cache (a full point-in-time panel build);
    milliseconds afterwards. Caveats ship inside the payload rather than in
    documentation nobody reads.
    """
    return factor_lab_service.run(universe, years, horizon)


@app.get("/api/factors/universes", tags=["research"])
def get_factor_universes():
    return {"universes": factor_lab_service.available_universes()}


@app.get("/api/providers/capabilities", tags=["ops"])
def provider_capabilities():
    """What every provider can do, and which are live right now.

    Introspection-driven (see `fabric.capability_matrix`), so a newly added
    vendor appears here without anyone updating a list. Answers the question
    the orchestrator asks on every request — "who can contribute to this" —
    and the one a deploy engineer asks — "is the key actually configured".

    Reports `configured` and `healthy` separately because they fail for
    different reasons: a missing key is a deploy problem, a tripped circuit is
    an outage. Only the *name* of the environment variable is exposed, never
    its value.
    """
    matrix = fabric.capability_matrix({
        "market": providers.market_data.vendors,
        "fundamentals": providers.fundamentals.vendors,
        "news": providers.news.vendors,
        "macro": providers.macro.vendors,
        "visual": visual_intelligence.IMAGE_VENDORS,
    })
    matrix["visual"] = visual_intelligence.diagnostics()
    return matrix


@app.get("/api/company/{ticker}/media", tags=["research"])
def company_media(ticker: str, sector: str = "", industry: str = "", name: str = ""):
    """Brand mark and editorial imagery for one company.

    A separate endpoint from `/api/research` on purpose: imagery must never
    sit on the critical path of a price. The research payload renders first,
    and the page asks for this afterwards — a slow stock-photo API can then
    only delay a photograph.

    Identity and context are returned in separate fields and never merged: a
    logo is a factual claim about a company, a stock photograph is a claim
    about an industry.
    """
    symbol = ticker.upper().strip()
    if not symbol or len(symbol) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    domain = ""
    resolved_name, resolved_sector, resolved_industry = name, sector, industry
    try:
        profile = providers.fundamentals.get_company(symbol)
        if profile.ok and profile.data:
            domain = profile.data.domain or ""
            resolved_name = resolved_name or profile.data.name
            resolved_sector = resolved_sector or profile.data.sector
            resolved_industry = resolved_industry or profile.data.industry
    except Exception:  # noqa: BLE001 — media is never fatal
        logger.exception("profile lookup failed for %s", symbol)

    return {
        "ticker": symbol,
        "identity": visual_intelligence.identity(symbol, domain, resolved_name),
        "context": visual_intelligence.hero_for_company(
            symbol, name=resolved_name, sector=resolved_sector, industry=resolved_industry,
        ),
        "domain": domain,
    }


@app.get("/api/metrics", tags=["ops"])
def get_metrics(reset: bool = Query(False, description="clear counters after reading")):
    """Latency percentiles and counters for every instrumented seam.

    Percentiles rather than averages: the distribution here is bimodal — a
    cache hit at 0.4 ms and a vendor exhausting its retries at 18 s average
    to a number that never happened. p95/p99 are what an operator can act on.

    `?reset=true` starts a fresh window, so a vendor that misbehaved an hour
    ago stops colouring the current picture.
    """
    snapshot = observability.registry.snapshot()
    if reset:
        observability.registry.reset()
    return snapshot


@app.get("/api/providers/health", tags=["ops"])
def get_providers_health():
    """Vendor health: success %, latency, cooldowns, cache and dedupe stats."""
    return providers.providers_health()


@app.get("/api/backtest/{ticker}")
def get_backtest(ticker: str):
    """Walk-forward validation of the scoring engine's momentum core (1h cache)."""
    from src.services import backtest_service

    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")
    return backtest_service.run_backtest(ticker)


@app.get("/api/screen")
def get_screen(q: str = Query(..., min_length=1, max_length=120)):
    """Natural-language ticker screening: lookup or thematic web-grounded search."""
    from src.services import screen_service

    return screen_service.screen(q)


@app.get("/api/quotes")
def get_quotes(symbols: str = Query(..., description="Comma-separated tickers, max 25")):
    """
    Batch quotes for watchlists: price, 1-day and 1-week change per symbol.
    Served from the MarketDataProvider series cache; per-symbol failures
    return an error entry rather than failing the batch.
    """
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()][:25]
    if not requested:
        raise HTTPException(status_code=400, detail="No symbols supplied")

    out: dict[str, Any] = {}
    for symbol in requested:
        if len(symbol) > 10:
            out[symbol] = {"error": "invalid symbol"}
            continue
        try:
            result = providers.market_data.get_series(symbol, "3mo")
            if not result.ok or len(result.data.bars) < 6:
                out[symbol] = {"error": "no data"}
                continue
            bars = result.data.bars
            closes = [bar.close for bar in bars]
            out[symbol] = {
                "price": round(closes[-1], 2),
                "change_1d": round((closes[-1] / closes[-2] - 1) * 100, 2) if closes[-2] else None,
                "change_1w": round((closes[-1] / closes[-6] - 1) * 100, 2) if len(closes) >= 6 and closes[-6] else None,
                "source": result.source,
                "stale": result.stale,
            }
        except Exception:  # noqa: BLE001 — one bad symbol never fails the batch
            logger.exception("quote failed for %s", symbol)
            out[symbol] = {"error": "unavailable"}
    return {"quotes": out, "count": len(out)}


@app.get("/api/dashboard")
def get_dashboard():
    """Market intelligence dashboard: macro board, breadth, sectors, events."""
    from src.services import dashboard_service

    return dashboard_service.get_dashboard()


@app.get("/api/memo/{ticker}")
def get_memo(ticker: str):
    """
    Full analyst memo: runs the research pipeline, collects + ranks cited
    evidence, and generates a citation-audited investment memo. Heavier than
    /api/research (evidence search + larger LLM call); cached 15 minutes.
    """
    from src.services import memo_service

    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    research = research_ticker(ticker, fast=False)
    memo = memo_service.generate_memo(research)
    return {"memo": memo, "research": research}
