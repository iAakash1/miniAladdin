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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.providers.research_schemas import KnowledgeBundle
from src.services.research.authority import authority_of, corroborated, host_of
from src.services.research.base import ProviderHealth, ResearchHit, ResearchProvider
from src.services.research.providers import (
    ApifyProvider,
    BraveProvider,
    ExaProvider,
    GNewsProvider,
    NewsApiProvider,
    NewsProvider,
    TavilyProvider,
)

logger = logging.getLogger(__name__)

# Priority order: AI-native first, then semantic discovery, then news
# breadth, then keyless fallback, then metered page extraction last.
# Order still matters under parallel execution — it decides which providers
# are dispatched in the first wave and which are held back as fallback.
DEFAULT_ORDER = ["tavily", "exa", "newsapi", "gnews", "brave", "news", "apify"]

_REGISTRY: dict[str, type[ResearchProvider]] = {
    "tavily": TavilyProvider,
    "exa": ExaProvider,
    "newsapi": NewsApiProvider,
    "gnews": GNewsProvider,
    "brave": BraveProvider,
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


PARALLEL_WAVE = 4       # providers dispatched concurrently
PROVIDER_TIMEOUT = 12.0  # seconds; a slow provider never blocks the rest


def _dedupe_and_rank(hits: list[ResearchHit]) -> tuple[list[ResearchHit], dict[str, set[str]]]:
    """One row per source, best-authority first, plus who corroborated it.

    Dedup is by (host, path) so the same article with different tracking
    parameters collapses to one piece of evidence. The returned map records
    which providers independently surfaced each source — that agreement is
    real signal and raises confidence downstream.
    """
    seen: dict[str, ResearchHit] = {}
    corroboration: dict[str, set[str]] = {}
    for hit in hits:
        if not hit.url.startswith("http"):
            continue
        key = f"{host_of(hit.url)}{hit.url.split('?')[0].split('#')[0][-60:]}"
        corroboration.setdefault(key, set()).add(hit.provider or "unknown")
        existing = seen.get(key)
        if existing is None:
            seen[key] = hit
        elif len(hit.snippet) > len(existing.snippet):
            # Same source, richer extract — keep the more informative one.
            seen[key] = hit
    ranked = sorted(
        seen.values(),
        key=lambda h: (-authority_of(h.url), h.title.lower()),
    )
    by_url = {
        hit.url: corroboration[f"{host_of(hit.url)}{hit.url.split('?')[0].split('#')[0][-60:]}"]
        for hit in ranked
    }
    return ranked, by_url


def _gather(providers: list[ResearchProvider], call) -> list[ResearchHit]:
    """Run providers in parallel waves, stopping once evidence suffices.

    Waves (rather than one big pool) preserve priority: the best providers
    are consulted first, and slower/lower-priority ones are only paid for
    when the first wave came up short.
    """
    collected: list[ResearchHit] = []
    for start in range(0, len(providers), PARALLEL_WAVE):
        wave = providers[start:start + PARALLEL_WAVE]
        if not wave:
            break
        with ThreadPoolExecutor(max_workers=len(wave), thread_name_prefix="research") as pool:
            futures = {pool.submit(call, p): p for p in wave}
            for future in as_completed(futures, timeout=PROVIDER_TIMEOUT + 3):
                provider = futures[future]
                try:
                    collected.extend(future.result(timeout=PROVIDER_TIMEOUT))
                except Exception:  # noqa: BLE001 — one provider never breaks research
                    logger.info("research provider %s failed", provider.name, exc_info=True)
        if len({h.url for h in collected}) >= TARGET_HITS:
            break
    return collected


def search(query: str, limit: int = 8) -> list[ResearchHit]:
    """Search every capable provider in parallel waves; merge and rank."""
    usable = [p for p in providers_in_order()
              if p.capabilities().search and p.is_configured()]
    collected = _gather(usable, lambda p: p.search(query, limit=limit))
    ranked, _ = _dedupe_and_rank(collected)
    return ranked[:limit]


def research_company(symbol: str, company_name: str = "") -> KnowledgeBundle:
    """Company research across the chain, merged, deduplicated, ranked."""
    symbol = symbol.upper().strip()
    if not symbol:
        return KnowledgeBundle()

    subject = company_name or symbol
    query = f"{subject} {symbol} recent developments competitive position risks"

    def call(provider: ResearchProvider) -> list[ResearchHit]:
        if provider.capabilities().search:
            return provider.search(query, limit=6)
        # Providers without a general index (ticker-scoped RSS) still
        # contribute through their own company path.
        bundle = provider.research_company(symbol, company_name)
        return [
            ResearchHit(url=e.source.url, title=e.source.title,
                        snippet=e.excerpt, published_at=e.source.published_at,
                        provider=provider.name)
            for claim in bundle.claims for e in claim.evidence if e.source.url
        ]

    usable = [p for p in providers_in_order() if p.is_configured()]
    collected = _gather(usable, call)
    ranked, corroboration = _dedupe_and_rank(collected)
    ranked = ranked[:TARGET_HITS]
    if not ranked:
        return KnowledgeBundle()

    # Normalization is shared: identical evidence rules regardless of which
    # provider (or mix) produced these hits.
    bundle = ResearchProvider.normalize(_NORMALIZER, symbol, ranked)

    # Independent corroboration raises confidence — two providers finding
    # the same source is evidence about the source, not about the providers.
    for claim in bundle.claims:
        url = claim.evidence[0].source.url if claim.evidence else ""
        providers_seen = corroboration.get(url or "", set())
        if len(providers_seen) > 1:
            claim.confidence = corroborated(claim.confidence, len(providers_seen))
    return bundle


class _EngineNormalizer(ResearchProvider):
    """Carries the engine's name onto merged claims, since the evidence may
    come from several providers at once."""
    name = "research"


_NORMALIZER = _EngineNormalizer()


def reset_for_tests() -> None:
    _instances.clear()
