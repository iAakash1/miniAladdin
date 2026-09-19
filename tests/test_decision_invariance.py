"""One scorecard, three presentations.

Beginner, Intermediate and Advanced are presentation modes. The property that makes that
claim true rather than aspirational is structural: `experience_mode` is stored
in user preferences, read by the frontend to decide what to draw, and never
reaches a scoring path at all. If it ever did, the modes would become separate
models wearing one name, and a reader switching modes could watch a verdict
change underneath them.

These tests hold the line in both directions — the mode cannot reach the
engine, and the engine's verdict is carried verbatim by every surface that
reports it.
"""

import inspect
import pathlib

import pytest

from src.scoring import engine
from src.services import explore_service
from src.services.explore_service import ExploreRow


class _Card:
    """A scorecard stand-in carrying only what the surfaces read."""

    def __init__(self, verdict="Buy", raw_score=0.31, confidence=61, risk=42, completeness=0.93):
        self.verdict = verdict
        self.raw_score = raw_score
        self.confidence = confidence
        self.risk_score = risk
        self.data_completeness = completeness
        self.momentum_score = 0.2
        self.quality_score = 0.1
        self.fundamental_score = -0.05
        self.factors = []


# ── the mode cannot reach the engine ─────────────────────────────────────────

def test_the_scoring_engine_has_no_experience_mode_parameter():
    """The structural guarantee. A mode the engine cannot see cannot move it."""
    # Matched as whole words. A substring test flags `model_rolling_ic`,
    # which is a model diagnostic and has nothing to do with presentation —
    # and a detector that cries wolf is one somebody deletes.
    import re

    signature = inspect.signature(engine.score_ticker)
    forbidden = re.compile(r"\b(experience|beginner|intermediate|advanced|presentation)\b|(^|_)mode(_|$)")
    for name in signature.parameters:
        assert not forbidden.search(name.lower()), name


def test_decision_quality_has_no_experience_mode_parameter():
    """Same structural guarantee, for the module that grades the evidence.

    A stronger proof than a runtime check: /api/research/{ticker} itself has
    no mode/experience parameter at all (checked below), so there is no value
    a caller could even pass that would reach decision_quality.assess()
    differently depending on which shell the reader is using.
    """
    import inspect as _inspect
    import re as _re

    from src.services import decision_quality

    forbidden = _re.compile(r"\b(experience|beginner|intermediate|advanced|presentation)\b|(^|_)mode(_|$)")
    for name in _inspect.signature(decision_quality.assess).parameters:
        assert not forbidden.search(name.lower()), name


def test_the_research_endpoint_has_no_experience_mode_parameter():
    """/api/research/{ticker} — the endpoint decision_quality is attached to
    — cannot receive a mode at all. Beginner, Intermediate and Advanced all
    call the identical endpoint with the identical arguments; the only
    thing that can differ between them is how much of one response a
    component chooses to render.
    """
    import inspect as _inspect
    import re as _re

    import api.index as api_module

    forbidden = _re.compile(r"\b(experience|beginner|intermediate|advanced|presentation)\b|(^|_)mode(_|$)")
    for name in _inspect.signature(api_module.research_ticker).parameters:
        assert not forbidden.search(name.lower()), name


def test_the_verdict_cut_points_match_their_frontend_mirror():
    """The two numbers a "why isn't this stronger" panel needs are duplicated
    by necessity — Python and TypeScript share no build step — and duplicated
    values drift silently unless something is watching both sides.

    dashboard/src/lib/beginner.ts's SIGNAL_CUT_ACTION/SIGNAL_CUT_STRONG exist
    to compute a reader-facing "N points from Buy" without a network round
    trip. If either constant here ever changes, this test fails and says
    exactly which frontend constants to update alongside it — the alternative
    is a distance-to-threshold sentence that quietly starts lying.
    """
    assert engine.CUT_ACTION == 0.15, (
        "update dashboard/src/lib/beginner.ts's SIGNAL_CUT_ACTION to match"
    )
    assert engine.CUT_STRONG == 0.40, (
        "update dashboard/src/lib/beginner.ts's SIGNAL_CUT_STRONG to match"
    )


@pytest.mark.parametrize("module_path", [
    "src/scoring/engine.py",
    "src/decision.py",
    "src/services/explore_service.py",
    "src/services/explore_ranking.py",
    "src/services/explore_eligibility.py",
])
def test_no_scoring_module_mentions_the_experience_mode(module_path):
    """Not even in a comment: the point is that this concept is absent from
    the decision path, and a reference is where a dependency starts."""
    body = pathlib.Path(module_path).read_text().lower()
    assert "experience_mode" not in body, module_path


def test_the_preferences_allowlist_is_the_only_writer_of_the_mode():
    """It is a user preference, alongside theme — not a scoring input."""
    from src.services.database.repositories.preferences import (
        _ALLOWED_EXPERIENCE_MODES, _ALLOWED_FIELDS,
    )
    assert "experience_mode" in _ALLOWED_FIELDS
    assert _ALLOWED_EXPERIENCE_MODES == {"beginner", "intermediate", "advanced"}


# ── the verdict is carried, never recomputed ─────────────────────────────────

@pytest.mark.parametrize("verdict", ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"])
def test_explore_carries_the_scorecard_verdict_verbatim(verdict):
    """`model_signal` is the engine's own string, not a re-derivation.

    Re-mapping a score to a label in a second place is how two surfaces end
    up disagreeing about one security while both look internally consistent.
    """
    row = ExploreRow(symbol="X", company_name="X Inc.", sector="Information Technology")
    card = _Card(verdict=verdict)
    row.model_signal = card.verdict
    assert row.model_signal == verdict


def test_explore_does_not_map_scores_to_verdicts_itself():
    """Only the engine owns that mapping."""
    for name in ("explore_service.py", "explore_ranking.py"):
        body = pathlib.Path("src/services") / name
        text = body.read_text()
        assert "map_verdict" not in text, name
        for label in ("STRONG_BUY", "Strong Buy"):
            assert label not in text, f"{name} constructs a verdict label"


def test_signal_strength_is_passed_through_rather_than_rescaled():
    """raw_score is bounded [-1, 1]; reporting it as anything else would make
    the number in a response differ from the number the engine computed."""
    assert explore_service.ranking.signal_strength(0.3142) == 0.3142
    assert explore_service.ranking.signal_strength(-0.9) == -0.9
    assert explore_service.ranking.signal_strength(None) is None


def test_rank_and_verdict_are_independent():
    """A high rank is not a Buy and a low rank is not a Sell.

    Rank orders securities against each other; a verdict is a statement about
    one security on its own. A ranking that quietly implied a verdict would be
    a second decision authority.
    """
    from src.services.explore_service import ExploreSnapshot, rank

    rows = [
        ExploreRow(symbol="TOP", company_name="Top", sector="Energy", eligible=True,
                   overall_rank=99.0, model_signal="Sell"),
        ExploreRow(symbol="BOT", company_name="Bot", sector="Energy", eligible=True,
                   overall_rank=1.0, model_signal="Strong Buy"),
    ]
    snapshot = ExploreSnapshot(
        generated_at="2026-09-11T00:00:00+00:00", universe_version="us-v1",
        rows=rows, eligible_count=2, evaluated_count=2,
    )
    ordered = rank(snapshot, "overall")
    assert [r.symbol for r in ordered] == ["TOP", "BOT"]
    # The verdicts ride along untouched, including the uncomfortable pairing.
    assert ordered[0].model_signal == "Sell"
    assert ordered[1].model_signal == "Strong Buy"


# ── the capabilities payload cannot carry a decision ─────────────────────────

def test_capabilities_carry_no_financial_state(monkeypatch):
    """A presentation preference must not become a channel for a verdict."""
    from src.services import authz

    # Without this the role lookup builds a real Supabase client on a machine
    # that happens to hold credentials, and reaches the network.
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    payload = authz.capabilities_for("user_abc", "beginner")
    forbidden = {"verdict", "signal", "score", "risk", "confidence", "price", "rank"}
    assert not (forbidden & set(payload)), payload.keys()
