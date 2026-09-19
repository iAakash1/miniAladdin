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
| Existing local Dolt + Parquet | OPEN per manifests | OHLCV, actions, rates, options aggregates, earnings, estimates, statements | Mixed; estimates vintage dated, statement revisions unknown | Already present, ~14 GB raw | Manifests say open; retain source/version and verify upstream terms before redistribution | Highest; first task is provenance/quality, not another download | **Audit and exploit before buying** |
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

## Ranked acquisition recommendation

| Rank | Acquisition | Expected alpha value | Cost/effort | Reason |
|---:|---|---|---|---|
| 1 | SEC filing-time corpus: 8-K earnings exhibits plus Forms 3/4/5 | Medium-high, orthogonal event information | Low cash / medium engineering | Open, timestamped, improves provenance and supports recent earnings-text/insider hypotheses |
| 2 | PIT security master and delisting layer (WRDS/CRSP if licensed; otherwise curated SEC/exchange mapping) | High reliability value; medium alpha-enabling value | Medium-high | Required for neutralization, survivorship, sectors and realistic exits |
| 3 | Repair/audit existing analyst-estimate revisions | Medium-high | Low cash / medium validation | Seven million local rows already exist; buying duplicates before proving quality is wasteful |
| 4 | ALFRED vintage macro | Low direct alpha, high leakage-control value | Low | Removes revised-macro ambiguity cheaply |
| 5 | Contract-level Cboe/Massive/OptionMetrics options | Uncertain/mixed | High cash/storage/engineering | Literature is synchronization-sensitive and incremental power is mixed |
| 6 | Licensed news/transcript archive | Potentially medium | High license and NLP burden | Valuable only with durable rights and exact availability times |

Immediate conclusion: do not buy a broad market-data bundle for EXP-008.
First formalize the data manifest and exploit the existing estimate/earnings
inventory; independently build the public SEC event corpus. Defer options until
the low-cost objective/turnover experiment establishes that model research can
clear net-economic gates.
