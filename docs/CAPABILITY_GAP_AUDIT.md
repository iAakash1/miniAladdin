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

**Where it is weaker than it looks.** Three checks could not be run.
Authenticated browser QA is blocked — the terminal is behind Clerk, this
session's browser pane has no sign-in, and bypassing it is out of scope, so
nothing here claims a rendered-DOM verification it did not perform. Options
depth is unknown because no options credential exists in this environment.
Massive is verified only as far as a live 401 probe: its wire format is
Polygon-compatible, and no keyed response has been observed.

---

## 1. The headline number

**Nine of twenty-eight research payload keys reach the reader.**

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

## 6. Defects this audit found

**The conflict flag counts incomparable readings as disagreement.** *(fixed
in this pass.)* `consensus_price` reports `conflict: true`, `provider_count:
4`, `dispersion_pct: 2.2521` for Apple. Three vendors report a *last sale* —
321.03, 320.98, 321.03, a spread of 0.02% — and the fourth reports the
*previous session's close* from the day before. The 2.25% is the distance
between two different measurements a day apart. Readings are now grouped by
basis before agreement is stated.

**`comparable()` called a basis mismatch a scale mismatch.** *(fixed.)* True
of the case it was written for and false in general: two prices measured
against a last sale and a prior close are both dollars.

**`comparable()` had no branch for an unstated basis.** *(fixed.)* The period
checks always had one; the basis check did not, so an unlabelled quantity
compared against a labelled one passed in silence. yfinance returns
321.0299…, within a rounding error of the two last sales — resembling a last
sale is not evidence of being one.

**Series agreement was reported over a subset without saying so.** *(fixed.)*
`agreement_pct: 100.0` is computed over `shared_sessions` (65), not
`union_sessions` (92). The other 27 sessions came from one vendor and were
cross-checked by nothing.

**`statements.period` is an empty string.** *(open.)* The one field under
`statements.fields` — `eps`, at 8.72665 — arrives with no period. Earnings
per share with no period is not comparable with anything: trailing twelve
months against a quarter is a factor-of-four error that looks like a number.
The semantic layer has enforced period-awareness since Phase 13 and will
refuse this, correctly. **P0 blocker on §2's top item.**

**Two vendor counts for the same question.** *(open.)* `analyst` reports 39
analysts; `street_intelligence` reports 53. Both are in one payload. Neither
is necessarily wrong — different vendors poll different panels — and showing
either alone asserts a consensus size that the other contradicts.

**SEC XBRL fails `Assets = Liabilities + Equity`.** *(surfaced, not fixed —
correctly.)* By up to 51% of assets. Reported to the reader in `Financials`
rather than silently reconciled, because reconciling it would invent a
statement no filer filed.

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

**P0**
1. Widen `statements.fields` beyond `eps` at the source, then expose
   `observations` through `MetricRef.conflict`. The wiring is cheap; the
   supply is the work.
2. Fix `statements.period` — currently `''`. Blocks (1): the semantic layer
   will refuse a comparison of two unlabelled periods, and it is right to.

**P1**
3. Data coverage matrix per security; connect `/api/research/providers/health`.
4. `technical_intelligence` — support/resistance with its 40-day lookback stated.
5. `macro_context` — FRED series with `series_id` and `as_of` per rate.

**P2**
6. `analyst` and `street_intelligence`, together, with the 39-against-53
   disagreement shown rather than resolved.
7. Options, once a credential exists.
8. `/api/graph/path` — relatedness between two securities.

**P3**
9. Delete or connect the remaining uncalled endpoints.
10. `macro` — subsumed by `macro_context`; remove rather than render twice.

## 12. Owed verifications

- **Rendered-DOM checks** for `PaperWorkspace` (needs a broker account),
  `Options` (needs a credential), `MarketStats`, `FiledComparison` and
  `DataQuality` (need an authenticated browser session). All five are
  currently counted at source in `table-contract.test.ts` and each says so.
- **A keyed Massive response.** Wire compatibility is inferred from a 401
  discriminating `"API Key was not provided"` from `"Unknown API Key"`.
- **Options chain depth** — unknown until entitled.
