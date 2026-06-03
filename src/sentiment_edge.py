"""
OmniSignal Sentiment Edge
Multi-source headline sentiment analysis.

Source priority:
  1. NewsAPI (Reuters, Bloomberg, FT, WSJ — if key configured)
  2. Yahoo Finance RSS (free, always available)
  3. Yahoo Finance HTML scrape (fallback)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.models import AggregateSentiment, SentimentLabel, SentimentResult
from src.news_api import NewsAPIClient


# ── Keyword dictionaries ─────────────────────────────────────────────────────

BULLISH_KEYWORDS: set[str] = {
    "surge", "surges", "surging", "rally", "rallies", "rallying",
    "soar", "soars", "soaring", "jump", "jumps", "jumping",
    "beat", "beats", "beating", "outperform", "outperforms",
    "upgrade", "upgrades", "upgraded", "buy", "bullish",
    "gain", "gains", "gaining", "record", "records",
    "breakout", "boom", "booming", "growth", "strong",
    "profit", "profitable", "revenue", "partnership",
    "optimistic", "upside", "positive", "momentum",
    "innovation", "breakthrough", "expansion", "acquisition",
    "dividend", "buyback", "guidance", "raised", "above",
    "exceeds", "exceeded", "outpaced", "upbeat", "strength",
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
    "disappoints", "disappointing", "missed", "below", "shortfall",
    "uncertainty", "headwinds", "tariff", "sanctions", "ban",
}

BREAKING_NEWS_AMPLIFIERS: set[str] = {
    "breaking", "urgent", "alert", "just in", "developing",
    "exclusive", "flash", "confirmed",
}


class SentimentAnalyzer:
    """
    Multi-source news sentiment engine.

    Pipeline:
        1. Try NewsAPI (premium sources, better quality)
        2. Fall back to Yahoo Finance RSS
        3. Fall back to Yahoo Finance HTML scrape
        4. Score all headlines with keyword model
    """

    YAHOO_RSS_TEMPLATE  = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    YAHOO_QUOTE_URL     = "https://finance.yahoo.com/quote/{ticker}/"
    USER_AGENT          = "OmniSignal/1.0 (Research Agent)"
    BREAKING_AMPLIFIER  = 1.5

    def __init__(self, max_headlines: int = 8):
        self.max_headlines  = max_headlines
        self.news_client    = NewsAPIClient()

    # ── Scoring ─────────────────────────────────────────────────────────────

    def score_headline(self, headline: str, is_breaking: bool = False) -> tuple[float, SentimentLabel]:
        words = set(re.findall(r"[a-z]+", headline.lower()))
        bullish_hits = len(words & BULLISH_KEYWORDS)
        bearish_hits = len(words & BEARISH_KEYWORDS)
        total_hits   = bullish_hits + bearish_hits

        if total_hits == 0:
            return 0.0, SentimentLabel.NEUTRAL

        raw_score = (bullish_hits - bearish_hits) / total_hits
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

    def _detect_breaking(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in BREAKING_NEWS_AMPLIFIERS)

    # ── Headline sources ─────────────────────────────────────────────────────

    def _fetch_newsapi(self, ticker: str, company_name: str = "") -> list[dict]:
        """Primary: NewsAPI multi-source headlines."""
        try:
            articles = self.news_client.fetch_headlines(
                ticker, company_name=company_name, max_results=self.max_headlines
            )
            return articles
        except Exception as e:
            print(f"[SentimentEdge] NewsAPI failed: {e}")
            return []

    def _fetch_yahoo_rss(self, ticker: str) -> list[dict]:
        """Fallback 1: Yahoo Finance RSS."""
        url = self.YAHOO_RSS_TEMPLATE.format(ticker=ticker.upper())
        try:
            r = requests.get(url, headers={"User-Agent": self.USER_AGENT}, timeout=10)
            r.raise_for_status()
        except Exception as e:
            print(f"[SentimentEdge] Yahoo RSS failed: {e}")
            return []

        soup  = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item", limit=self.max_headlines)
        out   = []
        for item in items:
            tag = item.find("title")
            if tag and tag.text:
                title = tag.text.strip()
                out.append({
                    "title":      title,
                    "source":     "Yahoo Finance",
                    "is_breaking": self._detect_breaking(title),
                })
        return out

    def _fetch_yahoo_html(self, ticker: str) -> list[dict]:
        """Fallback 2: Yahoo Finance HTML scrape."""
        url = self.YAHOO_QUOTE_URL.format(ticker=ticker.upper())
        try:
            r = requests.get(url, headers={"User-Agent": self.USER_AGENT}, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"[SentimentEdge] Yahoo HTML failed: {e}")
            return []

        soup     = BeautifulSoup(r.text, "html.parser")
        page_txt = soup.get_text().lower()
        has_breaking = "breaking news" in page_txt or "breaking:" in page_txt

        out = []
        for h3 in soup.find_all("h3", limit=self.max_headlines * 2):
            text = h3.get_text(strip=True)
            if text and len(text) > 15:
                out.append({
                    "title":      text,
                    "source":     "Yahoo Finance",
                    "is_breaking": has_breaking or self._detect_breaking(text),
                })
                if len(out) >= self.max_headlines:
                    break
        return out

    # ── Aggregation ──────────────────────────────────────────────────────────

    def analyze_headlines(self, headlines: list[dict]) -> AggregateSentiment:
        results: list[SentimentResult] = []
        for h in headlines:
            is_breaking = h.get("is_breaking", False)
            score, label = self.score_headline(h["title"], is_breaking=is_breaking)
            source = h.get("source", "unknown")
            if is_breaking:
                source = f"🔴 BREAKING | {source}"
            results.append(SentimentResult(
                headline=h["title"],
                score=score,
                label=label,
                source=source,
                url=h.get("url",""),
                published_at=h.get("published",""),
            ))

        if not results:
            return AggregateSentiment()

        avg_score = sum(r.score for r in results) / len(results)
        label_counts = {
            SentimentLabel.BULLISH: 0,
            SentimentLabel.BEARISH: 0,
            SentimentLabel.NEUTRAL: 0,
        }
        for r in results:
            label_counts[r.label] += 1
        dominant = max(label_counts, key=label_counts.get)   # type: ignore

        return AggregateSentiment(
            headlines=results,
            average_score=avg_score,
            dominant_label=dominant,
            headline_count=len(results),
        )

    def analyze_ticker(self, ticker: str, company_name: str = "") -> AggregateSentiment:
        """
        Full pipeline: fetch from best available source and score.

        Args:
            ticker:       Stock ticker e.g. "NVDA"
            company_name: Optional full name for better NewsAPI query e.g. "Nvidia"
        """
        ticker = ticker.upper()

        # 1. Try NewsAPI first
        headlines = self._fetch_newsapi(ticker, company_name)
        source_used = "NewsAPI" if headlines else None

        # 2. Fall back to Yahoo RSS
        if not headlines:
            headlines = self._fetch_yahoo_rss(ticker)
            source_used = "Yahoo RSS" if headlines else None

        # 3. Fall back to Yahoo HTML
        if not headlines:
            headlines = self._fetch_yahoo_html(ticker)
            source_used = "Yahoo HTML" if headlines else None

        if not headlines:
            print(f"[SentimentEdge] No headlines found for {ticker}")
            return AggregateSentiment(headline_count=0)

        print(f"[SentimentEdge] {ticker}: {len(headlines)} headlines via {source_used}")
        return self.analyze_headlines(headlines[:self.max_headlines])
