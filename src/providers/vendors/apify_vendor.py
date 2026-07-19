"""
Apify vendor — web research normalized into citable evidence.

Apify runs third-party Actors; their raw output is unstructured and
inconsistent. This adapter's entire job is to turn that into
ResearchClaim/ResearchEvidence objects that name their source, so web
research is held to the same evidence standard as SEC filings.

Discipline enforced here:
  * A claim without at least one resolvable source URL is DISCARDED.
    Unsourced web text is exactly the kind of input that would let
    hallucinated content enter the platform through the back door.
  * Web-sourced claims carry lower confidence than filings by
    construction — they inform, they never override deterministic data.
  * Actor runs are synchronous with a hard timeout; a slow or failed run
    contributes nothing rather than blocking research.

Requires APIFY_API_TOKEN. Absent it, the vendor is simply unavailable and
every consumer degrades to the providers that remain.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from src.providers.base import VendorClient
from src.providers.research_schemas import (
    KnowledgeBundle,
    ResearchClaim,
    ResearchEvidence,
    ResearchSource,
)

logger = logging.getLogger(__name__)

# Web research is corroborating context, never authority: capped well below
# the confidence carried by filings (1.0) and encyclopedic facts (0.9).
WEB_CLAIM_CONFIDENCE = 0.55

# Domains whose content is not research-grade for financial claims.
LOW_QUALITY_HOSTS = {
    "reddit.com", "quora.com", "pinterest.com", "facebook.com",
    "instagram.com", "tiktok.com", "x.com", "twitter.com",
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _sentences(text: str, limit: int = 4) -> list[str]:
    """Split prose into claim-sized statements, dropping fragments."""
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 40][:limit]


class ApifyVendor(VendorClient):
    NAME = "apify"
    KEY_ENV = "APIFY_API_TOKEN"
    DEFAULT_RPM = 6  # Actor runs are expensive; keep concurrency low

    BASE = "https://api.apify.com/v2"

    # Actor ids are configurable so a deprecated Actor never requires a
    # code change — only an env update.
    PERPLEXITY_ACTOR = "jons/perplexity-actor"
    GOOGLE_SEARCH_ACTOR = "apify/google-search-scraper"

    def _run_actor(self, actor_id: str, payload: dict[str, Any], timeout_secs: int = 90) -> list[dict[str, Any]]:
        """Run an Actor synchronously and return its dataset items."""
        actor_path = actor_id.replace("/", "~")
        url = f"{self.BASE}/acts/{actor_path}/run-sync-get-dataset-items"
        data = self._request_json(
            "POST", url,
            params={"token": self.api_key, "timeout": timeout_secs},
            json_body=payload,
        )
        return data if isinstance(data, list) else []

    # ── research: sourced claims about a company ─────────────────────────────
    def research_company(self, symbol: str, company_name: str, question: str = "") -> KnowledgeBundle:
        """Web research → sourced claims. Unsourced output is discarded."""
        if not self.available:
            return KnowledgeBundle()
        subject = company_name or symbol
        query = question or (
            f"{subject} ({symbol}) recent business developments, competitive position, "
            f"and key risks — cite sources"
        )
        try:
            items = self._run_actor(self.PERPLEXITY_ACTOR, {"query": query, "maxResults": 1})
        except Exception:  # noqa: BLE001 — web research is always optional
            logger.info("apify perplexity run failed for %s", symbol, exc_info=True)
            return KnowledgeBundle()

        return self._claims_from_items(symbol, items, "apify.perplexity")

    def _claims_from_items(self, symbol: str, items: list[dict[str, Any]], provider: str) -> KnowledgeBundle:
        bundle = KnowledgeBundle()
        for item in items[:3]:
            answer = str(item.get("answer") or item.get("text") or item.get("content") or "")
            raw_sources = item.get("sources") or item.get("citations") or item.get("links") or []
            sources: list[ResearchSource] = []
            for entry in raw_sources[:6]:
                url = entry.get("url") if isinstance(entry, dict) else str(entry)
                if not url or not str(url).startswith("http"):
                    continue
                host = _host(str(url))
                if not host or host in LOW_QUALITY_HOSTS:
                    continue
                title = (entry.get("title") if isinstance(entry, dict) else None) or host
                sources.append(ResearchSource(
                    provider=provider, title=str(title), url=str(url), document_type="web",
                ))
            # The rule that keeps hallucinated content out: no source, no claim.
            if not sources:
                continue
            for index, statement in enumerate(_sentences(answer)):
                evidence = [
                    ResearchEvidence(
                        id=f"evidence:{provider}:{symbol}:{index}:{n}",
                        source=source, excerpt=statement, doc_section="web research",
                    )
                    for n, source in enumerate(sources[:3])
                ]
                bundle.claims.append(ResearchClaim(
                    id=f"claim:{provider}:{symbol}:{index}",
                    statement=statement,
                    evidence=evidence,
                    confidence=WEB_CLAIM_CONFIDENCE,
                ))
        return bundle

    # ── search: general web research for a themed question ───────────────────
    def search(self, query: str, limit: int = 6) -> list[dict[str, str]]:
        """Google results as structured rows (title/url/snippet)."""
        if not self.available:
            return []
        try:
            items = self._run_actor(
                self.GOOGLE_SEARCH_ACTOR,
                {"queries": query, "maxPagesPerQuery": 1, "resultsPerPage": limit},
                timeout_secs=60,
            )
        except Exception:  # noqa: BLE001
            logger.info("apify google search failed", exc_info=True)
            return []
        out: list[dict[str, str]] = []
        for item in items:
            for result in (item.get("organicResults") or [])[:limit]:
                url = str(result.get("url") or "")
                if not url.startswith("http"):
                    continue
                out.append({
                    "title": str(result.get("title") or ""),
                    "url": url,
                    "snippet": str(result.get("description") or ""),
                    "host": _host(url),
                })
        return out[:limit]
