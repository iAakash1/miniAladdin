# Data-completion cycle: status at push time (2026-09-20)

> **Superseded status update.** The interruption state below is preserved as historical evidence. The currency defect has since been repaired: the foreign store has zero multi-currency filings and passes real-data chunk invariance; repaired Rich PIT v2 is `ds-richpit2-6368cccdb94c62d0` with zero changes in the frozen 76-feature block and 18 admitted foreign columns. The outcome-blind revenue audit classified the EXP-011 mapping impact as `UNRESOLVED_MAPPING_IMPACT`, so EXP-012 was not prepared. See `docs/RICH_PIT_V2_AUDIT.md`, `docs/EXP_011_REVENUE_MAPPING_IMPACT_AUDIT.md`, and `docs/FINAL_HOLDOUT_READINESS.md`.

Written when the cycle was interrupted for time. It states what exists, what is known to be wrong, and what has not been done. Nothing here is a result about returns: no EXP-012 fit has been run, the sealed holdout (2025-08-26 to 2026-08-28) has not been touched, and no hyperparameter or feature selection has used an outcome.

## Built and committed

| Piece | State |
| --- | --- |
| Gate frozen before measurement | `docs/DATA_COMPLETION_GATE_2026.md` (0a863b4), amended once by A1 (strictness only; no threshold changed) |
| Foreign 20-F/40-F facts (`ifrs-core-facts-v1`) | built, **has a known defect (below)** |
| Security master v4 (identity, exits, succession, shares tiers, filer regimes) | built; `security_master_pit = true` |
| Point-in-time industry attach | fixes a look-ahead in the EXP-011-era staleness rule (a 2014 SIC could be validated by a 2016 filing); EXP-011 features were not affected because the controls were withheld |
| D5, multi-listed issuers have no share count | domestic market cap 0.868-0.912 by fold, so the frozen 0.90 size gate **fails** and the seven withheld controls are **not admitted** |
| ALFRED | `BLOCKED_EXTERNAL_FRED_KEY`; no key present; ALFRED would add no predictor columns (Treasury 3m/2y/10y are unrevised) |
| Rich PIT v2 | `ds-richpit2-361bd5029c791444`: the frozen 76 EXP-011 columns copied unchanged (0 changed cells over 10,586,192) plus 18 foreign `fc_*` columns. **Provisional: see the defect** |
| Manual audit | frozen section-7 audit: 30 issuer-periods, 30 reconcile; supplementary hard-case audit: 36, 36 reconcile; 22 and 17 share counts traced to source |
| Validation (`pit_validation_v4.json`) | fundamentals truncation invariance PASS (0 changed cells at two cut-offs, domestic sample and all foreign); industry and share truncation PASS; v2 dataset PASS; holdout exclusion PASS; gate consistency PASS; identity PARTIAL (retrospective grades, disclosed); ALFRED BLOCKED; **foreign store FAIL** |

## Known defect: two currencies in one filing

`src/quant/pit/foreign_facts.py::curate_foreign_archive` chooses each filing's reporting currency **per 600,000-row chunk** of `num.txt`. A filing whose rows straddle two chunks can be assigned a different "most frequent" currency in each, so both survive. Measured on the built store: 309 of 9,979 filings (3.5% of 343,084 rows) hold two currencies, for example a TWD reporter with USD convenience-translation rows kept beside the TWD rows. The v2 build reads these facts without a currency filter, so a ratio for such a filing can combine a numerator and a denominator from different currencies. Effect on the 18 `fc_*` columns has **not** been quantified.

Fix (not yet made): compute reporting currency over the whole archive before the chunk loop, then rebuild the foreign store, the v2 dataset, the audits and the validation. Until then `ds-richpit2-361bd5029c791444` must not be used for EXP-012.

## Recorded, not corrected (frozen block)

Revenue in the frozen v3 store uses `RevenueFromContractWithCustomerExcludingAssessedTax` first. Where a filer reports `Revenues` too, the primary tag can be a component: 506 of 63,301 annual filings differ by more than 10%, 481 with the primary tag the smaller (Devon Energy FY2018: 4.449B against 10.734B). Documented mapping limitation, not a point-in-time error; the 76 EXP-011 columns are frozen and were not altered. See Amendment A1.6.

## Not done

`docs/RICH_PIT_V2_AUDIT.md`, `docs/FINAL_HOLDOUT_READINESS.md`, the EXP-012 module, its tests, its preregistration and fingerprint, the gate and the dry-run, and tests for the audit and validation modules. EXP-012 is not prepared and must not be run.
