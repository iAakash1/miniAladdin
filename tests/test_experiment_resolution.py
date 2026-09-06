"""List, detail and latest must agree about an experiment.

Two readers decided the artifact shape independently. `experiments()` knew
about the selection shape and reported EXP-007 as complete; `experiment()`
read only `metrics.json` and answered "no artifact for EXP-007" for the same
experiment in the same request cycle. `latest()` compounded it — it picks the
newest completed experiment from the first reader and loads it through the
second, so the landing page's own selection was the one thing it could not
open.

EXP-007 is the experiment whose recorded verdict is NO PRODUCTION CANDIDATE.
It is the result this product is built around, and it was unopenable.
"""

import json

import pytest

from src.services import quant_service
from src.services.quant_service import resolve_experiment_artifact


def _rows(out):
    return out["experiments"] if isinstance(out, dict) and "experiments" in out else out


# ── the resolver ────────────────────────────────────────────────────────────

def test_a_search_shaped_experiment_resolves_to_its_selection_artifact():
    artifact = resolve_experiment_artifact("EXP-007")
    assert artifact is not None, "EXP-007 has a recorded result and did not resolve"
    assert artifact.shape == "selection"
    assert artifact.experiment_id == "EXP-007"


def test_a_metrics_shaped_experiment_still_resolves_to_metrics():
    artifact = resolve_experiment_artifact("EXP-006")
    assert artifact is not None
    assert artifact.shape == "metrics"


def test_an_experiment_with_no_artifact_resolves_to_nothing(tmp_path):
    (tmp_path / "EXP-999").mkdir()
    assert resolve_experiment_artifact("EXP-999", tmp_path) is None


# ── the three readers agree ─────────────────────────────────────────────────

def test_the_detail_view_opens_the_search_shaped_experiment():
    detail = quant_service.experiment("EXP-007")
    assert detail["status"] == "complete", (
        f"experiment('EXP-007') answered {detail.get('detail') or detail['status']!r}"
    )
    assert detail["experiment_id"] == "EXP-007"


def test_latest_returns_the_experiment_it_selected():
    latest = quant_service.latest()
    assert latest["status"] == "complete", "latest() could not open its own selection"
    assert latest["experiment_id"] == "EXP-007"


def test_list_detail_and_latest_report_the_same_state():
    row = next(r for r in _rows(quant_service.experiments()) if r["experiment_id"] == "EXP-007")
    detail = quant_service.experiment("EXP-007")
    latest = quant_service.latest()
    for key in ("status", "artifact", "verdict", "verdict_passed", "holdout_touched"):
        assert row.get(key) == detail.get(key) == latest.get(key), (
            f"the three readers disagree about {key}: "
            f"{row.get(key)!r} / {detail.get(key)!r} / {latest.get(key)!r}"
        )


# ── the recorded result is carried verbatim ─────────────────────────────────

def test_the_verdict_matches_the_artifact_on_disk_exactly():
    with open("artifacts/experiments/EXP-007/final_selection.json") as fh:
        recorded = json.load(fh)["verdict"]
    for view in (quant_service.experiment("EXP-007"), quant_service.latest()):
        assert view["verdict"] == recorded["status"] == "NO PRODUCTION CANDIDATE"
        assert view["verdict_passed"] == recorded["passed"] is False


def test_the_holdout_is_reported_untouched_everywhere():
    for view in (quant_service.experiment("EXP-007"), quant_service.latest()):
        assert view["holdout_touched"] is False


def test_no_reader_reports_a_passing_experiment():
    """The firewall, at every read path."""
    views = _rows(quant_service.experiments()) + [
        quant_service.experiment("EXP-007"), quant_service.latest(),
    ]
    for view in views:
        assert view.get("verdict_passed") is not True, (
            f"{view.get('experiment_id')} is reported as having passed its gates"
        )


def test_the_detail_view_says_where_the_full_record_lives():
    detail = quant_service.experiment("EXP-007")
    assert detail["detail_endpoint"] == "/api/quant/selection/EXP-007"


def test_an_unknown_experiment_is_still_unavailable():
    """The honest empty state survives; this is not a blanket 'assume complete'."""
    out = quant_service.experiment("EXP-DOES-NOT-EXIST")
    assert out["status"] == "unavailable"
