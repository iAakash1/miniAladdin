# Data-completion gate (frozen 2026-09-20, before any new coverage is measured)

Scope: one bounded, **outcome-blind** data-completion cycle (Path A). This document is committed and pushed before any source is fetched, any mapping is built or any
coverage is re-measured. Anything below that is later found to be inconvenient is reported as such; it is not edited to pass.

## 1. Rules of the cycle

* **Outcome-blind.** No feature → future-return correlation, no feature Rank IC, no univariate Sharpe or top-minus-bottom return, no model validation result is computed at any point
  before the incremental specification is frozen and preregistered. Only coverage, identity and data-quality statistics are computed.
* **No relaxation.** The prior thresholds in §2 are quoted from the repository and are used unchanged. No easier replacement is introduced.
* **Frozen research history.** EXP-006 … EXP-011 outcomes, `ds-richpit-ff3d3f556488b7da` and every method file covered by the EXP-011 fingerprint are not modified. New behaviour goes in new modules;
  older data tables stay in place (`security_master_v3`, `sec_v3`) and new tables are written beside them (`*_v4`).
* **Holdout.** 2025-08-26 → 2026-08-28 is not read, scored, inspected for coverage or used for any identity decision. Price windows stay capped at 2025-05-09.
* **Bug rule.** A genuine historical error in an EXP-011 feature stops the cycle: it is documented (error, scope, affected rows/features, whether EXP-011 is invalidated) and reported, and is not silently repaired.

## 2. Prior thresholds, quoted from `src/quant/pit/pit_coverage.py::THRESHOLDS` (unchanged)

| Threshold | Value |
|---|---:|
| trusted identity (A/B) share of universe name-dates, every year from 2015 | ≥ 0.95 |
| trusted identity share, every validation fold | ≥ 0.95 |
| contradicted (`X_CONTRADICTED`) share, every validation fold | ≤ 0.02 |
| SIC share of identified names, every validation fold | ≥ 0.95 |
| market-cap share of identified names, every validation fold (size features) | ≥ 0.90 |

`security_master_pit` is computed by the existing `security_master_status(coverage)` function, unchanged: it is true only if **every** identity, contradiction and SIC check passes; market cap does not enter that flag.
`size_features_allowed` and `neutralization_allowed` are true only if the market-cap check passes **and** `security_master_pit` is true.

Prior measured state (tracked `data/manifests/security_master_coverage_v3.json`): 950 universe tickers, 813 resolved (grades A 828 / B 33 / C 1 / D 96 / X 18 / unresolved 37 links), 976 identity intervals,
`security_master_pit = false`; trusted identity by fold 0.9498, 0.9251, 0.9367, 0.9257, 0.9180, 0.9347, 0.9371, 0.9442; no-10-K/10-Q filers 4.2–7.1%; unresolved 0.0–1.6%; contradicted 0.2–1.1%;
market cap of identified 0.9078–0.9509. ALFRED `BLOCKED_EXTERNAL_FRED_KEY`.

## 3. Declared definitions for this cycle (fixed before measurement)

* **D1 — evidence forms.** For the identity grade, "periodic filings" are extended from the 10-K/10-Q families to also include the annual-report families of foreign private issuers: `20-F`, `40-F` and their `/A` amendments, taken from the same SEC Financial Statement Data Sets. `6-K` is audited and counted but is **not**
  periodic evidence (it is event-driven). The grade definitions A/B/C/X/D/UNRESOLVED are otherwise unchanged. Rationale: the D grade meant "no 10-K/10-Q", which is a statement about the form, not about whether the ticker→CIK link is testable.
* **D2 — foreign-filer policy.** A *foreign filer name-date* is one whose latest available periodic-report snapshot is a 20-F/40-F-family filing. For those: currency-neutral ratios only; the reporting currency of a filing is the most frequent currency among its core monetary facts and facts in other currencies are dropped;
  IFRS and US-GAAP tags are **not** treated as interchangeable (§5); shares, market capitalisation and every price-dependent feature are **undefined** for foreign filers because the ADS-to-ordinary ratio and the FX rate are not available point-in-time.
* **D3 — size-gate population.** The market-cap gate is evaluated over identified **domestic** name-dates (foreign filers have no defined market cap under D2). The all-identified figure is reported beside it. This does not touch `security_master_pit`, which never used market cap.
* **D4 — share-basis hierarchy (unchanged).** 1) cover-page count; 2) balance-sheet count; 3) labelled `WEIGHTED_AVG_PROXY` only where 1 and 2 have nothing in the 400-day window. Coverage is reported per tier and never merged into one number.

## 4. Closed list of evidence sources

SEC Financial Statement Data Sets (all forms in scope, already local and verified); SEC `submissions` API (name history, tickers, exchanges, filing forms and 8-K items); SEC `companyconcept` API (`dei` cover shares); Kenneth French SIC files (already hashed);
FRED/ALFRED (key required); OpenFIGI as a **cross-check only** (it may never create an effective date). No other source will be added during this cycle. Exchange notices and issuer investor-relations archives are not systematically obtainable and are used
only to inspect a named ambiguous case during the manual audit, never to move coverage.

**Exhaustion rule.** The cycle ends when every gate below is evaluated as PASS, or when the sources above are exhausted and each remaining gap is classified `UNRESOLVED_EVIDENCE_EXHAUSTED` with its reason. It does not continue by finding new sources to cross a threshold.

## 5. IFRS support (frozen scope)

Concepts are limited to those needed by existing rich characteristics: revenue, cost of revenue, gross profit, operating income, net income, operating cash flow, capital expenditure, depreciation and amortisation, assets, current assets, liabilities, current liabilities, equity, cash, inventory, receivables, long-term and short-term debt. For each mapping the map records
canonical concept, taxonomy, tag, unit requirement, instant/duration, priority, fallback, semantic caveat and measured coverage, under the version string `ifrs-core-facts-v1`. Ambiguous IFRS concepts (for example equity attributable to owners versus total equity, or profit versus profit attributable to owners) keep an explicit priority and caveat. No new characteristic families are created.

## 6. Admission gates for the incremental block (dataset v2)

The 76 EXP-011 features are copied unchanged. The incremental block contains **only** information withheld or unavailable in EXP-011 because of the data limitations, and a category is admitted only if its gate passes.

| Category | Columns | Admission gate |
|---|---|---|
| **Size and industry controls** | the seven `CONTROL_FEATURES` already defined and withheld in EXP-011 (`log_market_cap` and six industry-relative characteristics) with their `_xs` ranks | `security_master_pit` is true **and** the D3 market-cap gate passes in every fold. (The old rule, unchanged.) |
| **Foreign-filer completion** | up to 18 declared currency-neutral characteristics, prefixed `fc_` and ranked against the same-date domestic reference distribution (so no domestic rank changes): roa, roe, operating_profitability, cash_profitability, gross_margin, operating_margin, net_margin, cash_flow_margin, asset_turnover, asset_growth, capex_to_assets, accruals, cash_flow_quality, liabilities_to_assets, current_ratio, cash_to_assets, revenue_growth, earnings_growth | in **every** validation fold at least 50% of foreign trusted name-dates have at least 5 of the columns non-null, **and** every fold has at least 8 distinct foreign securities. A single column is dropped if its coverage over foreign trusted name-dates is below 30% in any fold. |
| **Vintage macro** | none. The existing macro inputs are the Treasury 3-month, 2-year and 10-year yields (DGS3MO, DGS2, DGS10), which are not revised; an ALFRED replacement re-derives the same values and adds **no** predictor columns | ALFRED is admitted only if `FRED_API_KEY` is present and vintage validation passes; otherwise the status stays `BLOCKED_EXTERNAL_FRED_KEY` and nothing substitutes revised data |

Foreign columns are non-null only where the name-date's latest available periodic snapshot is 20-F/40-F-family (so domestic and foreign regimes are disjoint). EXP-012 is preregistered only if the admitted incremental block has **at least 5 columns**; otherwise no experiment is prepared on an empty block and the cycle reports that.

## 7. Other frozen checks

* **Exit evidence** (`security_exit_event`: `security_id, event_type, effective_date, evidence_date, source, confidence, classification`): classification EXACT / APPROXIMATED / UNKNOWN reported for every closed identity. An event is EXACT only with a Form 25 within 45 days of the last trade. No delisting return is invented (invariant, tested).
* **Truncation invariance** for identity, SIC, shares, fundamentals, foreign facts and ALFRED: build with data through T and with the complete source; every observation available before T must be unchanged.
* **Old-block invariance:** the 76 EXP-011 columns on the common rows have **zero** changed cells against `ds-richpit-ff3d3f556488b7da`; recorded as old-block hash, common-row count and changed-cell count.
* **Manual audit:** at least 25 issuer-periods chosen by a frozen rule: candidates are (CIK, accession) pairs from the v2 population, ordered by SHA-256 of `"exp012-manual-audit-v1:" + cik + ":" + accession`, taking the first three from each of these strata that exist: amendment, after-close acceptance, ticker reuse or succession, foreign filer, multiple share classes, delisted name, missing fact, restatement, split, and an unconstrained stratum. Each is traced source row → curated fact → snapshot → feature value, and every trace must reconcile. Examples are not hand-picked.
* **Holdout exclusion:** no curated row, identity window or feature date after 2025-05-09.
* **validate-all:** re-run unchanged in structure; each component is recorded as PASS, PARTIAL, BLOCKED or FAIL. Gates are not edited to reach PASS.

## 8. What happens next (also fixed now)

`security_master_pit` is set mechanically by §2. It is not chosen, and EXP-012 is not made dependent on it being true. The incremental block is whatever §6 admits. EXP-012 (C0: frozen 76 features + Ridge; C1: 76 + block + the same Ridge; C2: 76 + the frozen boosting specification; C3: 76 + block + the same boosting) reuses the frozen
EXP-011 E1 and E3 predictions as C0 and C2 wherever hash-verified reuse is exact. Its interpretation rule is written before any fit, uses the EXP-010A noise floor only as descriptive context, and records the accumulated research-trial count. It is prepared here and **not run**.

## Amendment A1 (recorded after the first manual-audit run; strictness-only; no threshold changed)

Written before the audit is re-run and before market-cap coverage is re-measured. Nothing in §2 (thresholds) or §6 (admission gates) is relaxed. Everything below either makes the audit follow §7 more literally or removes information from the incremental block.

**A1.1 What happened.** The first audit run used a hard-case strata list of its own (IFRS 20-F, US-GAAP 20-F, 40-F, non-USD currency, mixed regime, share-proxy tier, identity B/C, former name, domestic grade A, plus amendment, succession, exiting). It is **not** the list in §7. It audited 36 filings: 29 reconciled and 7 were flagged. Six flags were the auditor's own net-income tag list (`ProfitLoss`, which includes non-controlling interest) ranking ahead of the documented owner-attributable priority; one (Devon Energy, FY2018 10-K) was a revenue tag-priority divergence in the frozen v3 store (see A1.5). That run is kept as a **supplementary hard-case audit** and reported as such. The §7 audit is run separately, from the list below.

**A1.2 §7 strata, operationalised from identifiers and filing metadata only** (first three per stratum by the SHA-256 rule in §7; a filing is audited once, under the first stratum it qualifies for, in this order): *amendment* = annual form ending `/A`; *after-close acceptance* = accepted at or after 16:00 US Eastern, or on a non-session day; *ticker reuse or succession* = CIK in a succession link, or a ticker resolved to more than one CIK; *foreign filer* = 20-F or 40-F (with amendments); *multiple share classes* = CIK with two or more trusted securities; *delisted name* = CIK with any exit event; *missing fact* = annual filing in the v2 population with no curated annual `assets`, `net_income` or `revenue` fact; *restatement* = annual filing whose prior-period `assets`, `net_income` or `revenue` differs by more than 0.5% from the value in an earlier annual filing of the same CIK; *split* = annual filing of a CIK whose ticker has a split-table event in the 365 days before acceptance; *unconstrained* = any annual filing in the v2 population.

**A1.3 What "reconciles" means.** A trace reconciles when (i) the curated value equals the raw `num.txt` value **of the tag the curated row cites**, (ii) the snapshot value equals the curated value, (iii) the stored availability session equals the session re-derived from the acceptance timestamp, and (iv) the recomputed ROA equals the snapshot ROA. A different definition available in the same filing (an alternative total-revenue or total-profit tag) is reported as a `DEFINITION_NOTE`, counted, and never turned into a pass or a fail. Share counts are traced the same way: the stored share value against the raw cover-page or balance-sheet rows of the cited tag, with any per-class rows listed.

**A1.4 D5 - multi-listed issuers have no share count.** The audit showed why a per-issuer share count cannot be multiplied by a per-class price: for Berkshire Hathaway the stored value is a Class-A-equivalent count (about 1.64 million), so the Class B price times that count is roughly 1,500 times too small, and `multi_class_summed` is false for every one of the 147,760 share vintages, so nothing guards the case. Policy: any CIK with two or more trusted securities in the universe has shares, share basis, share age and market cap **undefined** for all of them. Single-listed-class issuers whose vendor name carries a class designation (about 15% of trusted CIKs) are **not** excluded: their total share count times the listed class's price is the standard approximation, and it is disclosed as a residual limitation. Coverage denominators are unchanged: an excluded name counts as missing in the §2 market-cap measure; nothing is removed from the denominator to protect the gate.

**A1.5 Stated consequence.** The market-cap gate is re-measured under D5 with the unchanged 0.90 threshold. The pre-D5 measurement was a PASS (domestic market cap 0.906-0.947 by fold); the post-D5 result decides whether the seven withheld controls are admitted, mechanically. A FAIL removes them and the incremental block is then the foreign block alone.

**A1.6 A finding about the frozen block, recorded not corrected.** `sec_v3` maps `revenue` with `RevenueFromContractWithCustomerExcludingAssessedTax` first and `Revenues` as a fallback (`docs/SEC_TAG_MAP_AUDIT.md`). Where a filer reports both, the primary tag can be a component of total revenue. Measured on the annual filings in the v3 store: 1,101 report both tags; 506 differ by more than 10%; in 481 the primary tag is the smaller. That is 0.8% of the 63,301 annual filings with any revenue fact. The values are exactly what the cited tags report and were public at the filing time, so this is a documented definitional limitation and not a point-in-time error; revenue-based ratios for those filings are overstated in margin terms. The 76 EXP-011 columns are frozen and are **not** altered here. It is carried into the readiness document as a limitation, and any correction would be a new dataset version and a new preregistered study.
