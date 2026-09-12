"""The rank-comparison endpoint: contract, refusals, and no invented ordering."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.services.explore_ranking import overall_rank
from src.services.explore_service import ExploreRow, ExploreSnapshot

NON_FINITE = re.compile(r'(?<![A-Za-z0-9_"])(-?Infinity|NaN)(?![A-Za-z0-9_"])')


def _row(symbol, *, signal, confidence, risk, completeness) -> ExploreRow:
    row = ExploreRow(symbol=symbol, company_name=f"{symbol} Inc.", sector="Information Technology")
    row.eligible = True
    row.signal_percentile = signal
    row.confidence = confidence
    row.risk_score = risk
    row.data_completeness = completeness
    row.overall_rank = overall_rank(
        signal_percentile=signal, confidence=confidence, risk_score=risk,
        data_completeness_pct=None if completeness is None else completeness * 100.0,
    )
    return row


@pytest.fixture
def client(monkeypatch):
    rows = [
        _row("AAA", signal=85.0, confidence=48, risk=38, completeness=1.0),
        _row("BBB", signal=52.0, confidence=44, risk=55, completeness=0.9),
        _row("UNRANKED", signal=None, confidence=44, risk=55, completeness=0.9),
    ]
    snapshot = ExploreSnapshot(
        generated_at="2026-09-12T09:00:00+00:00", data_as_of="2026-09-11",
        universe_version="us-v1", rows=rows, eligible_count=2, evaluated_count=3,
    )
    monkeypatch.setattr("src.services.explore_service.get_snapshot", lambda *a, **k: snapshot)
    return TestClient(api.app)


def test_a_comparison_decomposes_the_gap(client):
    body = client.get("/api/compare/rank?a=AAA&b=BBB").json()
    assert body["status"] == "AVAILABLE"
    assert body["leader"] == "AAA"
    assert body["contributions"], "no decomposition was returned"
    total = sum(c["contribution"] for c in body["contributions"])
    assert total == pytest.approx(body["rank_gap"], abs=0.01)
    assert body["summary"]


def test_the_response_says_rank_is_not_a_recommendation(client):
    body = client.get("/api/compare/rank?a=AAA&b=BBB").json()
    assert "not a recommendation" in body["caveat"]


def test_a_security_outside_the_universe_is_reported_not_guessed(client):
    body = client.get("/api/compare/rank?a=AAA&b=ZZZ").json()
    assert body["status"] == "INSUFFICIENT_DATA"
    assert body["missing"] == ["ZZZ"]
    assert "contributions" not in body or not body.get("contributions")


def test_an_unranked_security_is_refused_rather_than_partially_explained(client):
    body = client.get("/api/compare/rank?a=AAA&b=UNRANKED").json()
    assert body["status"] == "AVAILABLE"      # it is in the universe
    assert body["contributions"] == []        # but the gap cannot be decomposed
    assert body["unavailable_reason"]
    assert "UNRANKED" in body["unavailable_reason"]
    assert body["leader"] is None


def test_comparing_a_security_with_itself_is_refused(client):
    body = client.get("/api/compare/rank?a=AAA&b=AAA").json()
    assert body["status"] == "UNSUPPORTED"


def test_the_comparison_is_symmetric_in_magnitude(client):
    forward = client.get("/api/compare/rank?a=AAA&b=BBB").json()
    backward = client.get("/api/compare/rank?a=BBB&b=AAA").json()
    assert forward["leader"] == backward["leader"] == "AAA"
    assert forward["rank_gap"] == pytest.approx(-backward["rank_gap"], abs=1e-9)


@pytest.mark.parametrize("pair", [("", "BBB"), ("AAA", ""), ("A" * 11, "BBB"), ("../x", "BBB")])
def test_malformed_tickers_are_refused(client, pair):
    assert client.get(f"/api/compare/rank?a={pair[0]}&b={pair[1]}").status_code == 422


def test_a_missing_snapshot_is_a_dependency_state_not_a_stack_trace(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("rebuild in progress")

    monkeypatch.setattr("src.services.explore_service.get_snapshot", explode)
    response = TestClient(api.app).get("/api/compare/rank?a=AAA&b=BBB")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DEPENDENCY_UNAVAILABLE"
    assert "rebuild in progress" not in json.dumps(body)


def test_the_response_carries_no_non_finite_numbers(client):
    for query in ("a=AAA&b=BBB", "a=AAA&b=UNRANKED", "a=AAA&b=ZZZ"):
        text = client.get(f"/api/compare/rank?{query}").text
        assert not NON_FINITE.search(text), query
        json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
