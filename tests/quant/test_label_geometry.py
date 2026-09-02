"""
Label geometry: the dependence structure a forward label imposes on itself.

A label spanning H sessions sampled every S sessions makes consecutive
observations share (H − S)/H of their outcome. That one ratio determines the
purge, the embargo's justification, and the bootstrap block length — three
things that were being derived by hand in three places, with the bootstrap block
hardcoded in a service module where it could drift from the study it described.

It had also drifted in the safe-looking direction: `21 // 5` floors to 4, which
leaves dependence inside the resample and narrows the confidence interval. The
ceiling is 5.
"""

from __future__ import annotations

import pytest

from src.quant.labels.geometry import LabelGeometry, geometry_for, horizon_from_target


# ── horizon parsing ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("target,expected", [
    ("fwd_rank_21", 21), ("fwd_ret_5", 5), ("fwd_ret_63", 63), ("fwd_vol_21", 21),
])
def test_the_horizon_is_read_from_the_target_name(target, expected):
    assert horizon_from_target(target) == expected


@pytest.mark.parametrize("target", ["prediction", "fwd_rank", "", "fwd_ret_x"])
def test_a_nameless_horizon_refuses_rather_than_defaulting(target):
    """A guessed horizon yields a wrong purge and a wrong block silently."""
    assert horizon_from_target(target) is None
    assert geometry_for(target, step_sessions=5) is None


# ── the arithmetic ───────────────────────────────────────────────────────────

def test_overlap_matches_the_project_configuration():
    g = geometry_for("fwd_rank_21", step_sessions=5, embargo_sessions=5)
    assert g.overlapping_sessions == 16
    assert g.overlap_fraction == pytest.approx(16 / 21)


def test_the_block_rounds_up_not_down():
    """The correction. floor(21/5) = 4 leaves dependence in the resample."""
    g = geometry_for("fwd_rank_21", step_sessions=5)
    assert g.block_length == 5, "must be ceil(21/5), not floor"


def test_a_non_overlapping_label_needs_no_block():
    """Horizon equal to the step means consecutive labels share nothing."""
    g = geometry_for("fwd_ret_5", step_sessions=5)
    assert g.overlapping_sessions == 0
    assert g.overlap_fraction == 0.0
    assert g.block_length == 1


def test_purge_equals_the_horizon():
    """A label formed on the last training date resolves `horizon` later."""
    g = geometry_for("fwd_rank_21", step_sessions=5)
    assert g.purge_sessions == 21


def test_independent_observations_are_not_overstated():
    """The direction of the estimate matters more than its sharpness."""
    g = geometry_for("fwd_rank_21", step_sessions=5)
    assert g.independent_observations(404) == 80
    assert g.independent_observations(404) < 404
    assert g.independent_observations(0) == 0


def test_the_explanation_is_derived_not_written():
    g = geometry_for("fwd_rank_21", step_sessions=5, embargo_sessions=5)
    why = g.as_dict()["why"]
    for fragment in ("21-session", "every 5", "16 of 21", "76%"):
        assert fragment in why, f"{fragment!r} must be derived into the explanation"


def test_the_independence_note_states_what_significance_is_claimed_against():
    payload = geometry_for("fwd_rank_21", step_sessions=5).as_dict(observations=404)
    assert "against 80, not 404" in payload["independence_note"]


# ── guards ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("step", [0, -1])
def test_a_nonsensical_cadence_refuses(step):
    assert geometry_for("fwd_rank_21", step_sessions=step) is None


def test_a_step_longer_than_the_horizon_still_yields_one_block():
    g = LabelGeometry("fwd_ret_5", horizon_sessions=5, step_sessions=21, embargo_sessions=0)
    assert g.overlapping_sessions == 0
    assert g.block_length == 1


def test_the_served_series_derives_its_block_from_the_experiment():
    """No hardcoded horizon in the service layer."""
    from src.services import quant_series

    served = quant_series.fold_series("EXP-006", "gradient_boosting")
    if served.get("status") != "ok":
        pytest.skip("EXP-006 predictions not present in this checkout")

    geometry = served["label_geometry"]
    assert geometry["horizon_sessions"] == 21
    assert geometry["step_sessions"] == 5
    assert geometry["block_length"] == 5
    assert f"block={geometry['block_length']}" in served["pooled_ic"]["method"]
