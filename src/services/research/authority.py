"""
Source authority ranking — the rule that keeps community chatter from
outranking a filing.

Authority is a property of the SOURCE, not of the provider that found it.
Brave, Tavily and Exa all surface SEC filings and all surface forums; what
matters is the host. Ranking here (rather than per provider) is what makes
the research engine provider-agnostic: swap every provider and the
ordering of evidence is unchanged.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Descending authority. The first matching tier wins.
TIER_FILING = 100      # SEC/EDGAR and equivalents — the primary record
TIER_GOVERNMENT = 90   # .gov, central banks, statistical agencies
TIER_COMPANY_IR = 80   # the company's own investor relations
TIER_MAJOR_NEWS = 65   # wire services and major financial press
TIER_RESEARCH = 50     # independent research, exchanges, data providers
TIER_GENERAL = 35      # everything else
TIER_COMMUNITY = 10    # forums, social — never outranks the above

FILING_HOSTS = {"sec.gov", "efts.sec.gov", "edgar.sec.gov"}

GOVERNMENT_SUFFIXES = (".gov", ".gov.uk", ".europa.eu")
GOVERNMENT_HOSTS = {
    "federalreserve.gov", "stlouisfed.org", "bls.gov", "treasury.gov",
    "ecb.europa.eu", "imf.org", "worldbank.org", "bis.org",
}

MAJOR_NEWS_HOSTS = {
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "apnews.com", "barrons.com", "economist.com", "forbes.com",
    "marketwatch.com", "nytimes.com", "washingtonpost.com", "axios.com",
    "businessinsider.com", "fortune.com",
}

RESEARCH_HOSTS = {
    "morningstar.com", "spglobal.com", "moodys.com", "fitchratings.com",
    "nasdaq.com", "nyse.com", "investor.gov", "cfainstitute.org",
    "seekingalpha.com", "fool.com", "zacks.com",
}

COMMUNITY_HOSTS = {
    "reddit.com", "quora.com", "stocktwits.com", "x.com", "twitter.com",
    "facebook.com", "instagram.com", "tiktok.com", "medium.com",
    "substack.com", "wordpress.com", "blogspot.com",
}

# Investor-relations paths are the company's own primary disclosure.
IR_MARKERS = ("investor.", "investors.", "/investor", "/investors", "ir.")


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def authority_of(url: str) -> int:
    """Score a URL's source authority. Unknown hosts get TIER_GENERAL —
    never zero, so a legitimate but unlisted source is still usable."""
    host = host_of(url)
    if not host:
        return 0
    lowered = url.lower()

    if host in FILING_HOSTS or host.endswith(".sec.gov"):
        return TIER_FILING
    if host in GOVERNMENT_HOSTS or host.endswith(GOVERNMENT_SUFFIXES):
        return TIER_GOVERNMENT
    if any(marker in lowered for marker in IR_MARKERS):
        return TIER_COMPANY_IR
    if host in MAJOR_NEWS_HOSTS or any(host.endswith("." + h) for h in MAJOR_NEWS_HOSTS):
        return TIER_MAJOR_NEWS
    if host in RESEARCH_HOSTS:
        return TIER_RESEARCH
    if host in COMMUNITY_HOSTS or any(host.endswith("." + h) for h in COMMUNITY_HOSTS):
        return TIER_COMMUNITY
    return TIER_GENERAL


def is_community(url: str) -> bool:
    return authority_of(url) <= TIER_COMMUNITY


def confidence_for(url: str) -> float:
    """Map authority to the claim-confidence band.

    Capped at 0.75 so no web source, however authoritative, can rival the
    deterministic record (SEC XBRL 1.0, Wikidata 0.9). Community content
    bottoms out at 0.25.
    """
    score = authority_of(url)
    if score >= TIER_FILING:
        return 0.75
    if score >= TIER_GOVERNMENT:
        return 0.70
    if score >= TIER_COMPANY_IR:
        return 0.65
    if score >= TIER_MAJOR_NEWS:
        return 0.60
    if score >= TIER_RESEARCH:
        return 0.50
    if score >= TIER_GENERAL:
        return 0.40
    return 0.25


# ── provider priors ──────────────────────────────────────────────────────────
# Retrieval quality differs between providers, but it only matters when the
# SOURCE itself is unremarkable. A SEC filing is authoritative no matter who
# found it; a generic blog is worth slightly more from semantic retrieval
# (Exa) than from a keyword index. So the prior nudges generic sources and
# is ignored for high-authority ones — which keeps "community never outranks
# a filing" true regardless of provider.
PROVIDER_PRIOR: dict[str, float] = {
    "exa": 0.60,
    "tavily": 0.55,
    "brave": 0.52,
    "newsapi": 0.50,
    "gnews": 0.48,
    "news": 0.50,
    "apify": 0.45,
    "research": 0.50,
}

PRIOR_APPLIES_BELOW = TIER_MAJOR_NEWS  # above this, the source speaks for itself


def confidence_for_source(url: str, provider: str = "", published_at: str = "") -> float:
    """Delegates to the confidence policy — this module owns SOURCE
    authority (what a URL is worth); the policy owns how authority,
    provider reliability, corroboration and freshness combine."""
    from src.services.confidence import score

    return score(
        provider or "research",
        source_authority=confidence_for(url),
        published_at=published_at or None,
        is_web_source=True,
    ).value


# Independent corroboration is genuine evidence: two providers finding the
# same claim in different sources raises confidence, toward a ceiling that
# still sits below the deterministic record.
CORROBORATION_STEP = 0.05
CORROBORATION_CEILING = 0.80


def corroborated(confidence: float, provider_count: int) -> float:
    """Delegates to the confidence policy."""
    from src.services.confidence import score

    if provider_count <= 1:
        return confidence
    return score("research", source_authority=confidence,
                 corroborating_providers=provider_count, is_web_source=True).value
