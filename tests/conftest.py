"""
Shared test fixtures for OmniSignal test suite.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import (
    AggregateSentiment,
    MacroIndicators,
    MacroStatus,
    RiskAssessment,
    SentimentLabel,
    SentimentResult,
    SignalVerdict,
    TechnicalAnalysis,
)


# ── Macro Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def normal_indicators() -> MacroIndicators:
    """Macro indicators with normal (stable) conditions."""
    return MacroIndicators(
        yield_spread=1.5,
        inflation_rate=2.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def inverted_yield_indicators() -> MacroIndicators:
    """Macro indicators with inverted yield curve."""
    return MacroIndicators(
        yield_spread=-0.5,
        inflation_rate=2.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def high_inflation_indicators() -> MacroIndicators:
    """Macro indicators with high inflation (> 4%)."""
    return MacroIndicators(
        yield_spread=1.0,
        inflation_rate=5.5,
        fed_funds_rate=3.0,
    )


@pytest.fixture
def crisis_indicators() -> MacroIndicators:
    """Macro indicators with inverted yield + high inflation + high rates."""
    return MacroIndicators(
        yield_spread=-0.8,
        inflation_rate=6.0,
        fed_funds_rate=5.5,
    )


@pytest.fixture
def stable_risk() -> RiskAssessment:
    """A stable risk assessment with multiplier 1.0."""
    return RiskAssessment(
        risk_multiplier=1.0,
        yield_curve_inverted=False,
        status=MacroStatus.STABLE,
    )


@pytest.fixture
def critical_risk() -> RiskAssessment:
    """A critical risk assessment with high multiplier."""
    return RiskAssessment(
        risk_multiplier=1.5,
        yield_curve_inverted=True,
        status=MacroStatus.CRITICAL,
        recession_warning=True,
    )


# ── Sentiment Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def bullish_headlines() -> list[dict]:
    """Headlines with bullish sentiment."""
    return [
        {"title": "NVDA surges to record high on AI boom", "source": "Yahoo Finance"},
        {"title": "Strong earnings beat expectations, stock rallies", "source": "Reuters"},
        {"title": "Analyst upgrades to Strong Buy with growth momentum", "source": "Bloomberg"},
    ]


@pytest.fixture
def bearish_headlines() -> list[dict]:
    """Headlines with bearish sentiment."""
    return [
        {"title": "Stock crashes on fraud investigation", "source": "Yahoo Finance"},
        {"title": "Regulatory concerns and lawsuit risks decline shares", "source": "Reuters"},
        {"title": "Weak earnings miss, warns of layoffs", "source": "Bloomberg"},
    ]


@pytest.fixture
def neutral_headlines() -> list[dict]:
    """Headlines with neutral sentiment."""
    return [
        {"title": "Company announces new product line", "source": "Yahoo Finance"},
        {"title": "CEO speaks at industry conference", "source": "Reuters"},
    ]


# ── Price Data Fixture ───────────────────────────────────────────────────────

@pytest.fixture
def mock_price_data() -> pd.DataFrame:
    """Mock price data for technical analysis (60 days)."""
    dates = pd.date_range(end=datetime.now(), periods=60, freq="B")
    base_price = 100.0
    closes = [base_price + i * 0.5 + (i % 5 - 2) for i in range(60)]
    volumes = [1000000 + i * 10000 for i in range(60)]
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in closes],
            "High": [c + 1.0 for c in closes],
            "Low": [c - 1.0 for c in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=dates,
    )
