"""
The read layer: reports absence honestly, and never estimates in its place.

The behaviour under test is mostly what the service *refuses* to do. A research
surface that renders a cheap approximation where a walk-forward result belongs
is worse than an empty one, because the reader cannot tell them apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.services import ml_service


@pytest.fixture(autouse=True)
def _clear_cache():
    ml_service.reset_for_tests()
    yield
    ml_service.reset_for_tests()


@pytest.fixture
def client():
    import api.index as index

    return TestClient(index.app)


def _study_fixture(root: Path) -> Path:
    payload = {
        "generated_at": "2026-08-29T00:00:00+00:00",
        "git_commit": "abc123",
        "seed": 0,
        "dependency_versions": {"numpy": "2.2.6"},
        "features_used": ["mom_252_21_xs", "vol_63_xs"],
        "dataset": {
            "dataset_version": "ds-test",
            "rows": 1000,
            "symbols": 50,
            "dates": 20,
            "start": "2014-04-01",
            "end": "2016-12-31",
            "content_hash": "deadbeef",
            "guard_report": {"passed": True, "total": 7, "failed": 0, "checks": []},
            "source_datasets": [{"dataset_id": "dolthub_stocks_ohlcv", "rows": 10}],
        },
        "universe": {"unique_members": 998, "snapshots": 184, "point_in_time": True},
        "regimes": {"rules": {"method": "rule_based", "distribution": {"low_vol_bull": 100}}},
        "labels": {
            "fwd_ret_21": {
                "label": "fwd_ret_21",
                "horizon_sessions": 21,
                "walk_forward_plan": {"folds": [{"index": 0}], "embargo_sessions": 5},
                "fold_rows": [],
                "overlap_check": {"ok": True},
                "experiment_distribution": {"experiments": 12, "best": 0.1, "median": 0.05},
                "leaderboard": [
                    {"model_id": "lasso", "mean_ic": 0.03, "ic_t_stat": 1.1,
                     "fold_ic_positive_rate": 0.6, "rmse_vs_zero": 1.2},
                    {"model_id": "baseline_mom_252_21_xs", "mean_ic": 0.05,
                     "ic_t_stat": 2.6, "fold_ic_positive_rate": 0.8},
                ],
                "backtests": {"lasso": {"metrics": {"net_sharpe": 0.4}}},
                "cost_sensitivity": {"lasso": []},
                "factor_attribution": {"lasso": {"alpha_significant": False, "verdict": "explained"}},
                "regime_performance": {"lasso": []},
                "significance": {"lasso": {"deflated_sharpe": {"deflated_probability": 0.3}}},
                "probability_of_backtest_overfitting": {"pbo": 0.45},
                "experiments": {"results": [{"model_id": "lasso", "explanation": {"kind": "linear_coefficients"}}]},
            }
        },
    }
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / "study.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ── absence ─────────────────────────────────────────────────────────────────


def test_overview_reports_unavailable_with_a_remediation(tmp_path):
    result = ml_service.overview(tmp_path)
    assert result["status"] == "unavailable"
    assert "scripts.quant.study" in result["remediation"]
    # Nothing numeric is invented alongside the refusal.
    assert "labels" not in result


def test_label_report_names_the_available_labels(tmp_path):
    _study_fixture(tmp_path)
    result = ml_service.label_report("fwd_ret_999", tmp_path)
    assert result["status"] == "unavailable"
    assert result["available"] == ["fwd_ret_21"]


def test_registry_reports_unavailable_when_empty(tmp_path):
    assert ml_service.registry(tmp_path)["status"] == "unavailable"


# ── catalogs work without any study ─────────────────────────────────────────


def test_feature_catalog_is_available_before_any_study():
    catalog = ml_service.feature_catalog()
    assert catalog["feature_count"] > 20
    assert catalog["unsafe_features"] == []
    assert any(f["name"] == "mom_252_21" for f in catalog["features"])
    assert all("point_in_time_safe" in f for f in catalog["features"])


def test_dataset_catalog_names_what_is_gated_and_why():
    """A source behind a publication gate must be reported as restricted.

    It is not `excluded` — the builder will read it — but it is not free to use
    either, and a payload that showed only the excluded tier would imply the
    period-keyed statement tables are unconditionally safe.
    """
    catalog = ml_service.dataset_catalog()
    gated = {e["dataset_id"]: e for e in catalog["gated"]}
    assert "dolthub_earnings_income_statement" in gated
    entry = gated["dolthub_earnings_income_statement"]
    assert entry["classification"] == "publication_lagged"
    assert "as-of join" in entry["gate"]
    # The restatement caveat has to travel with it to the UI, not stay in a docstring.
    assert entry["residual_risk"], "gated source must carry its residual risk forward"
    assert any("restatement" in r.lower() for r in entry["residual_risk"])


def test_every_gated_source_explains_its_gate():
    catalog = ml_service.dataset_catalog()
    assert catalog["gated"], "the period-keyed statement tables must appear here"
    for entry in catalog["gated"]:
        assert entry["reason"]
        assert entry["gate"]


def test_capabilities_reports_each_capability_with_a_reason(tmp_path):
    result = ml_service.capabilities(tmp_path)
    for name, entry in result["capabilities"].items():
        assert entry["status"] in {"available", "unavailable"}
        assert entry["detail"]


# ── presence ────────────────────────────────────────────────────────────────


def test_overview_surfaces_the_experiment_count_beside_the_best(tmp_path):
    _study_fixture(tmp_path)
    result = ml_service.overview(tmp_path)
    headline = result["labels"][0]
    assert headline["experiments"] == 12
    assert headline["median_ic"] == 0.05


def test_verdict_reports_losing_to_a_baseline(tmp_path):
    """A learned model that does not beat a free factor must be said to fail."""
    _study_fixture(tmp_path)
    result = ml_service.overview(tmp_path)
    verdict = result["labels"][0]["verdict"]
    assert "NO STATISTICALLY USEFUL SIGNAL" in verdict or "does not beat" in verdict


def test_label_report_includes_losers_not_just_the_winner(tmp_path):
    _study_fixture(tmp_path)
    result = ml_service.label_report("fwd_ret_21", tmp_path)
    ids = {m["model_id"] for m in result["models"]}
    assert ids == {"lasso", "baseline_mom_252_21_xs"}
    kinds = {m["model_id"]: m["kind"] for m in result["models"]}
    assert kinds["baseline_mom_252_21_xs"] == "baseline"
    assert kinds["lasso"] == "learned"


def test_provenance_tags_every_stage_with_a_data_kind(tmp_path):
    _study_fixture(tmp_path)
    chain = ml_service.provenance("fwd_ret_21", "lasso", tmp_path)["chain"]
    kinds = {stage["kind"] for stage in chain}
    assert kinds <= {"OBSERVED", "DERIVED", "MODEL_PREDICTED"}
    assert any(stage["kind"] == "OBSERVED" for stage in chain)
    assert any(stage["kind"] == "MODEL_PREDICTED" for stage in chain)
    stages = [stage["stage"] for stage in chain]
    assert stages.index("source") < stages.index("model") < stages.index("attribution")


# ── API ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "/api/ml/capabilities",
        "/api/ml/datasets",
        "/api/ml/features",
        "/api/ml/overview",
        "/api/ml/registry",
        "/api/ml/labels/fwd_ret_21",
        "/api/ml/provenance/fwd_ret_21/ridge",
    ],
)
def test_every_ml_endpoint_answers(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


def test_label_path_rejects_an_injection_shaped_value(client):
    assert client.get("/api/ml/labels/..%2F..%2Fetc").status_code in {404, 422}
    assert client.get("/api/ml/labels/DROP TABLE").status_code in {404, 422}


def test_no_endpoint_leaks_a_filesystem_path_outside_the_research_root(client):
    payload = client.get("/api/ml/capabilities").json()
    assert payload["root"].startswith("data/research")


# ── invalidated studies ─────────────────────────────────────────────────────
#
# A void result must never render as a finding. The artifact is deliberately
# retained rather than deleted — removing it would erase the multiple-testing
# exposure it created — so every surface that reads it has to carry the
# retraction.


def test_the_audited_study_is_marked_invalid():
    from src.services.ml_service import INVALIDATED_STUDIES, study_validity

    assert "ds-e691b48ca49deb16" in INVALIDATED_STUDIES
    verdict = study_validity("ds-e691b48ca49deb16")
    assert verdict["valid"] is False
    assert "merge_asof" in verdict["reason"]
    assert verdict["audit"].endswith("PRE_HOLDOUT_AUDIT.md")


def test_an_unknown_study_version_is_treated_as_valid():
    from src.services.ml_service import study_validity

    assert study_validity("ds-something-else")["valid"] is True
    assert study_validity(None)["valid"] is True


def test_void_studies_lead_with_the_retraction(tmp_path):
    """The retraction outranks every other verdict clause."""
    from src.services import ml_service

    path = _study_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dataset"]["dataset_version"] = "ds-e691b48ca49deb16"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ml_service.reset_for_tests()

    result = ml_service.overview(tmp_path)
    assert result["validity"]["valid"] is False
    for headline in result["labels"]:
        assert headline["verdict"].startswith("RESULT VOID")


def test_surviving_baselines_are_not_marked_void(tmp_path):
    """Single-feature passthroughs were unaffected and must say so."""
    from src.services.ml_service import _verdict, study_validity

    validity = study_validity("ds-e691b48ca49deb16")
    report = {
        "leaderboard": [
            {"model_id": "baseline_momentum", "mean_ic": 0.0158, "ic_t_stat": 0.88},
        ],
        "backtests": {}, "factor_attribution": {}, "significance": {},
    }
    verdict = _verdict(report, "baseline_momentum", validity=validity)
    assert verdict.startswith("RESULT VALID")
    assert "not significant" in verdict


def test_label_report_carries_validity(tmp_path):
    from src.services import ml_service

    path = _study_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dataset"]["dataset_version"] = "ds-e691b48ca49deb16"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ml_service.reset_for_tests()

    assert ml_service.label_report("fwd_ret_21", tmp_path)["validity"]["valid"] is False


# ── invalidation is a property of the study, not of the dataset ─────────────


def test_a_void_study_is_identified_by_experiment_id():
    result = ml_service.study_validity("ds-e691b48ca49deb16", experiment_id="EXP-002")
    assert result["valid"] is False
    assert "merge_asof" in result["reason"]


def test_a_clean_rerun_on_the_same_dataset_version_is_valid():
    """The defect was in the feature code, not in the data.

    EXP-004 rebuilt the very same dataset version with the fix applied. Keying
    invalidity on `dataset_version` alone condemned it — and would condemn every
    future study that rebuilds that version, which is the opposite of what a
    retraction is for.
    """
    result = ml_service.study_validity("ds-e691b48ca49deb16", experiment_id="EXP-004")
    assert result["valid"] is True


def test_a_legacy_study_with_no_id_still_falls_back_to_the_dataset_version():
    """The old artifact carries no experiment id, so the coarse key must remain."""
    assert ml_service.study_validity("ds-e691b48ca49deb16")["valid"] is False


def test_the_fix_commit_clears_a_legacy_study():
    result = ml_service.study_validity(
        "ds-e691b48ca49deb16", git_commit=ml_service.AS_OF_FIX_COMMIT
    )
    assert result["valid"] is True
    assert "feature code" in result["note"]


def test_an_unrelated_dataset_version_is_valid():
    assert ml_service.study_validity("ds-something-else")["valid"] is True
