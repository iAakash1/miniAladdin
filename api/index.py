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
from src import providers
from src.providers.schemas import PriceSeries
from src.scoring import score_ticker
from src.scoring import technical_intelligence
from src.services import analyst_store, database, fundamentals_data, news_scoring, street_intelligence
from src.services.backtest_service import peek_cached as peek_backtest
from src.services.clerk_auth import optional_clerk_user
from src.services.database.repositories import AnalysisRepository

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
    logger.info(
        "rid=%s %s %s%s -> %d in %.0fms",
        request_id, request.method, request.url.path,
        f" user={user}" if user else "",
        response.status_code, duration_ms,
    )
    response.headers["X-Request-Id"] = request_id
    return response

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
        return (prediction_result, full_frame, series_result.confidence,
                _days_to_earnings(), quality_inputs, pead_inputs)

    scoring_frame = None
    series_confidence = 1.0
    days_to_earnings: Optional[int] = None
    quality_inputs: dict[str, Any] = {}
    pead_inputs: dict[str, Any] = {}

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="research") as pool:
        macro_future = pool.submit(_fetch_macro_safe)
        tech_future = pool.submit(_run_technicals)
        multiplier, macro_stats = macro_future.result()
        try:
            (prediction, scoring_frame, series_confidence,
             days_to_earnings, quality_inputs, pead_inputs) = tech_future.result()
        except Exception:
            logger.exception("Technical analysis failed for %s", ticker)
            tech_error = "Technical analysis failed — check that the ticker symbol is valid"

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
    if prediction is not None and technicals.get("company_name") is None:
        try:
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

    # ── Step 3: Sentiment (after technicals — reuses the resolved company name)
    sentiment_data: Optional[dict[str, Any]] = None
    sentiment_obj = AggregateSentiment()
    if not fast:
        company_name = technicals.get("company_name", "") or ""
        try:
            # Headlines through the NewsProvider chain (NewsAPI → GNews →
            # Yahoo RSS → Tavily → stale cache); the keyword scorer is unchanged.
            news_result = providers.news.get_news(ticker, company_name, limit=12)
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
            if street_result.ok:
                street_intel = street_intelligence.build(street_result.data)
        except Exception:  # noqa: BLE001 — additive block, never fatal
            logger.exception("street intelligence failed for %s", ticker)

    scorecard = None
    if prediction is not None and scoring_frame is not None:
        try:
            spy_result = providers.market_data.get_series("SPY", "1y")
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
        "technical_intelligence": tech_intel,
        "street_intelligence": street_intel,
        "ai":          ai,
        "disclaimer":  DISCLAIMER,
        "elapsed_seconds": elapsed,
        "mode":  "fast" if fast else "full",
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


@app.get("/api/providers/health")
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
