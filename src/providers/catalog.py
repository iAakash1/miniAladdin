"""The provider catalogue: what each vendor is, beyond what its code can say.

The capability registry (`capabilities.py`) declares the questions; vendors
declare by introspection which they can answer; `base.VendorClient` records
what each one has actually done. None of those can say who a vendor is, what
kind of source it is, how it is reached, or what its terms allow. That is
this module, keyed by the adapter's `NAME` and held equal to the adapters by
`tests/test_provider_catalog.py`, so a new adapter without an entry fails the
build rather than appearing on the providers page as a bare identifier.

**What the licence fields are, and are not.** They record what was checked
and when, and nothing more:

  ``reviewed``     the terms page was read on `TERMS_CHECKED_ON`; `notes`
                   summarises the restrictions relevant to how OmniSignal
                   uses the data. A summary, not legal advice.
  ``located``      a terms page exists at `terms_url` (it answered HTTP 200 on
                   `TERMS_CHECKED_ON`) but its contents have not been reviewed.
  ``not_located``  no terms page was found at the address tried. The terms
                   still exist and still apply; they have not been read.

No entry claims a permission. Where a reviewed term restricts how the data may
be used, the note says so, and the operator decides — `PROVIDER_DISABLED`
takes a vendor out of routing without touching its credential.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

#: The date every `terms_status` below was established.
TERMS_CHECKED_ON = "2026-10-24"

DOMAINS = (
    "market_data", "fundamentals", "filings", "macro", "news", "search",
    "identity", "official_record", "knowledge", "visual",
)

SOURCE_KINDS = (
    "commercial",       # a company selling data or API access
    "government",       # a public agency publishing its own records
    "intergovernmental",  # ECB, World Bank
    "open_data",        # community-maintained open data (Wikidata)
    "unofficial",       # a library reaching a service that publishes no API
    "platform",         # a service running third-party scrapers (Apify)
)

TERMS_STATUSES = ("reviewed", "located", "not_located")


@dataclass(frozen=True)
class ProviderInfo:
    """Static facts about one vendor adapter."""

    name: str
    display_name: str
    domain: str
    source_kind: str
    #: How the adapter is reached. A host or library, never a URL with a key.
    endpoint: str
    terms_status: str
    terms_url: Optional[str] = None
    #: Restrictions read in the terms, or the open question they raise.
    notes: Optional[str] = None
    #: Wording the source requires wherever its data is shown.
    attribution: Optional[str] = None
    #: Settings besides the credential that change how the vendor behaves.
    optional_env: tuple[str, ...] = field(default_factory=tuple)
    #: The reviewed terms restrict a use this deployment makes, so the owner
    #: must confirm the plan or licence before the vendor serves the public.
    licence_review: bool = False

    def describe(self) -> dict[str, Any]:
        out = asdict(self)
        out["optional_env"] = list(self.optional_env)
        out["terms_checked_on"] = TERMS_CHECKED_ON
        return out


FRED_NOTICE = (
    "This product uses the FRED® API but is not endorsed or certified by the "
    "Federal Reserve Bank of St. Louis."
)

_ENTRIES: tuple[ProviderInfo, ...] = (
    # ── market data and fundamentals ────────────────────────────────────────
    ProviderInfo(
        "polygon", "Polygon.io", "market_data", "commercial", "api.polygon.io (HTTPS JSON)",
        "located", "https://polygon.io/terms",
        notes="Massive serves the same Polygon wire format; whether the two share terms was not checked.",
    ),
    ProviderInfo(
        "massive", "Massive", "market_data", "commercial", "api.massive.com (HTTPS JSON)",
        "reviewed", "https://massive.com/terms",
        notes=(
            "Index page only: products labelled Individual Use are for personal, non-business use; "
            "business use falls under separate Business terms, which were not reviewed. Display "
            "and redistribution limits are in those terms."
        ),
    ),
    ProviderInfo(
        "finnhub", "Finnhub", "market_data", "commercial", "finnhub.io/api/v1 (HTTPS JSON)",
        "reviewed", "https://finnhub.io/terms-of-service",
        notes=(
            "Plans are for personal use unless stated otherwise. Redistributing or sharing the data, "
            "or results derived from it, needs Finnhub's written approval. Data must be deleted when "
            "the subscription ends. Showing Finnhub-derived values to other users needs that approval."
        ),
        licence_review=True,
    ),
    ProviderInfo(
        "twelvedata", "Twelve Data", "market_data", "commercial", "api.twelvedata.com (HTTPS JSON)",
        "located", "https://twelvedata.com/terms",
    ),
    ProviderInfo(
        "fmp", "Financial Modeling Prep", "fundamentals", "commercial",
        "financialmodelingprep.com/stable (HTTPS JSON)",
        "located", "https://site.financialmodelingprep.com/terms-of-service",
    ),
    ProviderInfo(
        "marketstack", "Marketstack", "market_data", "commercial", "api.marketstack.com (HTTPS JSON)",
        "located", "https://marketstack.com/terms",
    ),
    ProviderInfo(
        "tiingo", "Tiingo", "market_data", "commercial", "api.tiingo.com (HTTPS JSON)",
        "not_located",
    ),
    ProviderInfo(
        "alpha_vantage", "Alpha Vantage", "fundamentals", "commercial",
        "www.alphavantage.co (HTTPS JSON, via src/alpha_vantage.py)",
        "located", "https://www.alphavantage.co/terms_of_service/",
    ),
    ProviderInfo(
        "yfinance", "Yahoo Finance (yfinance)", "market_data", "unofficial",
        "yfinance library — not a published Yahoo API",
        "reviewed", "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
        notes=(
            "yfinance is not affiliated with or endorsed by Yahoo, and its README states that Yahoo's "
            "finance API is intended for personal use only. Use in a public or paid service is an open "
            "licensing question for the owner."
        ),
        licence_review=True,
    ),
    # ── filings and identity ────────────────────────────────────────────────
    ProviderInfo(
        "sec", "SEC EDGAR", "filings", "government", "data.sec.gov, www.sec.gov (HTTPS JSON)",
        "reviewed", "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data",
        notes=(
            "Fair-access policy: at most 10 requests per second, and every request declares a "
            "User-Agent naming the requester and a contact address."
        ),
        optional_env=("SEC_USER_AGENT", "SEC_API"),
    ),
    ProviderInfo(
        "openfigi", "OpenFIGI", "identity", "commercial", "api.openfigi.com (HTTPS JSON)",
        "located", "https://www.openfigi.com/docs/terms-of-service",
    ),
    # ── macro ───────────────────────────────────────────────────────────────
    ProviderInfo(
        "fred", "FRED (St. Louis Fed)", "macro", "government", "fredapi library → api.stlouisfed.org",
        "reviewed", "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
        notes=(
            "Public applications must show the not-endorsed notice and link to these terms. Some "
            "series are copyrighted by third parties and need the owner's permission beyond personal "
            "use; those series carry a copyright note in FRED."
        ),
        attribution=FRED_NOTICE,
    ),
    ProviderInfo(
        "bls", "U.S. Bureau of Labor Statistics", "macro", "government", "api.bls.gov (HTTPS JSON)",
        "not_located",
    ),
    ProviderInfo(
        "bea", "U.S. Bureau of Economic Analysis", "macro", "government", "apps.bea.gov/api (HTTPS JSON)",
        "located", "https://apps.bea.gov/API/signup/",
    ),
    ProviderInfo(
        "eia", "U.S. Energy Information Administration", "macro", "government", "api.eia.gov (HTTPS JSON)",
        "located", "https://www.eia.gov/about/copyrights_reuse.php",
    ),
    ProviderInfo(
        "treasury_fiscal", "U.S. Treasury Fiscal Data", "macro", "government",
        "api.fiscaldata.treasury.gov (HTTPS JSON)", "not_located",
    ),
    ProviderInfo(
        "ecb", "ECB Data Portal", "macro", "intergovernmental", "data-api.ecb.europa.eu (HTTPS)",
        "not_located",
    ),
    ProviderInfo(
        "world_bank", "World Bank Open Data", "macro", "intergovernmental", "api.worldbank.org (HTTPS JSON)",
        "located", "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
    ),
    # ── news and search ─────────────────────────────────────────────────────
    ProviderInfo(
        "newsapi", "NewsAPI", "news", "commercial", "newsapi.org/v2 (HTTPS JSON)",
        "reviewed", "https://newsapi.org/terms",
        notes=(
            "The free Developer plan is for development only and may not run in staging or "
            "production; a paid plan is required there. Copyrighted articles may not be republished."
        ),
        licence_review=True,
    ),
    ProviderInfo(
        "gnews", "GNews", "news", "commercial", "gnews.io/api/v4 (HTTPS JSON)", "not_located",
    ),
    ProviderInfo(
        "marketaux", "Marketaux", "news", "commercial", "api.marketaux.com (HTTPS JSON)", "not_located",
    ),
    ProviderInfo(
        "yahoo_rss", "Yahoo Finance RSS", "news", "commercial", "feeds.finance.yahoo.com (RSS)",
        "located", "https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html",
    ),
    ProviderInfo(
        "tavily", "Tavily", "search", "commercial", "api.tavily.com (HTTPS JSON)",
        "located", "https://tavily.com/terms",
    ),
    ProviderInfo(
        "exa", "Exa", "search", "commercial", "api.exa.ai (HTTPS JSON)", "located", "https://exa.ai/terms",
    ),
    # ── official record ─────────────────────────────────────────────────────
    ProviderInfo(
        "federal_register", "Federal Register", "official_record", "government",
        "www.federalregister.gov/api (HTTPS JSON)",
        "located", "https://www.federalregister.gov/developers/documentation/api/v1",
    ),
    ProviderInfo(
        "openfda", "openFDA", "official_record", "government", "api.fda.gov (HTTPS JSON)",
        "located", "https://open.fda.gov/terms/",
    ),
    ProviderInfo(
        "clinicaltrials", "ClinicalTrials.gov", "official_record", "government",
        "clinicaltrials.gov/api (HTTPS JSON)",
        "located", "https://clinicaltrials.gov/about-site/terms-conditions",
    ),
    # ── knowledge and identity imagery ──────────────────────────────────────
    ProviderInfo(
        "wikidata", "Wikidata", "knowledge", "open_data", "query.wikidata.org (SPARQL)",
        "located", "https://www.wikidata.org/wiki/Wikidata:Licensing",
    ),
    ProviderInfo(
        "apify", "Apify", "knowledge", "platform", "api.apify.com/v2 (actor runs)",
        "located", "https://docs.apify.com/legal/general-terms-and-conditions",
        notes="Runs third-party scrapers; the terms of each scraped site apply in addition to Apify's.",
    ),
    ProviderInfo(
        "logo_dev", "Logo.dev", "visual", "commercial", "img.logo.dev (image CDN)", "not_located",
    ),
)

CATALOG: dict[str, ProviderInfo] = {entry.name: entry for entry in _ENTRIES}


def info(name: str) -> Optional[ProviderInfo]:
    return CATALOG.get(name)
