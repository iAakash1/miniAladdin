"""The Explore and recommendations endpoints.

Driven against a stubbed snapshot rather than the live universe sweep: the
sweep is ~77 securities of provider traffic, and what these tests are about
is the contract — status codes, shapes, what is refused, and what a stale
snapshot admits to — none of which needs a network.
"""

import json
import math
import re

import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.services import explore_service
from src.services.explore_service import ExploreRow, ExploreSnapshot

NON_FINITE = re.compile(r'(?<![A-Za-z0-9_"])(-?Infinity|NaN)(?![A-Za-z0-9_"])')


def _row(symbol, **kw):
    base = dict(
        company_name=f"{symbol} Inc.", sector="Information Technology", eligible=True,
        price=100.0, price_as_of="2026-09-10", model_signal="Buy",
        signal_strength=0.3, signal_percentile=70.0, confidence=70, risk_score=40,
        risk_level="MEDIUM", data_completeness=0.9, overall_rank=70.0,
        trend_score=50.0, trend_direction="high_attention",
    )
    base.update(kw)
    return ExploreRow(symbol=symbol, **base)


def _snapshot(rows=None, **kw):
    rows = rows if rows is not None else [_row("AAA", overall_rank=90.0), _row("BBB", overall_rank=50.0)]
    base = dict(
        generated_at="2026-09-11T09:00:00+00:00", data_as_of="2026-09-10",
        universe_version="us-v1", rows=rows,
        eligible_count=sum(1 for r in rows if r.eligible), evaluated_count=len(rows),
    )
    base.update(kw)
    return ExploreSnapshot(**base)


@pytest.fixture()
def served(monkeypatch):
    """Serve a given snapshot without touching a provider."""

    def _install(snapshot):
        monkeypatch.setattr(explore_service, "get_snapshot", lambda force=False: snapshot)
        return TestClient(api.app)

    return _install


# ── contract ─────────────────────────────────────────────────────────────────

def test_explore_returns_the_requested_ordering(served):
    with served(_snapshot()) as client:
        body = client.get("/api/explore?category=overall").json()
    assert [r["symbol"] for r in body["results"]] == ["AAA", "BBB"]
    assert body["category"] == "overall"


def test_every_response_is_versioned(served):
    """A ranking is only reproducible against the universe it ran over."""
    with served(_snapshot()) as client:
        body = client.get("/api/explore").json()
    for field in ("generated_at", "data_as_of", "universe_version", "scoring_version"):
        assert body.get(field), field


def test_an_unknown_category_is_refused_rather_than_silently_replaced(served):
    with served(_snapshot()) as client:
        response = client.get("/api/explore?category=guaranteed_winners")
    assert response.status_code == 422
    assert "Expected one of" in response.json()["detail"]


def test_the_category_list_is_served(served):
    with served(_snapshot()) as client:
        body = client.get("/api/explore/categories").json()
    keys = [c["key"] for c in body["categories"]]
    assert "overall" in keys and "trending" in keys and "low_risk" in keys


def test_growth_is_not_offered_while_periods_are_unreconciled(served):
    """A tab built on TTM-versus-fiscal-year would rank accounting, not companies."""
    with served(_snapshot()) as client:
        keys = [c["key"] for c in client.get("/api/explore/categories").json()["categories"]]
    assert "growth" not in keys


def test_no_endpoint_emits_a_non_finite_number(served):
    with served(_snapshot()) as client:
        for path in ("/api/explore", "/api/explore/categories", "/api/recommendations"):
            text = client.get(path).text
            assert not NON_FINITE.search(text), path
            json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_working_state_is_not_serialised(served):
    """The price frame the ranking pass carries must not reach the wire."""
    with served(_snapshot()) as client:
        assert "_raw" not in client.get("/api/explore").text


# ── filters ──────────────────────────────────────────────────────────────────

def test_filters_narrow_the_result(served):
    rows = [_row("A", sector="Energy"), _row("B", sector="Financials")]
    with served(_snapshot(rows)) as client:
        body = client.get("/api/explore?sector=Energy").json()
    assert [r["symbol"] for r in body["results"]] == ["A"]


def test_a_risk_filter_excludes_unmeasured_risk(served):
    rows = [_row("A", risk_score=20), _row("B", risk_score=None, risk_level=None)]
    with served(_snapshot(rows)) as client:
        body = client.get("/api/explore?max_risk=40").json()
    assert [r["symbol"] for r in body["results"]] == ["A"]


@pytest.mark.parametrize("query", ["max_risk=500", "min_confidence=-1", "min_data_completeness=2"])
def test_out_of_range_filters_are_refused(served, query):
    with served(_snapshot()) as client:
        assert client.get(f"/api/explore?{query}").status_code == 422


# ── recommendations ──────────────────────────────────────────────────────────

def test_recommendations_follow_the_ranking(served):
    rows = [_row("LOWEST", overall_rank=5.0), _row("HIGHEST", overall_rank=95.0)]
    with served(_snapshot(rows)) as client:
        body = client.get("/api/recommendations?limit=2").json()
    assert [r["symbol"] for r in body["results"]] == ["HIGHEST", "LOWEST"]


def test_recommendations_carry_the_educational_framing(served):
    with served(_snapshot()) as client:
        body = client.get("/api/recommendations").json()
    assert "not personalised investment advice" in body["disclaimer"].lower()


def test_recommendations_return_nothing_when_nothing_qualifies(served):
    """Rather than relaxing a gate to fill the slots."""
    rows = [_row("A", eligible=False), _row("B", eligible=False)]
    with served(_snapshot(rows)) as client:
        body = client.get("/api/recommendations").json()
    assert body["results"] == [] and body["count"] == 0


def test_recommendations_never_name_a_security_the_model_did_not_rank(served):
    """Flip the ranking; the output must flip with it."""
    with served(_snapshot([_row("AAA", overall_rank=10.0), _row("ZZZ", overall_rank=90.0)])) as c:
        first = c.get("/api/recommendations").json()["results"][0]["symbol"]
    assert first == "ZZZ"
    with served(_snapshot([_row("AAA", overall_rank=90.0), _row("ZZZ", overall_rank=10.0)])) as c:
        first = c.get("/api/recommendations").json()["results"][0]["symbol"]
    assert first == "AAA"


# ── staleness ────────────────────────────────────────────────────────────────

def test_a_stale_snapshot_says_so(served):
    """Old data is served labelled, never disguised as current."""
    stale = _snapshot(stale=True, stale_reason="the last refresh failed (TimeoutError)")
    with served(stale) as client:
        body = client.get("/api/explore").json()
    assert body["stale"] is True
    assert "refresh failed" in body["stale_reason"]


def test_an_unavailable_snapshot_is_a_503_not_an_empty_page(monkeypatch):
    """"No security qualified" and "we could not reach the vendors" look
    identical once the rows are gone, and only one of them is a finding."""

    def _boom(force=False):
        raise RuntimeError("providers unreachable")

    monkeypatch.setattr(explore_service, "get_snapshot", _boom)
    with TestClient(api.app) as client:
        for path in ("/api/explore", "/api/recommendations"):
            assert client.get(path).status_code == 503
