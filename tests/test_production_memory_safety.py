from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api.index as api
from api import persistence
from src import observability
from src.providers import parallel
from src.services import factor_lab_service, log_sanitizer, memory_diagnostics, quant_service


def test_memory_limit_prefers_explicit_env_and_reads_cgroup(tmp_path):
    cgroup = tmp_path / "memory.max"
    cgroup.write_text(str(512 * 1024 * 1024), encoding="utf-8")
    assert memory_diagnostics.memory_limit_mb(environ={}, cgroup_paths=(cgroup,)) == 512.0
    assert memory_diagnostics.memory_limit_mb(
        environ={"MEMORY_LIMIT_MB": "768"}, cgroup_paths=(cgroup,)
    ) == 768.0


@pytest.mark.parametrize("value,expected", [(69.9, None), (70, "elevated"), (85, "high"), (95, "critical")])
def test_memory_pressure_thresholds_are_limit_relative(value, expected):
    assert memory_diagnostics.pressure_level(value) == expected


def test_request_profile_is_cleared_when_call_next_raises():
    request = SimpleNamespace(
        method="GET", url=SimpleNamespace(path="/boom"), state=SimpleNamespace()
    )

    async def exercise():
        async def explode(_request):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await api.request_logging(request, explode)
        assert observability.current() is None

    asyncio.run(exercise())


def test_log_filter_redacts_known_values_query_fields_and_exceptions(monkeypatch):
    secret = "unit-test-alpha-secret-123"
    monkeypatch.setenv("ALPHA_VANTAGE_KEY", secret)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(log_sanitizer.SecretRedactionFilter())
    logger = logging.getLogger("test.redaction")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        raise RuntimeError(f"provider rejected apikey={secret}")
    except RuntimeError:
        logger.exception("request failed https://example.test?q=1&api_key=%s", secret)

    rendered = stream.getvalue()
    assert secret not in rendered
    assert "<redacted>" in rendered


def test_factor_api_missing_artifact_never_starts_a_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(factor_lab_service, "ARTIFACT_ROOT", tmp_path)
    before = {thread.ident for thread in threading.enumerate()}
    result = factor_lab_service.run("mega30", 2.5, 21)
    after = {thread.ident for thread in threading.enumerate()}
    assert result["status"] == "BUILD_REQUIRED"
    assert before == after


def test_factor_artifact_is_hash_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(factor_lab_service, "ARTIFACT_ROOT", tmp_path)
    result = {"universe": {"name": "mega30"}, "window": {"end": "2026-09-20"}, "factors": []}
    path = factor_lab_service._artifact_path("mega30", 2.5, 21)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "artifact_id": "test", "universe": "mega30",
        "years": 2.5, "horizon": 21,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": factor_lab_service._canonical_hash(result), "result": result,
    }), encoding="utf-8")
    assert factor_lab_service.run("mega30", 2.5, 21)["status"] == "READY"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["result"]["factors"] = [{"factor": "tampered"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert factor_lab_service.run("mega30", 2.5, 21)["reason"] == "ARTIFACT_INTEGRITY_FAILED"


def test_system_health_does_not_probe_database_or_inference_network():
    with patch("src.services.database.get_client", side_effect=AssertionError("db probe")), \
         patch("src.services.inference_client.health", side_effect=AssertionError("network probe")):
        response = TestClient(api.app).get("/api/system/health")
    assert response.status_code == 200
    assert "process_memory" in response.json()


def test_model_lab_response_is_bounded_runtime_summary():
    response = TestClient(api.app).get("/api/quant/model-lab")
    assert response.status_code == 200
    assert len(response.content) < 500_000
    payload = response.json()
    assert all(row["phase"] == "OUTER_EVALUATION" for row in payload["completed_trials"])
    assert payload["completed_inner_trial_count"] >= 0


def test_production_status_reuses_unchanged_registry_and_invalidates_on_metadata(tmp_path):
    calls = 0

    class FakeRegistry:
        def __init__(self, root):
            nonlocal calls
            calls += 1
            self.path = tmp_path / "registry.json"
            self.source_present = False

    quant_service._production_status_cached.cache_clear()
    try:
        with patch("src.quant.models.registry.ModelRegistry", FakeRegistry):
            quant_service.production_status(tmp_path)
            quant_service.production_status(tmp_path)
            assert calls == 1
            (tmp_path / "registry.json").write_text("{}", encoding="utf-8")
            quant_service.production_status(tmp_path)
            assert calls == 2
    finally:
        quant_service._production_status_cached.cache_clear()


def test_prediction_agent_does_not_retain_eager_yfinance_module_alias():
    import src.prediction_agent as prediction_agent

    assert not hasattr(prediction_agent, "yf")


def test_provider_process_pool_is_a_hard_batch_cap():
    release = threading.Event()
    entered = 0
    peak = 0
    lock = threading.Lock()

    def work(_item):
        nonlocal entered, peak
        with lock:
            entered += 1
            peak = max(peak, entered)
        release.wait(0.05)
        with lock:
            entered -= 1

    parallel.map_concurrent(work, list(range(40)), workers=40, timeout=3)
    assert peak <= parallel.PROCESS_WORKER_LIMIT


def test_preferences_schema_drift_is_typed_not_raw_500():
    class SchemaError(Exception):
        code = "PGRST204"

    body = persistence.PreferencesPatchBody(experience_mode="advanced")
    with patch.object(persistence, "_client", return_value=object()), \
         patch.object(persistence.PreferencesRepository, "patch", side_effect=SchemaError()):
        with pytest.raises(HTTPException) as raised:
            persistence.patch_preferences(body, user="user_test")
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "PERSISTENCE_SCHEMA_DRIFT"
