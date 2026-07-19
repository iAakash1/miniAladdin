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
