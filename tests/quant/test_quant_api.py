"""
Quant API contract tests.

The contract these defend is narrow and important: the API must never hand the
frontend something it could render as a production prediction when no model has
been promoted, and it must never leak a filesystem path or a credential while
doing so.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.index import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ── availability ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "/api/quant/status",
    "/api/quant/experiments",
    "/api/quant/features",
    "/api/quant/datasets",
    "/api/quant/symbol/AAPL",
])
def test_endpoint_answers(client, path):
    assert client.get(path).status_code == 200


def test_an_unknown_experiment_is_404_not_an_empty_body(client):
    response = client.get("/api/quant/experiments/EXP-DOES-NOT-EXIST")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_a_malformed_experiment_id_is_rejected_by_the_route(client):
    """Path validation, so a traversal attempt never reaches the filesystem."""
    assert client.get("/api/quant/experiments/..%2F..%2Fetc").status_code in {404, 422}


def test_a_malformed_symbol_is_rejected(client):
    assert client.get("/api/quant/symbol/../../etc/passwd").status_code in {404, 422}


# ── the refusal ─────────────────────────────────────────────────────────────


def test_status_reports_the_registry_not_a_leaderboard(client):
    body = client.get("/api/quant/status").json()
    assert body["deployment_status"] in {
        "NO_MODEL", "EXPERIMENTAL", "CANDIDATE", "PRODUCTION",
    }
    assert body["production"] == 0, "no model has been promoted"
    assert body["serving_predictions"] is False


def test_status_carries_the_holdout_state(client):
    firewall = client.get("/api/quant/status").json()["firewall"]
    assert firewall["contract_armed"] is False
    assert "LOCKED" in firewall["headline"]


def test_symbol_never_returns_a_prediction_without_a_production_model(client):
    """The single most important refusal in the product."""
    body = client.get("/api/quant/symbol/AAPL").json()
    assert body["prediction"] is None
    assert body["model"] is None
    assert body["deployment_status"] != "PRODUCTION"
    assert "disclosure" in body


# ── nothing leaks ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [
    "/api/quant/status",
    "/api/quant/experiments",
    "/api/quant/datasets",
    "/api/quant/symbol/AAPL",
])
def test_no_absolute_filesystem_paths_in_any_payload(client, path):
    body = client.get(path).text
    assert "/Users/" not in body
    assert "/home/" not in body
    assert "/var/folders" not in body


@pytest.mark.parametrize("path", ["/api/quant/status", "/api/quant/datasets"])
def test_no_credential_shaped_strings_in_any_payload(client, path):
    body = client.get(path).text.lower()
    for token in ("api_key", "secret", "password", "authorization", "bearer "):
        assert token not in body, f"{token} appeared in {path}"


# ── the catalog tiers ───────────────────────────────────────────────────────


def test_the_dataset_catalog_reports_gated_sources(client):
    """A publication-lagged source is restricted, and the UI must be told."""
    body = client.get("/api/quant/datasets").json()
    assert "gated" in body
    gated = {e["dataset_id"] for e in body["gated"]}
    assert "dolthub_earnings_income_statement" in gated
    for entry in body["gated"]:
        assert entry["gate"], "a gated source must explain its gate"


def test_void_experiments_remain_listed(client):
    body = client.get("/api/quant/experiments").json()
    ids = {e["experiment_id"]: e for e in body["experiments"]}
    assert "EXP-002" in ids
    assert ids["EXP-002"]["void"] is True


def test_features_are_registry_backed(client):
    body = client.get("/api/quant/features").json()
    assert body.get("features") or body.get("feature_count")
