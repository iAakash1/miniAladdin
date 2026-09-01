"""
The inference service must refuse rather than degrade.

An inference service that returns *some* answer when its artifact is wrong is
worse than one that is down: downstream, a wrong prediction is indistinguishable
from a right one. Every check here leaves the model unloaded, which makes
/predict return 503.
"""

from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

ARTIFACTS = Path("artifacts")
NAME = "gradient_boosting@EXP-006"

pytestmark = pytest.mark.skipif(
    not (ARTIFACTS / f"{NAME}.joblib").exists(),
    reason="deployed artifact not present in this checkout",
)


@pytest.fixture()
def service(tmp_path, monkeypatch):
    """A copy of the real artifact in a directory tests may corrupt."""
    for suffix in (".joblib", ".metadata.json"):
        shutil.copy(ARTIFACTS / f"{NAME}{suffix}", tmp_path / f"{NAME}{suffix}")
    monkeypatch.setenv("MODEL_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("MODEL_ARTIFACT", NAME)

    def load(mutate=None):
        meta_path = tmp_path / f"{NAME}.metadata.json"
        meta = json.loads((ARTIFACTS / f"{NAME}.metadata.json").read_text())
        if mutate:
            mutate(meta)
        meta_path.write_text(json.dumps(meta))
        import services.inference.app as app

        importlib.reload(app)
        app._load()
        return app

    return load


def test_the_untampered_artifact_serves(service):
    app = service()
    assert app._state["model"] is not None
    assert app._state["error"] is None
    # The verified digest is exposed, not just computed and discarded.
    assert app._state["fingerprint"] == json.loads(
        (ARTIFACTS / f"{NAME}.metadata.json").read_text()
    )["sha256"]


def test_sha256_mismatch_refuses(service):
    app = service(lambda m: m.update(sha256="0" * 64))
    assert app._state["model"] is None
    assert "sha256 mismatch" in app._state["error"]


def test_an_artifact_with_no_declared_hash_refuses(service):
    """Unverifiable is not the same as verified."""
    app = service(lambda m: m.pop("sha256"))
    assert app._state["model"] is None
    assert "no sha256" in app._state["error"]


def test_feature_count_mismatch_refuses(service):
    app = service(lambda m: m.update(feature_count=26))
    assert app._state["model"] is None
    assert "feature count mismatch" in app._state["error"]


def test_feature_order_mismatch_refuses(service):
    """A tree scores columns positionally; reordering silently changes answers."""
    app = service(lambda m: m.update(features=list(reversed(m["features"]))))
    assert app._state["model"] is None
    assert "feature ORDER" in app._state["error"]


def test_a_mostly_imputed_row_is_refused_not_scored(service):
    """The worst fail-open: a confident number computed from almost no input."""
    from fastapi.testclient import TestClient

    app = service()
    client = TestClient(app.app)
    features = app._state["features"]

    full = client.post("/predict", json={
        "items": [{"symbol": "AAPL", "features": {f: 0.1 for f in features}}],
    }).json()["predictions"][0]
    assert full["prediction"] is not None
    assert full["feature_completeness"] == 1.0
    assert full["refused_reason"] is None

    sparse = client.post("/predict", json={
        "items": [{"symbol": "AAPL", "features": {f: 0.1 for f in features[:3]}}],
    }).json()["predictions"][0]
    assert sparse["prediction"] is None, "a 3-of-27 row must not be scored"
    assert "training medians" in sparse["refused_reason"]


def test_predict_never_claims_production(service):
    from fastapi.testclient import TestClient

    app = service()
    client = TestClient(app.app)
    body = client.post("/predict", json={
        "items": [{"symbol": "AAPL",
                   "features": {f: 0.1 for f in app._state["features"]}}],
    }).json()
    assert body["promotion_status"] == "BLOCKED"
    assert body["research_status"] == "EXPERIMENTAL"
    assert body["artifact_fingerprint"]
