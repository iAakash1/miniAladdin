"""
OmniSignal API — FastAPI Serverless Backend for Vercel
Exposes the risk engine, prediction agent, and sentiment analyzer as REST endpoints.
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

# Add project root to path for src/ imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models import MacroStatus, SignalVerdict
from src.risk_analysis import OmniSignalRiskEngine
from src.prediction_agent import RiskAwarePredictionAgent
from src.sentiment_edge import SentimentAnalyzer

# ── App Setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniSignal API",
    description="Agentic Multi-Factor Risk & Prediction Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared Instances ─────────────────────────────────────────────────────────

risk_engine = OmniSignalRiskEngine()
sentiment_analyzer = SentimentAnalyzer(max_headlines=5)


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "OmniSignal API",
        "version": "1.0.0",
    }


@app.get("/api/macro")
async def get_macro():
    """
    Fast endpoint (~2s): returns Systemic Risk Multiplier + macro indicators.
    Designed to stay well within Vercel's 10s timeout.
    """
    start = time.time()
    try:
        multiplier, stats = risk_engine.get_systemic_risk_multiplier()
        elapsed = round(time.time() - start, 2)
        return {
            "risk_multiplier": multiplier,
            "stats": stats,
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        return JSONResponse(
            status_code=200,
            content={
                "risk_multiplier": 1.0,
                "stats": {"status": "DATA_ERROR", "error": str(e)},
                "elapsed_seconds": round(time.time() - start, 2),
            },
        )


@app.get("/api/research/{ticker}")
async def research_ticker(
    ticker: str,
    fast: bool = Query(False, description="Fast mode: skip sentiment for speed"),
):
    """
    Full OmniSignal research pipeline for a given ticker.

    - Fetches macro risk (SRM)
    - Runs technical analysis with dampening
    - Analyzes news sentiment (unless fast=true)
    - Returns unified research payload

    Query params:
        fast (bool): If true, skips sentiment analysis for faster response (~4s vs ~7s)
    """
    start = time.time()
    ticker = ticker.upper().strip()

    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker symbol")

    # Step 1: Macro risk
    try:
        multiplier, macro_stats = risk_engine.get_systemic_risk_multiplier()
    except Exception:
        multiplier = 1.0
        macro_stats = {"status": "DATA_ERROR"}

    # Step 2: Technical analysis
    try:
        agent = RiskAwarePredictionAgent(ticker, period="3mo")
        prediction = agent.predict(risk_multiplier=multiplier)
        technicals = {
            "ticker": prediction.ticker,
            "current_price": prediction.current_price,
            "return_5d": round(prediction.return_5d, 4) if prediction.return_5d else None,
            "return_21d": round(prediction.return_21d, 4) if prediction.return_21d else None,
            "volatility": round(prediction.volatility, 4) if prediction.volatility else None,
            "sharpe_ratio": prediction.sharpe_ratio,
            "sortino_ratio": prediction.sortino_ratio,
            "rsi_14": prediction.rsi_14,
            "max_drawdown": round(prediction.max_drawdown, 4) if prediction.max_drawdown else None,
            "momentum": prediction.momentum,
            "raw_signal": prediction.raw_signal.value if prediction.raw_signal else None,
            "risk_adjusted_signal": prediction.risk_adjusted_signal.value if prediction.risk_adjusted_signal else None,
        }
    except Exception as e:
        technicals = {"error": str(e)}

    # Step 3: Sentiment (skip in fast mode)
    sentiment_data = None
    if not fast:
        try:
            sentiment = sentiment_analyzer.analyze_ticker(ticker, browser_verify=False)
            sentiment_data = {
                "headline_count": sentiment.headline_count,
                "average_score": sentiment.average_score,
                "dominant_label": sentiment.dominant_label.value,
                "headlines": [
                    {
                        "title": h.headline,
                        "score": h.score,
                        "label": h.label.value,
                        "source": h.source,
                    }
                    for h in sentiment.headlines
                ],
            }
        except Exception as e:
            sentiment_data = {"error": str(e), "headline_count": 0}

    # Step 4: Compute verdict
    raw_signal = technicals.get("risk_adjusted_signal", "Hold")
    verdict = raw_signal if isinstance(raw_signal, str) else "Hold"

    elapsed = round(time.time() - start, 2)

    return {
        "ticker": ticker,
        "macro": {
            "risk_multiplier": multiplier,
            **macro_stats,
        },
        "technicals": technicals,
        "sentiment": sentiment_data,
        "verdict": verdict,
        "elapsed_seconds": elapsed,
        "mode": "fast" if fast else "full",
    }
