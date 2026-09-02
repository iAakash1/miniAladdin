"""
The preflight read layer: exposes the gates without becoming a way to spend the
holdout.

Nine integrity gates decided whether the holdout may be opened, and they were
reachable only from a CLI — the most direct answer this product has to "can this
research be trusted", invisible to it.

The tests that matter here are the safety ones. This surface must never claim to
be the gate the holdout runner requires, and must never be a path to opening it.
"""

from __future__ import annotations

from pathlib import Path

from src.services import quant_preflight_service as service


def test_the_gates_are_reported():
    result = service.preflight()
    assert result["available"] is True
    assert len(result["checks"]) >= 8
    for check in result["checks"]:
        assert {"check", "passed", "blocking", "detail"} <= set(check)


def test_this_surface_is_never_valid_for_an_actual_run():
    """The single most important assertion in this file.

    A fast preflight omits the contamination probe — the check that found the
    as-of join defect which voided EXP-002. Reporting it as sufficient would
    invite opening the holdout on a weaker gate than the runner demands.
    """
    result = service.preflight()
    assert result["valid_for_run"] is False
    assert result["contamination_probe"]["run"] is False
    assert "voided EXP-002" in result["contamination_probe"]["why"]


def test_the_fast_flag_is_named_so_it_cannot_be_mistaken_for_readiness():
    """`ready` from the underlying report is a weaker claim on this path."""
    result = service.preflight()
    assert "fast_gates_clear" in result
    assert "ready" not in result, "the stronger word must not leak through"


def test_it_gates_the_newest_valid_study_not_the_void_one():
    resolved = service._newest_valid_study()
    assert resolved is not None
    experiment_id, artifact = resolved
    assert experiment_id not in service.VOID_EXPERIMENT_IDS
    assert artifact.exists()

    result = service.preflight()
    assert result["experiment_id"] == experiment_id


def test_a_void_study_is_never_selected(tmp_path, monkeypatch):
    import json

    void = tmp_path / "EXP-002"
    void.mkdir()
    (void / "metrics.json").write_text(json.dumps({
        "experiment": {"experiment_id": "EXP-002"},
        "labels": {"fwd_rank_21": {"leaderboard": []}},
        "generated_at": "2099-01-01T00:00:00+00:00",
    }), encoding="utf-8")
    monkeypatch.setattr(service, "EXPERIMENTS_ROOT", tmp_path)
    assert service._newest_valid_study(tmp_path) is None


def test_a_missing_study_reports_unavailable_rather_than_passing(monkeypatch, tmp_path):
    """No study means nothing to gate — never a clear result."""
    monkeypatch.setattr(service, "EXPERIMENTS_ROOT", tmp_path / "absent")
    monkeypatch.setattr(service, "LEGACY_STUDY", tmp_path / "nothing.json")
    result = service.preflight()
    assert result["available"] is False
    assert "nothing to gate" in result["detail"]


def test_the_note_states_that_clearing_gates_promotes_nothing():
    result = service.preflight()
    assert "does not open the holdout" in result["note"]
    assert "does not promote" in result["note"]


def test_root_constants_are_resolved_at_call_time_not_import_time():
    """A recurring trap in this codebase, pinned.

    `def f(root: Path = MODULE_CONSTANT)` binds at import, so
    `monkeypatch.setattr(module, "MODULE_CONSTANT", ...)` is accepted and
    silently ignored — the override appears to work and does nothing. It was
    written three times here before being caught each time by a test that
    expected the override to take effect.

    Numeric tuning constants used as defaults are fine; the trap is specific to
    roots a test or a deployment needs to redirect.
    """
    import inspect

    from src.services import ml_service

    for module, function in (
        (service, service._newest_valid_study),
        (ml_service, ml_service._newest_valid_experiment),
    ):
        signature = inspect.signature(function)
        default = signature.parameters["root"].default
        assert default is None, (
            f"{function.__name__} defaults `root` to {default!r}; it must default "
            "to None and resolve the module constant inside the body, or an "
            "override of that constant will be silently ignored"
        )
