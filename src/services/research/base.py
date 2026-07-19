"""
The ResearchProvider interface.

Every research source — Brave, Tavily, Exa, Google News, Apify — implements
this and nothing else. The rest of the Intelligence OS never learns which
provider answered: it receives `ResearchHit` rows or a `KnowledgeBundle`,
both provider-neutral.

Adding a provider means implementing this class and adding its name to the
registry's default order. No other code changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.providers.research_schemas import (
    KnowledgeBundle,
    ResearchClaim,
    ResearchEvidence,
    ResearchSource,
)
from src.services.research.authority import authority_of, confidence_for_source


@dataclass
class ResearchHit:
    """One search result, normalized. The common currency between providers."""
    url: str
    title: str
    snippet: str = ""
    published_at: Optional[str] = None
    provider: str = ""

    @property
    def authority(self) -> int:
        return authority_of(self.url)


@dataclass
class ProviderCapabilities:
    """What a provider can do, so the engine can route without special-casing."""
    search: bool = True
    company_research: bool = True
    news: bool = False
    semantic: bool = False        # finds conceptually related material
    extracts_content: bool = False  # returns page text, not just snippets


@dataclass
class ProviderHealth:
    name: str
    available: bool
    configured: bool
    detail: str = ""
    stats: dict[str, Any] = field(default_factory=dict)


def _sentences(text: str, limit: int = 3) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if len(p.strip()) > 40][:limit]


class ResearchProvider:
    """Base class. Subclasses implement `search`; everything else is shared."""

    name = "research"

    # ── to implement ─────────────────────────────────────────────────────────
    def search(self, query: str, limit: int = 6) -> list[ResearchHit]:
        raise NotImplementedError

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def health(self) -> ProviderHealth:
        return ProviderHealth(name=self.name, available=self.is_configured(),
                              configured=self.is_configured())

    def is_configured(self) -> bool:
        return True

    # ── shared ───────────────────────────────────────────────────────────────
    def research_company(self, symbol: str, company_name: str = "", question: str = "") -> KnowledgeBundle:
        """Default company research: one authority-ranked search, normalized."""
        subject = company_name or symbol
        query = question or f"{subject} {symbol} recent developments competitive position risks"
        return self.normalize(symbol, self.search(query, limit=6))

    def normalize(self, symbol: str, hits: list[ResearchHit]) -> KnowledgeBundle:
        """Hits → sourced claims. Identical for every provider, which is what
        keeps evidence rules from drifting between them:
          * no resolvable URL → no claim
          * confidence comes from SOURCE authority, never from the provider
        """
        bundle = KnowledgeBundle()
        for index, hit in enumerate(hits):
            if not hit.url.startswith("http"):
                continue
            text = hit.snippet or hit.title
            statements = _sentences(text) or ([hit.title] if len(hit.title) > 25 else [])
            if not statements:
                continue
            source = ResearchSource(
                provider=hit.provider or self.name,
                title=hit.title or hit.url,
                url=hit.url,
                document_type="web",
                published_at=hit.published_at,
            )
            for n, statement in enumerate(statements):
                bundle.claims.append(ResearchClaim(
                    id=f"claim:{self.name}:{symbol}:{index}:{n}",
                    statement=statement,
                    confidence=confidence_for_source(hit.url, hit.provider or self.name),
                    evidence=[ResearchEvidence(
                        id=f"evidence:{self.name}:{symbol}:{index}:{n}",
                        source=source, excerpt=statement, doc_section="web research",
                    )],
                ))
        return bundle
