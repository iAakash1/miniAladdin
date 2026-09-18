"""Deployment contracts for the first-class Book route.

The research workstation has an ignored 9 MB predictions file and SciPy from
the modelling environment. Render has only tracked files and requirements.txt.
These tests deliberately remove the legacy artifact and, for the absence path,
block SciPy imports so that local developer state cannot mask deployment bugs.
"""

from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.index as api
from src.quant.portfolio.optimizer import METHODS
from src.services import quant_portfolio_service as service


@pytest.fixture()
def client():
    return TestClient(api.app, raise_server_exceptions=False)


def _deployment_without_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(service, "EXPERIMENTS", tmp_path / "experiments")
    monkeypatch.setattr(service, "RUNTIME_ARTIFACTS", tmp_path / "runtime")
    service._cache.clear()


@pytest.mark.parametrize("method", METHODS)
def test_every_allocator_answers_missing_deployment_artifact_without_500(
    client, monkeypatch, tmp_path, method,
):
    _deployment_without_artifacts(monkeypatch, tmp_path)

    # Reproduce the old Render dependency set. The missing-artifact branch must
    # answer before risk.engine attempts to import SciPy.
    real_import = builtins.__import__

    def without_scipy(name, *args, **kwargs):
        if name == "scipy" or name.startswith("scipy."):
            raise ModuleNotFoundError("No module named 'scipy'", name="scipy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_scipy)
    response = client.get(f"/api/quant/portfolio?method={method}")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "unavailable"
    assert body["reason"] == "ARTIFACT_NOT_DEPLOYED"
    assert body["required_artifact"] == "gradient_boosting.parquet"
    assert "/Users/" not in response.text and "/opt/render/" not in response.text


def _write_metadata(path: Path, **overrides) -> None:
    metadata = {
        "schema_version": service.RUNTIME_SCHEMA_VERSION,
        "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        **overrides,
    }
    path.with_suffix(".json").write_text(json.dumps(metadata), encoding="utf-8")


def test_an_unreadable_runtime_artifact_is_typed_not_500(client, monkeypatch, tmp_path):
    _deployment_without_artifacts(monkeypatch, tmp_path)
    path = service._runtime_artifact("EXP-006", "fwd_rank_21", "gradient_boosting")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not parquet")
    _write_metadata(path)

    response = client.get("/api/quant/portfolio?method=risk_parity")

    assert response.status_code == 200
    assert response.json()["reason"] == "ARTIFACT_UNREADABLE"


def test_an_incompatible_runtime_schema_is_typed_not_500(client, monkeypatch, tmp_path):
    _deployment_without_artifacts(monkeypatch, tmp_path)
    path = service._runtime_artifact("EXP-006", "fwd_rank_21", "gradient_boosting")
    path.parent.mkdir(parents=True)
    pd.DataFrame({"symbol": ["AAPL"]}).to_parquet(path, index=False)
    _write_metadata(path)

    response = client.get("/api/quant/portfolio?method=risk_parity")
    body = response.json()

    assert response.status_code == 200
    assert body["reason"] == "ARTIFACT_SCHEMA_INCOMPATIBLE"
    assert set(body["missing_columns"]) >= {"date", "model", "prediction", "fwd_rank_21"}


def test_render_runtime_dependency_is_explicitly_pinned():
    requirements = (service.REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert any(line.startswith("scipy==") for line in requirements.splitlines())


def test_committed_compact_runtime_artifact_builds_the_default_book(monkeypatch, tmp_path):
    # Ignore the workstation's legacy predictions file. The result must come
    # from artifacts/runtime, which is the only file Render receives.
    monkeypatch.setattr(service, "EXPERIMENTS", tmp_path / "no-legacy-artifacts")
    service._cache.clear()

    book = service.build(method="risk_parity")

    assert book["status"] == "ok"
    assert book["model_id"] == "gradient_boosting"
    assert book["target"] == "fwd_rank_21"
    assert book["weights"]
    assert book["allocation"]["feasible"] is True
