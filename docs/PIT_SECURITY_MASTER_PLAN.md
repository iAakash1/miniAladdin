# Point-in-time security master — what exists and the plan

Date: 2026-09-19. Aggregates: `experiments/EXP-009-forensics/security.json`
(`python -m scripts.quant.data_forensics security`).

## 1. What exists

| Asset | Content | Point-in-time? |
|---|---|---|
| `dolthub_stocks_symbol` | 24,058 rows / 24,058 symbols: `security_name`, `listing_exchange` (NASDAQ 11,394; NYSE 6,102; NYSE Arca 3,803; BATS 2,041; NYSE MKT 714; a handful other), `market_category`, `is_etf` (30.2% ETFs), `is_test_issue`, `financial_status`, and a `date` column (the vendor's `last_seen`, 2017-10-26 → 2026-08-22) | **No — a current snapshot.** Descriptive fields are treated as static. `last_seen` is the only historical field and is used solely as a delisting bound. |
| `universe/liquid.json` | 184 monthly snapshots 2011-01-31 → 2026-07-31; top-250 by trailing 3-month median dollar volume; non-ETF, non-test-issue, close ≥ $5; dropped after `last_seen` | **Yes, by construction** (trailing window only), classed `complete` from 2017-10-26 and `partial` before, where `last_seen` has no data and delisting is inferred only from leaving the cross-section |
| Universe dynamics | 998 distinct members ever; **906 later exit**; a mean of 24.3 entries per monthly rebalance (≈ 9.7% of the 250 turn over each month, ≈ 117% a year) | — |

**Not present anywhere locally:** sector or industry (no GICS, SIC or NAICS field),
point-in-time market capitalisation, shares outstanding history, a CIK/FIGI/PERMNO
identifier, or a corporate-action-adjusted identity history (mergers, ticker
changes, spin-offs). 308 estimate-table symbols show a gap of more than a year
between vintages (see `docs/ANALYST_DATA_FORENSICS.md`): the ticker itself is not a
stable identifier.

## 2. Consequences

* **Sector/industry/size neutralisation cannot be done honestly today.** Using
  today's `security_name` to guess a sector, or today's market cap for 2016,
  would be both a look-ahead and a survivorship distortion. The neutralisation
  candidate in `docs/EXP_009_NEUTRALIZATION_CANDIDATE.md` remains a
  *prerequisite project*, not an EXP-009 arm.
* **Delisting returns are incomplete before 2017-10-26**; results before then
  carry a survivorship caveat the universe file already records.
* **Ticker reuse** is unmodelled: a symbol that disappears and returns as another
  company would be treated as one series by every per-symbol computation. The
  price and estimate features are protected by their own gap rules; the labels
  are not.
* **GICS is licensed** (MSCI/S&P). No plan here assumes it is freely
  redistributable; nothing in this repository should claim GICS sectors.

## 3. Plan

The external-source details below were rechecked on 2026-09-19 against the
[SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[SEC fair-access limit](https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits),
and [OpenFIGI API documentation](https://www.openfigi.com/api/documentation).
The SEC publishes filer submission history (including current/former names,
exchanges and tickers), real-time APIs and a nightly bulk `submissions.zip`;
OpenFIGI is a mapping service, not a historical effective-date authority.

| Need | Free/public source | Method | Limits |
|---|---|---|---|
| Stable identity | SEC EDGAR **CIK** (`company_tickers.json` current snapshot + `submissions` API, whose filings carry the ticker at each filing date) | build (cik, ticker, effective_from, effective_to) from filing-header history rather than a snapshot | tickers of never-SEC-registered names (some ADRs/ETFs) are absent; foreign private issuers file 20-F/6-K |
| Ticker ↔ security history | **OpenFIGI** mapping API (free key) and exchange symbol-change notices; Nasdaq Trader / NYSE daily symbol files (current only) archived going forward | store dated snapshots from now on, so the future master is genuinely point-in-time | history before archiving starts must come from filings |
| Industry (not sector) | **SIC code** from EDGAR filing headers, which change over time and are dated by filing | Fama-French 12/17/48-industry mapping from SIC (published mapping tables) | SIC is coarse and lagged; it is *industry classification*, not GICS |
| PIT market cap | shares outstanding from XBRL `dei:EntityCommonStockSharesOutstanding` (dated by filing) × close | as-of join on `accepted` ≤ t | quarterly refresh; share-class handling |
| Delistings / corporate actions | EDGAR Form 25/15 and 8-K item 3.01/2.01; CRSP is licensed and out of scope | join to the universe's `last_seen` to correct the inferred exits | manual review for mergers vs bankruptcies |
| Index membership (context only) | Public S&P 500 change lists (Wikipedia/press releases) | as a *sanity cross-check* on the liquid-250, not as a training input | not redistributable as data; index membership is not the universe |

Deliverables, in order: (1) a dated (cik, ticker) history covering the 998 ever-members;
(2) a dated SIC-based industry table with a per-year coverage report; (3) PIT market
cap; (4) a feature-level flag `security_master_pit: true/false` recorded in every
dataset manifest. Each step ships with a leakage test in the style of
`tests/quant/test_analyst_pit.py`. None is started here: it is a data-engineering
project that should precede — not ride along with — any neutralisation experiment.

## 3A. Concrete schema and tests

Store intervals rather than overwriting identity:

| Table | Minimum columns |
|---|---|
| `security_identity_interval` | `security_id`, `cik`, `ticker`, `exchange`, `name`, `effective_from`, `effective_to`, `source`, `accession`, `retrieved_at` |
| `security_classification_interval` | `security_id`, `sic`, `ff_industry`, `effective_from`, `effective_to`, `source_accession` |
| `shares_fact_vintage` | `security_id`, `period_end`, `accepted_at`, `accession`, `form`, `tag`, `unit`, `value`, `is_amendment` |
| `security_exit_event` | `security_id`, `event_date`, `form`, `reason`, `last_trade_date`, `return_treatment`, `source_accession` |

Identity inference may use a later filing only from its acceptance time forward.
OpenFIGI mappings are cross-checks; they never manufacture a historical start
date. Archive exchange symbol files prospectively with content hashes.

Required gates:

1. no overlapping identity intervals for one security/share class;
2. ticker reuse produces distinct `security_id` values;
3. truncating the source at date *t* leaves every interval and feature before
   *t* byte-identical;
4. an after-close acceptance becomes usable next session;
5. amendments never overwrite the original vintage;
6. all universe rows either resolve to one identity or carry an explicit
   unresolved reason; and
7. size/industry neutralization is prohibited until coverage and unresolved
   identity rates are reported by fold.

For the initial 998-name universe, expected curated storage is well below 2 GB
and the work is CPU/data-engineering bound. It belongs on the MacBook.

## 4. Classification

| Item | Class |
|---|---|
| Liquid-250 membership by month | EXACT (PIT by construction, trailing windows only) |
| Delisting bound `last_seen` | **APPROXIMATED** before 2017-10-26 |
| Sector / industry | **NOT AVAILABLE** (plan: SIC → Fama-French industries; not GICS) |
| Market cap / shares history | **NOT AVAILABLE** |
| Identifier stability (ticker reuse) | **NOT REPRODUCIBLE** without CIK history |
