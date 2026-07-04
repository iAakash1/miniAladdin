"""Tests for the news evidence methodology (decay, novelty, confirmation, n_eff)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.services import news_scoring as ns

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def row(title, score=0.5, source="Reuters", url="https://reuters.com/a",
        hours_ago=1.0):
    ts = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"title": title, "score": score, "source": source, "url": url,
            "published_at": ts}


class TestDecay:
    def test_old_news_weighs_less(self):
        fresh = ns.score_headlines([row("NVDA earnings beat estimates", hours_ago=1)], now=NOW)
        stale = ns.score_headlines([row("NVDA earnings beat estimates", hours_ago=120)], now=NOW)
        assert fresh.headlines[0].decay > stale.headlines[0].decay
        assert stale.headlines[0].decay < 0.35  # ~2 half-lives at 60h

    def test_half_life_is_sixty_hours(self):
        evidence = ns.score_headlines([row("Some headline about stocks", hours_ago=60)], now=NOW)
        assert abs(evidence.headlines[0].decay - 0.5) < 0.03


class TestNoveltyAndClustering:
    def test_duplicates_cluster_and_repeats_are_discounted(self):
        evidence = ns.score_headlines([
            row("Apple beats earnings expectations on strong iPhone sales", source="Reuters",
                url="https://reuters.com/a"),
            row("Apple beats earnings expectations on strong iPhone sales today", source="CNBC",
                url="https://cnbc.com/b"),
            row("Fed considers rate cut in September", source="WSJ", url="https://wsj.com/c"),
        ], now=NOW)

        assert evidence.clusters == 2
        first, repeat = evidence.headlines[0], evidence.headlines[1]
        assert first.cluster_id == repeat.cluster_id
        assert first.novelty == 1.0
        assert repeat.novelty == ns.REPEAT_WEIGHT

    def test_repeats_do_not_inflate_effective_evidence(self):
        one = ns.score_headlines([row("Apple beats earnings expectations", score=0.8)], now=NOW)
        five_dupes = ns.score_headlines([
            row("Apple beats earnings expectations", score=0.8, url=f"https://reuters.com/{i}")
            for i in range(5)
        ], now=NOW)
        # 5 identical stories from the SAME source: n_eff must stay well
        # below 5x — repeats carry REPEAT_WEIGHT and no confirmation bonus.
        assert five_dupes.n_eff < one.n_eff * 2.5


class TestConfirmation:
    def test_distinct_sources_confirm(self):
        single = ns.score_headlines([
            row("Tesla announces massive buyback program", source="Reuters", url="https://reuters.com/x"),
        ], now=NOW)
        confirmed = ns.score_headlines([
            row("Tesla announces massive buyback program", source="Reuters", url="https://reuters.com/x"),
            row("Tesla announces massive buyback program plan", source="WSJ", url="https://wsj.com/y"),
        ], now=NOW)
        assert confirmed.headlines[0].confirmation > single.headlines[0].confirmation
        assert confirmed.headlines[0].confirmation <= 1 + ns.CONFIRMATION_BONUS_CAP


class TestReliabilityWeighting:
    def test_tier1_outweighs_ugc_at_equal_age(self):
        evidence = ns.score_headlines([
            row("Stock surges on earnings", source="Reuters", url="https://reuters.com/a"),
            row("Totally different headline about the same ticker", source="reddit",
                url="https://reddit.com/r/stocks/z"),
        ], now=NOW)
        tier1, ugc = evidence.headlines
        assert tier1.weight > ugc.weight * 2


class TestEventTaxonomy:
    def test_classification(self):
        assert ns.classify_event("Apple beats earnings expectations") == "earnings"
        assert ns.classify_event("Microsoft raises full-year guidance") == "guidance"
        assert ns.classify_event("Broadcom to acquire startup in $10B deal to buy") == "mna"
        assert ns.classify_event("DOJ opens antitrust probe into pricing") == "legal_regulatory"
        assert ns.classify_event("Analyst upgrades NVDA, lifts price target") == "analyst_action"
        assert ns.classify_event("Company unveils new chip lineup") == "product"
        assert ns.classify_event("Fed rate decision looms over markets") == "macro_passthrough"
        assert ns.classify_event("Shareholders meet on Tuesday") == "general"


class TestEffectiveSentiment:
    def test_s_eff_is_weighted_not_raw_mean(self):
        evidence = ns.score_headlines([
            row("Fresh tier-1 bullish story on earnings", score=0.8, hours_ago=1),
            row("Ancient unrelated bearish take", score=-0.8, hours_ago=200,
                source="blog", url="https://randomblog.io/z"),
        ], now=NOW)
        # Raw mean would be 0; weighting must pull toward the fresh tier-1 story.
        assert evidence.s_eff is not None and evidence.s_eff > 0.4

    def test_empty_input(self):
        evidence = ns.score_headlines([], now=NOW)
        assert evidence.n_eff == 0 and evidence.s_eff is None
