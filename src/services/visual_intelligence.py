"""
Visual intelligence — company identity and editorial context.

Two capabilities that must never be confused with each other:

* **Identity** is a company's actual logo, from Logo.dev, keyed on its ticker
  or its domain. It is a factual claim about who a company is.
* **Context** is an editorial photograph from Pexels or Unsplash, chosen from
  a query built out of the company's own sector and industry. It is a claim
  about what an industry looks like, and nothing more.

They are kept in separate types and separate fields all the way to the
browser. Collapsing them into one "image" is how a photograph of an orchard
ends up rendering where Apple's logo belongs.

## Why both image libraries are queried

Pexels and Unsplash have different contributor bases and return genuinely
different photographs for the same query. They run **concurrently through the
evidence fabric**, and both result sets are kept and ranked together — a
fallback would halve the candidate pool for no latency saving, since the calls
overlap in time.

## Why nothing here blocks financial data

Imagery is resolved by its own endpoint, on its own cache, after the research
payload has already rendered. A slow stock-photo API must never delay a price.

## Rate limits

Pexels allows 200 requests/hour, Unsplash 50/hour on a demo application.
A company's sector does not change, so the cache TTL is measured in days and
a repeated page view costs nothing. The cache is keyed on the *normalised
query*, not the ticker, so every semiconductor company shares one lookup.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Optional

from src.providers import fabric
from src.providers.schemas import VisualAsset
from src.providers.vendors.visual_vendors import (
    LogoDevVendor,
    PexelsVendor,
    UnsplashVendor,
    stable_pick,
)

logger = logging.getLogger(__name__)

# Contextual imagery is a function of a company's industry, which changes on a
# scale of years. A day's cache is already conservative.
CONTEXT_TTL_SECONDS = 86_400.0
# A brand mark is pure URL construction — no request is made — so this cache
# exists only to avoid repeating the string work per row of a table.
IDENTITY_TTL_SECONDS = 604_800.0

# Terminal cards are wide. A portrait photograph in a 16:5 strip is mostly
# crop, so anything squarer than this is penalised rather than excluded —
# excluded would sometimes leave nothing at all.
PREFERRED_ASPECT = 1.6
MIN_USABLE_WIDTH = 800

# Words that carry no visual meaning and would only dilute a two-or-three
# term image query.
_STOPWORDS = {
    "inc", "inc.", "corp", "corporation", "co", "company", "ltd", "limited",
    "plc", "holdings", "group", "the", "and", "&", "class", "common", "stock",
    "sa", "nv", "ag", "se",
}


class _Cache:
    """Small TTL map. Deliberately in-process and not Redis.

    The values are a handful of URLs per query, the working set is the
    industries the user actually browses, and the provider layer already has
    an in-memory cache with the same lifetime as the process. Adding a network
    hop and a dependency to memoise two image URLs would cost more than it
    saves.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires, value = entry
            if time.monotonic() > expires:
                self._data.pop(key, None)
                return None
            return value

    def put(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._data)}


_context_cache = _Cache()
_identity_cache = _Cache()

_logo = LogoDevVendor()
_pexels = PexelsVendor()
_unsplash = UnsplashVendor()

IMAGE_VENDORS = [_pexels, _unsplash]


def reset_for_tests() -> None:
    _context_cache._data.clear()
    _identity_cache._data.clear()


# ── query construction ─────────────────────────────────────────────────────

def build_query(
    *, name: str = "", sector: str = "", industry: str = "",
) -> str:
    """A short visual query from what the company profile already says.

    Industry over sector over name, because specificity is what makes the
    photograph relevant: "semiconductor manufacturing" returns fabs, while
    "Technology" returns laptops on desks and "NVIDIA" returns logos and
    press shots that are not ours to use.

    The company name is deliberately *excluded* from the query. Searching a
    stock library for a brand name returns either nothing or somebody else's
    photograph of that brand's products, and presenting either as context for
    the company would be the exact confusion this module exists to prevent.
    The one exception is a company with no sector or industry recorded, where
    a name-derived query is better than none — and even then the name is
    stripped of its corporate suffixes first.
    """
    industry = (industry or "").strip()
    sector = (sector or "").strip()
    if industry:
        return _normalise(industry)
    if sector:
        return _normalise(f"{sector} industry")
    tokens = [
        w for w in re.split(r"[\s,]+", (name or "").lower())
        if w and w not in _STOPWORDS
    ]
    return _normalise(" ".join(tokens[:2])) if tokens else ""


def _normalise(query: str) -> str:
    """Lowercased, punctuation-free, whitespace-collapsed.

    The cache is keyed on this, so "Semiconductors  &  Equipment" and
    "semiconductors and equipment" must not be two entries against a 200/hour
    budget.
    """
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (query or "").lower())
    return " ".join(cleaned.split())[:80]


# ── ranking ────────────────────────────────────────────────────────────────

def score(asset: VisualAsset, query: str) -> float:
    """Deterministic, explainable relevance. No model, no embedding.

    Four additive terms, each defensible on its own:
      * word overlap between the query and the asset's own description,
      * a penalty for shapes that will be mostly crop in a wide card,
      * a penalty for images too small to render sharply,
      * a small bonus for a described image, since alt text is required and
        an undescribed photograph cannot supply one.
    """
    terms = set(query.split())
    described = f"{asset.alt_text} {' '.join(asset.provider_metadata.get('tags') or [])}".lower()
    words = set(re.sub(r"[^a-z0-9\s]", " ", described).split())
    overlap = len(terms & words) / len(terms) if terms else 0.0

    shape = 0.0
    if asset.aspect_ratio:
        # Distance from the preferred landscape ratio, capped so a square
        # image is penalised but not disqualified.
        shape = -min(0.4, abs(asset.aspect_ratio - PREFERRED_ASPECT) * 0.25)

    size = 0.0 if (asset.width or 0) >= MIN_USABLE_WIDTH else -0.3
    has_alt = 0.15 if asset.alt_text else 0.0

    return round(overlap + shape + size + has_alt, 4)


def _dedupe(assets: list[VisualAsset]) -> list[VisualAsset]:
    """Drop assets that are the same photograph.

    Keyed on provider+id first, then on the image URL. Deliberately *not* on
    visual similarity: two different photographs of the same subject are two
    candidates, and collapsing them would shrink the pool the ranking is
    supposed to choose from.
    """
    seen: set[str] = set()
    out: list[VisualAsset] = []
    for asset in assets:
        key = f"{asset.provider}:{asset.provider_asset_id}" if asset.provider_asset_id else asset.image_url
        if key in seen:
            continue
        seen.add(key)
        out.append(asset)
    return out


# ── public API ─────────────────────────────────────────────────────────────

def identity(symbol: str, domain: str = "") -> Optional[dict[str, Any]]:
    """A company's brand mark, or None when Logo.dev is not configured.

    Returns None rather than a placeholder: the UI already draws a monogram
    for an unresolved company, and a stand-in URL here would replace a
    deliberate fallback with a broken image.
    """
    key = f"{symbol.upper()}|{domain}"
    cached = _identity_cache.get(key)
    if cached is not None:
        return cached
    mark = _logo.get_brand(symbol, domain)
    payload = mark.model_dump() if mark else None
    _identity_cache.put(key, payload, IDENTITY_TTL_SECONDS)
    return payload


def context_images(
    query: str, *, limit: int = 8,
) -> dict[str, Any]:
    """Editorial imagery for a query, from every configured image library.

    Both libraries run concurrently through the evidence fabric, both result
    sets are kept, and the merged pool is deduplicated and ranked together.
    Provider failures are returned as evidence rather than swallowed, so the
    provenance panel can say which library answered and how fast.
    """
    normalised = _normalise(query)
    if not normalised:
        return {"query": "", "assets": [], "evidence": [], "cached": False,
                "providers": [], "reason": "no query could be derived"}

    cached = _context_cache.get(normalised)
    if cached is not None:
        return {**cached, "cached": True}

    evidence = fabric.collect(
        "image_search", normalised, IMAGE_VENDORS,
        lambda v: v.search_images(normalised, limit=limit * 2),
        timeout=8.0,
    )

    assets: list[VisualAsset] = []
    for item in evidence:
        if item.ok and isinstance(item.data, list):
            assets.extend(item.data)

    for asset in assets:
        asset.relevance = score(asset, normalised)
    ranked = sorted(_dedupe(assets), key=lambda a: a.relevance, reverse=True)[:limit]

    payload = {
        "query": normalised,
        "assets": [a.model_dump() for a in ranked],
        "providers": sorted({e.provider for e in evidence if e.ok}),
        "evidence": [
            {
                "provider": e.provider, "ok": e.ok, "status": e.status,
                "latency_ms": e.latency_ms,
                "results": len(e.data) if e.ok and isinstance(e.data, list) else 0,
            }
            for e in evidence
        ],
        "cached": False,
    }
    # Only successful lookups are cached. Caching an outage would turn a
    # transient 429 into a day without imagery.
    if ranked:
        _context_cache.put(normalised, payload, CONTEXT_TTL_SECONDS)
    return payload


def hero_for_company(
    symbol: str, *, name: str = "", sector: str = "", industry: str = "",
) -> Optional[dict[str, Any]]:
    """One contextual image for a company page, chosen deterministically.

    Hash-indexed by ticker so two semiconductor companies do not show the
    same photograph, and so one company's image does not change between page
    loads — an image that reshuffles on refresh reads as decoration rather
    than as part of the record.

    Unsplash asks that a download be registered when an image is actually
    displayed; that happens here, for the single chosen asset, rather than
    for all thirty search results.
    """
    query = build_query(name=name, sector=sector, industry=industry)
    if not query:
        return None
    pool = context_images(query, limit=8)
    assets = pool["assets"]
    if not assets:
        return None

    chosen = stable_pick([VisualAsset(**a) for a in assets], symbol.upper())
    if chosen is None:
        return None

    if chosen.provider == "unsplash":
        location = chosen.provider_metadata.get("download_location")
        if location:
            _unsplash.register_download(str(location))

    return {
        "asset": chosen.model_dump(),
        "query": query,
        "providers": pool["providers"],
        "cached": pool["cached"],
        "evidence": pool["evidence"],
        # Stated in the payload so a renderer cannot present this as the
        # company's own photograph.
        "kind": "editorial_context",
        "disclaimer": "Editorial stock imagery selected from the company's "
                      "industry — not a photograph of this company.",
    }


def diagnostics() -> dict[str, Any]:
    """Configuration state, without ever reading a secret's value."""
    return {
        "logo_dev": {
            "configured": _logo.available,
            # Presence only. The value never leaves this process.
            "secret_configured": bool(_logo.secret),
        },
        "pexels": {"configured": _pexels.available, "healthy": _pexels.healthy},
        "unsplash": {"configured": _unsplash.available, "healthy": _unsplash.healthy},
        "cache": {
            "context": _context_cache.stats(),
            "identity": _identity_cache.stats(),
        },
    }
