"""Confidence policy — the single source of every confidence number."""

from __future__ import annotations

from datetime import date, timedelta

from src.services import confidence


class TestBaselines:
    def test_primary_record_outranks_curated_outranks_web(self):
        # The ordering IS the claim: filings > encyclopedic > web research.
        assert confidence.for_provider("sec") > confidence.for_provider("wikidata")
        assert confidence.for_provider("wikidata") > confidence.for_provider("exa")
        assert confidence.for_provider("exa") > confidence.for_provider("gnews")

    def test_unknown_provider_gets_a_neutral_default_not_zero(self):
        value = confidence.for_provider("some-new-provider")
        assert value == confidence.DEFAULT_BASELINE

    def test_compound_provider_names_resolve_to_their_class(self):
        # "sec,wikidata" (merged edge) and "apify.web" both resolve.
        assert confidence.score("sec,wikidata").value == confidence.score("sec").value
        assert confidence.score("apify.web").value == confidence.score("apify").value


class TestSourceAuthority:
    def test_authoritative_source_outranks_a_weak_provider(self):
        # A SEC filing surfaced by GNews is still a SEC filing.
        result = confidence.score("gnews", source_authority=0.75)
        assert result.value > confidence.for_provider("gnews")
        assert any("outranks" in r for r in result.reasons)

    def test_weak_source_is_not_lifted_by_a_strong_provider(self):
        # A forum post found by Exa is still a forum post.
        result = confidence.score("exa", source_authority=0.25)
        assert result.value < confidence.for_provider("exa")


class TestCorroborationAndContradiction:
    def test_independent_agreement_raises_confidence(self):
        single = confidence.score("tavily")
        triple = confidence.score("tavily", corroborating_providers=3)
        assert triple.value > single.value
        assert any("independent providers" in r for r in triple.reasons)

    def test_contradiction_lowers_confidence(self):
        clean = confidence.score("wikidata")
        disputed = confidence.score("wikidata", contradicting_providers=1)
        assert disputed.value < clean.value
        assert any("contradicting" in r for r in disputed.reasons)

    def test_contradiction_outweighs_a_single_corroboration(self):
        # Disagreement is stronger evidence than one extra agreement.
        result = confidence.score("tavily", corroborating_providers=2, contradicting_providers=1)
        assert result.value < confidence.score("tavily", corroborating_providers=2).value


class TestFreshness:
    def test_recent_claims_are_not_penalised(self):
        today = date.today().isoformat()
        assert confidence.score("newsapi", published_at=today).value == confidence.score("newsapi").value

    def test_old_claims_decay(self):
        old = (date.today() - timedelta(days=900)).isoformat()
        aged = confidence.score("newsapi", published_at=old)
        assert aged.value < confidence.score("newsapi").value
        assert any("age" in r for r in aged.reasons)

    def test_unparseable_dates_are_ignored_not_fatal(self):
        assert confidence.score("newsapi", published_at="not-a-date").value == \
               confidence.score("newsapi").value


class TestCeilings:
    def test_web_evidence_cannot_rival_the_primary_record(self):
        stacked = confidence.score(
            "tavily", source_authority=0.75, corroborating_providers=8, is_web_source=True,
        )
        assert stacked.value <= confidence.WEB_CEILING
        assert stacked.value < confidence.for_provider("sec")

    def test_nothing_reaches_certainty(self):
        maxed = confidence.score("sec", corroborating_providers=20)
        assert maxed.value <= confidence.ABSOLUTE_CEILING < 1.0

    def test_confidence_never_goes_below_the_floor(self):
        crushed = confidence.score("apify", contradicting_providers=20)
        assert crushed.value >= confidence.FLOOR


class TestExplainability:
    def test_every_score_explains_itself(self):
        result = confidence.score(
            "tavily", source_authority=0.6, corroborating_providers=2,
            published_at=(date.today() - timedelta(days=700)).isoformat(),
        )
        assert result.reasons
        explanation = result.explain()
        # A reader can reconstruct the number from the reasons.
        assert "baseline" in explanation
        assert "providers" in explanation

    def test_is_deterministic(self):
        args = dict(source_authority=0.6, corroborating_providers=2)
        assert confidence.score("exa", **args).value == confidence.score("exa", **args).value
