"""The What-If endpoints: contract, refusals, and the no-mutation guarantee.

Driven against a synthetic context rather than live providers — what these
tests are about is the route's contract and the isolation promise, neither of
which needs a network.
"""

import json
import math
import re

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.agents.orchestrator import attach_scorecard
from src.agents.schemas import EvidenceContext

NON_FINITE = re.compile(r'(?<![A-Za-z0-9_"])(-?Infinity|NaN)(?![A-Za-z0-9_"])')


@pytest.fixture
def client():
    return TestClient(api.app)


def _frame(drift: float = 0.004, seed: int = 3, n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.cumprod(1.0 + rng.normal(drift, 0.011, n))
    return pd.DataFrame(
        {"Open": closes, "High": closes * 1.004, "Low": closes * 0.996,
         "Close": closes, "Volume": np.full(n, 1_000_000.0)},
        index=pd.bdate_range("2024-01-01", periods=n),
    )


@pytest.fixture
def stub_context(monkeypatch):
    """One deterministic context, and a record of how often it was built."""
    calls: list[str] = []

    def build(symbol, **_):
        calls.append(symbol)
        return EvidenceContext(symbol=symbol, price_frame=_frame(), macro_multiplier=1.0)

    monkeypatch.setattr("src.agents.orchestrator.build_context", build)
    return calls


def test_scenarios_are_listed_and_labelled_as_simulation(client):
    response = client.get("/api/what-if/scenarios")
    assert response.status_code == 200
    body = response.json()
    assert body["simulation"] is True
    assert body["scenarios"], "the interface has nothing to offer"
    for entry in body["scenarios"]:
        assert {"key", "label", "lever", "change"} <= set(entry)


def test_a_simulation_returns_both_columns_and_the_simulation_flag(client, stub_context):
    response = client.post("/api/what-if", json={"ticker": "TEST", "scenario": "macro_stress"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "AVAILABLE"
    assert body["simulation"] is True
    assert body["scenario"] == "macro_stress"
    assert body["current_signal"] and body["simulated_signal"]
    assert body["current_score"] is not None and body["simulated_score"] is not None
    assert body["note"]


def test_an_unknown_scenario_is_refused_without_inventing_one(client, stub_context):
    response = client.post("/api/what-if", json={"ticker": "TEST", "scenario": "moon_landing"})
    assert response.status_code == 200, "an unsupported scenario is a state, not a broken route"
    body = response.json()
    assert body["status"] == "UNSUPPORTED"
    assert body["scenarios"], "the refusal should say what is on offer"
    assert "simulated_score" not in body
    assert not stub_context, "an unknown scenario must be refused before any data is fetched"


def test_a_security_with_no_baseline_reports_that_rather_than_simulating(client, monkeypatch):
    monkeypatch.setattr(
        "src.agents.orchestrator.build_context",
        lambda symbol, **_: EvidenceContext(symbol=symbol),  # no price frame
    )
    response = client.post("/api/what-if", json={"ticker": "TEST", "scenario": "macro_stress"})
    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT_DATA"


def test_a_context_failure_is_a_dependency_state_not_a_stack_trace(client, monkeypatch):
    def explode(symbol, **_):
        raise RuntimeError("vendor down")

    monkeypatch.setattr("src.agents.orchestrator.build_context", explode)
    response = client.post("/api/what-if", json={"ticker": "TEST", "scenario": "macro_stress"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DEPENDENCY_UNAVAILABLE"
    assert "vendor down" not in json.dumps(body), "a raw error reached the caller"


@pytest.mark.parametrize("ticker", ["", "  ", "A" * 11, "../etc", "SELECT 1", "A;B"])
def test_malformed_tickers_are_refused(client, ticker):
    response = client.post("/api/what-if", json={"ticker": ticker, "scenario": "macro_stress"})
    assert response.status_code == 422


def test_response_carries_no_non_finite_numbers(client, stub_context):
    for scenario in ("momentum_down_20", "momentum_up_20", "macro_stress", "macro_calm",
                     "valuation_cheaper", "valuation_richer", "sentiment_negative"):
        response = client.post("/api/what-if", json={"ticker": "TEST", "scenario": scenario})
        assert response.status_code == 200
        raw = response.text
        assert not NON_FINITE.search(raw), f"{scenario} serialised a non-finite number"
        for key in ("current_score", "simulated_score", "current_confidence", "simulated_risk"):
            value = response.json().get(key)
            if isinstance(value, (int, float)):
                assert math.isfinite(value)


def test_simulating_does_not_mutate_the_stored_production_analysis(client, monkeypatch):
    """The property the brief names. A shared context is handed to the route and
    checked afterwards, because the route's own copy being clean proves nothing
    if the object it borrowed was modified."""
    shared = attach_scorecard(
        EvidenceContext(symbol="TEST", price_frame=_frame(), macro_multiplier=1.0)
    )
    card = shared.scorecard
    before = (card.verdict, card.raw_score, card.confidence, card.risk_score)
    frame_before = shared.price_frame.copy(deep=True)

    monkeypatch.setattr("src.agents.orchestrator.build_context", lambda symbol, **_: shared)
    for scenario in ("momentum_down_20", "macro_stress", "valuation_richer"):
        assert client.post(
            "/api/what-if", json={"ticker": "TEST", "scenario": scenario}
        ).status_code == 200

    # Identity of the scorecard object is asserted at the service level, where
    # `simulate` is handed a context it must leave alone. Here the route builds
    # its own context and scores it, so the property under test is that the
    # *values* a reader would see are unchanged and the shared frame is intact.
    assert (shared.scorecard.verdict, shared.scorecard.raw_score,
            shared.scorecard.confidence, shared.scorecard.risk_score) == before
    assert frame_before.equals(shared.price_frame)


def test_simulating_does_not_modify_the_explore_ranking_snapshot(client, stub_context):
    """Also named in the brief. Explore serves a cached snapshot; a simulation
    that reached it would silently reorder the rankings for every reader."""
    from src.services import explore_service

    before = getattr(explore_service, "_CACHE", None)
    before_copy = dict(before) if isinstance(before, dict) else before

    for scenario in ("momentum_up_20", "macro_calm", "valuation_cheaper"):
        assert client.post(
            "/api/what-if", json={"ticker": "TEST", "scenario": scenario}
        ).status_code == 200

    after = getattr(explore_service, "_CACHE", None)
    if isinstance(before_copy, dict):
        assert dict(after) == before_copy
    else:
        assert after is before
