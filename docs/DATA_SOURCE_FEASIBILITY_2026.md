# Data-source feasibility, 2026

Assessment date: 2026-09-19. Prices and vendor terms change; verify them at
purchase time. `PIT` below means the source can expose a usable first-available
time, not merely that it has old rows. Unknowns are deliberately not promoted
to assumptions.

## Feasibility matrix

| Source | Class | Relevant coverage | PIT/revisions | Access/cost | License/redistribution | Engineering fit | Decision |
|---|---|---|---|---|---|---|---|
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | OPEN | Submissions, XBRL company facts; Forms 3/4/5, 8-K, 10-Q/K, 13F through EDGAR | Acceptance/accession timestamps support PIT versioning | Free; no API key; fair-access limits; nightly bulk archives | Public filings, but SEC access policy and third-party exhibit rights still apply | High; JSON/XML, stable identifiers, local parser needed | **Acquire first** |
| [FRED/ALFRED](https://fred.stlouisfed.org/docs/api/fred/) | FREE WITH API KEY | Macro/rates, economic release vintages | ALFRED real-time periods explicitly support vintages | Free API key | Some series include third-party restrictions; inspect each series | High; replaces non-vintage macro ambiguity | **Acquire/normalize first** |
| Existing local Dolt + Parquet | OPEN per manifests | OHLCV, actions, rates, options aggregates, earnings, estimates, statements | Mixed; estimates vintage dated, statement revisions unknown | Already present, ~14 GB raw | Manifests say open; retain source/version and verify upstream terms before redistribution | Highest; first task is provenance/quality, not another download | **Use price/volume; quarantine statement history; analyst arm already null** |
| [Alpha Vantage](https://www.alphavantage.co/documentation/) | FREE KEY / PAID | Equities, historical options, fundamentals, estimates, news, transcripts, insider/institutional | Historical endpoints exist; true estimate/restatement vintages not established by docs | Free throttled tier; many full/history endpoints premium | Terms must be checked for storage/redistribution | Easy REST; broad fallback, weaker research provenance | **Pilot only** |
| [Finnhub](https://finnhub.io/docs/api/) | FREE KEY / PAID | Prices, fundamentals, estimates, ownership, news | Historical revision guarantees unverified | Free/paid tiers | Commercial/storage rights plan-specific | Easy REST | **Do not rely on for PIT until contract confirms** |
| [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs) | FREE KEY / PAID | Prices, statements, estimates, earnings, transcripts | Historical availability/revision guarantees unverified | Free/paid | Plan-specific | Easy REST | **Operational fallback, not PIT authority** |
| [Nasdaq Data Link](https://docs.data.nasdaq.com/docs/getting-started) | FREE KEY / PAID | Marketplace for open and premium financial datasets | Dataset-specific | API; many useful datasets paid a la carte | Dataset-specific, often restrictive | Good API, but not one uniform source | **Evaluate per dataset** |
| Nasdaq official symbol/short-interest/market data | OPEN metadata / PAID market data | Listings and selected regulatory files; exchange market data | Dataset-specific | Mixed | Exchange terms; do not conflate symbol files with licensed feeds | Useful for identifiers, not a one-stop PIT master | **Target specific public files only** |
| [Tiingo](https://www.tiingo.com/pricing) | FREE KEY / PAID | Long price history and fundamentals | Corporate-action support; statement vintage semantics need confirmation | Public pricing includes free starter and paid personal tiers | Personal/internal-use restrictions; no assumed redistribution | Straightforward API | **Price-data backup; not new alpha priority** |
| [Twelve Data](https://twelvedata.com/pricing) | FREE KEY / PAID | Market/time-series APIs | Historical depth and corrections plan-specific | Credit-based free/paid tiers | Licensing varies by use/exchange | Easy API; overlaps current prices | **Low incremental value** |
| [Massive](https://massive.com/pricing) | PAID | US stocks/options market data | Timestamped trades/quotes; correction/history depends tier | Paid tiers | Market-data licensing/redistribution constraints | Strong for contract-level data, material storage/cost | **Options upgrade candidate, later** |
| [Cboe DataShop](https://datashop.cboe.com/) | PAID / ACADEMIC DISCOUNT | Authoritative US option EOD/quotes from roughly 2012; IV/Greeks add-ons | Exchange timestamps; derived IV method documented by product | Paid; academic discount advertised; large recurring packages | Redistribution is separate/restricted | High-quality but heavy ingest and cost | **Best options source if funded** |
| ORATS / Intrinio options | COMMERCIAL | Derived surfaces/options history | Product-specific; contract verification required | Paid, quote required | Commercial restrictions | Potentially easier derived features, weaker reproducibility | **Not primary without funded license** |
| Tradier | FREE KEY / PAID brokerage API | Current/limited option chains | Long PIT historical archive not established | Account/plan dependent | Terms plan-specific | Live collection, not immediate historical research | **Not a replacement for OptionMetrics history** |
| [WRDS](https://wrds-www.wharton.upenn.edu/) / CRSP, Compustat, IBES, OptionMetrics | ACADEMIC / COMMERCIAL | Gold-standard returns, delistings, fundamentals, estimates, options | Strong histories; exact PIT fields product-specific | Institutional academic subscription | Raw redistribution generally prohibited | Excellent research reference, poor public-product portability | **Use if institution already licenses** |
| Yahoo Finance/LSEG | COMMERCIAL / IMPRACTICAL FOR PUBLIC RESEARCH | Consumer market/fundamental display | No research-grade revision commitment | Free UI/endpoints may be unstable | [Provider terms](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html) restrict copying/republication/redistribution | Fragile/unofficial for bulk reproducibility | **Reject as canonical research feed** |
| Stooq | UNVERIFIED | EOD history | PIT/corrections and delisting policy not verified | Often free downloads | License/redistribution not verified | Easy bulk files | **Blocked pending written terms and methodology** |
| Hugging Face finance datasets | OPEN/MIXED | Text, sentiment, filings, benchmark labels | Dataset-card dependent; often not PIT equity panels | Usually downloadable | Per-dataset license/source chain | Useful for NLP pretraining/evaluation, rarely full stock-selection replication | **Verify each card; no blanket approval** |
| Kaggle mirrors | OPEN/MIXED | Arbitrary mirrors of prices/fundamentals/news | Often unknown | Usually free | Provenance/license frequently incomplete | Low reproducibility unless upstream is authoritative | **Reject unless provenance and license resolve** |

## Source-by-source risk notes

1. Public does not mean costless. EDGAR requires identifier normalization,
   amendments, units, duplicate fact resolution, filing cutoffs, and respectful
   rate limiting.
2. Vendor statement histories often present the latest restated value for an
   old period. Unless the contract/schema identifies filing vintage, that data
   is prohibited for historical simulation.
3. Consensus estimates require contributor set, effective timestamp, horizon
   roll, and correction policy. A dated row alone does not prove unbiased PIT
   construction.
4. Options need contract-level bid/ask, underlying synchronization, corporate
   actions, stale/zero-bid filters, early-exercise conventions, and a reproducible
   IV solver. Aggregated volatility histories cannot stand in for that proof.
5. Raw licensed data must remain outside git. Commit a manifest, source URL or
   contract identifier, retrieval time, schema/version, date/symbol coverage,
   row count, and SHA-256.

## Acquisition properties needed for replication

Values are planning ranges. Vendor prices and entitlements are deliberately
not guessed; `quote/plan` means verify in a contract before purchase.

| Source / family | Historical depth and frequency | Bulk/API and rate | PIT quality | US coverage | Storage / acquisition estimate | Student access / cost | Redistribution | Closest paper use |
|---|---|---|---|---|---|---|---|---|
| SEC Financial Statement Data Sets | 2009+, quarterly bulk publication; facts at filing granularity | Quarterly ZIPs; `sub`, `num`, `tag`, `pre` | **High** when keyed by accession and accepted/filed; amendments retained | SEC filers | 5–20 GB raw/cache; hours to download, days to normalize | Open/free | Public-record access policy applies; commit derived metadata, not bulk corpus | GKX-style PIT fundamentals |
| SEC Submissions / Company Facts | XBRL required from 2009; real-time JSON plus nightly bulk ZIPs | No key; SEC maximum 10 requests/s across machines; bulk preferred | High for filing availability; Company Facts can contain multiple filing vintages that must not be collapsed | SEC registrants including domestic/foreign forms listed by SEC | 1–10 GB targeted; 1–3 days initial pipeline | Open/free | Respect SEC policy and exhibit rights | Identity, facts, filing text |
| SEC Form 4 | Electronic filings since early 2000s; event/filer transaction detail | EDGAR index/bulk/XML | High if acceptance time and amendment retained | Section 16 reporters | 1–5 GB targeted; several engineering days | Open/free | Public filing; no blanket right over third-party attachments | Insider events |
| SEC 13F | Quarterly, up to 45-day reporting lag; amendments | EDGAR XML/bulk | High for *reported-at* time, not quarter-end availability | US institutional managers in scope | 2–10 GB; 1–2 weeks entity/security mapping | Open/free | Public filing; identifiers/mappings need terms | Institutional ownership change |
| FRED / ALFRED | Series-dependent; daily to annual; real-time vintages for ALFRED | API key, series endpoints | **High** for vintage macro when real-time periods are retained | Macro, not securities | <5 GB; hours-days | Free | Series-specific third-party restrictions | Macro state controls |
| OpenFIGI | Current mapping service, not a complete historical master | API: 25 requests/min and 10 jobs/request without key; 25/6 sec and 100 jobs with key | Mapping response is not a historical effective-date record | Broad identifiers | <100 MB; hours for 998 names | Free; free account raises limit | OpenFIGI terms apply; do not assume mapping redistribution | Identity cross-check only |
| Exchange symbol directories/notices | Current daily files and dated notices; archival depth varies | Download/files; exchange-specific | Medium if snapshots are archived prospectively | Listed US instruments | <10 GB; ongoing daily job | Mixed open metadata / paid feeds | Exchange-specific | Listing/exchange status |
| CRSP / Compustat / IBES / OptionMetrics through WRDS | Decades; daily/monthly/event/vendor-specific | Institutional bulk/query | Research-grade, but PIT semantics still field-specific | Strong | Tens to hundreds of GB; days-weeks | Academic institution subscription; commercial otherwise | Raw redistribution prohibited | Most canonical papers |
| Cboe DataShop / OptionMetrics | Roughly 1996/2012+ depending product; daily/intraday contracts | Bulk commercial delivery | High timestamps, but synchronization/filtering still required | Listed US options | 0.1–2+ TB contract-level; days-weeks | Paid; academic terms may exist | Restricted | IV surface/moments |
| Massive / Polygon-style market APIs | Plan-specific daily/intraday stocks/options | API/bulk by plan | Good timestamps; corrections/history require contract review | US market | 50 GB–TB; days | Paid | Restricted | Feasible option-chain substitute |
| Analyst vendors (IBES/Refinitiv/FactSet) | Decades, estimate-level snapshots depending product | Licensed bulk/API | Potentially high with contributor/effective timestamps | Broad US | 10–100+ GB; weeks to validate | Academic/commercial | Restricted | Stickiness, breadth, acceleration |
| News/transcript vendors | Provider-dependent archives and timestamps | Licensed feeds | Variable; corrections/publication time are critical | Broad | 100 GB–TB with text/audio | Commercial, often costly | Strongly restricted | FinBERT/LLM/transcripts |
| Alpha Vantage / Finnhub / FMP / Tiingo / Twelve Data | Plan-specific | REST, rate/credit limits | **Unproven for revision-vintage research** unless contract says otherwise | Broad but endpoint-dependent | GB-scale targeted | Free/paid tiers | Plan-specific | Operational fallback, not canonical replication |
| Nasdaq Data Link | Dataset-specific | API/bulk | Dataset-specific | Dataset-specific | Dataset-specific | Free/paid marketplace | Dataset-specific | Discovery/procurement channel only |

## Ranked acquisition recommendation

| Rank | Acquisition | Expected alpha value | Cost/effort | Reason |
|---:|---|---|---|---|
| 1 | SEC as-reported numeric facts (`sub`/`num`/`tag`/`pre`) | **High information-content prior** | Low cash / medium-high engineering | Enables broad profitability/value/investment panel with auditable vintages |
| 2 | PIT CIK/ticker/SIC/shares/security master and delisting layer | High reliability and alpha-enabling value | Medium-high | Required for identity, size/industry controls, survivorship and realistic exits |
| 3 | ALFRED vintage macro | Low direct alpha, high leakage-control value | Low | Removes revised-macro ambiguity cheaply |
| 4 | SEC filing text and earnings exhibits | Medium, orthogonal event information | Low cash / high engineering | Supported by filing/earnings-text studies; follows numeric SEC build |
| 5 | SEC Form 4 / 13F | Uncertain-to-medium | Low cash / high mapping work | Public and orthogonal, but lag/event semantics require separate preregistration |
| 6 | Contract-level Cboe/Massive/OptionMetrics options | Uncertain/mixed | High cash/storage/engineering | Synchronization-sensitive and weak incremental evidence; local aggregates are insufficient |
| 7 | Licensed analyst-level or news/transcript archive | Potentially medium | High license and validation burden | Only justified if it supplies genuinely new granularity/rights, not another consensus snapshot |

Post-EXP-009 conclusion: do not retest the same analyst aggregates, do not buy a
broad bundle, and do not prioritize options. Build the SEC numeric/PIT identity
foundation first. The official SEC API page confirms real-time submissions and
XBRL APIs plus nightly `submissions.zip` and `companyfacts.zip`; the Financial
Statement Data Set documentation links `NUM` to `SUB` by accession and tags to
`TAG`/`PRE`. Use quarterly bulk files for reproducibility and keep the API for
incremental refreshes.
