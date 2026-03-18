"""Tests for the Enhanced Sentiment Analyzer with Browser Actuation."""

import pytest

from src.models import SentimentLabel
from src.sentiment_edge import (
    BREAKING_NEWS_AMPLIFIERS,
    SentimentAnalyzer,
    BrowserVerificationResult,
)


class TestScoreHeadline:
    """Test keyword-based headline scoring."""

    def setup_method(self):
        self.analyzer = SentimentAnalyzer()

    def test_bullish_headline(self):
        score, label = self.analyzer.score_headline(
            "Stock surges to record high on strong earnings beat"
        )
        assert score > 0
        assert label == SentimentLabel.BULLISH

    def test_bearish_headline(self):
        score, label = self.analyzer.score_headline(
            "Shares crash on fraud investigation and regulatory concerns"
        )
        assert score < 0
        assert label == SentimentLabel.BEARISH

    def test_neutral_headline(self):
        score, label = self.analyzer.score_headline(
            "Company schedules annual meeting for shareholders"
        )
        assert score == 0.0
        assert label == SentimentLabel.NEUTRAL

    def test_mixed_headline(self):
        score, label = self.analyzer.score_headline(
            "Strong growth despite regulatory risk concerns"
        )
        assert isinstance(score, float)
        assert -1.0 <= score <= 1.0

    def test_empty_like_headline(self):
        score, label = self.analyzer.score_headline("123 456 789")
        assert score == 0.0
        assert label == SentimentLabel.NEUTRAL


class TestBreakingNewsAmplification:
    """Test that Breaking News headlines get amplified scores."""

    def setup_method(self):
        self.analyzer = SentimentAnalyzer()

    def test_breaking_bullish_amplified(self):
        """Breaking bullish headline should have higher score than non-breaking."""
        normal_score, _ = self.analyzer.score_headline(
            "Stock surges on strong earnings", is_breaking=False
        )
        breaking_score, _ = self.analyzer.score_headline(
            "Stock surges on strong earnings", is_breaking=True
        )
        # Breaking should amplify the absolute score
        assert abs(breaking_score) >= abs(normal_score)

    def test_breaking_bearish_amplified(self):
        """Breaking bearish headline should have more negative score."""
        normal_score, _ = self.analyzer.score_headline(
            "Stock crashes on fraud scandal", is_breaking=False
        )
        breaking_score, _ = self.analyzer.score_headline(
            "Stock crashes on fraud scandal", is_breaking=True
        )
        assert breaking_score <= normal_score

    def test_breaking_neutral_stays_neutral(self):
        """Breaking news with no keywords stays at 0."""
        score, label = self.analyzer.score_headline(
            "Company holds annual meeting", is_breaking=True
        )
        assert score == 0.0
        assert label == SentimentLabel.NEUTRAL

    def test_detect_breaking_in_text(self):
        """Test breaking news keyword detection."""
        assert self.analyzer._detect_breaking_in_text("BREAKING: Stock surges")
        assert self.analyzer._detect_breaking_in_text("URGENT market alert")
        assert not self.analyzer._detect_breaking_in_text("Regular market update")


class TestAnalyzeHeadlines:
    """Test aggregate sentiment analysis."""

    def setup_method(self):
        self.analyzer = SentimentAnalyzer()

    def test_bullish_aggregate(self, bullish_headlines):
        result = self.analyzer.analyze_headlines(bullish_headlines)
        assert result.headline_count == 3
        assert result.average_score > 0
        assert result.dominant_label == SentimentLabel.BULLISH

    def test_bearish_aggregate(self, bearish_headlines):
        result = self.analyzer.analyze_headlines(bearish_headlines)
        assert result.headline_count == 3
        assert result.average_score < 0
        assert result.dominant_label == SentimentLabel.BEARISH

    def test_empty_headlines(self):
        result = self.analyzer.analyze_headlines([])
        assert result.headline_count == 0
        assert result.average_score == 0.0

    def test_single_headline(self):
        result = self.analyzer.analyze_headlines(
            [{"title": "Stock soars on massive rally", "source": "Test"}]
        )
        assert result.headline_count == 1
        assert result.average_score > 0

    def test_breaking_headline_tagged_in_source(self):
        """Breaking headlines should get tagged with BREAKING in source."""
        result = self.analyzer.analyze_headlines(
            [{"title": "BREAKING: Stock surges to record", "source": "Yahoo", "is_breaking": True}]
        )
        assert result.headline_count == 1
        assert "BREAKING" in result.headlines[0].source


class TestBrowserVerification:
    """Test browser verification logic."""

    def setup_method(self):
        self.analyzer = SentimentAnalyzer()

    def test_verification_detects_breaking_in_rss(self):
        rss_headlines = [
            {"title": "Breaking: NVDA surges 10%", "source": "Yahoo", "is_breaking": True},
            {"title": "Market update for today", "source": "Yahoo", "is_breaking": False},
        ]
        # Patch out the HTML fetch to avoid network calls
        self.analyzer.fetch_headlines_html = lambda ticker: []

        result = self.analyzer.browser_verify_headlines("NVDA", rss_headlines)
        assert result.has_breaking_banner is True
        assert len(result.breaking_headlines) == 1

    def test_verification_no_breaking(self):
        rss_headlines = [
            {"title": "Regular market update", "source": "Yahoo", "is_breaking": False},
        ]
        self.analyzer.fetch_headlines_html = lambda ticker: []

        result = self.analyzer.browser_verify_headlines("NVDA", rss_headlines)
        assert result.has_breaking_banner is False
        assert len(result.breaking_headlines) == 0

    def test_browser_verification_result_defaults(self):
        result = BrowserVerificationResult()
        assert result.has_breaking_banner is False
        assert result.breaking_headlines == []
        assert result.live_price is None
        assert result.verified_headlines == []
