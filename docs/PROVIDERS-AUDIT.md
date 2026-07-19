# Provider Audit — v4.5 (July 2026)

Scope: every external provider adapter (`src/providers/vendors/`), the legacy
Alpha Vantage client (`src/alpha_vantage.py`), and internal services that call
them. Method: read our implementation, cross-reference each vendor's current
free-tier documentation, and mark what we use, what we don't, and what is
worth using. Priority scale: **P0** (implement now, high value / low effort),
**P1** (next), **P2** (worthwhile later), **✗** (not worth it or not available
on our plan).

## Summary of findings

1. The single largest untapped source of intelligence is **not an API at all**:
   we fetch a full year of OHLCV for every analysis and then compute only
   RSI-14, returns, volatility ratios and drawdown from it. Every classic
   technical indicator (EMA/SMA crosses, ADX, ATR, Bollinger, Stochastic,
   OBV, MFI, CCI, Aroon, ROC, VWAP, support/resistance) is computable locally
   from data we already have — zero API calls, zero rate-limit cost. **P0.**
2. **Finnhub free tier** includes three high-value endpoints we never call:
   recommendation trends, historical EPS surprises, and insider sentiment
   (MSPR). These directly answer "what do analysts and insiders think?" —
   currently absent from the product. **P0.**
3. **FMP's free tier has shrunk** (most statement/ratio/ownership endpoints
   are now premium). The v4 wishlist (DCF, institutional ownership, segments,
   executive comp, buybacks…) is ~80% paywalled. We already use what remains
   valuable (profile, quote, income-statement for quality inputs). **✗ for
   the wishlist; no action.**
4. **Alpha Vantage technical endpoints exist but are pointless for us**: the
   25 req/day cap is consumed by fundamentals/MACD, and one analysis needing
   ~12 indicators would burn half the daily budget for data we can compute
   locally from the same OHLCV. **✗ — compute locally instead (finding 1).**
5. **FRED** is effectively unlimited for our volumes and the dashboard already
   reads 14 series across three groups. Marginal additions (credit spreads
   are already in the stress gate) are P2 polish, not gaps.
6. **News intelligence largely exists** (clustering, novelty decay, source
   confirmation, event typing in `src/services/news_scoring.py`). The v4
   "cluster/dedupe/categorize" ask is already shipped; remaining value is
   surfacing it more prominently, not new pipeline. **P2 (UI only).**

## Per-provider detail

### Finnhub — `src/providers/vendors/market_vendors.py`

| Endpoint | Returns | Used today | Free tier | Effort | Value | Priority |
|---|---|---|---|---|---|---|
| `/quote` | live quote | ✓ (price chain) | ✓ 60/min | — | — | keep |
| `/stock/profile2` | company profile | ✓ | ✓ | — | — | keep |
| `/stock/metric?metric=all` | ~90 fundamental metrics | ✓ (subset mapped) | ✓ | low | high — margins/ROE/liquidity already come back and are dropped | **P1: map more fields** |
| `/stock/price-target` | analyst targets | ✓ | ✓ (limited) | — | — | keep |
| `/stock/recommendation` | monthly analyst buy/hold/sell trend | ✗ | ✓ | low | high — "what does the street think," trend over 4 months | **P0** |
| `/stock/earnings` | last 4 EPS surprises | ✗ | ✓ | low | high — earnings execution record; corroborates PEAD | **P0** |
| `/stock/insider-sentiment` | MSPR insider-sentiment index | ✗ | ✓ | low | high — insider conviction signal | **P0** |
| `/stock/insider-transactions` | raw insider trades | ✗ | ✓ | med | med — raw feed; MSPR summarizes it better | P2 |
| `/stock/peers` | peer tickers | ✗ | ✓ | low | med — enables peer context later | P2 |
| `/calendar/earnings` | upcoming earnings | ✗ (yfinance covers) | ✓ | — | duplicate | ✗ |
| `/company-news` | per-ticker news | ✗ (NewsAPI chain covers) | ✓ | — | duplicate | ✗ |
| SEC filings, IPO calendar, supply chain | various | ✗ | partly premium | med | low for our product | ✗ |

### Financial Modeling Prep — `market_vendors.py`, `fundamentals_data.py`

Used today: `/quote/{sym}`, `/profile/{sym}`, historical price series,
income-statement (quality inputs). Free tier (2026): 250 req/day, and the
majority of the v4 wishlist — DCF, ratios history, key-metrics history,
enterprise value, institutional/insider ownership, ETF holdings, segments,
executive info, buybacks, analyst estimates — returns 402 Premium. Verified
against current FMP pricing docs. **No expansion possible without a paid
plan; the audit's recommendation is to keep FMP exactly where it is** (quote/
profile/series fallback + income statement) and lean on Finnhub `metric=all`
for ratio intelligence.

### Alpha Vantage — `src/alpha_vantage.py`

Used today: OVERVIEW (fundamentals) + MACD. 25 req/day hard cap. The
technical-indicator endpoints (EMA, SMA, ADX, ATR, BBANDS, STOCH, OBV, …)
exist on the free tier but at 1 call per indicator per ticker they are
economically useless against a 25/day budget. **Recommendation: never call AV
for anything computable from OHLCV; compute all indicators locally** (P0
technical engine). AV stays for OVERVIEW/MACD where it already works.

### FRED — `data_vendors.py`, `dashboard_service.py`, scoring stress gate

Used today: 10Y-2Y spread, CPI, Fed funds (SRM); NFCI, credit spread,
volatility percentile (stress gate); 14 dashboard series (rates, inflation,
labor, housing, consumption groups). Rate limit 120 req/min — no pressure.
Marginal candidates: M2, dollar index (DTWEXBGS), Michigan sentiment — all P2
dashboard polish; the scoring engine deliberately keeps its macro input set
small and documented. **No P0/P1 gaps.**

### NewsAPI / GNews / Yahoo RSS / Tavily — `news_vendors.py`, `news_scoring.py`

The v2.1 news methodology already implements decay, novelty, clustering,
source confirmation and event typing (acquisition/guidance/lawsuit/etc.), and
the effective-evidence output feeds the news sleeve. Remaining opportunity is
presentation (cluster/timeline UI) — P2. No new endpoints needed.

### Groq (`llm_service.py`), Polygon/TwelveData/MarketStack (price chain), Exa/Tavily (search)

All correctly scoped. Groq's contract (narrate deterministic payloads only)
is unchanged by this release. Price-chain vendors have no unused free
endpoints of value beyond OHLCV. Search is research-context only.

## What this audit commits to (v4.5 scope)

- **P0-A: Technical Intelligence Engine** — local, deterministic computation
  of the full indicator set from the existing 1y OHLCV frame, classified into
  trend/momentum/volatility/volume regimes with plain-language findings,
  attached additively to `/api/research` as `technical_intelligence`, fully
  covered by the Learn More glossary.
- **P0-B: Street & Insider Intelligence (Finnhub)** — recommendation trends,
  EPS surprise history, insider sentiment through the provider abstraction
  (new facade methods, cached, rate-limited, deduped), attached additively as
  `street_intelligence`, with deterministic interpretation and glossary
  coverage.
- **P1: map the unused fields Finnhub `metric=all` already returns** (margins,
  ROE, liquidity ratios) into `FundamentalsData` for the financial-health
  read.
- Everything marked P2 is documented for the next release; everything marked
  ✗ is deliberately out of scope with the reason stated above.


## v5 knowledge providers (July 2026)

Three research-grade providers added since the original audit. All
normalize into `src/providers/research_schemas.py` (KnowledgeBundle) and
merge through `src/services/knowledge_graph.py`.

| Provider | Key | Cost | What it contributes |
|---|---|---|---|
| SEC EDGAR | none (SEC_API optional) | free | Filings with resolved URLs, XBRL company facts (restatement-aware), filing timeline, evidence-bearing financial findings |
| Wikidata | none | free | Executives, founders, subsidiaries, products, industry, exchange, HQ — the entity graph |
| Apify | APIFY_API_TOKEN | paid credits | Web research as **sourced claims only**; unsourced text is discarded |

**Confidence hierarchy is structural, not advisory:** SEC 1.0 > Wikidata
0.9 > web research 0.55. Corroboration across providers raises an edge's
confidence toward a 0.99 ceiling; certainty is never asserted.

**Two findings worth recording for future work:**

1. Wikidata stores tickers as a *qualifier* (`pq:P249`) on the
   `p:P414` exchange-listing statement, not as a direct `wdt:P249`
   property. The obvious query returns zero rows for every company.
2. FMP's premium wall (documented above) is what makes SEC XBRL valuable:
   `companyfacts` provides revenue, net income, balance-sheet and
   cash-flow history for free, straight from the filer, which is
   strictly better provenance than any vendor aggregation.
