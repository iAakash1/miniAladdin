"""
OmniSignal Sentiment Edge
Enhanced headline sentiment analysis with Browser Actuation for Breaking News verification.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.models import AggregateSentiment, SentimentLabel, SentimentResult


# ── Keyword dictionaries ─────────────────────────────────────────────────────

BULLISH_KEYWORDS: set[str] = {
    "surge", "surges", "surging", "rally", "rallies", "rallying",
    "soar", "soars", "soaring", "jump", "jumps", "jumping",
    "beat", "beats", "beating", "outperform", "outperforms",
    "upgrade", "upgrades", "upgraded", "buy", "bullish",
    "gain", "gains", "gaining", "record", "records",
    "breakout", "boom", "booming", "growth", "strong",
    "profit", "profitable", "revenue",
    "optimistic", "upside", "positive", "momentum",
    "innovation", "breakthrough", "expansion", "partnership",
}

BEARISH_KEYWORDS: set[str] = {
    "crash", "crashes", "crashing", "plunge", "plunges", "plunging",
    "drop", "drops", "dropping", "fall", "falls", "falling",
    "decline", "declines", "declining", "sell", "sells", "selling",
    "downgrade", "downgrades", "downgraded", "miss", "misses",
    "bearish", "loss", "losses", "losing", "fear", "fears",
    "risk", "risks", "risky", "warning", "warns", "warned",
    "lawsuit", "investigation", "fraud", "scandal", "default",
    "bankruptcy", "recession", "layoff", "layoffs", "cut", "cuts",
    "weak", "weakness", "negative", "concern", "concerns",
    "regulation", "regulatory", "fine", "penalty", "probe",
}

# Breaking-news specific keywords — these amplify sentiment scores
BREAKING_NEWS_AMPLIFIERS: set[str] = {
    "breaking", "urgent", "alert", "just in", "developing",
    "exclusive", "flash", "confirmed",
}


@dataclass
class BrowserVerificationResult:
    """Result from browser-actuated headline verification."""
    has_breaking_banner: bool = False
    breaking_headlines: list[str] = field(default_factory=list)
    live_price: Optional[float] = None
    verified_headlines: list[dict] = field(default_factory=list)
    screenshot_path: Optional[str] = None


class SentimentAnalyzer:
    """
    Analyzes news headlines for a given stock ticker using keyword scoring.

    Enhanced with Browser Actuation support:
    - Fetches headlines via Yahoo Finance RSS
    - Optionally verifies via browser to detect 'Breaking News' banners
    - Breaking News detection amplifies sentiment scores by 1.5x
    """

    YAHOO_RSS_TEMPLATE = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    YAHOO_QUOTE_URL = "https://finance.yahoo.com/quote/{ticker}/"
    USER_AGENT = "OmniSignal/1.0 (Research Agent)"
    BREAKING_AMPLIFIER = 1.5  # 50% boost to sentiment when Breaking News detected

    def __init__(self, max_headlines: int = 5):
        self.max_headlines = max_headlines

    def score_headline(self, headline: str, is_breaking: bool = False) -> tuple[float, SentimentLabel]:
        """
        Score a single headline using keyword matching.

        Args:
            headline: The headline text to score
            is_breaking: If True (from Breaking News banner), amplify the score by 1.5x

        Returns:
            (score, label) where score is in [-1.0, 1.0]
        """
        words = set(re.findall(r"[a-z]+", headline.lower()))

        bullish_hits = len(words & BULLISH_KEYWORDS)
        bearish_hits = len(words & BEARISH_KEYWORDS)
        total_hits = bullish_hits + bearish_hits

        if total_hits == 0:
            # Check for breaking news amplifiers even with no keyword hits
            if is_breaking:
                return 0.0, SentimentLabel.NEUTRAL
            return 0.0, SentimentLabel.NEUTRAL

        # Net score normalized to [-1, 1]
        raw_score = (bullish_hits - bearish_hits) / total_hits

        # Apply breaking news amplification
        if is_breaking:
            raw_score *= self.BREAKING_AMPLIFIER

        score = max(-1.0, min(1.0, raw_score))

        if score > 0.1:
            label = SentimentLabel.BULLISH
        elif score < -0.1:
            label = SentimentLabel.BEARISH
        else:
            label = SentimentLabel.NEUTRAL

        return round(score, 4), label

    def _detect_breaking_in_text(self, text: str) -> bool:
        """Check if text contains breaking news indicators."""
        lower = text.lower()
        return any(kw in lower for kw in BREAKING_NEWS_AMPLIFIERS)

    def fetch_headlines_rss(self, ticker: str) -> list[dict]:
        """
        Fetch headlines from Yahoo Finance RSS feed.

        Returns list of {"title": str, "source": str, "is_breaking": bool} dicts.
        """
        url = self.YAHOO_RSS_TEMPLATE.format(ticker=ticker.upper())
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[SentimentEdge] RSS fetch failed: {e}")
            return []

        soup = BeautifulSoup(response.content, "xml")
        items = soup.find_all("item", limit=self.max_headlines)

        headlines = []
        for item in items:
            title_tag = item.find("title")
            if title_tag and title_tag.text:
                title = title_tag.text.strip()
                is_breaking = self._detect_breaking_in_text(title)
                headlines.append({
                    "title": title,
                    "source": "Yahoo Finance",
                    "is_breaking": is_breaking,
                })
        return headlines

    def fetch_headlines_html(self, ticker: str) -> list[dict]:
        """
        Fetch headlines by scraping Yahoo Finance quote page HTML.
        This serves as a fallback and also checks for Breaking News banners
        in the page structure.

        Returns list of {"title": str, "source": str, "is_breaking": bool} dicts.
        """
        url = self.YAHOO_QUOTE_URL.format(ticker=ticker.upper())
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[SentimentEdge] HTML fetch failed: {e}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Detect Breaking News banners anywhere on the page
        page_text = soup.get_text().lower()
        has_breaking_banner = (
            "breaking news" in page_text
            or "breaking:" in page_text
            or "just in:" in page_text
        )

        headlines = []
        # Yahoo Finance uses h3 tags for news headlines in the feed
        for h3 in soup.find_all("h3", limit=self.max_headlines * 2):
            text = h3.get_text(strip=True)
            if text and len(text) > 15:  # Filter out UI elements
                is_breaking = has_breaking_banner or self._detect_breaking_in_text(text)
                headlines.append({
                    "title": text,
                    "source": "Yahoo Finance (Browser)",
                    "is_breaking": is_breaking,
                })
                if len(headlines) >= self.max_headlines:
                    break

        return headlines

    def browser_verify_headlines(
        self, ticker: str, rss_headlines: list[dict]
    ) -> BrowserVerificationResult:
        """
        Verify RSS headlines against the live Yahoo Finance page.

        This method checks for:
        1. 'Breaking News' banners on the page
        2. Whether any RSS headlines are tagged as breaking/urgent
        3. Cross-references RSS headlines with page content

        For full browser actuation (with screenshots), use the Antigravity
        Browser Agent via the /research workflow.
        """
        result = BrowserVerificationResult()

        # Check RSS headlines for breaking indicators
        for h in rss_headlines:
            if h.get("is_breaking", False):
                result.has_breaking_banner = True
                result.breaking_headlines.append(h["title"])

        # Attempt HTML scrape to verify page content
        html_headlines = self.fetch_headlines_html(ticker)
        if html_headlines:
            result.verified_headlines = html_headlines
            # If any HTML-scraped headline is marked as breaking, flag it
            for h in html_headlines:
                if h.get("is_breaking", False) and not result.has_breaking_banner:
                    result.has_breaking_banner = True
                    result.breaking_headlines.append(h["title"])

        return result

    def analyze_headlines(self, headlines: list[dict]) -> AggregateSentiment:
        """
        Score a list of headline dicts and return aggregate sentiment.

        Args:
            headlines: list of {"title": str, "source": str, "is_breaking": bool (optional)}
        """
        results: list[SentimentResult] = []

        for h in headlines:
            is_breaking = h.get("is_breaking", False)
            score, label = self.score_headline(h["title"], is_breaking=is_breaking)

            # Tag source with [BREAKING] if detected
            source = h.get("source", "unknown")
            if is_breaking:
                source = f"🔴 BREAKING | {source}"

            results.append(SentimentResult(
                headline=h["title"],
                score=score,
                label=label,
                source=source,
            ))

        if not results:
            return AggregateSentiment()

        avg_score = sum(r.score for r in results) / len(results)

        # Determine dominant label
        label_counts = {
            SentimentLabel.BULLISH: 0,
            SentimentLabel.BEARISH: 0,
            SentimentLabel.NEUTRAL: 0,
        }
        for r in results:
            label_counts[r.label] += 1
        dominant = max(label_counts, key=label_counts.get)  # type: ignore

        return AggregateSentiment(
            headlines=results,
            average_score=avg_score,
            dominant_label=dominant,
            headline_count=len(results),
        )

    def analyze_ticker(self, ticker: str, browser_verify: bool = True) -> AggregateSentiment:
        """
        Full pipeline: fetch headlines for a ticker, optionally verify via browser,
        and score them.

        Args:
            ticker: Stock ticker symbol
            browser_verify: If True, cross-reference RSS headlines against live page
                            for Breaking News banner detection
        """
        # Step 1: Fetch RSS headlines
        headlines = self.fetch_headlines_rss(ticker)

        # Step 2: Browser verification for Breaking News
        if browser_verify and headlines:
            verification = self.browser_verify_headlines(ticker, headlines)

            if verification.has_breaking_banner:
                print(
                    f"[SentimentEdge] 🔴 BREAKING NEWS detected for {ticker}: "
                    f"{len(verification.breaking_headlines)} headline(s)"
                )
                # Mark matching headlines as breaking in our list
                breaking_titles = {h.lower() for h in verification.breaking_headlines}
                for h in headlines:
                    if h["title"].lower() in breaking_titles or h.get("is_breaking"):
                        h["is_breaking"] = True

            # Merge any additional headlines found via HTML that RSS missed
            rss_titles = {h["title"].lower() for h in headlines}
            for vh in verification.verified_headlines:
                if vh["title"].lower() not in rss_titles:
                    headlines.append(vh)
                    if len(headlines) >= self.max_headlines:
                        break

        if not headlines:
            return AggregateSentiment(headline_count=0)

        return self.analyze_headlines(headlines)
