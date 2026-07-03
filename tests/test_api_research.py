"""
Endpoint contract tests for /api/research/{ticker}.

All upstreams are mocked; asserts that the v1.0 response contract is intact
and the v1.1 additive fields behave — including the LLM fallback path when
GROQ_API_KEY is unset.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.models import AggregateSentiment, SignalVerdict, TechnicalAnalysis
from src.providers.schemas import MacroSnapshot, ProviderResult


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    api_module._macro_cache.clear()  # module-level SRM cache must not leak between tests

    technicals = TechnicalAnalysis(
        ticker="NVDA",
        current_price=193.06,
        return_5d=0.0028,
        return_21d=-0.10,
        volatility=0.3988,
        sharpe_ratio=1.0712,
        sortino_ratio=0.1145,
        rsi_14=39.1,
        max_drawdown=-0.1823,
        momentum=-21.44,
        raw_signal=SignalVerdict.HOLD,
        risk_adjusted_signal=SignalVerdict.HOLD,
        company_name="NVIDIA Corporation",
        sector="TECHNOLOGY",
    )
    macro_stats = {
        "yield_spread": 0.31,
        "inflation_rate": "4.47%",
        "fed_funds_rate": "3.63%",
        "yield_curve_inverted": False,
        "status": "ELEVATED",
        "recession_warning": False,
    }

    # Macro flows through the MacroProvider now: 4.47% inflation > 4% adds
    # +0.2 → SRM 1.2 via the real calculate_multiplier (same numbers as the
    # old (1.2, stats) mock, but exercising the actual SRM math).
    macro_result = ProviderResult[MacroSnapshot](
        data=MacroSnapshot(yield_spread=0.31, inflation_rate=4.47, fed_funds_rate=3.63),
        source="fred", confidence=0.85,
    )
    del macro_stats  # shape now produced by the endpoint itself

    with patch.object(
        api_module.providers.macro, "get_macro", return_value=macro_result
    ), patch.object(
        api_module.providers.market_data, "get_series",
        return_value=ProviderResult(data=None, error="mocked out"),
    ), patch.object(
        api_module.providers.fundamentals, "get_company",
        return_value=ProviderResult(data=None, error="mocked out"),
    ), patch.object(
        api_module.providers.fundamentals, "get_fundamentals",
        return_value=ProviderResult(data=None, error="mocked out"),
    ), patch.object(
        api_module.providers.news, "get_news",
        return_value=ProviderResult(data=None, error="mocked out"),
    ), patch.object(
        api_module.RiskAwarePredictionAgent, "predict", return_value=technicals
    ), patch.object(
        api_module.sentiment_analyzer, "analyze_ticker", return_value=AggregateSentiment()
    ):
        yield TestClient(api_module.app)


REQUIRED_V1_KEYS = ("ticker", "macro", "technicals", "sentiment", "verdict", "elapsed_seconds", "mode")


def test_research_keeps_v1_contract_and_adds_v11_fields(client):
    response = client.get("/api/research/NVDA")
    assert response.status_code == 200
    body = response.json()

    for key in REQUIRED_V1_KEYS:
        assert key in body, f"missing v1 key {key}"

    # v1.1 additive fields
    assert isinstance(body["confidence"], int) and 0 <= body["confidence"] <= 100
    assert body["risk_level"] in ("LOW", "MEDIUM", "HIGH")
    assert isinstance(body["rationale"], str) and body["rationale"]
    assert "disclaimer" in body

    # Verdict semantics: SRM 1.2 (>= dampen threshold) pulls raw Hold one
    # step down to Sell — same arithmetic the sequential v1 code produced.
    assert body["technicals"]["raw_signal"] == "Hold"
    assert body["verdict"] == "Sell"
    assert body["technicals"]["risk_adjusted_signal"] == "Sell"


def test_research_llm_fallback_when_unconfigured(client):
    body = client.get("/api/research/NVDA").json()
    ai = body["ai"]
    assert ai is not None
    assert ai["generated"] is False
    assert ai["recommendation"] == "SELL"  # maps the dampened Sell verdict
    assert ai["risk"] == body["risk_level"]
    assert ai["confidence"] == body["confidence"]
    assert isinstance(ai["executive_summary"], str) and ai["executive_summary"]
    assert isinstance(ai["confidence_reason"], str) and ai["confidence_reason"]

    # Confidence breakdown is deterministic and sums to the confidence value
    breakdown = body["confidence_breakdown"]
    assert sum(item["points"] for item in breakdown) == body["confidence"]


def test_fast_mode_skips_sentiment_and_llm(client):
    body = client.get("/api/research/NVDA", params={"fast": "true"}).json()
    assert body["mode"] == "fast"
    assert body["sentiment"] is None
    assert body["ai"] is None


def test_invalid_ticker_rejected(client):
    assert client.get("/api/research/WAYTOOLONGTICKER").status_code == 400
