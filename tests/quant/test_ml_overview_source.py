"""
The Models workspace must render a named, valid study — and must never call an
overfitting control the best model.

Two production defects, found together:

1. `/api/ml/overview` read `data/research/reports/study.json`, a standalone
   artifact generated before the as-of fix and carrying no experiment id. With
   nothing to key on but its dataset version, `study_validity` correctly marked
   it VOID — so the leaderboard, walk-forward, cost and regime sections were
   rendering the invalidated EXP-002 study under headings that did not say which
   study they were. EXP-004 onward were on disk, valid, and unused.

2. Once it pointed at valid data, the headline became `gradient_boosting_deep` —
   the deliberately over-parameterised control, which tops an IC-ordered
   leaderboard *because* it memorises the training fold. Reading row zero named
   the one model in the ladder that exists to prove the diagnostic fires.
"""

from __future__ import annotations

import json

import pytest

from src.services import ml_service


def test_the_newest_valid_experiment_is_selected():
    found = ml_service._newest_valid_experiment()
    assert found is not None, "EXP-004 onward are on disk and must be found"
    experiment_id, artifact = found
    assert experiment_id not in ml_service.VOID_EXPERIMENT_IDS
    assert artifact.name == "metrics.json"


def test_the_overview_names_the_study_it_renders():
    overview = ml_service.overview()
    assert overview["status"] == "available"
    assert overview["experiment_id"], "a page that cannot name its study served a void one"
    assert overview["source_artifact"]


def test_the_rendered_study_is_not_void():
    overview = ml_service.overview()
    assert overview["validity"]["valid"] is True


def test_the_overfitting_control_is_never_the_headline():
    """The regression that matters most.

    The control stays in the leaderboard table, where its gap makes the point it
    exists to make. It may not be called best.
    """
    overview = ml_service.overview()
    assert overview["labels"], "expected at least one label with a leaderboard"
    for headline in overview["labels"]:
        assert headline["best_model"] not in ml_service.OVERFIT_CONTROL_MODELS


def test_headline_selection_skips_controls_in_order():
    board = [
        {"model_id": "gradient_boosting_deep", "mean_ic": 0.9},
        {"model_id": "random_forest", "mean_ic": 0.04},
        {"model_id": "ridge", "mean_ic": 0.01},
    ]
    assert ml_service._headline_model(board)["model_id"] == "random_forest"


def test_a_board_of_only_controls_has_no_best_model():
    """Falling back to the control would defeat the exclusion."""
    board = [{"model_id": "gradient_boosting_deep", "mean_ic": 0.9}]
    assert ml_service._headline_model(board) is None


def test_a_void_experiment_directory_is_skipped(tmp_path, monkeypatch):
    void = tmp_path / "EXP-002"
    void.mkdir()
    (void / "metrics.json").write_text(json.dumps({
        "experiment": {"experiment_id": "EXP-002"},
        "labels": {"fwd_rank_21": {"leaderboard": [{"model_id": "ridge"}]}},
        "generated_at": "2099-01-01T00:00:00+00:00",   # newest by far
    }), encoding="utf-8")
    monkeypatch.setattr(ml_service, "EXPERIMENTS_ROOT", tmp_path)
    assert ml_service._newest_valid_experiment() is None, (
        "a void study must never be selected, however recent"
    )
