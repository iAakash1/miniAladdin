# Financial statements — point-in-time remediation

Date: 2026-09-19. Aggregates: `experiments/EXP-009-forensics/fundamentals.json`
(`python -m scripts.quant.data_forensics fundamentals`). Nothing after 2025-05-09
was read.

## 1. The problem, measured

Five local statement tables (income statement; balance-sheet assets, liabilities,
equity; cash flow) hold 176,631 – 284,716 rows each (period ends 2012-10-31 →
2026-07-31; quarterly and annual). For every one of them:

| Property | Finding |
|---|---|
| Date field | a **fiscal period end** — 99.98–99.99% of `date` values are month-ends |
| Filing / acceptance date | **absent** |
| Restatement vintage | **absent** — one row per (symbol, period); the value is what the vendor holds *today* |
| Duplicate (symbol, date, period) rows | 0 — so a restatement has *overwritten*, not appended |
| Manifest status | `publication_lagged` (after the EXP-005 gate was added) |

The only way to time-stamp a statement locally is to join it to the earnings
calendar and take the first announcement 5–150 days after the period end. That
join is possible for only part of the data:

| Table | Rows before the calendar starts (2020-01-22) | Share gateable via calendar (all rows) | …since 2020 |
|---|---:|---:|---:|
| Income statement | 98,375 (40.5%) | 51.0% | 79.5% |
| Balance sheet: assets | 102,956 (40.2%) | 49.0% | 75.8% |
| Balance sheet: liabilities | 102,956 (40.1%) | 48.9% | 75.7% |
| Balance sheet: equity | 102,956 (40.1%) | 48.9% | 75.7% |
| Cash flow | 36,648 (25.0%) | 60.4% | 77.3% |

Matched announcement lag from period end: median 40 days (p5 22, p95 130).
**Even where the join works, ~21–24% of post-2020 rows have no matching
announcement**, and the *values* are potentially restated. So:

1. **Timing** is recoverable only from 2020 and only for ~3/4 of rows;
2. **Values** are as-of-today, not as-originally-filed. A restated figure attached
   at its original announcement date is a look-ahead of *content* even when the
   timing is right (Gu, Kelly & Xiu lag annual data ≥ 6 months and quarterly ≥ 4
   months to be safe against exactly this).

Two columns are also mostly empty: income-statement `depreciation_and_amortization`
is 75% null; `payment_of_dividends...` 11%; equity `shares_outstanding` and
`book_value_per_share` 6.4%.

## 2. Decision

**Statement-derived features are not used as historical ML features in any
EXP-009 arm.** The statement-derived features already in the registry stay
gated behind the earnings calendar and remain excluded from `C_base`; no new
statement feature is added. This is the same conclusion the earlier audit
reached, now with measured coverage.

## 3. Remediation plan: an as-reported dataset from SEC EDGAR

The clean fix is a source that records *what was filed and when*. The EDGAR facts below (dataset names, the `filed`/`accepted` fields, the XBRL phase-in dates, fair-access limits) are stated from the SEC's public documentation as remembered and were **not re-verified in this pass**; the first step of the project is to confirm them against the current SEC pages.

| Step | Detail |
|---|---|
| Source | SEC EDGAR **Financial Statement Data Sets** (quarterly bulk files of XBRL `sub`, `num`, `tag`, `pre`) and the **XBRL "Frames"/company-facts** APIs. The data are public; the SEC's fair-access rule (a declared User-Agent and a modest request rate) applies. |
| PIT key | `sub.filed` and `sub.accepted` (a datetime): the value is knowable from `accepted` (next session if after 16:00 ET). `adsh` (accession number) is the immutable vintage id. |
| Restatements | A 10-K/A or later 10-Q that restates a prior period arrives as a **new row with a later `filed`**. As-first-reported = earliest `filed` per (cik, tag, period); as-of-t = latest `filed` ≤ t. Both are recoverable. |
| Identity | `cik` (stable) ↔ ticker via SEC `company_tickers.json` **with effective dates from the filing header history**, not a current snapshot (see `docs/PIT_SECURITY_MASTER_PLAN.md`). |
| Coverage | XBRL statements exist from 2009 (large filers) / 2011 (all); financial-statement data sets start 2009. Sufficient for 2014-2025. |
| Tag mapping | Map us-gaap tags to the ten statement fields (revenue, gross profit, net income, assets, …); document every choice (companies use different tags; `Revenues` vs `SalesRevenueNet`). A wrong mapping is silent, so a coverage report per tag is part of the build. |
| Validation | Reproduce known filed values for a hand-checked sample; assert `accepted` ≤ first use; assert restated values never appear before the restating filing. |
| Cost | Free data; storage ~ a few GB; a bounded engineering project (days, not hours), separate from research. |
| Not to be done | Do not backfill by assuming a fixed reporting lag; do not attach today's values at historical dates; do not rely on a vendor's "PIT" label without a vintage column. |

Until that dataset exists and passes the tests above, fundamentals stay out of
EXP-009 and any statement-based result is labelled NOT POINT-IN-TIME.

## 4. Reproducibility classification

| Item | Class |
|---|---|
| Statement values as first filed | **NOT REPRODUCIBLE** locally (no vintage) |
| Period-end → announcement timing (2020+) | **APPROXIMATED** (calendar snapshot; ~76% coverage) |
| Announcement timing before 2020 | **NOT REPRODUCIBLE** |
| Ratio features (margins, growth) from as-of-today values | computable but **NOT POINT-IN-TIME** |
