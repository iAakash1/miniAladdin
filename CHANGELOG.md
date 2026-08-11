# Changelog

Engineering changes to OmniSignal, newest first. Every performance claim here
is reproducible from a script in `benchmarks/`; every correctness claim has a
test that has been shown capable of failing.

## V15 — research platform (in progress)

### UI polish pass

Uiverse was used for implementation patterns, not visual identity. Three
ideas translated to a dark financial terminal; the rest (3D loaders, neon,
glassmorphism) were rejected as wrong for the product.

- **Depth vocabulary.** On near-black, shadow alone reads as smudge — a 1px
  inset highlight along the top edge is what makes an element look physical.
  `--edge-hi` / `--lift-1` / `--lift-2` / `--ring` replace ad-hoc shadows, and
  the light theme gets its own values because paper is not lit from above.
- **Buttons**: layered elevation, press that collapses the shadow so the
  button meets the surface, a real loading state that reserves label width so
  the control never resizes under the cursor, focus ring drawn as shadow.
- **Inputs**: recessed rather than raised — a field is a well you type into,
  so the highlight is on the inner top edge. Selects inherit the same
  treatment plus a drawn chevron, so dropdowns and text fields read as one
  family.
- **Skeletons**: a left-to-right sweep instead of an opacity pulse. Throbbing
  reads as the page breathing; a travelling highlight reads as content
  arriving, which is what is happening.
- **ResearchLoader**: a 1px scan line across the panel edge, the running
  stage marked with an accent rule and nudged 2px forward, completed detail
  text receding. One moving element, not five.
- **Factor cards**: selection is a left rule, not a 2px outline — a ring that
  size dominated the panel and competed with the t-statistic bars.
- Tabs get an underline flush with the header border; badges get tinted
  hairlines; tables get tabular numerals and row hover; empty states get a
  dashed boundary, because dashed reads as "space reserved" while a solid
  card reads as finished.
- Fixed during the pass: the loader let its timer estimate run *ahead* of the
  stage the server reported, briefly showing two rows as active. A reported
  stage now wins outright, and the footer switches from "timing is estimated"
  to "stages reported by the running job". Both pinned by tests.
- Every animation is behind `prefers-reduced-motion`.

### Browser verification: four real bugs found and fixed

Verified in an authenticated session, not by typechecking.

- **Stock analysis never loaded in development.** The once-per-ticker `ranFor`
  ref survived React StrictMode's remount, so the second effect run returned
  early while the first run's in-flight response arrived to a cancelled
  closure and was discarded. The loader span forever against a request that
  had **succeeded in 4.7 s**. The guard is now released on an undelivered
  teardown. This was the actual "frozen screen", not a loading-state polish
  problem.
- **`/api/factors` blocked the HTTP request for 44 s.** Backend logged
  `200 in 44413ms` while the browser showed a network failure — the Next dev
  proxy gives up first, and a serverless deploy would time out harder. The
  endpoint now starts a background build and answers immediately (**21 ms**)
  with the stage the build has actually reached; the client polls. The loader
  ticks are now *server-reported facts* rather than timer estimates.
- **`/company/[ticker]` rendered in light theme** inside the dark terminal.
  `ThemeSync` and the pre-hydration script both matched only `/terminal`,
  so clicking a symbol flipped the whole app mid-workflow. `/company` is
  terminal chrome and is now treated as such in both places.
- **`TerminalShell` boot showed a bare centred label on an empty page** — no
  header, no navigation — then janked as chrome popped in. The header does
  not depend on the session, so it renders immediately and only the content
  column waits. No layout shift.
- **Graph explorer grouped nothing.** A comment claimed edges were "grouped by
  relationship" while the code walked them in arrival order, drawing 22
  semantically distinct links as one starburst. Edges are now laid out in
  labelled arcs by relationship family — Industry (6), Subsidiary (4),
  Owns (3), Product (3), Founder (2), Location (2), CEO (1), Exchange (1).
  The data was always semantic; only the picture was not.
- Fixed during verification: an unknown universe briefly returned
  `status: building` instead of failing fast, because validation had been
  moved behind the background job.
- Stale copy: the redundancy heading said "Seven factors" after `asset_growth`
  made it eight; it now derives from the data.

### Product: analysis loader, Factor Lab root cause, typed Workspace

**Factor Lab 404 — root cause was configuration, not code.** `/api/factors`
is proxied to whatever `BACKEND_ORIGIN` names. The deployed Render backend
answers **404** for it and **200** for `/api/dashboard`: it is running a build
that predates the endpoint. Locally it returns 200. **The endpoint has never
been deployed** — nothing in this repository was broken.

- The frontend now distinguishes that case truthfully. A 404/405 says the
  endpoint is missing from the connected backend and names the fix; a 5xx or
  network failure says the backend is unreachable. Neither is described as a
  computation failure any more, which is what the old copy did.
- Route contract pinned in `tests/test_api_research.py` so a genuine
  regression is caught here rather than in a browser two deploys later.
- Verified end to end against real data: mega30 returns 8 factors, 3,482
  evaluable cells, screen + redundancy + attribution + portfolios + stability
  all populated, 49.6 s cold.

**`ResearchLoader`** replaces the skeleton on stock analysis, which read as a
frozen screen while the backend worked.

- Shows the real pipeline, stage by stage, in execution order.
- **A stage is only ticked when completion is known.** The chart request
  resolves independently of the analysis, so that one completion is a real
  signal and ticks stage one; every other stage is a highlight driven by
  measured durations, and the footer says so outright. Overrunning the
  estimate parks on the final stage rather than claiming everything finished
  — asserted in `tests/researchLoader.test.ts`.
- Shared with the Factor Lab, so both pipelines look and behave the same.
- One pulse on the active row; `prefers-reduced-motion` respected.

**Workspace objects are typed.** The previous version reduced everything to
four counts, which made a note and a company indistinguishable — the same
flattening that made the old graph meaningless. A thesis renders as a thesis,
notes as prose with their entity references, entities as chips, activity as a
trail. All from persistence that already existed.

### Craftsmanship: one page header, zero lint errors

- **`PageHeader`** replaces six hand-rolled page headers. Three of them
  repeated the identical `style={{ fontSize: '1rem', marginBottom: 6 }}`
  override verbatim — the tell that the token was wrong, not the usage — and
  several routes opened at `<h2>`, shipping **with no `<h1>` at all**. Line
  length, type scale and heading level are now decided once.
- Applied to Validation, Vault, Methodology, Workspace, Factor Lab, Graph
  workspace and Graph explorer. Dead `.ws-head` rules deleted.
- **Frontend lint is clean for the first time.** Four pre-existing errors
  fixed rather than tolerated, all the same class of bug:
  - `CompanyEcosystem`, `GraphExplorer`: `setState` in an effect body →
    settled-result-tagged-by-key, so loading is *derived* and a stale
    response for a previous ticker/node can no longer overwrite the current
    one. Same pattern already used in `FactorLabView`.
  - `company/[ticker]`: ticker validity is derived from the URL, not fetched,
    so it is computed during render; the quota write is deferred.
  - `CommandPalette`: reset-on-open now adjusts during render against the
    previous value (React's documented pattern) instead of writing state from
    an effect — one less render pass and no frame of stale query. A counter
    mutated during render is now derived, which matters under concurrent
    rendering.

### Product: market map, workspace, and Factor Lab states

Three UI rebuilds, none of them incremental.

- **Market map** replaces the breadth panel. Reorganised around the *market*
  rather than a score: eleven sectors each drawn as 90 sessions of real
  rebased price action, with breadth as the left-hand read. The first rebuild
  of this panel was too conservative — before and after were hard to tell
  apart — so it was rebuilt again from a different question.
- Sector price history is real and free: recomputed from the same series the
  panel already fetched, rebased to 100 so eleven instruments trading between
  $30 and $250 share a scale.
- **Workspace** rebuilt around the work. Sessions already stored pins,
  collections, snapshots, notes and an activity log; **none of it was ever
  surfaced**. Cards now render that substance, the most recent investigation
  gets a full-width resume rail, and search shows matched note text with the
  term highlighted rather than listing that a match exists.
- **Factor Lab loading and errors.** A cold build takes 30-60s and used to
  show a bare skeleton; it now narrates the real pipeline stage by stage and
  labels its own timings as estimated, not live. Failures no longer expose
  backend strings — the three known causes each get an explanation and a
  next step (a too-small universe offers to switch to mega30).
- Deleted `heatIntensity` and its tests, dead after the rewrite.

### Point-in-time fundamentals from SEC XBRL

`SECVendor.get_xbrl_timeline` + `src/panel/fundamentals.py`: every filed
figure with its filing date, so a fact is visible only once it was published.

- **Found by capability audit:** `get_xbrl_facts` existed and was **completely
  unused** — the only integrated source carrying filing dates, which is exactly
  what kept 8 of 15 panel factors NULL.
- The existing method **dedupes each fiscal year to its latest restatement**,
  correct for display and look-ahead for research: a 2020 row would see a 2023
  figure. The new timeline preserves every filing.
- First fundamental factor `asset_growth` (Cooper-Gulen-Schill) built on it —
  and **it failed validation**: IC −0.009 (t −0.23), long/short −27.0%,
  Sharpe −0.44, worst of eight. The anomaly points the wrong way on 30
  mega-caps during an AI-capex expansion; 2% turnover shows it is a static
  directional bet, not a factor effect.
- **Rule established (CLAUDE.md 1b):** the panel tests factors, the engine
  takes survivors. `asset_growth` stays in the lab as evidence and does not
  enter the scoring engine.
- Factor Lab now evaluates whatever the panel populated rather than a
  hardcoded price sleeve, so new factors face the same bar automatically.
- Tests: 13 (`tests/test_panel_fundamentals.py`), incl. restatement visibility.

### Factor Lab — cross-sectional factor evidence

New `/terminal/factors` and `GET /api/factors`: rank IC, Newey-West corrected
t-statistics, quantile spreads and the full ranked cross-section for every
factor in the scoring engine. `src/research/` + `src/services/factor_lab_service.py`.

- **Why:** every view in the product examined one stock, which cannot
  distinguish a working factor from a rising market. The point-in-time panel
  was built for cross-sectional reads and had no consumer that used it that way.
- **The headline result is negative and stated as such:** no factor is
  statistically significant on ~2.5 years of mega-cap data. Naive t-statistics
  were inflated **1.20-1.58x** by overlapping forward returns.
- **A finding the view produced on its own:** `r12_1` clips **24%** of the
  universe at the winsorization bound, so it does not rank those six names
  relative to each other — ordering information discarded at exactly the end a
  long/short reading depends on. Every other price factor clips under 5%.
- Caveats (multiple comparisons, survivorship, overlap, sample size) ship
  inside the API payload, not in documentation.
- Corrected during development: an earlier version asserted a worthless factor
  is *never* flagged significant. It failed on a seed — rightly, since a 5%
  level means ~1 in 20 look significant by chance. The test now measures the
  false-positive rate.
- Two bugs found by running it rather than by tests: an inner join hid the
  current cross-section (open forward windows), and small universes rendered
  an empty page instead of an explanation.
- **Factor portfolios** (`src/research/portfolio.py`): each factor traded as an
  equal-weight long/short book, rebalanced weekly, with equity curve, Sharpe,
  max drawdown and turnover. Holding period equals the rebalance interval, so
  periods do not overlap and the Sharpe needs no autocorrelation correction —
  the overlap is designed out rather than corrected for.
- **Result: not one factor beat holding the universe equally weighted.** Best
  was `r12_1` at +48.4% (Sharpe 0.52) against +64.8% for equal weight; three
  factors lost money; drawdowns ran 24-41%. Costs are not modelled and
  `reversal` turns over 66% of its book weekly, which would erase its +9.8%.
- **Cross-sectional screen** (`src/research/screen.py`): every name ranked by
  the mean of its factor percentiles, with a **factor-agreement** column. Two
  names can share a composite while one has every factor agreeing and the other
  is split — the mean cannot separate them, agreement can.
- **Result: zero names in the mega-cap universe have aligned factors today**
  (13 mixed, 12 conflicted). ABBV and CSCO rank 4th/5th on composite while being
  the most internally contradictory names in the top ten.
- Equal weights on purpose: IC-weighting would fit weights to noise, since no
  factor is significant. `dispersion` reports days when the engine has no opinion.
- **Factor stability** (`src/research/stability.py`): rolling IC, half-sample
  split, best/worst windows, edge concentration and sign flips — answering
  "did this work *recently*?", which a pooled mean IC cannot.
- **Result: the two strongest first-half factors are the two that stopped
  working.** `rel21_vs_spy` (+0.064 → −0.005) and `reversal` (+0.027 → −0.044)
  both decayed; `r12_1` weakened 6×; `r21` and `r63` were *negative* early and
  positive later. Every factor crossed zero 5-8 times.
- **Factor redundancy** (`src/research/redundancy.py`): average cross-sectional
  rank correlation between every factor pair, plus the eigenvalue participation
  ratio — "how many independent bets is this composite really making?"
- **Result: 7 factors behave like 3.2 independent ones.** `r21` and
  `rel21_vs_spy` correlate at **0.967** — a 21-day return and a 21-day return
  minus SPY, over a universe that largely *is* the index. `reversal` is −0.64
  against `r21`: momentum with the sign flipped, not a seventh opinion.
- **This is a direct criticism of the equal-weighted screen shipped two
  milestones earlier** — momentum gets roughly triple the vote — and the
  finding is stated on that panel, not buried in docs.
- **Return attribution** (`src/research/attribution.py`): Fama-MacBeth
  cross-sectional regression of forward returns on factor exposures, per date
  then averaged — "how much of what happened do the factors explain?"
- **Raw R² would have overstated the model by more than double.** 0.475 raw vs
  **0.196 adjusted**; seven predictors on ~25 names manufacture 0.28 of fit from
  chance alone. The page reports adjusted and footnotes the raw figure.
- Honest reading: the factors explain ~20% of cross-sectional return variance,
  and **no factor return is significant at |t| > 2**.
- Per-date rather than pooled, so a day when everything rises cannot masquerade
  as a factor return (pinned by a test).
- Docs: `docs/FACTOR-LAB.md` §9-10. Tests: 97.

### Observability — latency attribution and percentiles

Added `src/observability/`: bucketed latency histograms with p50/p95/p99, a
bounded-cardinality metric registry, and per-request attribution that shows
where a request's time went and whether it was parallel.

- **Why:** answering "where did the dashboard's 25 s go?" required a
  throwaway instrumentation script four separate times. Existing stats were
  per-vendor means since boot — and the mean of a bimodal distribution
  (0.4 ms cache hit, 18 s vendor timeout) describes nothing that happened.
- **Overhead:** 0.194 µs per record; **0.189 µs contended at 8 threads**, so
  no measurable lock contention. 0.0003% of a 300 ms provider call. On in
  production, not behind a flag.
- **Found immediately:** ~33% of dashboard work is spent on vendor calls that
  *fail*; FRED is 38.4% of work across 15 *successful* calls; 12 polygon
  rate-limit rejections per load. Findings (1) and (3) contradict assumptions
  made earlier in this repository's optimisation work.
- **New:** `GET /api/metrics` (`?reset=true` for a fresh window). Request log
  lines now carry `work`, `parallelism` and `unattributed`.
- Fixed during development: two recording paths meant `timer` attributed to
  the request while direct `observe` calls did not — request reports read
  `work 0ms` while global metrics looked perfect. Collapsed to one path.
- Docs: `docs/OBSERVABILITY.md`. Benchmark: `benchmarks/observability.py`.
  Tests: 29, all 11 mutations killed.

### Price validation at the provider boundary

`PriceSeries` now rejects impossible bars on construction and records what it
dropped in a `quality` field; `FallbackChain` treats an untrustworthy payload
as a vendor failure and falls through.

- **Why:** the schema layer had **zero validators**. `OHLCVBar.close: float`
  accepted `0.0`, negatives, NaN and inf, and handed them to 25 consumption
  sites. Observed live: a zero close crashed four of eleven sector rows.
- **The crash was the lucky outcome.** A zero close in a return calculation
  yields −100%, which looks plausible, flows into momentum as real signal,
  and would be recorded by the panel as point-in-time truth.
- **Policy split by certainty, from measurement:** 1,879 real bars across
  three vendors showed zero violations of any rule. Non-finite, non-positive
  and `high < low` are **dropped**; a close outside `[low, high]` is
  **recorded but kept**, because adjusted closes legitimately produce it.
- **Confirmed in production within the hour:** `SPY: dropped 2 of 248 bars
  (2 non-positive)`.
- Cost: 0.1–0.5 ms per series, under 0.2% of a provider round trip.
- Tests: 25, all 9 mutations killed.

### Concurrent provider fan-out

Added `src/providers/parallel.py` (bounded, input-ordered, failure-isolating)
and `src/services/research_prefetch.py` (speculative cache warming).

- **Why:** `get_dashboard()` made 32 provider calls in sequence — 43.6 s cold,
  **100% of it inside those calls**, 0.000 s warm. The entire cost fell on
  cold-cache users, which on Render means after every deploy and spin-down.
- **Dashboard: 43.6 s → 25.5 s**, 2.75× against its own serial cost, peak
  concurrency exactly 8.
- **Research: 1.53×** on the prefetched segment (3.97 s vs 6.06 s
  serial-equivalent), 7/7 upstreams warm, repeat call 0.9 ms — achieved
  **without modifying the 469-line handler**, because `FallbackChain` is
  cache-first *and* single-flight wrapped.
- **Bounded, not unbounded:** `RateLimiter.try_acquire` is non-blocking, so
  an oversized burst converts slow successes into instant failures and
  silently demotes answers to a worse vendor. 8 workers captures 93% of the
  maximum speedup at half the burst pressure of 16.
- Fixed during development: `with ThreadPoolExecutor(...)` calls
  `shutdown(wait=True)` on exit, blocking on the very hung thread the timeout
  existed to escape — the timeout was decorative.
- Docs: `docs/CONCURRENCY.md`. Benchmark: `benchmarks/provider_fanout.py`.

### Vectorized factor engine

Added `src/panel/factors.py` and `src/panel/windowed.py`.

- **31× faster** panel builds: 48.6 s → 1.53 s for 30 symbols × 756 days;
  430 → 13,648 cells/s, flat across four shapes.
- **Proven equal to the scalar engine** at 1e-12 at every date for every
  factor. Outside the domain where equality is provable, the fast path
  **refuses** rather than approximating.
- pandas' rolling median beat a NumPy window matrix **55×** (incremental
  skiplist vs O(n·L)); MAD cannot use that trick because it subtracts a
  per-window median.
- Removed six inert `lookback - k` expressions that mutation testing proved
  could not change any result.
- Known cliff: history longer than the lookback falls back to scalar
  (11,285 → 394 cells/s). Root cause is an engine RSI warm-up artifact;
  the one-line fix changes production scores by a median 1.5e-3 and is
  **flagged for a human decision**, not taken unilaterally.
- Docs: `docs/PANEL.md` §7. Benchmark: `benchmarks/panel_build.py`.

### Point-in-time factor panel

Added `src/panel/` — immutable, content-addressed Parquet snapshots recording
what every factor was worth on every date *and when that was knowable*.

- Look-ahead is impossible by construction: factor computation for date D
  receives a window truncated at D, so future bars are absent, not merely
  unused.
- Flagship test appends a year of future data, rebuilds, and asserts every
  historical row is byte-identical.
- Parquet rather than Postgres, so the planned DuckDB layer lands on these
  files with zero migration.
- Documented limitations rather than hidden ones: survivorship bias, vendor
  history depth, unpopulated fundamental factors, FOMC regimes unlabelable
  historically.
- Docs: `docs/PANEL.md`. CLI: `python -m src.panel.cli`.

---

## Known debt

- `api/index.py` `/quotes` reimplements percent-change inline and loops over
  symbols sequentially. `PriceSeries.pct_change()` is now the canonical
  implementation and `map_concurrent` the fan-out; the endpoint has not been
  migrated.
- `research_ticker` is 469 lines.
- Panel content hashes are reproducible per-engine, not across engines (a
  1-ULP difference changes Parquet bytes). `omni verify` must rebuild with
  the engine named in the manifest.
