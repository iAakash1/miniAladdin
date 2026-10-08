"""A run in which no provider answered is not an "ok" run.

`/api/agents/{ticker}/validation` and `/api/analysis-runs/{ticker}` exist to deliver a decision
and the trace behind it. With every provider down the pipeline still runs: each specialist
reports what it is missing, the macro agent states that the regime could not be measured, and
no scorecard exists to copy a signal from. Both routes answered `ok` / `AVAILABLE` over that,
because the only guard was "no claims and no evidence", and a statement of absence is a claim.

The rule held here: no decision and no specialist that finished cleanly is unavailable. Any
clean specialist, or any decision, keeps the route's previous behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.index as api_module
from src.agents.schemas import AgentStatus


@pytest.fixture
def client():
    return TestClient(api_module.app, raise_server_exceptions=False)


def _agent(name, status, *, claims=0, evidence=0, missing=()):
    return SimpleNamespace(
        agent=name, status=status, claims=[object()] * claims, evidence=[object()] * evidence,
        missing=list(missing), warnings=[], latency_ms=0.1,
        model_dump=lambda: {"agent": name, "status": status.value, "missing": list(missing)},
    )


# ── the rule ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("signal,statuses,expected", [
    (None, [AgentStatus.UNAVAILABLE, AgentStatus.PARTIAL], True),
    (None, ["unavailable", "partial", "unavailable"], True),
    (None, [], True),
    (None, [AgentStatus.OK, AgentStatus.UNAVAILABLE], False),
    (None, ["ok"], False),
    ("BUY", [AgentStatus.UNAVAILABLE], False),
    ("HOLD", [AgentStatus.PARTIAL, AgentStatus.UNAVAILABLE], False),
    ("BUY", [AgentStatus.OK], False),
])
def test_nothing_gathered_truth_table(signal, statuses, expected):
    assert api_module._nothing_gathered(signal, statuses) is expected


# ── /api/agents/{ticker}/validation ──────────────────────────────────────────

def _analysis(signal, agents, *, claims=1, evidence=1):
    return SimpleNamespace(
        model_signal=signal, confidence=0.5 if signal else None, risk_score=None,
        data_completeness=0.8 if signal else None,
        validation=SimpleNamespace(model_dump=lambda: {"status": "VERIFIED"}),
        agents=agents,
        claims=[SimpleNamespace(model_dump=lambda: {"claim_id": "C1"})] * claims,
        evidence=[SimpleNamespace(model_dump=lambda: {"evidence_id": "E1"})] * evidence,
        generated_at="2026-10-08T00:00:00Z", agent_schema_version="v1", scoring_version="s1",
    )


def test_validation_with_no_decision_and_no_clean_specialist_is_unavailable(client, monkeypatch):
    outage = _analysis(None, [
        _agent("market", AgentStatus.UNAVAILABLE, missing=["price_series"]),
        _agent("macro", AgentStatus.PARTIAL, claims=1, evidence=1, missing=["risk_multiplier"]),
    ])
    monkeypatch.setattr("src.agents.analyse", lambda symbol: outage)
    body = client.get("/api/agents/AAPL/validation").json()
    assert body["status"] == "unavailable"
    assert "no decision" in body["detail"]
    assert body["agents"], "the specialists' own statuses must still be shown"


def test_validation_with_a_decision_keeps_ok(client, monkeypatch):
    healthy = _analysis("BUY", [_agent("market", AgentStatus.OK, claims=1, evidence=1),
                                _agent("fundamental", AgentStatus.UNAVAILABLE, missing=["fundamentals"])])
    monkeypatch.setattr("src.agents.analyse", lambda symbol: healthy)
    body = client.get("/api/agents/AAPL/validation").json()
    assert body["status"] == "ok" and body["model_signal"] == "BUY"


def test_validation_with_a_clean_specialist_but_no_signal_keeps_ok(client, monkeypatch):
    mixed = _analysis(None, [_agent("news", AgentStatus.OK, claims=2, evidence=2),
                             _agent("market", AgentStatus.UNAVAILABLE, missing=["price_series"])])
    monkeypatch.setattr("src.agents.analyse", lambda symbol: mixed)
    assert client.get("/api/agents/AAPL/validation").json()["status"] == "ok"


# ── /api/analysis-runs/{ticker} ──────────────────────────────────────────────

def _state(signal, agents):
    return {
        "run_id": "r1", "requested_at": "2026-10-08T00:00:00Z", "model_signal": signal,
        "confidence": 0.5 if signal else None, "risk_score": None,
        "data_completeness": 0.8 if signal else None,
        "agent_results": {a.agent: a for a in agents}, "timings": {"market": 1.0},
        "validation": None, "reconciliation": None, "errors": [], "warnings": [], "fallbacks": [],
        "graph_version": "g1", "agent_schema_version": "v1", "scoring_version": "s1",
    }


def test_analysis_run_with_no_decision_and_no_clean_specialist_is_dependency_unavailable(client, monkeypatch):
    monkeypatch.setattr("src.agents.graph.run", lambda symbol: _state(None, [
        _agent("market", AgentStatus.UNAVAILABLE, missing=["price_series"]),
        _agent("macro", AgentStatus.PARTIAL, claims=1, evidence=1),
    ]))
    body = client.get("/api/analysis-runs/AAPL").json()
    assert body["status"] == "DEPENDENCY_UNAVAILABLE"
    assert body["reason"] == "NO_PROVIDER_ANSWERED"
    assert {a["agent"] for a in body["agents"]} == {"market", "macro"}


def test_analysis_run_with_a_decision_stays_available(client, monkeypatch):
    monkeypatch.setattr("src.agents.graph.run", lambda symbol: _state("BUY", [
        _agent("market", AgentStatus.OK, claims=1, evidence=1),
        _agent("fundamental", AgentStatus.UNAVAILABLE, missing=["fundamentals"]),
    ]))
    body = client.get("/api/analysis-runs/AAPL").json()
    assert body["status"] == "AVAILABLE" and body["model_signal"] == "BUY"
