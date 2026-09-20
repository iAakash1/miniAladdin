# Rich PIT v2 audit — repaired foreign-currency build

Audit date: 2026-09-20  
Dataset: `ds-richpit2-6368cccdb94c62d0`  
Content hash: `6368cccdb94c62d09dd048b972ae75272721f4f6cc56f246ccf36cff63319d8e`

This dataset supersedes the defective provisional `ds-richpit2-361bd5029c791444`. The old identity remains in Git history as evidence and must never be used for an experiment. No target statistic, model, return, portfolio, or holdout row was used to build or admit this dataset.

## Identity and invariance

| Property | Result |
|---|---:|
| Rows | 139,292 |
| Securities | 839 |
| Tickers | 874 |
| Date range | 2014-04-03 → 2025-05-09 |
| Frozen EXP-011 columns | 76 |
| Incremental columns | 18 |
| Total features | 94 |
| Frozen feature hash | `7212297bc55a45f66ffceb3548000e899773e1959e365b266fb477f24d8b8614` |
| Frozen cells compared | 10,586,192 |
| Frozen cells changed | **0** |
| Incremental feature hash | `6176eb288d4fcbf93e617a874b0851ee59761cb0ab4a2369dcca6c1402600d43` |

The frozen 76 columns are copied from EXP-011, not recomputed with the corrected revenue shadow view. This is deliberate: a corrected-data replication is a separate scientific study.

## Repaired foreign store

- Map: `ifrs-core-facts-v1`; store hash `a49476f4e8a226591dae3c294e7d77d6cae2d4dc617186ea33379701da0190be`.
- 342,556 curated rows, 9,979 filings with mapped facts, 1,838 registry CIKs.
- Reporting currency is selected once per accession by a filing-global two-pass scan.
- Zero filings contain more than one selected reporting currency; the defective store had 309.
- 21,448 other-currency rows were excluded; no filing lacked a reporting currency.
- Currency tie cases: 0. Taxonomy-family tie cases: 1 (IFRS wins under the frozen rule).
- Real 2024Q2 rebuild at 25,000 and 900,000 parser rows per chunk produced the same 19,633 rows and content hash `77d49a7c1abfba1c9ffb146a2977a0f12cb50892a3d19c775f951f7005f0e283`.

## Admission decisions

The frozen gates were rerun unchanged.

### Foreign block — admitted

Every validation fold has at least 13 foreign securities (gate: 8), at least 59.3% of foreign name-dates carry five or more columns (gate: 50%), and every admitted column clears its 30% per-fold coverage requirement. No column was dropped.

Admitted columns:

`fc_roa_xs`, `fc_roe_xs`, `fc_operating_profitability_xs`, `fc_cash_profitability_xs`, `fc_gross_margin_xs`, `fc_operating_margin_xs`, `fc_net_margin_xs`, `fc_cash_flow_margin_xs`, `fc_asset_turnover_xs`, `fc_asset_growth_xs`, `fc_capex_to_assets_xs`, `fc_accruals_xs`, `fc_cash_flow_quality_xs`, `fc_liabilities_to_assets_xs`, `fc_current_ratio_xs`, `fc_cash_to_assets_xs`, `fc_revenue_growth_xs`, `fc_earnings_growth_xs`.

### Size and industry controls — not admitted

`security_master_pit = true`, but the unchanged 0.90 every-fold market-cap requirement fails. Domestic market-cap coverage among identified rows ranges from 0.8684 to 0.9119. The seven size/industry-relative controls remain withheld; the denominator and threshold were not changed.

### ALFRED — blocked

`BLOCKED_EXTERNAL_FRED_KEY`. No FRED key is present, no vintage table was fabricated, revised observations were not substituted, and ALFRED adds no predictor columns.

## Manual source audit

The deterministic audit was rerun against the repaired panel:

- Frozen section-7 strata: 30/30 issuer-periods PASS; 22/22 traced share counts reconcile.
- Supplementary hard cases: 36/36 PASS; 17/17 traced share counts reconcile.
- Definition differences remain notes rather than being relabelled as point-in-time failures.

## Validator

| Check | Status |
|---|---|
| Foreign store | PASS |
| Fundamental truncation invariance | PASS |
| Industry/share truncation invariance | PASS |
| Security-master gate consistency | PASS |
| Rich PIT v2 dataset and frozen-block invariance | PASS |
| Holdout exclusion | PASS |
| Identity CIK stability | PARTIAL — retrospective trust grades, already disclosed |
| ALFRED | BLOCKED — external key absent |

There is no FAIL in any component used by the admitted incremental block.

## Revenue-mapping integrity finding

The parallel outcome-blind audit is in `docs/EXP_011_REVENUE_MAPPING_IMPACT_AUDIT.md`. It reproduces the frozen feature block with zero changed cells, then finds 171 unique filings with unambiguous corrected disagreement, 100 ambiguous filings, 4,256 directly affected name-dates, and 981,502 changed rank cells after same-date propagation across all 14 revenue-dependent features. Classification: `UNRESOLVED_MAPPING_IMPACT`.

Therefore this v2 dataset is a valid immutable data artifact, but **EXP-012 is not prepared**. The research lineage stops for an explicit corrected-data replication decision. The sealed 2025-08-26 through 2026-08-28 holdout remains untouched.

