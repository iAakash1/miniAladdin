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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
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
    version="1.1.0",
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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request, call_next):
    """One structured line per request: method, path, status, duration."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled error %s %s", request.method, request.url.path)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %d in %.0fms",
        request.method, request.url.path, response.status_code, duration_ms,
    )
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
    """SRM + stats with demo fallback and a short TTL cache. Never raises."""
    now = time.time()
    with _macro_lock:
        entry = _macro_cache.get("srm")
        if entry and entry[0] > now:
            return entry[1]
    try:
        result = risk_engine.get_systemic_risk_multiplier()
        # Only healthy responses are cached; failures retry on the next call.
        if str(result[1].get("status", "")) != MacroStatus.DATA_ERROR.value:
            with _macro_lock:
                _macro_cache["srm"] = (now + MACRO_CACHE_TTL_SECONDS, result)
        return result
    except Exception:
        logger.exception("Macro fetch failed — serving DEMO_MODE fallback")
        return DEMO_MACRO_MULTIPLIER, _demo_macro_stats()


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
    return {
        "status":  "ok",
        "service": "OmniSignal API",
        "version": "1.1.0",
        "data_sources": {
            "fred":          bool(os.getenv("FRED_API_KEY")),
            "alpha_vantage": av_client.available,
            "news_api":      NewsAPIClient().available,
            "llm":           bool(os.getenv("GROQ_API_KEY")),
            "yfinance":      True,
            "yahoo_scraper": True,
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

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="research") as pool:
        macro_future = pool.submit(_fetch_macro_safe)
        tech_future = pool.submit(
            lambda: RiskAwarePredictionAgent(
                ticker, period="3mo", av_client=av_client
            ).predict(risk_multiplier=1.0)
        )
        multiplier, macro_stats = macro_future.result()
        try:
            prediction = tech_future.result()
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

    # ── Step 3: Sentiment (after technicals — reuses the resolved company name)
    sentiment_data: Optional[dict[str, Any]] = None
    sentiment_obj = AggregateSentiment()
    if not fast:
        company_name = technicals.get("company_name", "") or ""
        try:
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

    # ── Step 4: Deterministic decision synthesis (shared with the CLI pipeline)
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

    return {
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
        "ai":          ai,
        "disclaimer":  DISCLAIMER,
        "elapsed_seconds": elapsed,
        "mode":  "fast" if fast else "full",
    }


@app.get("/api/chart/{ticker}")
def get_chart(ticker: str, period: str = "3mo"):
    """Daily close + volume series for the terminal chart."""
    import yfinance as yf

    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker")

    try:
        hist = yf.Ticker(ticker).history(period=period)
        if hist.empty:
            return {"ticker": ticker, "prices": [], "error": "No data"}

        prices = []
        for idx, row in hist.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            prices.append({
                "date":   date_str,
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else None,
            })

        return {"ticker": ticker, "prices": prices}
    except Exception:
        logger.exception("Chart fetch failed for %s period=%s", ticker, period)
        return {"ticker": ticker, "prices": [], "error": "Price history unavailable"}
