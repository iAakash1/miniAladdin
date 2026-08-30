"""
Feature audit — generated from the registry, so it cannot drift from the code.

The tests assert the audit's *conclusions*, not just its shape. If a feature is
declared point-in-time safe here, a leakage test must exist for it; if it
declares a fit, the scope must be one the pipeline actually uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.quant.audit.features import build_feature_audit, write_feature_audit
from src.quant.features import earnings, macro, options, price  # noqa: F401 - register
from src.quant.features.registry import REGISTRY


@pytest.fixture(scope="module")
def audit() -> dict:
    return build_feature_audit()


def test_every_registered_feature_appears(audit):
    documented = {e["feature"] for e in audit["features"]}
    for name in REGISTRY.names(pit_only=False):
        assert name in documented, f"{name} is registered but not audited"


def test_cross_sectional_variants_are_audited(audit):
    """The _xs columns are what the models actually consume."""
    ranks = [e for e in audit["features"] if e["is_cross_sectional"]]
    assert len(ranks) == 28
    for entry in ranks:
        assert entry["feature"].endswith("_xs")
        assert entry["base_feature"] is not None


def test_no_feature_claims_to_use_future_information(audit):
    assert all(e["uses_future_information"] is False for e in audit["features"])
    assert audit["declared_unsafe"] == []


def test_every_feature_names_a_leakage_mechanism_and_a_test(audit):
    """'None known' is a weaker claim than silence, and it must be made explicitly."""
    for entry in audit["features"]:
        assert entry["leakage_mechanism"], f"{entry['feature']} names no leakage mechanism"
        assert entry["leakage_test"], f"{entry['feature']} names no leakage test"


def test_named_leakage_tests_actually_exist(audit):
    """A cited test that does not exist is worse than no citation."""
    for entry in audit["features"]:
        path, _, name = entry["leakage_test"].partition("::")
        source = Path(path)
        assert source.exists(), f"{entry['feature']} cites a missing file {path}"
        assert name.split("[")[0] in source.read_text(encoding="utf-8"), (
            f"{entry['feature']} cites {name}, which is not defined in {path}"
        )


def test_only_cross_sectional_features_require_fitting(audit):
    """The only fitted feature transform is the per-date rank."""
    fitted = [e for e in audit["features"] if e["requires_fitting"]]
    assert {e["group"] for e in fitted} == {"cross_sectional"}
    assert audit["fit_scopes"] == ["per_date_within_point_in_time_universe"]


def test_every_feature_names_its_sources_with_a_pit_class(audit):
    for entry in audit["features"]:
        assert entry["sources"], f"{entry['feature']} names no source dataset"
        for source in entry["sources"]:
            assert source["point_in_time_class"] in {
                "point_in_time", "publication_lagged", "not_point_in_time"
            }


def test_no_feature_draws_on_an_inadmissible_source(audit):
    """A NOT_POINT_IN_TIME source must not appear behind any feature."""
    for entry in audit["features"]:
        for source in entry["sources"]:
            assert source["admissible_as_feature"], (
                f"{entry['feature']} draws on {source['dataset_id']}, which the "
                "catalog bars from training"
            )


def test_lagged_sources_declare_an_availability_lag(audit):
    """Macro is published after the day it describes; the lag must be declared."""
    for entry in audit["features"]:
        if entry["feature"].startswith("rates_"):
            assert entry["availability_lag_sessions"] >= 1, entry["feature"]
        if entry["feature"].startswith("earn_"):
            assert entry["availability_lag_sessions"] >= 1, entry["feature"]


def test_earliest_required_observation_covers_lookback_and_lag(audit):
    for entry in audit["features"]:
        assert (
            entry["earliest_required_observation_sessions_before"]
            == entry["lookback_sessions"] + entry["availability_lag_sessions"]
        )


def test_missing_data_behaviour_is_never_zero_fill(audit):
    for entry in audit["features"]:
        assert "NULL" in entry["missing_data_behaviour"]
        assert "never zero" in entry["missing_data_behaviour"]


def test_audit_serialises_and_round_trips(tmp_path):
    path = tmp_path / "feature_audit.json"
    written = write_feature_audit(str(path))
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["feature_count"] == written["feature_count"]
    assert reloaded["features"][0]["feature"] == written["features"][0]["feature"]


def test_study_feature_set_is_fully_covered():
    """Every feature the study actually used must be audited."""
    study_path = Path("data/research/reports/study.json")
    if not study_path.exists():
        pytest.skip("no study artifact")
    used = json.loads(study_path.read_text(encoding="utf-8"))["features_used"]
    audit = build_feature_audit(used)
    covered = {e["feature"] for e in audit["features"] if e.get("used_in_study")}
    assert covered == set(used), f"unaudited features in the study: {set(used) - covered}"
