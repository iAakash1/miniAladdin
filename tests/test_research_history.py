"""The research-history read layer: honest statuses, nothing promoted, facts agree with manifests and documents."""

import json
from pathlib import Path

from src.services import research_history as H

REPO = Path(__file__).resolve().parents[1]


def rows():
    return {r["id"]: r for r in H.research_history(REPO / "experiments")["experiments"]}


def test_every_row_says_nothing_is_promoted_and_the_holdout_is_untouched():
    payload = H.research_history(REPO / "experiments")
    assert payload["promoted_models"] == 0 and payload["holdout"]["state"] == "SEALED"
    for row in payload["experiments"]:
        assert row["promoted"] is False and row["promotion"] == "NOT_ASSESSED" and row["holdout_touched"] is False


def test_negative_and_not_run_studies_are_present_and_labelled():
    r = rows()
    assert r["EXP-006"]["negative_or_inconclusive"] and r["EXP-009B"]["result"] == "NO_ORDERING_GAIN" and r["EXP-009C"]["negative_or_inconclusive"]
    assert r["EXP-008"]["status"] == "PREREGISTERED_NOT_RUN" and r["EXP-008"]["result"] == "NOT_RUN"


def test_exp010b_keeps_its_exposure_disclosure():
    r = rows()["EXP-010B"]
    assert "seed-0 prototype" in r["caveat"] and "Not perfectly blind" in r["summary"] and "profitability" in r["caveat"]


def test_recorded_manifests_agree_with_the_history():
    r = rows()
    assert r["EXP-010B"]["recorded_classification"] == "ECONOMICALLY_IMPROVED" == r["EXP-010B"]["result"]
    for experiment in ("EXP-010A", "EXP-010B", "EXP-011"):
        manifest = json.loads((REPO / "experiments" / experiment / "manifest.json").read_text())
        assert manifest["holdout"]["touched"] is False


def test_every_linked_document_exists():
    for row in H.HISTORY:
        for doc in row["docs"]:
            assert (REPO / doc).exists(), doc


def test_exp011_is_complete_mixed_and_never_promoted():
    r = rows()["EXP-011"]
    assert r["status"] == "COMPLETE" and r["result"] == "IMPROVES_ONLY_LINEAR"
    assert r["promoted"] is False and r["promotion"] == "NOT_ASSESSED" and r["holdout_touched"] is False
    assert r["negative_or_inconclusive"] is True              # a partial result is never shown as a plain win
    assert "Ridge ordering improved" in r["summary"] and "no detectable ordering gain" in r["summary"]
    assert "RuntimeWarning" in r["caveat"] and "environment caveat" in r["caveat"]


def test_exp011_row_agrees_with_its_recorded_manifest():
    manifest = json.loads((REPO / "experiments" / "EXP-011" / "manifest.json").read_text())
    r = rows()["EXP-011"]
    assert manifest["holdout"]["touched"] is False and manifest["best_seed_selected"] is False
    assert r["recorded_classification"] == manifest["classification"] == r["result"]
    metrics = json.loads((REPO / "experiments" / "EXP-011" / "metrics.json").read_text())["classification"]
    assert (metrics["boosted_status"], metrics["linear_status"], metrics["boosted_fold_robust"], metrics["promotion"]) == \
        ("NO_DETECTABLE_CHANGE", "IMPROVES", False, "NOT ASSESSED")


def test_no_study_is_left_marked_not_run_when_it_has_recorded_outputs():
    for row in H.HISTORY:
        if (REPO / "experiments" / row["id"] / "manifest.json").exists():
            assert row["status"] == "COMPLETE", row["id"]
