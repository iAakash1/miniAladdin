"""No relationship is drawn that a record does not name.

The temptation in a research product is to connect things that obviously go
together. A factor and a security look related — but every factor can be
computed for every security, so that edge carries no information and would only
make the graph look richer than the data is.

The rule is that an edge exists when an artifact names both of its ends. These
tests assert the frontend's relationship module keeps to that: the edges it
draws correspond to fields that actually exist in the payloads, and the ones it
refuses are documented as refused rather than quietly missing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.index import app

ROOT = Path(__file__).resolve().parents[1]
RELATIONS = ROOT / "dashboard" / "src" / "lib" / "research" / "relations.ts"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_every_registry_edge_reads_a_field_the_payload_has(client: TestClient) -> None:
    """The model edges invert registry fields. Those fields must be real."""
    entries = client.get("/api/ml/registry").json().get("entries") or []
    if not entries:
        pytest.skip("no registry entries to check against")
    present = set(entries[0])

    source = RELATIONS.read_text()
    # Fields the module reads off a registry entry.
    for field in ("features", "dataset_sources", "experiments_run", "label"):
        assert f"e.{field}" in source or f"entry?.{field}" in source, (
            f"relations.ts no longer reads {field}; this test is stale"
        )
        assert field in present, (
            f"relations.ts draws an edge from `{field}`, which the registry "
            f"payload does not carry. An edge from an absent field is invented."
        )


def test_every_experiment_edge_reads_a_field_the_payload_has(client: TestClient) -> None:
    artifact = client.get("/api/quant/experiments/EXP-006").json()
    source = RELATIONS.read_text()
    for field in ("features_used", "dataset_sources", "leaderboard"):
        assert f"artifact.{field}" in source, (
            f"relations.ts no longer reads {field}; this test is stale"
        )
        assert field in artifact, (
            f"experimentRelations draws an edge from `{field}`, which the "
            f"experiment artifact does not carry."
        )


def test_the_unbacked_edges_are_documented_as_refused() -> None:
    """An edge left out on purpose must say so, or it reads as an oversight."""
    source = RELATIONS.read_text()
    for edge in ("security → factor", "security → model", "factor → feature"):
        assert edge in source, (
            f"{edge} is not recorded anywhere in the backend, and the reason it "
            f"is not drawn should be stated in relations.ts — otherwise the next "
            f"reader adds it because it looks like an omission."
        )


def test_no_edge_is_drawn_from_a_null_model_reference(client: TestClient) -> None:
    """The symbol endpoint carries `model`, and it can be null.

    A security-to-model edge built from that field would render a relationship
    for every security whose model reference is absent.
    """
    payload = client.get("/api/quant/symbol/AAPL").json()
    if payload.get("model") is not None:
        pytest.skip("this symbol now carries a model reference; revisit the edge")
    source = RELATIONS.read_text()
    assert not re.search(r"kind:\s*'model'[^}]*verb:\s*'predicts'", source), (
        "a security-to-model edge exists while the symbol payload's model is null"
    )
