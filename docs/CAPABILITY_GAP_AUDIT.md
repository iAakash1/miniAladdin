# Capability gap audit

What this product pays for, what it computes, and what it throws away.

**Method.** Every number below was measured, not recalled. The payload
inventory is a live `/api/research/AAPL` response taken on 4 September 2026.
The exposure map is a transitive import walk from
`dashboard/src/app/terminal/security/page.tsx` — 28 files — checking each
payload key for a real property access rather than a mention. The endpoint
list is parsed from `api/index.py` decorators and matched against a
concatenation of every `.ts`/`.tsx` file under `dashboard/src`. The vendor
list is the `VendorClient` subclasses on disk.

**Second pass, 5 September 2026.** The pipeline was traced end to end —
provider, raw response, adapter, normalisation, service, API, frontend,
reader — and four defects were found and fixed. Sections 1, 2, 6 and 11 are
rewritten; the rest stands. Every figure below was re-measured after the
fixes, and the end-to-end numbers come from a live `/api/research/AAPL`
against the current code rather than from the recorded payload.

**Where it is weaker than it looks.** Three checks could not be run.
Authenticated browser QA is blocked — the terminal is behind Clerk, this
session's browser pane has no sign-in, and bypassing it is out of scope, so
nothing here claims a rendered-DOM verification it did not perform. Options
depth is unknown because no options credential exists in this environment.
Massive is verified only as far as a live 401 probe: its wire format is
Polygon-compatible, and no keyed response has been observed.

---

## 1. The headline number

**Ten of twenty-eight research payload keys now reach the reader**, up from
six before this pass began and nine after the previous one. `technicals`,
`series_integrity`, `consensus_price`, `statements` and the two street blocks
were connected across the two passes.

The bigger finding is that the count was never the real problem. Three of the
four defects below were in data that *did* reach the reader and was wrong.

Not fifteen, which is what a naive substring scan reports. Six of that
fifteen are false positives worth naming, because they are the shape of
error this product exists to catch:

| Key | Why it looked exposed | What it actually is |
|---|---|---|
| `analyst` | the word appears in a doc comment | prose: "An analyst opening AAPL wants…" |
| `confidence` | "confidence band", "confidence figure" | comments in `charts.tsx` and `Workbench.tsx` |
| `quant` | matched `/api/quant/selection/EXP-007` | a different endpoint, not the payload key |
| `verdict` | matched `d.verdict` in `SecurityView` | the selection artifact's verdict, not the payload's |
| `ticker` | matched `ticker: string` in `Options.tsx` | the options endpoint's field |
| `sentiment` | declared as `sentiment?: number \| string` | declared in a type in `SecurityProfile` and never rendered |

The nine that genuinely render: `profile`, `ratios`, `ownership`, `filings`,
`provenance` (only `generated_at`), `news_stream` (only `collected`),
`technicals`, `series_integrity`, `consensus_price`. The last three were
connected in this pass; before it the number was six.

## 2. What is still discarded, ranked by what it would buy

| Key | Contents | Value | Priority |
|---|---|---|---|
| `statements` | `fields.<name>.{value, providers[], observations[{provider, value}], agrees}`, plus `providers`, `conflicts`, `history` | Per-field multi-vendor observations — the exact shape `MetricRef.conflict` was built for and is currently fed by hand. **But `fields` currently holds one entry, `eps`.** The structure is right and the supply is not | **P0 (structure) / P1 (supply)** |
| `technical_intelligence` | `indicators[]`, `regimes{trend,momentum,volatility}`, `levels{support, resistance, lookback_days: 40}`, `as_of`, `bars: 253` | Support/resistance derived from a stated 40-day swing window over 253 bars — better provenance than most of what is already shown | **P1** |
| `macro_context` | FRED series, each with `series_id`, `unit`, `value`, `as_of`, `prior`, `change`, `source` | Real primary-source rates with per-series identifiers | **P1** |
| `analyst` | `target_mean`, `target_high`, `target_low`, `analyst_count: 39`, `recommendation`, `vendor_count: 1` | Attributable third-party opinion, and a 215–400 spread that is itself the finding | **P2** |
| `street_intelligence` | `recommendations{analysts: 53, strong_buy…}`, `surprises{quarters, beats}`, `insider{mspr, net_shares}` | Same, at more depth. Note it disagrees with `analyst`: 53 analysts against 39 | **P2** |
| `macro` | `yield_spread`, `fed_funds_rate`, `yield_curve_inverted`, `status` | Duplicates `macro_context` at lower fidelity and with no `as_of` | **P3** |
| `elapsed_seconds`, `mode`, `history_id`, `disclaimer` | request metadata | Operational, not analytical | **P3** |

## 3. What must stay hidden, and why

Not everything unexposed is a gap. Three are deliberate.

`ai` — thirteen of its twenty-nine fields are empty strings, and its own text
says *"AI narrative unavailable: not configured — showing the engine's own
rationale."* The non-empty ones open `BUY at 50% confidence`. Rendering that
beside a price would present an unpromoted scoring function as a
recommendation this product stands behind, when the research programme's
recorded verdict is **NO PRODUCTION CANDIDATE** and production models are
zero.

`confidence` / `confidence_breakdown` — a 100-point score decomposed into six
deductions (family dispersion −21, data completeness −12, freshness −6, model
reliability −9, macro uncertainty −1, conflicting signals −1). The
decomposition is honest and the total is still a confidence number attached
to an unpromoted signal.

`risk_level`, `rationale`, `verdict` — the same scoring function's output in
three other shapes.

**These are not deferred. They are refused for as long as the research state
says what it says.**

## 4. Provider inventory

Twenty-one `VendorClient` subclasses across ten modules.

**Market data (7)** — Polygon, Finnhub, TwelveData, FMP, MarketStack,
YFinance, Tiingo. **Options (1)** — Massive (`get_option_chain`, Polygon
wire-compatible, unverified beyond a 401 probe). **Filings (1)** — SEC EDGAR,
keyless by design, four methods including `get_xbrl_timeline`. **Macro (1)** —
FRED. **Fundamentals (1)** — AlphaVantage. **News (4)** — NewsAPI, GNews,
Yahoo RSS, plus Tavily/Exa search. **Reference (2)** — Wikidata (keyless),
Apify. **Visual (3)** — LogoDev, Pexels, Unsplash.

## 5. Endpoint surface

Fifty-one backend endpoints; **41 are called by the frontend, 10 are not**:
`/api/factors/universes`, `/api/graph/path`, `/api/health`,
`/api/memo/{ticker}`, `/api/metrics`, `/api/ml/capabilities`,
`/api/quant/datasets`, `/api/quant/features`, `/api/quant/registry`,
`/api/research/providers/health`.

Two of those are worth connecting rather than deleting:
`/api/research/providers/health` is the per-vendor availability the coverage
matrix (§7) needs, and `/api/graph/path` answers "how are these two
securities related", which nothing currently asks.

## 6. Defects found, by pipeline stage

Ordered by where the information died. The first three were found by pulling
on one thread: the accounting identity, which a balance sheet cannot get
wrong.

### Raw → adapter

**`fp: FY` includes the quarters.** *(fixed.)* A 10-K tags its four quarters
`fp: FY` alongside the annual figure. Apple's 2018 filing carries revenue of
265.60B for 2017-10-01→2018-09-29 and 62.90B for 2018-07-01→2018-09-29 — same
end date, same form, same `fp`. Annual spans are now measured at 300–400 days,
which admits every 52- and 53-week year across four filers with September,
June and January year ends and excludes every quarter.

**The first alias with any data won.** *(fixed.)* Several XBRL tags map to one
label and the loop kept whichever it met first. Apple tagged `Revenues` once,
in 2018, and moved to the contract-with-customer tag afterwards — so Apple's
revenue series was one fact from 2018 and Microsoft's one fact from 2010,
while the tag carrying six years sat unused. The alias covering the most
periods now wins and `concept_tag` records which. Not unioned: a column whose
definition changes partway down is worse than a shorter one.

**`fy` is the filing's year, not the fact's period.** *(fixed — the largest
of the four.)* A 10-K carries a comparative balance sheet, so one filing
contributes several rows per concept and all carry that filing's `fy`. Apple's
FY2025 10-K supplies assets for period end 2025-09-27 (359.24B) and 2024-09-28
(364.98B), both `fy: 2025`. Keyed by `fy` they collapsed and the first won —
for Apple, the prior year. The column headed FY2025 held 2024's balance sheet
while liabilities and equity for that column came from a different date.

Measured live, before and after:

| | before | after |
|---|---|---|
| AAPL revenue | 1 fact (FY2018) | 6 years, FY2020–2025 |
| MSFT revenue | 1 fact (FY2010) | 6 years, FY2021–2026 |
| NVDA revenue | 6 facts spanning 2018–26 | 6 contiguous years |
| WMT revenue | 6 facts | 6 contiguous years |
| `A = L + E` (AAPL) | fails 0.27%–12.91% | 0.0000% every year |
| `A = L + E` (MSFT) | fails up to 12.16% | 0.0000% |
| `A = L + E` (NVDA) | fails up to 51.28% | 0.0000% |

### Adapter → normalisation

**The statement merge read fourteen fields off a model with one.** *(fixed.)*
`merge_fundamentals` iterated fourteen names via `getattr(data, name, None)`
against `FundamentalsData`, which has only `eps` — and no `period` or
`history` either. `statements.fields` could never hold more than one entry.
The figures were in `vendor_metrics` (131 Finnhub keys, 10 yfinance) and were
dropped at the API boundary by `if k not in (…, "vendor_metrics")`. Now
normalised through an explicit map: **27 comparable groups for AAPL through
the live API, from one surviving field.**

Passing the dictionary through would have been worse than dropping it. Four
traps, measured across AAPL, MSFT, NVDA and WMT:

- **Scale differs between vendors.** Finnhub reports market cap and enterprise
  value in millions; yfinance in units. The ratio is 966,142 / 996,663 /
  1,020,088 / 1,033,887 across the four.
- **Basis differs between vendors.** Finnhub reports revenue per share
  (31.725 TTM); yfinance absolute (466,822,987,776). Their ratio is the share
  count.
- **One vendor mixes bases with no marker.** yfinance's `book_value` is per
  share — 7.36 against Finnhub's named 7.3599 for AAPL, 59.565/59.5647 MSFT,
  9.483/9.4829 NVDA — beside `total_revenue`, which is absolute.
- **One vendor mixes scales with no marker.** `ebitda` is currency;
  `ebitda_margins` is a percentage.

### Normalisation → API

**A session assembled from two different days.** *(fixed.)* `reconcile_price`
took each session field from the first vendor supplying one. Polygon answered
with the previous session (as_of 3 September) while Finnhub and Twelve Data
answered with the current one, so the block published a day range of
324.11–330.81 beside a last sale of 321.03 — a last price below its own low.
The real low was 317.86, which two vendors reported and iteration order passed
over. The session is now pinned to one date, the open/high/low triple comes
from a single vendor, excluded vendors are named, and `session_coherent`
reports whether every in-session price falls inside the range.

### Why these survived

Two of the four were protected by test fixtures that did not match
production. `test_fundamentals_are_a_union…` builds a class with all fourteen
attributes set, so the dead path was exercised against a schema that does not
exist. `test_xbrl_keeps_latest_restatement_per_year` omitted `start` and `end`,
which every real EDGAR row carries. Both fixtures now use the real shapes.

### Still open

**Two vendor counts for the same question.** *(surfaced, not reconciled —
correctly.)* `analyst` reports 39 analysts; `street_intelligence` reports 53.
Each vendor polls its own panel, so the counts describe different
populations. Both are shown with one sentence explaining why they differ.

**`statements.period` is the empty string.** *(superseded.)* The global period
was always going to be wrong — Finnhub returns annual, quarterly and trailing
figures in one response. Period now travels per fact in `statements.reported`.

**Apple's dividend series is two facts.** *(open, real.)* Apple stopped using
`PaymentsOfDividendsCommonStock`. A further alias would fix it; the concept is
reported as sparse rather than filled.

**Walmart has no Total liabilities.** *(open, real.)* It does not tag
`Liabilities`. `LiabilitiesAndStockholdersEquity` equals assets by definition,
so mapping it to that label would print a number four times too large under a
correct-looking heading. The identity is reported as not computable for that
filer.

## 7. Coverage matrix — the gap

There is no generated per-security data coverage matrix. `/api/providers/
capabilities` and `/api/research/providers/health` exist; the latter is
uncalled. What is missing is the join: *for this security, which provider
answered, which declined, and which was never asked.* Absent that, "no data"
and "not configured" and "asked and refused" are indistinguishable to the
reader on every surface except `Options`, which distinguishes them by hand.

**P1.**

## 8. Fundamentals coverage

`ratios` carries 28 fields and all 28 render. The gap is not breadth, it is
**period**: coverage across concepts is uneven by years, which `Financials`
surfaces per row (`latest FY2018` beside `FY2025`) and `Fundamentals2` does
not. Estimates are absent because no configured provider returns them —
an absence of supply, not of wiring.

## 9. Options

`Options.tsx` is written and distinguishes unconfigured from asked-and-
refused from genuinely-unlisted. No entitlement exists in this environment,
so the chain has never rendered and its table is counted at source rather
than in the DOM. Massive advertises `get_option_chain`. **Blocked on a
credential, not on code. P2.**

## 10. What this product is better at than its references

Neither OpenBB nor Fincept makes **per-field provenance** a primary
interaction (see `PRODUCT_REFERENCE_FINCEPT_OPENBB.md` §7). Both attribute at
the provider level. The employee-count case is the proof: three vendors
contribute to one profile, two disagree by 10%, and the honest rendering is
`158,000±` opening onto both observations rather than a confident midpoint.

`statements.fields.*.observations` (§2) is the same structure arriving
pre-built from the backend and going unused — `eps` currently arrives with
readings of 8.7233 from finnhub and 8.73 from yfinance and an `agrees: true`
the interface never shows. Connecting it is the highest-leverage item here,
with the caveat that widening `fields` beyond `eps` is a backend change and
the exposure is worth little until that lands.

## 11. Ranked backlog

**P0 — correctness.** None outstanding. The four found this pass are fixed
and pinned by 39 new tests.

**P1 — major research capability, needs code**
1. `technical_intelligence` — indicators, trend/momentum/volatility regimes,
   and support/resistance over a stated 40-day swing window across 253 bars.
   Fully computed, entirely unexposed. The `levels` block is factual; the
   `regimes` labels are interpretive and would need the same treatment the
   street ratings got.
2. `macro_context` — FRED series with `series_id`, `unit`, `as_of`, `prior`
   and `change` per rate. Real primary-source data.
3. Data coverage matrix per security; connect `/api/research/providers/health`.
4. A second alias for Apple's dividends (`PaymentsOfDividends`).

**P2 — meaningful, needs code**
5. `/api/graph/path` — relatedness between two securities, uncalled.
6. Extend the statement map: Finnhub returns 131 keys and 20 are mapped. The
   unmapped remainder is mostly ratios, which belong on the ratio surface.

**P2 — needs credential or entitlement**
7. Options chain depth — blocked on an options credential.
8. Massive — no local key; wire compatibility inferred from a 401 only.

**P3 — polish**
9. Delete or connect the remaining uncalled endpoints.
10. `macro` — subsumed by `macro_context`; remove rather than render twice.

**Not worth doing**
- A composite data-quality score. Rejected explicitly; see §14 of the brief
  and the tests that enforce it.
- `ai`, `confidence`, `confidence_breakdown`, `rationale`, `risk_level` —
  refused while the recorded research state is NO PRODUCTION CANDIDATE.

## 12. Owed verifications

- **Rendered-DOM checks** for `PaperWorkspace` (needs a broker account),
  `Options` (needs a credential), `MarketStats`, `FiledComparison` and
  `DataQuality` (need an authenticated browser session). All five are
  currently counted at source in `table-contract.test.ts` and each says so.
- **A keyed Massive response.** Wire compatibility is inferred from a 401
  discriminating `"API Key was not provided"` from `"Unknown API Key"`.
- **Options chain depth** — unknown until entitled.
