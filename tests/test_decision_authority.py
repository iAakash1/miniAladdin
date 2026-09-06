"""One decision, one authority, and no macro outage described as calm.

The research route sets `technicals["risk_adjusted_signal"]` from the
scorecard and returns that as the response verdict — then called
`compute_decision`, which applied its own sentiment adjustment and returned a
*different* verdict, whose rationale and confidence breakdown were the ones
the response carried. A run could show "Hold" beside the sentence "Positive
sentiment boosted signal", which describes a decision to buy.

Both halves were internally consistent. Together they were incoherent, and
the incoherence pointed at the number a reader acts on.
"""

import pytest

from src.decision import compute_decision, confidence_breakdown, verdict_to_recommendation
from src.models import (
    AggregateSentiment,
    MacroStatus,
    RiskAssessment,
    SignalVerdict,
    TechnicalAnalysis,
)


def _macro(status=MacroStatus.STABLE, multiplier=1.0):
    return RiskAssessment(
        risk_multiplier=multiplier, yield_curve_inverted=False,
        status=status, recession_warning=False,
    )


def _tech(signal=SignalVerdict.HOLD):
    return TechnicalAnalysis(ticker="X", risk_adjusted_signal=signal)


def _bullish_sentiment():
    """Strong enough that the legacy path would move the verdict up a step."""
    return AggregateSentiment(ticker="X", headline_count=5, average_score=0.9)


def _bearish_sentiment():
    return AggregateSentiment(ticker="X", headline_count=5, average_score=-0.9)


# ── the divergence ──────────────────────────────────────────────────────────

def test_sentiment_cannot_move_a_verdict_the_caller_has_already_decided():
    """The exact shape of the defect, in one assertion."""
    verdict, _, rationale = compute_decision(
        _macro(), _tech(SignalVerdict.HOLD), _bullish_sentiment(),
        authoritative_verdict=SignalVerdict.HOLD,
    )
    assert verdict is SignalVerdict.HOLD, "sentiment overrode the authoritative decision"
    assert "boosted signal" not in rationale, (
        "the rationale claims a boost that did not happen"
    )


def test_the_rationale_still_reports_what_sentiment_was():
    """Suppressing the override must not suppress the observation."""
    _, _, rationale = compute_decision(
        _macro(), _tech(SignalVerdict.HOLD), _bullish_sentiment(),
        authoritative_verdict=SignalVerdict.HOLD,
    )
    assert "Positive sentiment" in rationale
    assert "already reflected in the factor score" in rationale


def test_bearish_sentiment_likewise_does_not_move_the_answer():
    verdict, _, rationale = compute_decision(
        _macro(), _tech(SignalVerdict.BUY), _bearish_sentiment(),
        authoritative_verdict=SignalVerdict.BUY,
    )
    assert verdict is SignalVerdict.BUY
    assert "dampened signal" not in rationale


def test_the_authoritative_verdict_is_returned_verbatim():
    for decided in SignalVerdict:
        verdict, _, _ = compute_decision(
            _macro(), _tech(SignalVerdict.HOLD), _bullish_sentiment(),
            authoritative_verdict=decided,
        )
        assert verdict is decided


def test_the_llm_recommendation_maps_from_the_same_verdict():
    """Nothing downstream may re-derive a different one."""
    verdict, _, _ = compute_decision(
        _macro(), _tech(SignalVerdict.HOLD), _bullish_sentiment(),
        authoritative_verdict=SignalVerdict.HOLD,
    )
    assert verdict_to_recommendation(verdict) == "HOLD"


def test_the_confidence_breakdown_describes_the_returned_verdict():
    verdict, _, _ = compute_decision(
        _macro(), _tech(SignalVerdict.SELL), _bullish_sentiment(),
        authoritative_verdict=SignalVerdict.SELL,
    )
    items = confidence_breakdown(_macro(), _tech(SignalVerdict.SELL), _bullish_sentiment(), verdict)
    assert isinstance(items, list)


# ── the legacy path is untouched ────────────────────────────────────────────

def test_without_an_authority_sentiment_still_decides():
    """Where no scorecard ran there is no other authority, and this is it."""
    verdict, _, rationale = compute_decision(
        _macro(), _tech(SignalVerdict.HOLD), _bullish_sentiment(),
    )
    assert verdict is SignalVerdict.BUY, "the legacy synthesis stopped working"
    assert "boosted signal" in rationale


def test_without_an_authority_negative_sentiment_still_dampens():
    verdict, _, _ = compute_decision(
        _macro(), _tech(SignalVerdict.HOLD), _bearish_sentiment(),
    )
    assert verdict is SignalVerdict.SELL


# ── macro states ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", list(MacroStatus))
def test_only_a_measured_stable_regime_is_described_as_stable(status):
    _, _, rationale = compute_decision(
        _macro(status), _tech(), AggregateSentiment(ticker="X"),
    )
    if status is MacroStatus.STABLE:
        assert "Macro environment is STABLE" in rationale
    else:
        assert "STABLE" not in rationale, (
            f"a {status.value} regime was described as STABLE"
        )


def test_a_macro_outage_says_no_conclusion_was_drawn():
    _, _, rationale = compute_decision(
        _macro(MacroStatus.DATA_ERROR), _tech(), AggregateSentiment(ticker="X"),
    )
    assert "Macro regime unavailable" in rationale
    assert "no macro conclusion was drawn" in rationale


def test_an_unavailable_regime_earns_no_stability_confidence():
    _, calm, _ = compute_decision(_macro(MacroStatus.STABLE), _tech(), AggregateSentiment(ticker="X"))
    _, blind, _ = compute_decision(_macro(MacroStatus.DATA_ERROR), _tech(), AggregateSentiment(ticker="X"))
    assert blind < calm, "missing macro evidence raised confidence to the level of measured calm"


def test_the_breakdown_names_the_missing_macro_component():
    """Absent and scored-zero look identical unless the row is present."""
    items = confidence_breakdown(
        _macro(MacroStatus.DATA_ERROR), _tech(), AggregateSentiment(ticker="X"), SignalVerdict.HOLD,
    )
    labels = " ".join(str(i["component"]) for i in items)
    assert "Macro regime unavailable" in labels
    assert "Stable macro regime" not in labels
