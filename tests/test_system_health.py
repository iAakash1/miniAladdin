from pathlib import Path

from src.services.system_health import HealthState, build_health


def _manifests(root: Path, *, validation_status: str = "PASS") -> None:
    import json

    folder = root / "data/manifests"
    folder.mkdir(parents=True)
    (folder / "pit_validation_v4.json").write_text(json.dumps({"status": validation_status}))
    (folder / "rich_pit_v2_manifest.json").write_text(json.dumps({
        "dataset_id": "ds-test", "feature_count": 94, "content_hash": "abc",
        "holdout": {"touched": False},
    }))


def _report(tmp_path: Path, **overrides):
    _manifests(tmp_path, validation_status=overrides.pop("validation_status", "PASS"))
    values = dict(
        build_commit="abc123",
        persistence_configured=True,
        persistence_reachable=True,
        auth_configured=True,
        provider_health={"providers": {
            key: [{"vendor": key, "configured": True, "cooling_down": False,
                   "consecutive_failures": 0}]
            for key in ("market_data", "fundamentals", "news", "macro", "filings")
        }},
        quant_status={
            "deployment_status": "PRODUCTION", "registry_available": True,
            "message": "one production model", "production": 1,
            "candidates": 0, "total_entries": 1, "serving_predictions": True,
        },
        inference_configured=True,
        inference_health={"status": "ok"},
        langgraph_available=True,
        project_root=tmp_path,
    )
    values.update(overrides)
    return build_health(**values)


def test_holdout_governance_prevents_an_overall_ready_state(tmp_path):
    report = _report(tmp_path)
    assert report.status is HealthState.BLOCKED
    holdout = next(row for row in report.components if row.component == "final_holdout")
    assert holdout.status is HealthState.BLOCKED
    assert holdout.detail["touched"] is False


def test_missing_langgraph_is_unavailable_and_never_a_fallback(tmp_path):
    report = _report(tmp_path, langgraph_available=False)
    assert report.status is HealthState.UNAVAILABLE
    graph = next(row for row in report.components if row.component == "agent_graph")
    assert graph.status is HealthState.UNAVAILABLE


def test_partial_pit_validation_is_reported_as_degraded(tmp_path):
    report = _report(tmp_path, validation_status="PARTIAL")
    data = next(row for row in report.components if row.component == "data_registry")
    assert data.status is HealthState.DEGRADED


def test_not_configured_is_not_relabelled_unavailable(tmp_path):
    report = _report(
        tmp_path, persistence_configured=False, persistence_reachable=False,
        inference_configured=False,
        inference_health={"status": "unavailable", "detail": "not configured"},
    )
    by_name = {row.component: row for row in report.components}
    assert by_name["persistence"].status is HealthState.NOT_CONFIGURED
    assert by_name["quant_inference"].status is HealthState.NOT_CONFIGURED
