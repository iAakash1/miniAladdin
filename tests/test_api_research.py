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


# ── Factor Lab route contract ────────────────────────────────────────────────
#
# The Factor Lab returned 404 in the browser. The cause was not in this
# repository's code at all: `/api/factors` is proxied to whatever
# BACKEND_ORIGIN names, and the deployed backend was running a build that
# predates the endpoint. These pin the contract so a genuine regression —
# the route disappearing or being renamed — is caught here rather than in a
# browser two deploys later.

def test_factor_lab_routes_are_registered():
    """The 404 seen in the browser must never originate from this app."""
    from api.index import app

    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/factors" in paths
    assert "/api/factors/universes" in paths


def test_factor_lab_universes_endpoint_answers():
    from fastapi.testclient import TestClient
    from api.index import app

    response = TestClient(app).get("/api/factors/universes")
    assert response.status_code == 200
    names = {row["name"] for row in response.json()["universes"]}
    assert {"dev", "mega30"} <= names


def test_factor_lab_rejects_an_unknown_universe_without_500():
    """A bad universe is a 200 carrying an explanation, not a crash."""
    from fastapi.testclient import TestClient
    from api.index import app
    from src.services import factor_lab_service

    factor_lab_service.reset_for_tests()
    response = TestClient(app).get("/api/factors", params={"universe": "not-a-universe"})
    assert response.status_code == 200
    payload = response.json()
    assert "error" in payload
    assert "universes" in payload


def test_factor_lab_validates_query_bounds():
    """Out-of-range params are refused by FastAPI, not passed to the panel."""
    from fastapi.testclient import TestClient
    from api.index import app

    client = TestClient(app)
    assert client.get("/api/factors", params={"years": 99}).status_code == 422
    assert client.get("/api/factors", params={"horizon": 1}).status_code == 422


def test_factor_lab_never_blocks_the_request():
    """A cold build must not hold the HTTP request open.

    Blocking for 30-60s is not a slow endpoint, it is a broken one: the dev
    proxy gives up first and a serverless function times out. Observed
    directly before this changed — the backend logged `200 in 44413ms` while
    the browser reported a network failure.
    """
    import time
    from fastapi.testclient import TestClient
    from api.index import app
    from src.services import factor_lab_service

    factor_lab_service.reset_for_tests()
    started = time.perf_counter()
    response = TestClient(app).get("/api/factors", params={"universe": "mega30"})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 5.0, f"endpoint blocked for {elapsed:.1f}s"
    payload = response.json()
    assert payload["status"] in {"building", "ready"}
    if payload["status"] == "building":
        assert payload["stage"] in factor_lab_service.STAGES
        assert payload["stage_index"] == 0


def test_factor_lab_reports_stages_a_client_can_render():
    from src.services import factor_lab_service

    assert factor_lab_service.STAGES[0] == "prices"
    assert len(factor_lab_service.STAGES) == 5
