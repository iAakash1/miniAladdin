"""
Research engine — provider-agnostic orchestration.

Responsibilities, none of which any single provider owns:
  * ordering (env-configurable: RESEARCH_PROVIDER_ORDER)
  * fallback — walk the chain until enough evidence is gathered; a provider
    that is unconfigured, failing or empty is skipped silently
  * merge + deduplicate by URL across providers
  * rank by SOURCE authority, so community content can never outrank a
    filing regardless of which provider surfaced it

If every provider disappears the engine returns an empty bundle, never an
error: research is additive to the deterministic record, never required by
it.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from src.providers.research_schemas import KnowledgeBundle
from src.services.research.authority import authority_of, host_of
from src.services.research.base import ProviderHealth, ResearchHit, ResearchProvider
from src.services.research.providers import (
    ApifyProvider,
    BraveProvider,
    ExaProvider,
    NewsProvider,
    TavilyProvider,
)

logger = logging.getLogger(__name__)

# Priority order: independent index first, then AI-native, then semantic,
# then keyless news, then metered page extraction last.
DEFAULT_ORDER = ["brave", "tavily", "exa", "news", "apify"]

_REGISTRY: dict[str, type[ResearchProvider]] = {
    "brave": BraveProvider,
    "tavily": TavilyProvider,
    "exa": ExaProvider,
    "news": NewsProvider,
    "apify": ApifyProvider,
}

_instances: dict[str, ResearchProvider] = {}

# Enough evidence to stop walking the chain — more providers past this point
# add duplicates, not information.
TARGET_HITS = 8


def configured_order() -> list[str]:
    """RESEARCH_PROVIDER_ORDER overrides priority without a code change."""
    raw = os.getenv("RESEARCH_PROVIDER_ORDER", "").strip()
    if not raw:
        return list(DEFAULT_ORDER)
    names = [name.strip().lower() for name in raw.split(",") if name.strip()]
    return [name for name in names if name in _REGISTRY] or list(DEFAULT_ORDER)


def get_provider(name: str) -> Optional[ResearchProvider]:
    if name not in _REGISTRY:
        return None
    if name not in _instances:
        _instances[name] = _REGISTRY[name]()
    return _instances[name]


def providers_in_order() -> list[ResearchProvider]:
    out = []
    for name in configured_order():
        provider = get_provider(name)
        if provider is not None:
            out.append(provider)
    return out


def health() -> list[dict[str, object]]:
    """Per-provider status — observability without exposing keys."""
    rows = []
    for provider in providers_in_order():
        state: ProviderHealth = provider.health()
        rows.append({
            "name": state.name,
            "configured": state.configured,
            "available": state.available,
            "capabilities": vars(provider.capabilities()),
        })
    return rows


def _dedupe_and_rank(hits: list[ResearchHit]) -> list[ResearchHit]:
    """One row per URL, best-authority first.

    Dedup is by (host, path) rather than raw URL so the same article with
    different tracking parameters collapses to one piece of evidence.
    """
    seen: dict[str, ResearchHit] = {}
    for hit in hits:
        if not hit.url.startswith("http"):
            continue
        key = f"{host_of(hit.url)}{hit.url.split('?')[0].split('#')[0][-60:]}"
        existing = seen.get(key)
        if existing is None:
            seen[key] = hit
        elif len(hit.snippet) > len(existing.snippet):
            # Same source, richer extract — keep the more informative one.
            seen[key] = hit
    return sorted(
        seen.values(),
        key=lambda h: (-authority_of(h.url), h.title.lower()),
    )


def search(query: str, limit: int = 8) -> list[ResearchHit]:
    """Walk the provider chain until enough evidence is gathered."""
    collected: list[ResearchHit] = []
    for provider in providers_in_order():
        if not provider.capabilities().search or not provider.is_configured():
            continue
        try:
            collected.extend(provider.search(query, limit=limit))
        except Exception:  # noqa: BLE001 — one provider never breaks research
            logger.info("research provider %s failed", provider.name, exc_info=True)
            continue
        if len({h.url for h in collected}) >= TARGET_HITS:
            break
    return _dedupe_and_rank(collected)[:limit]


def research_company(symbol: str, company_name: str = "") -> KnowledgeBundle:
    """Company research across the chain, merged, deduplicated, ranked."""
    symbol = symbol.upper().strip()
    if not symbol:
        return KnowledgeBundle()

    subject = company_name or symbol
    query = f"{subject} {symbol} recent developments competitive position risks"
    collected: list[ResearchHit] = []

    for provider in providers_in_order():
        if not provider.is_configured():
            continue
        try:
            if provider.capabilities().search:
                collected.extend(provider.search(query, limit=6))
            else:
                # Providers without a general index (news RSS) still
                # contribute through their own company path.
                bundle = provider.research_company(symbol, company_name)
                for claim in bundle.claims:
                    for evidence in claim.evidence:
                        if evidence.source.url:
                            collected.append(ResearchHit(
                                url=evidence.source.url, title=evidence.source.title,
                                snippet=evidence.excerpt, provider=provider.name,
                            ))
        except Exception:  # noqa: BLE001
            logger.info("research provider %s failed for %s", provider.name, symbol, exc_info=True)
            continue
        if len({h.url for h in collected}) >= TARGET_HITS:
            break

    ranked = _dedupe_and_rank(collected)[:TARGET_HITS]
    if not ranked:
        return KnowledgeBundle()
    # Normalization is shared: identical evidence rules regardless of which
    # provider (or mix of providers) produced these hits.
    return ResearchProvider.normalize(_NORMALIZER, symbol, ranked)


class _EngineNormalizer(ResearchProvider):
    """Carries the engine's name onto merged claims, since the evidence may
    come from several providers at once."""
    name = "research"


_NORMALIZER = _EngineNormalizer()


def reset_for_tests() -> None:
    _instances.clear()
