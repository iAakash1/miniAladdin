# Data quality report, Phase II (independent firm sample and EDGAR registry)

Generated from the manifests under `data/manifests/` and `phase2_data_manifest.json`. Nothing here depends on a return, a rank label or any relation between a variable and a label. Hashes of every dataset are in
`phase2_data_manifest.json`; this page states what was checked and what was found.

## 1. Universe and prices

| Check | Result |
|---|---|
| Construction | liquidity ranks 251 to 1,000 by 3-month median dollar volume, non-ETF, non-test issue, close >= 5, read from each month's whole-market cross-section (delisted names present in the months they were liquid) |
| Size-250 rebuild against the frozen universe file | equal on 171 of 171 snapshots (mismatches: 0) |
| Snapshots, members | 171 monthly snapshots 2011-01-31..2025-06-30; 2,778 unique members; 750 per snapshot |
| Members that were ever in the frozen universe (other months) | 885; dropped from the confirmatory sample by company |
| Price rows, partitions | 15 yearly partitions, checksums verified, nothing dated at or after the holdout start (2025-08-26); capped 2025-06-30 |
| Listing-snapshot table | **not copied**: its `date` column runs to 2026-08-22, inside the sealed window |
| Baseline frame | 1,181,961 rows, 2,663 symbols, 559 decision dates 2014-04-07..2025-05-06, 417,346 in universe; every grid date is a market session; names per date: minimum 637, 5th percentile 735, median 749 |
| Label coverage in universe | `fwd_rank_21` 99.8%, `fwd_ret_21` 99.8%, `fwd_ret_5` 99.95%: the missing 0.2% are names with no price 21 sessions ahead (delistings and halts) |
| Baseline feature coverage in universe | minimum 96.8%, median 99.2% |
| Optional datasets (earnings, options) | absent from this store; the builder reports "absent, not zeroed"; none of the 26 baseline features uses them |

## 2. Identity (security master for the sample)

2,747 symbols resolved: A_CONFIRMED 483, B_CONSISTENT 1,702, C_PARTIAL 18, D_NO_PERIODIC_FILINGS 362, UNRESOLVED 337, X_CONTRADICTED 58; 2,044 trusted securities; 614 exit events; 367,683 share-count vintages.

| Year | Rows | Symbols | Trusted identity | Contradicted | SIC of identified | Shares of identified |
|---|---|---|---|---|---|---|
| 2014 | 28,196 | 1,053 | 79.7% | 0.28% | 96.4% | 94.7% |
| 2015 | 38,250 | 1,128 | 80.0% | 0.27% | 97.4% | 95.3% |
| 2016 | 37,491 | 1,090 | 80.8% | 0.47% | 97.7% | 94.8% |
| 2017 | 37,500 | 1,124 | 80.8% | 0.60% | 98.1% | 94.3% |
| 2018 | 37,126 | 1,212 | 80.4% | 0.94% | 98.4% | 94.0% |
| 2019 | 37,974 | 1,148 | 80.2% | 0.99% | 98.7% | 94.4% |
| 2020 | 38,153 | 1,260 | 80.7% | 0.66% | 99.0% | 94.4% |
| 2021 | 37,353 | 1,254 | 80.5% | 0.98% | 99.0% | 94.7% |
| 2022 | 37,342 | 1,181 | 81.1% | 0.73% | 99.5% | 96.1% |
| 2023 | 37,387 | 1,153 | 81.7% | 0.59% | 99.4% | 96.3% |
| 2024 | 38,070 | 1,144 | 81.9% | 0.58% | 99.6% | 96.4% |
| 2025 | 12,504 | 972 | 82.2% | 0.54% | 99.7% | 96.6% |

Row grades in the panel: A_CONFIRMED 40,985, B_CONSISTENT 296,130, C_PARTIAL 826, D_NO_PERIODIC_FILINGS 45,465, X_CONTRADICTED 2,706, nan 31,234. **The repository's identity gate fails** (it demands 95% trusted in every year and fold; the sample reaches about 80-82%): small and delisted
names are harder to tie to a company, and 10.9% of rows belong to securities for which no 10-K or 10-Q was found (for example foreign filers or trusts; the grade D rows were not examined one by one). The size and industry-relative controls are therefore withheld (as in the frozen panel). Only trusted rows enter the
confirmatory sample, which selects on identity. Rows leaving the sample within 30 days have a lower trusted share (76.5% against 80.8%)
and a lower share of present fundamentals (73.7% against 75.9%): missingness is slightly informative about a coming exit.

## 3. Panel

417,346 rows, 1,838 securities, 2,424 symbols, 559 dates; 76 features (26 baseline, 50 SEC characteristics), feature hash equal to the frozen rich panel's. Lowest feature coverage: `gross_profit_to_ev_xs` 17%, `operating_income_to_ev_xs` 21%, `sales_to_ev_xs` 22%, `debt_growth_xs` 24%, `debt_to_equity_xs` 25%, `gross_margin_stability_xs` 26%. 0 of the 50 new features are present in at least 80% of rows.

## 4. EDGAR registry

| Check | Result |
|---|---|
| Companies, filings kept | 2,098; 481,027 (periodic reports, amendments, 8-Ks, late-filing notices, deregistrations; accepted 2009-01-01..2025-06-30) |
| Page chains | 2,098 of 2,098 complete; 1,503 reach back before 2011 |
| Duplicates | 118 accession numbers appear under more than one company (co-registrants); keyed by company and accession |
| Dates | filing date minus acceptance date is 0 to 4 days for 99.97% of filings; 31 filings are back-dated by more than a day (largest 633 days) |
| Acceptance-clock audit | on 96,429 matched filings only 71.8% of registry stamps are correct UTC; 25.0% are 8-10 hours ahead; 3.3% are New York time labelled UTC (`validation/edgar_acceptance_clock_audit.md`) |
| Amendments | 4,219 periodic-report amendments, of which 1,215 are in the Financial Statement Data Sets; 3,004 are not (Part III, exhibits) |
| Item 4.02 8-Ks, late notices | 390 filings by 298 companies; 588 NT 10-K, 748 NT 10-Q |
| Nature of the download | current-state registry retrieved 2026-10-12, not a historical snapshot; acceptance times of accepted filings do not change, but withdrawn filings, if any, would be absent |

## 5. Confirmatory sample (label-free)

150,884 labelled rows, 1,141 firms, 559 dates. Rows without any original periodic report on the date: 2,541. Treated rows and companies (trailing 730 days):
core_730 2,277 / 65; other_730 59 / 5; unchanged_730 4,616 / 104; unclass_730 1,075 / 36; any_730 7,456 / 180; i402_730 2,368 / 74; nt_730 4,295 / 122; nonfsds_amend_730 13,075 / 287.

## 6. Known gaps (not fabricated, not filled)

* No historical snapshot of provider data exists for the live scorer; the archive library records only from the day capture starts.
* Delisting returns are not modelled; names with no price 21 sessions ahead lose their label (0.2% of rows).
* Amendment content is known for 55% of amendments (a previous version with comparable facts is needed); the rest enter as their own category.
* Prices are unadjusted for dividends and the split table starts 2014-03-28; the panel therefore starts in April 2014.
* The price source's licence has not been reviewed.
