"""
OmniSignal API — FastAPI Backend
Multi-factor risk intelligence: FRED macro + yfinance technicals + Alpha Vantage fundamentals + NewsAPI sentiment.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models import MacroStatus, SignalVerdict
from src.risk_analysis import OmniSignalRiskEngine
from src.prediction_agent import RiskAwarePredictionAgent
from src.sentiment_edge import SentimentAnalyzer
from src.alpha_vantage import AlphaVantageClient
from src.news_api import NewsAPIClient

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniSignal API",
    description="Agentic Multi-Factor Risk & Prediction Engine",
    version="1.0.0",
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

# ── Shared instances ──────────────────────────────────────────────────────────

risk_engine        = OmniSignalRiskEngine()
sentiment_analyzer = SentimentAnalyzer(max_headlines=12)
av_client          = AlphaVantageClient()


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check — reports which API keys are configured."""
    return {
        "status":  "ok",
        "service": "OmniSignal API",
        "version": "1.0.0",
        "data_sources": {
            "fred":         bool(os.getenv("FRED_API_KEY")),
            "alpha_vantage": av_client.available,
            "news_api":     NewsAPIClient().available,
            "yfinance":     True,     # always available
            "yahoo_scraper": True,    # always available
        },
        "environment": "production" if os.getenv("VERCEL") else "development",
    }


@app.get("/api/macro")
async def get_macro():
    """Systemic Risk Multiplier + FRED macro indicators."""
    start = time.time()
    try:
        multiplier, stats = risk_engine.get_systemic_risk_multiplier()
        return {
            "risk_multiplier": multiplier,
            "stats":           stats,
            "elapsed_seconds": round(time.time() - start, 2),
        }
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "risk_multiplier": 1.15,
            "stats": {
                "status":               "DEMO_MODE",
                "error":                "FRED API unavailable - using demo data",
                "yield_curve_inverted": False,
                "inflation_rate":       3.2,
                "fed_funds_rate":       5.25,
                "note":                 "Get a free FRED API key at fred.stlouisfed.org",
            },
            "elapsed_seconds": round(time.time() - start, 2),
        })


@app.get("/api/research/{ticker}")
async def research_ticker(
    ticker: str,
    fast: bool = Query(False, description="Skip sentiment for speed"),
):
    """
    Full OmniSignal research pipeline:
      1. FRED macro risk (SRM)
      2. yfinance technical analysis
      3. Alpha Vantage fundamentals + MACD  (if key configured)
      4. NewsAPI / Yahoo sentiment           (unless fast=true)
    """
    start  = time.time()
    ticker = ticker.upper().strip()

    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    # ── Step 1: Macro ────────────────────────────────────────────────────────
    try:
        multiplier, macro_stats = risk_engine.get_systemic_risk_multiplier()
    except Exception:
        multiplier  = 1.15
        macro_stats = {
            "status": "DEMO_MODE",
            "error":  "FRED API unavailable",
            "note":   "Using demo risk multiplier",
        }

    # ── Step 2 & 3: Technical analysis + Alpha Vantage ───────────────────────
    technicals = {}
    try:
        agent      = RiskAwarePredictionAgent(ticker, period="3mo", av_client=av_client)
        prediction = agent.predict(risk_multiplier=multiplier)

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
    except Exception as e:
        technicals = {"error": str(e), "note": "Technical analysis failed — check ticker"}

    # ── Step 4: Sentiment ────────────────────────────────────────────────────
    sentiment_data = None
    if not fast:
        # Pass company name from fundamentals for better NewsAPI query
        company_name = technicals.get("company_name", "") or ""
        try:
            sentiment = sentiment_analyzer.analyze_ticker(ticker, company_name=company_name)
            sentiment_data = {
                "headline_count": sentiment.headline_count,
                "average_score":  sentiment.average_score,
                "dominant_label": sentiment.dominant_label.value,
                "headlines": [
                    {
                        "title":       h.headline,
                        "score":       h.score,
                        "label":       h.label.value,
                        "source":      h.source,
                        "url":         h.url,
                        "published_at": h.published_at,
                    }
                    for h in sentiment.headlines
                ],
            }
        except Exception as e:
            sentiment_data = {
                "error":          str(e),
                "headline_count": 0,
                "note":           "Sentiment analysis failed",
            }

    # ── Verdict ──────────────────────────────────────────────────────────────
    verdict = technicals.get("risk_adjusted_signal") or "Hold"

    return {
        "ticker":  ticker,
        "macro":   {"risk_multiplier": multiplier, **macro_stats},
        "technicals": technicals,
        "sentiment":  sentiment_data,
        "verdict":    verdict,
        "elapsed_seconds": round(time.time() - start, 2),
        "mode":  "fast" if fast else "full",
    }


@app.get("/api/chart/{ticker}")
async def get_chart(ticker: str, period: str = "3mo"):
    """3-month daily OHLCV for the sparkline chart."""
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
    except Exception as e:
        return {"ticker": ticker, "prices": [], "error": str(e)}
