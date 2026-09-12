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


# ── test isolation ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_threaded_prefetch(request, monkeypatch):
    """Stop the research handler's prefetch from fanning out in background threads.

    `research_prefetch.warm` runs its warmers through `map_concurrent`, which
    abandons a worker when the future times out. Python cannot kill a thread,
    so the outbound call still happens — just later, and later can be inside a
    *different* test's `patch` window.

    That is not hypothetical: it is how a broker test asserting that no
    request was made saw seven calls to sec.gov.

    (The separate `test_result_is_cached` failure looked like this one but was
    not — instrumenting the patch window named a `factor-lab-mega30` thread,
    not a prefetch worker. That one is handled by the panel-build guard
    below. Both are the same class of defect and neither fix substitutes for
    the other.)

    Applied suite-wide because the leak is a property of the suite rather than
    of any one file, and no test's assertions depend on a warm cache: a cold
    cache is slower, never different. `test_research_prefetch.py` is exempt —
    it is the module that tests this function.
    """
    if request.node.module.__name__.endswith("test_research_prefetch"):
        yield
        return

    from src.services import research_prefetch

    monkeypatch.setattr(research_prefetch, "warm", lambda ticker: {})
    yield


@pytest.fixture(autouse=True)
def _no_background_panel_build(request, monkeypatch):
    """Stop factor-lab build workers from doing real work during tests.

    `/api/factors` starts a panel build on a daemon thread and returns
    immediately — deliberately, and there is a test for exactly that. The
    thread then keeps loading prices long after the test that started it has
    finished, and calls `providers.market_data.get_series` from inside
    whichever `patch` a later test has installed. That is the second half of
    the `test_result_is_cached` failure: the extra two calls were this builder
    fetching its benchmark and its first symbol.

    The job registry, the payload and the endpoint's non-blocking behaviour
    are untouched; only the body of the worker is stubbed, so a test asserting
    "returns promptly with status building" still asserts it. The factor-lab
    modules that test the job machinery itself are exempt.
    """
    module = request.node.module.__name__
    if module.endswith("test_factor_lab_termination") or module.endswith("test_factor_lab"):
        yield
        return

    from src.services import factor_lab_service

    monkeypatch.setattr(factor_lab_service, "_run_job", lambda *a, **k: None)
    yield
    # Any worker that did start is joined before the next test installs its
    # own patches.
    factor_lab_service.reset_for_tests(timeout=5.0)
