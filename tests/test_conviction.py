"""High Conviction: several independent things agreeing, not a stronger buy.

The tier does not touch the authoritative signal. It asks whether the evidence
*around* a positive signal is unusually well aligned, which is a different and
genuinely useful question — a Buy on thin evidence at high risk with no history
behind it is a materially different proposition from a Buy where all four
agree.

The property that makes it honest is that missing values block. A conviction
tier that treated silence as agreement would hand its strongest label to the
securities it understands least, which is the exact inversion this codebase
keeps having to defend against.
"""

import pytest

from src.services import conviction
from src.services.conviction import CONVICTION_POLICY_VERSION, DEFAULT_THRESHOLDS, assess


def _case(**kw):
    base = dict(
        model_signal="Buy", overall_rank=82.0, confidence=48, risk_score=40,
        data_completeness=1.0, performance_score=70.0, validation_state="VERIFIED",
        price_stale=False,
    )
    base.update(kw)
    return assess(**base)


# ── the thresholds are measured, not chosen ──────────────────────────────────

def test_the_confidence_bar_is_reachable_on_this_engine():
    """The obvious sketch for this feature used confidence >= 75, which
    qualifies nobody: the engine decays every reading multiplicatively from
    100 through eight factors, and the live maximum observed was 51. A gate
    nobody passes is not strict, it is broken."""
    assert DEFAULT_THRESHOLDS.min_confidence <= 51


def test_the_rank_bar_sits_in_the_top_quartile():
    """p75 of the live distribution was 68.2 and p90 was 74.6."""
    assert 68.0 <= DEFAULT_THRESHOLDS.min_overall_rank <= 75.0


def test_the_policy_is_versioned():
    """A security that qualified yesterday and not today may be a market
    change or a policy change, and the version is how a reader tells them
    apart."""
    assert _case().policy_version == CONVICTION_POLICY_VERSION


# ── what qualifies ───────────────────────────────────────────────────────────

def test_a_well_aligned_positive_case_qualifies():
    verdict = _case()
    assert verdict.qualifies
    assert verdict.blocked_by == []
    assert len(verdict.met) >= 6


def test_the_reasons_are_reported_in_the_reader_s_language():
    verdict = _case()
    blob = " ".join(verdict.met).lower()
    assert "model signal" in blob and "confidence" in blob and "risk" in blob


# ── what does not ────────────────────────────────────────────────────────────

def test_past_performance_alone_cannot_qualify_a_hold():
    """The headline rule. Strong history beside a Hold is a real state and must
    not be promoted into a conviction idea."""
    verdict = _case(model_signal="Hold", performance_score=99.0, overall_rank=95.0)
    assert not verdict.qualifies
    assert any("not a buy" in b for b in verdict.blocked_by)


def test_past_performance_alone_cannot_qualify_a_sell():
    verdict = _case(model_signal="Sell", performance_score=99.0)
    assert not verdict.qualifies


@pytest.mark.parametrize("field", [
    "overall_rank", "confidence", "risk_score", "data_completeness", "performance_score",
])
def test_a_missing_measurement_blocks_rather_than_passes(field):
    """Silence is not agreement."""
    verdict = _case(**{field: None})
    assert not verdict.qualifies, field
    assert verdict.blocked_by


def test_unmeasured_risk_says_so_rather_than_implying_safety():
    verdict = _case(risk_score=None)
    assert any("not the same as it being low" in b for b in verdict.blocked_by)


def test_high_risk_blocks():
    verdict = _case(risk_score=DEFAULT_THRESHOLDS.max_risk_score)
    assert not verdict.qualifies
    assert any("high band" in b for b in verdict.blocked_by)


def test_a_conflicted_evidence_state_blocks():
    assert not _case(validation_state="CONFLICTED").qualifies
    assert not _case(validation_state="UNSUPPORTED").qualifies


def test_a_stale_price_blocks():
    verdict = _case(price_stale=True)
    assert not verdict.qualifies
    assert any("stale" in b for b in verdict.blocked_by)


def test_a_near_miss_reports_exactly_what_it_was_missing():
    """So the interface can say why this one did not make it, rather than
    leaving a reader to guess which of seven conditions failed."""
    verdict = _case(confidence=10)
    assert not verdict.qualifies
    assert len(verdict.blocked_by) == 1
    assert "confidence" in verdict.blocked_by[0]
    assert len(verdict.met) >= 5


# ── the tier is rare, and does not invent members ────────────────────────────

def test_an_empty_conviction_tier_is_the_feature_working():
    from src.services.explore_service import ExploreRow, ExploreSnapshot, high_conviction

    rows = [
        ExploreRow(symbol="A", company_name="A", sector="Energy", eligible=True,
                   high_conviction=False, overall_rank=90.0),
        ExploreRow(symbol="B", company_name="B", sector="Energy", eligible=True,
                   high_conviction=False, overall_rank=88.0),
    ]
    snapshot = ExploreSnapshot(
        generated_at="2026-09-12T00:00:00+00:00", universe_version="us-v1",
        rows=rows, eligible_count=2, evaluated_count=2,
    )
    assert high_conviction(snapshot, 5) == []


def test_conviction_ordering_is_deterministic():
    """Ties break on ticker, so two runs over one snapshot agree."""
    from src.services.explore_service import ExploreRow, ExploreSnapshot, high_conviction

    rows = [
        ExploreRow(symbol="ZZZ", company_name="Z", sector="Energy", eligible=True,
                   high_conviction=True, overall_rank=80.0),
        ExploreRow(symbol="AAA", company_name="A", sector="Energy", eligible=True,
                   high_conviction=True, overall_rank=80.0),
    ]
    snapshot = ExploreSnapshot(
        generated_at="2026-09-12T00:00:00+00:00", universe_version="us-v1",
        rows=rows, eligible_count=2, evaluated_count=2,
    )
    assert [r.symbol for r in high_conviction(snapshot, 5)] == ["AAA", "ZZZ"]


def test_conviction_does_not_alter_the_signal():
    """It is a label on the evidence, not a promotion of the verdict."""
    import inspect

    source = inspect.getsource(conviction)
    for forbidden in ("model_signal =", "verdict =", "STRONG_BUY", "= 'Buy'"):
        assert forbidden not in source, forbidden
