"""Why one security ranks above another — and whether the arithmetic closes.

The module's entire claim is that the gap decomposes exactly. If the
contributions do not add back up to the gap, the explanation is describing a
different subtraction from the one the ranking performed, and every sentence
built on it is wrong in a way no reader could detect.
"""

from __future__ import annotations

import random

import pytest

from src.services.explore_ranking import overall_rank
from src.services.explore_service import ExploreRow
from src.services.rank_attribution import ATTRIBUTION_VERSION, attribute, summary


def _row(symbol: str, *, signal, confidence, risk, completeness) -> ExploreRow:
    row = ExploreRow(symbol=symbol, company_name=symbol, sector="Information Technology")
    row.signal_percentile = signal
    row.confidence = confidence
    row.risk_score = risk
    row.data_completeness = completeness
    row.overall_rank = overall_rank(
        signal_percentile=signal, confidence=confidence, risk_score=risk,
        data_completeness_pct=None if completeness is None else completeness * 100.0,
    )
    return row


# ── the identity ─────────────────────────────────────────────────────────────

def test_the_contributions_sum_to_the_gap():
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)

    result = attribute(a, b)
    assert result.unavailable_reason is None
    total = sum(c.contribution for c in result.contributions)
    assert total == pytest.approx(result.rank_gap, abs=0.01)


@pytest.mark.parametrize("seed", range(40))
def test_the_identity_holds_over_random_pairs(seed):
    """Forty random pairs, because one hand-picked example proves one example.

    This is the property that makes the explanation trustworthy, so it is
    checked against the real `overall_rank` rather than a restatement of it.
    """
    rng = random.Random(seed)

    def random_row(symbol: str) -> ExploreRow:
        return _row(
            symbol,
            signal=rng.uniform(0, 100),
            confidence=rng.randint(0, 100),
            risk=rng.randint(0, 100),
            completeness=rng.uniform(0.5, 1.0),
        )

    a, b = random_row("AAA"), random_row("BBB")
    result = attribute(a, b)
    assert result.unavailable_reason is None
    total = sum(c.contribution for c in result.contributions)
    assert total == pytest.approx(result.rank_gap, abs=0.01), (
        f"decomposition does not close: {total} vs {result.rank_gap}"
    )


def test_swapping_the_two_securities_negates_every_contribution():
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)

    forward = {c.key: c.contribution for c in attribute(a, b).contributions}
    backward = {c.key: c.contribution for c in attribute(b, a).contributions}
    assert set(forward) == set(backward)
    for key, value in forward.items():
        assert backward[key] == pytest.approx(-value, abs=1e-9)


# ── risk is the inverted term, and the sign has to be right ─────────────────

def test_lower_risk_contributes_positively():
    """The one term where a smaller raw number is the better one. Getting this
    sign wrong would say a safer security is being penalised for it."""
    safer = _row("SAFE", signal=60.0, confidence=45, risk=30, completeness=1.0)
    riskier = _row("RISKY", signal=60.0, confidence=45, risk=70, completeness=1.0)

    result = attribute(safer, riskier)
    risk_term = next(c for c in result.contributions if c.key == "risk_score")
    assert risk_term.inverted is True
    assert risk_term.difference == pytest.approx(-40.0)   # raw: safer has less
    assert risk_term.contribution > 0                     # but it helps SAFE
    assert result.leader == "SAFE"


def test_only_risk_is_inverted():
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)
    inverted = {c.key for c in attribute(a, b).contributions if c.inverted}
    assert inverted == {"risk_score"}


# ── refusals ────────────────────────────────────────────────────────────────

def test_an_unranked_security_yields_no_attribution():
    """A gap explained from three of four terms is not the gap."""
    ranked = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    unranked = _row("BBB", signal=None, confidence=44, risk=52, completeness=0.9)
    assert unranked.overall_rank is None

    result = attribute(ranked, unranked)
    assert result.contributions == []
    assert result.unavailable_reason is not None
    assert "BBB" in result.unavailable_reason
    assert result.leader is None


def test_both_unranked_names_both():
    a = _row("AAA", signal=None, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=None, confidence=44, risk=52, completeness=0.9)
    reason = attribute(a, b).unavailable_reason or ""
    assert "AAA" in reason and "BBB" in reason


def test_identical_securities_rank_level_with_no_leader():
    a = _row("AAA", signal=70.0, confidence=45, risk=50, completeness=1.0)
    b = _row("BBB", signal=70.0, confidence=45, risk=50, completeness=1.0)

    result = attribute(a, b)
    assert result.level is True
    assert result.leader is None
    assert result.rank_gap == pytest.approx(0.0, abs=0.001)
    assert all(c.contribution == pytest.approx(0.0, abs=1e-9) for c in result.contributions)
    assert "level" in summary(result)


# ── ordering and shares ─────────────────────────────────────────────────────

def test_the_largest_mover_is_first():
    a = _row("AAA", signal=95.0, confidence=45, risk=50, completeness=1.0)
    b = _row("BBB", signal=20.0, confidence=45, risk=50, completeness=1.0)
    assert attribute(a, b).contributions[0].key == "signal_percentile"


def test_shares_are_of_movement_not_of_the_gap():
    """Terms can point opposite ways. A share of a near-zero gap would be
    meaningless or enormous, so shares are of total absolute movement and
    always sum to 100."""
    a = _row("AAA", signal=90.0, confidence=30, risk=80, completeness=1.0)
    b = _row("BBB", signal=20.0, confidence=50, risk=20, completeness=1.0)

    result = attribute(a, b)
    assert sum(c.share for c in result.contributions) == pytest.approx(100.0, abs=0.3)
    assert all(0.0 <= c.share <= 100.0 for c in result.contributions)


def test_ordering_is_deterministic_on_ties():
    """Two terms contributing equally break on key, so two runs agree."""
    a = _row("AAA", signal=60.0, confidence=45, risk=50, completeness=1.0)
    b = _row("BBB", signal=60.0, confidence=45, risk=50, completeness=1.0)
    first = [c.key for c in attribute(a, b).contributions]
    second = [c.key for c in attribute(a, b).contributions]
    assert first == second


# ── what the sentence is allowed to say ─────────────────────────────────────

def test_the_summary_is_deterministic_and_mentions_no_business_reason():
    """The ranking has never looked at a business. A sentence that reached for
    market position or product quality would describe a model that does not
    exist."""
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)

    text = summary(attribute(a, b))
    assert text == summary(attribute(a, b))
    forbidden = (
        "market share", "moat", "management", "product", "competitive",
        "growth story", "brand", "innovation", "demand",
    )
    lowered = text.lower()
    for word in forbidden:
        assert word not in lowered, f"the summary reached for {word!r}: {text}"


def test_the_summary_says_when_the_largest_term_favours_the_trailing_security():
    """A term that pulled the other way must not be implied to have helped the
    leader — that would invert the reader's understanding of the gap."""
    # AAA leads on signal but is much riskier, so risk is the largest term and
    # it favours BBB.
    a = _row("AAA", signal=62.0, confidence=45, risk=95, completeness=1.0)
    b = _row("BBB", signal=50.0, confidence=45, risk=5, completeness=1.0)

    result = attribute(a, b)
    largest = result.contributions[0]
    assert largest.key == "risk_score"
    favours_leader = (largest.contribution > 0) == (result.leader == result.a)
    if not favours_leader:
        assert "despite" in summary(result)


def test_every_attribution_carries_the_rank_is_not_verdict_caveat():
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)

    result = attribute(a, b)
    assert result.version == ATTRIBUTION_VERSION
    assert "not a recommendation" in result.caveat
    # Also present on a refusal, where a reader is most likely to fill the gap
    # with their own interpretation.
    unranked = _row("CCC", signal=None, confidence=44, risk=52, completeness=0.9)
    assert "not a recommendation" in attribute(a, unranked).caveat


def test_every_component_states_what_it_is_not():
    """Confidence is not a probability of profit, risk is not a probability of
    loss, completeness is not accuracy. Each reading carries its disclaimer
    because these are the three most reliably misread numbers in the product."""
    a = _row("AAA", signal=80.0, confidence=48, risk=40, completeness=1.0)
    b = _row("BBB", signal=55.0, confidence=44, risk=52, completeness=0.9)

    readings = {c.key: c.reading for c in attribute(a, b).contributions}
    assert "not a probability of profit" in readings["confidence"]
    assert "not a probability of loss" in readings["risk_score"]
    assert "not how accurate" in readings["data_completeness_pct"]
