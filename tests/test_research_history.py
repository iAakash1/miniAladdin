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
    assert r["EXP-008"]["status"] == "PREREGISTERED_NOT_RUN" and r["EXP-011"]["status"] == "PREPARED_NOT_RUN"
    assert r["EXP-011"]["result"] == "NOT_RUN" and "No result exists" in r["EXP-011"]["summary"]


def test_exp010b_keeps_its_exposure_disclosure():
    r = rows()["EXP-010B"]
    assert "seed-0 prototype" in r["caveat"] and "Not perfectly blind" in r["summary"] and "profitability" in r["caveat"]


def test_recorded_manifests_agree_with_the_history():
    r = rows()
    assert r["EXP-010B"]["recorded_classification"] == "ECONOMICALLY_IMPROVED" == r["EXP-010B"]["result"]
    for experiment in ("EXP-010A", "EXP-010B"):
        manifest = json.loads((REPO / "experiments" / experiment / "manifest.json").read_text())
        assert manifest["holdout"]["touched"] is False


def test_every_linked_document_exists():
    for row in H.HISTORY:
        for doc in row["docs"]:
            assert (REPO / doc).exists(), doc
