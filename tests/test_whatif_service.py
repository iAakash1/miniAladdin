"""What-If: the simulator must move the right way, and move nothing else."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.agents.orchestrator import attach_scorecard, scoring_inputs
from src.agents.schemas import EvidenceContext
from src.services import whatif_service as wf
from src.services.whatif_service import Lever


def _frame(drift: float, seed: int = 7, n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, 0.011, n)
    closes = 100.0 * np.cumprod(1.0 + steps)
    index = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame(
        {"Open": closes, "High": closes * 1.004, "Low": closes * 0.996,
         "Close": closes, "Volume": np.full(n, 1_000_000.0)},
        index=index,
    )


def _window_return(frame: pd.DataFrame) -> float:
    return float(frame["Close"].iloc[-1]) / float(frame["Close"].iloc[0]) - 1.0


# --- the transformation ------------------------------------------------------

@pytest.mark.parametrize("drift", [0.0012, -0.0012, 0.0])
@pytest.mark.parametrize("change", [-0.20, 0.20])
def test_momentum_shift_moves_the_window_return_by_the_requested_amount(drift, change):
    """Signed, not scaled.

    The regression this pins: scaling each daily return by (1 + change) makes a
    *falling* stock's decline shallower when momentum is supposed to weaken, so
    the score rises. It is the one bug in this module that produced entirely
    finite, plausible-looking numbers.
    """
    frame = _frame(drift)
    before = _window_return(frame)
    after = _window_return(wf._shifted_frame(frame, change))
    assert after == pytest.approx(before + change, abs=1e-6)


def test_momentum_shift_is_directional_for_a_falling_security():
    frame = _frame(-0.0012)
    assert _window_return(frame) < 0
    weaker = _window_return(wf._shifted_frame(frame, -0.20))
    stronger = _window_return(wf._shifted_frame(frame, 0.20))
    assert weaker < _window_return(frame) < stronger


def test_momentum_shift_preserves_the_ordering_of_the_days():
    """The security keeps its character and changes its destination.

    The transform is an increasing affine map on daily returns, so the ordering
    of the days and the correlation with the original series survive exactly.
    Sign is *not* preserved for every day — the measured figure is 4-8% of days
    on a 260-bar path — and the docstring says so rather than claiming a
    stronger invariant than the maths gives.
    """
    frame = _frame(0.0008)
    shifted = wf._shifted_frame(frame, -0.15)
    before = frame["Close"].pct_change().dropna().to_numpy()
    after = shifted["Close"].pct_change().dropna().to_numpy()

    assert (np.argsort(before) == np.argsort(after)).all()
    assert np.corrcoef(before, after)[0, 1] == pytest.approx(1.0, abs=1e-12)
    flipped = int((np.sign(before) != np.sign(after)).sum())
    assert flipped / len(before) < 0.15, "a shift this size should not reshape the path"


def test_momentum_shift_never_produces_a_non_positive_price():
    frame = _frame(-0.002)
    shifted = wf._shifted_frame(frame, -5.0)  # far past a total loss
    assert (shifted["Close"] > 0).all()
    assert np.isfinite(shifted["Close"].to_numpy()).all()


def test_momentum_shift_returns_the_frame_unchanged_when_it_cannot_act():
    tiny = _frame(0.001, n=2)
    assert wf._shifted_frame(tiny, -0.2) is tiny


# --- isolation: the properties the brief names ------------------------------

def _context() -> EvidenceContext:
    return attach_scorecard(
        EvidenceContext(symbol="TEST", price_frame=_frame(0.0009), macro_multiplier=1.0)
    )


def test_simulation_does_not_mutate_the_production_analysis():
    context = _context()
    card = context.scorecard
    assert card is not None
    before = (card.verdict, card.raw_score, card.confidence, card.risk_score,
              card.data_completeness)
    frame_before = context.price_frame.copy(deep=True)

    for preset in wf.PRESETS:
        wf.simulate(context, lever=preset["lever"], change=preset["change"])

    after = (context.scorecard.verdict, context.scorecard.raw_score,
             context.scorecard.confidence, context.scorecard.risk_score,
             context.scorecard.data_completeness)
    assert after == before
    assert context.scorecard is card, "the stored scorecard object was replaced"
    assert frame_before.equals(context.price_frame), "the shared price frame was mutated"


def test_simulation_does_not_modify_the_explore_snapshot():
    """Explore's ranking is built from stored snapshots; a simulation must not
    reach them. Asserted by running the whole preset set against a live import
    of the service and checking its cache is untouched."""
    from src.services import explore_service

    before = getattr(explore_service, "_CACHE", None)
    before_copy = dict(before) if isinstance(before, dict) else before

    context = _context()
    for preset in wf.PRESETS:
        wf.simulate(context, lever=preset["lever"], change=preset["change"])

    after = getattr(explore_service, "_CACHE", None)
    if isinstance(before_copy, dict):
        assert dict(after) == before_copy
    else:
        assert after is before


def test_simulated_baseline_is_the_production_scorecard():
    """The "current" column must be the scorecard, not a reconstruction of it.

    They share an input builder, so this asserts the sharing actually holds
    rather than trusting that two argument lists stayed in step.
    """
    context = _context()
    result = wf.simulate(context, lever=Lever.MACRO_REGIME, change=0.3)
    assert result is not None
    assert result.current_score == context.scorecard.raw_score
    assert result.current_signal == context.scorecard.verdict
    assert result.current_confidence == context.scorecard.confidence
    assert result.current_risk == context.scorecard.risk_score


def test_scoring_inputs_covers_every_argument_attach_scorecard_would_pass():
    """Drift guard. If a future input is added to scoring, both callers get it."""
    context = _context()
    keys = set(scoring_inputs(context))
    assert {"srm", "price", "pe_ratio", "forward_pe", "analyst_target", "beta",
            "sentiment_avg", "headline_count", "spy_frame"} <= keys


# --- honesty about no-ops ----------------------------------------------------

def test_absent_sentiment_is_reported_not_invented():
    context = _context()  # no headlines
    result = wf.simulate(context, lever=Lever.SENTIMENT, change=-0.4)
    assert result is not None
    assert result.simulated_score == result.current_score
    assert "no scored headlines" in (result.note or "").lower()


def test_an_easing_regime_that_cannot_move_the_score_says_why():
    """The macro gate is one-sided: stress subtracts, calm does not add. A
    reader who sees an unchanged number without that sentence concludes the
    simulator is broken."""
    context = _context()
    result = wf.simulate(context, lever=Lever.MACRO_REGIME, change=-0.2)
    assert result is not None
    assert result.simulated_score == result.current_score
    assert "only ever subtracts" in (result.note or "")


def test_macro_stress_withdraws_credit_only_from_bullish_momentum():
    """Both halves of the gate's asymmetry, on fixtures chosen to show each.

    The engine gates the momentum sleeve on the bullish side only — stress
    taking credit away from an already-bearish reading would make stress a
    bullish input. So the score falls for a rising security and is untouched
    for a falling one, and the note has to distinguish the two or an unmoved
    number next to a moved dial reads as a broken simulator.
    """
    rising = attach_scorecard(
        EvidenceContext(symbol="UP", price_frame=_frame(0.004, seed=3),
                        macro_multiplier=1.0)
    )
    assert rising.scorecard.momentum_score > 0
    stressed = wf.simulate(rising, lever=Lever.MACRO_REGIME, change=0.3)
    assert stressed is not None
    assert stressed.simulated_score < stressed.current_score
    assert "gate" in (stressed.note or "").lower()

    falling = _context()  # momentum reading is negative on this fixture
    assert falling.scorecard.momentum_score < 0
    unmoved = wf.simulate(falling, lever=Lever.MACRO_REGIME, change=0.3)
    assert unmoved is not None
    assert unmoved.simulated_score == unmoved.current_score
    assert "bullish momentum only" in (unmoved.note or "")


# --- contract ----------------------------------------------------------------

def test_every_result_is_labelled_a_simulation():
    context = _context()
    for preset in wf.PRESETS:
        result = wf.simulate(context, lever=preset["lever"], change=preset["change"])
        assert result is not None and result.simulation is True
        assert result.version == wf.WHATIF_VERSION


def test_no_baseline_yields_no_simulation_rather_than_an_invented_one():
    assert wf.simulate(EvidenceContext(symbol="X"), lever=Lever.MOMENTUM, change=-0.2) is None


def test_every_preset_is_reachable_by_key_and_carries_its_magnitude():
    payload = wf.presets_payload()
    assert len(payload) == len(wf.PRESETS)
    for entry in payload:
        assert wf.preset(entry["key"]) is not None
        assert isinstance(entry["change"], float) and entry["change"] != 0.0
    assert wf.preset("no_such_scenario") is None


def test_every_note_states_a_number_or_says_there_was_nothing_to_move():
    """A simulation whose size is invisible cannot be interpreted.

    The label carries plain language and the note carries the arithmetic —
    before and after, in the lever's own units — because for macro and news
    tone the honest magnitude is on an internal scale that does not belong in a
    headline. A lever with no input to move says exactly that instead.
    """
    context = _context()
    for preset in wf.PRESETS:
        result = wf.simulate(context, lever=preset["lever"], change=preset["change"])
        assert result is not None
        note = result.note or ""
        assert note, f"{preset['key']} produced no explanation"
        states_number = any(ch.isdigit() for ch in note)
        says_nothing_to_move = "nothing to move" in note.lower()
        assert states_number or says_nothing_to_move, f"{preset['key']}: {note}"
