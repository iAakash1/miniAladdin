# Data acquisition plan

Plan date: 2026-09-19. This plan authorizes manifests and safe staging only;
it does not authorize a new model run or contact with the sealed holdout.

## Acquisition register

| Priority | Provider/dataset | Exact fields | Coverage | Method/auth | Estimated volume and storage | Partition | PIT/update rule | Cost/license | Fallback |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | Existing local EPS/sales consensus | vintage date, symbol, period/end, consensus, high/low, count, year-ago | 2017-10-26 onward; 7.06m rows/table | Existing Parquet/Dolt; no new auth | ~74 MB normalized already present | dataset/table, then vintage year if rebuilt | vintage is `available_at`; weekly source cadence; 45-day staleness | Manifest says DoltHub open; verify upstream before redistribution | No substitute needed; quarantine on license uncertainty |
| 2 | SEC EDGAR submissions + 8-K/10-Q/K metadata/XBRL | CIK, accession, form, acceptance time, period, document/exhibit URL/hash, XBRL fact/unit/context | SEC electronic history; issuer dependent | SEC JSON/XML/bulk; no key; identifying user-agent | Start with 998-universe metadata; text volume bounded by allowlisted forms | form/year/CIK | acceptance timestamp; amendments are new revisions; scheduled nightly refresh | Free/public filings; obey fair-access; raw exhibits may carry third-party rights | SEC bulk ZIP versus per-CIK API |
| 3 | SEC Form 3/4/5 flat files/XML | issuer/owner CIK, role, filing/transaction time, code, shares, price, direct/indirect, 10b5-1 flag where present | Public quarterly bulk + EDGAR history | SEC bulk/XML; no key | Metadata/transactions likely low GB, not estimated until pilot | filing year/quarter/issuer | usable at filing acceptance, never transaction date alone | Free; public filing/use policy | Direct EDGAR ownership submissions |
| 4 | PIT security master | stable id, ticker/exchange effective dates, sector/industry effective dates, shares, delisting date/reason/return | Full research window target 2011+ | WRDS/CRSP if institution licensed; otherwise curated SEC/exchange inputs | Unknown until provider; plan <5 GB normalized | effective year / security id | effective-from/to; never current-map backfill | WRDS academic/commercial or open-source composite with caveats | Partial SEC/Nasdaq mapping plus explicit `UNKNOWN` |
| 5 | ALFRED macro vintages | series id, observation date, real-time start/end, value | series-specific long history | FRED API key/bulk | MB-scale for selected series | series/year | real-time vintage is availability; release-calendar refresh | Free API; per-series redistribution rights | Keep Treasury-only macro if rights unclear |
| 6 | Contract options pilot | quote time, contract id, expiry, strike, type, bid/ask, IV/Greeks method, volume/OI, underlying | Prefer 2012+ | Cboe DataShop/Massive/OptionMetrics licensed bulk/API | Potentially 100s GB--TB; five-symbol pilot first | trade date/underlying/expiry | quote cutoff <= decision; correction versions retained | Paid and redistribution restricted | Existing 2019+ aggregates |

Volume estimates are intentionally absent where no pilot/quote exists. A false
precision budget is worse than an explicit procurement unknown.

## Phase 0 -- provenance ledger (one day)

Create one machine-readable record per existing family with source, license
identifier, retrieval time, raw path outside git, SHA-256, schema version, row
count, date range, symbol/identifier coverage, update policy, and first-
available semantics. Mark unknown licenses or vintages `BLOCKED`.

Exit: every row in `DATASET_GAP_ANALYSIS.md` maps to a ledger entry and a
deterministic validation command.

## Phase 1 -- existing estimates and fundamentals (two to four days)

1. Measure symbol/date coverage and missingness within the PIT universe.
2. Assert monotone estimate vintages and session-cutoff behavior.
3. Join statements by SEC accession/acceptance time where possible; otherwise
   quarantine restatement-sensitive features.
4. Produce permitted derived features only: revision breadth/magnitude,
   dispersion, surprise, filing age, and availability flags.

Exit: leakage fixtures fail when a post-cutoff revision or filing is injected;
no raw licensed values are committed.

## Phase 2 -- SEC event corpus (three to seven days)

Ingest submissions and selected filings for universe members: Forms 8-K
(especially Items 2.02/7.01 with earnings exhibits), 10-Q/K, and Forms 3/4/5.
Persist CIK/accession/form/acceptance timestamp/period/document hash and parsed
transactions or exhibit references. Respect SEC fair-access guidance, cache
responses, use an identifying user agent, and make retries idempotent.

Exit: a replay from the manifest yields identical metadata; amendments and
after-close filings become available only at the next tradable session.

## Phase 3 -- security master (parallel procurement, one to three weeks)

Prefer an already licensed WRDS/CRSP source. Otherwise combine SEC identifiers,
exchange directories and current mappings with explicit effective dates. Add
sector/industry history, share-count provenance, ticker/CUSIP changes,
delisting date/reason/return and exchange history. Never forward-fill a mapping
across an unknown identifier transition.

Exit: random historical dates reproduce the then-valid identifier and sector;
delisted names remain in prior universe snapshots.

## Phase 4 -- optional paid pilots

Only after EXP-008 is judged, run a small, non-holdout coverage pilot for
contract-level options or licensed text. Require written storage/derived-data/
redistribution rights, total annual cost, egress/storage estimate, cancellation
terms, and a five-symbol schema/leakage proof before purchasing broad history.

## Operational controls

- Raw and credentialed data stays in ignored storage; no secrets in commands,
  logs, manifests, or git.
- Downloads use a staging directory, content hashes, atomic promotion, bounded
  retries and provider-specific rate limits.
- New schemas fail closed on missing required columns or changed types.
- A data update cannot overwrite the frozen experiment manifest.
- Every feature declares economic timestamp, publication timestamp, first
  tradable session, transformation lookback, and maximum staleness.
- License expiry or unknown redistribution status changes readiness to
  `BLOCKED`, even if files remain locally readable.

## Budget decision gates

No paid purchase is approved merely because an endpoint exists. Advance only
if the source supplies a feature family not already locally present, closes a
measured provenance gap, has usable PIT semantics, and is testable on the
existing pre-holdout walk-forward without expanding the registered trial
budget. Options and news fail this gate today; SEC events and provenance repair
pass it.
