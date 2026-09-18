"""Decision quality: whether the evidence is trustworthy, not whether it is
good news. INSUFFICIENT must be exactly the eligibility gate, not a second,
slightly different one."""

from __future__ import annotations

import pytest

from src.services import decision_quality, explore_eligibility

ELIGIBLE_BASE = dict(
    asset_type="common_equity", bars=200, price=100.0, price_age_days=0.5,
    has_scorecard=True,
)


def test_insufficient_is_exactly_the_eligibility_gate():
    """Same call, same reasons, for every individual failing input — proven
    by sweeping each gate independently rather than asserting one example."""
    cases = [
        dict(ELIGIBLE_BASE, data_completeness=0.30, confidence=60),  # thin data
        dict(ELIGIBLE_BASE, data_completeness=0.90, confidence=10),  # unsure engine
        dict(ELIGIBLE_BASE, bars=10, data_completeness=0.90, confidence=60),  # short history
        dict(ELIGIBLE_BASE, price_age_days=30.0, data_completeness=0.90, confidence=60),  # stale
        dict(ELIGIBLE_BASE, has_scorecard=False, data_completeness=0.90, confidence=60),
        dict(ELIGIBLE_BASE, data_completeness=0.90, confidence=60, validation_state="CONFLICTED"),
    ]
    for kwargs in cases:
        eligibility = explore_eligibility.assess(**kwargs)
        assert not eligibility.eligible, f"fixture was meant to be ineligible: {kwargs}"
        quality = decision_quality.assess(**kwargs)
        assert quality.grade == "INSUFFICIENT"
        assert quality.reasons == eligibility.reasons


def test_eligible_securities_are_never_insufficient():
    quality = decision_quality.assess(
        **ELIGIBLE_BASE, data_completeness=0.60, confidence=26,
    )
    assert quality.grade != "INSUFFICIENT"


def test_full_completeness_and_ample_confidence_margin_is_strong():
    quality = decision_quality.assess(
        **ELIGIBLE_BASE, data_completeness=1.0, confidence=50,
    )
    assert quality.grade == "STRONG"


def test_barely_clearing_the_confidence_floor_is_weak_even_with_full_data():
    """Full data completeness cannot buy back a confidence reading the engine
    itself is barely past being unsure about — the two are independent
    signals and one cannot substitute for the other silently."""
    quality = decision_quality.assess(
        **ELIGIBLE_BASE,
        data_completeness=1.0,
        confidence=explore_eligibility.MIN_CONFIDENCE + 1,  # 26: just past the gate
    )
    assert quality.grade == "WEAK"


def test_barely_clearing_the_completeness_floor_is_weak_even_with_high_confidence():
    quality = decision_quality.assess(
        **ELIGIBLE_BASE,
        data_completeness=explore_eligibility.MIN_DATA_COMPLETENESS + 0.01,
        confidence=90,
    )
    assert quality.grade == "WEAK"


def test_a_resolved_but_previously_partial_validation_state_does_not_force_weak():
    # PARTIAL is not in the two conflicted states explore_eligibility (or this
    # module) treats as disqualifying evidence; only CONFLICTED/UNSUPPORTED do.
    quality = decision_quality.assess(
        **ELIGIBLE_BASE, data_completeness=1.0, confidence=50, validation_state="PARTIAL",
    )
    assert quality.grade == "STRONG"


def test_an_unsupported_validation_state_is_insufficient_not_weak():
    """CONFLICTED/UNSUPPORTED already fail the shared eligibility gate before
    grading is reached at all — there is no separate WEAK-for-conflict path,
    because that would be a second judgement about the same fact the gate
    already made. High completeness and confidence do not buy this back."""
    quality = decision_quality.assess(
        **ELIGIBLE_BASE, data_completeness=1.0, confidence=90, validation_state="UNSUPPORTED",
    )
    assert quality.grade == "INSUFFICIENT"
    assert "unresolved_evidence_conflict" in quality.reasons


@pytest.mark.parametrize("grade", ["STRONG", "ACCEPTABLE", "WEAK"])
def test_every_eligible_grade_has_a_summary_with_no_profit_language(grade):
    """Never a probability-of-profit or probability-of-loss claim, on any grade."""
    fixtures = {
        "STRONG": dict(data_completeness=1.0, confidence=50),
        "ACCEPTABLE": dict(data_completeness=0.75, confidence=35),
        "WEAK": dict(data_completeness=0.56, confidence=26),
    }
    quality = decision_quality.assess(**ELIGIBLE_BASE, **fixtures[grade])
    assert quality.grade == grade
    forbidden = ("chance of", "probability", "% likely", "guaranteed", "will rise", "will fall")
    lowered = quality.summary.lower()
    for phrase in forbidden:
        assert phrase not in lowered, f"{grade} summary reads as a probability claim: {quality.summary}"


def test_insufficient_summary_matches_the_demo_language():
    quality = decision_quality.assess(
        **ELIGIBLE_BASE, data_completeness=0.10, confidence=None,
    )
    assert quality.grade == "INSUFFICIENT"
    assert "excluded from Top Ranked Ideas" in quality.summary


def test_grading_is_deterministic():
    kwargs = dict(ELIGIBLE_BASE, data_completeness=0.8, confidence=40)
    assert decision_quality.assess(**kwargs) == decision_quality.assess(**kwargs)
