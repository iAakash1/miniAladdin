# Rich PIT panel audit

Dataset `ds-richpit-ff3d3f556488b7da`: 139,292 universe name-dates, 762 securities (874 tickers), 2014-04-03 to 2025-05-09, 76 features (`7212297bc55a45f6...`), content hash `ff3d3f556488b7da...`. Holdout touched: **false**. Built from commit `fefc5af6fe`.

This document reports what the panel contains and does not contain. It contains no performance evidence: no feature was scored against any return.

## Identity resolution and survivorship

* Trusted (A/B) identity by fold: fold_0 95.0%, fold_1 92.5%, fold_2 93.7%, fold_3 92.6%, fold_4 91.8%, fold_5 93.5%, fold_6 93.7%, fold_7 94.4%.
* `security_master_pit` = **false**; size/industry controls **withheld**.
* Unresolved tickers: 37 (sample: AABA, AUY, BA$A, BBBY, BBL, BDXB, BHGE, CLR, CTRP, CYBR, DGAZ, DIDI, EQC, EQR, FNGA, FTCH, GLOG, GRUB, HDS, HPE$C...). Foreign/no-10-K issuers (`D`): 96 links.

**Survivorship through missingness.** Fundamentals are absent for names the security master cannot resolve, and those are disproportionately delisted names. A model that sees only
`NaN` could in principle learn 'missing = will delist'. Measured on the panel rows (names whose price series ends within 30 days versus all others):

| | Names exiting within 30 days | All other rows |
|---|---:|---:|
| ROA feature present | 85.3% | 87.2% |
| Trusted identity | 85.3% | 93.6% |

Identity is 8.2 points less often trusted for names about to exit, and the ROA feature is present 1.9 points less often, measured on only 109 exiting rows: the association is real in sign, small, and imprecisely measured. It is not zero, which is why EXP-011 reports a covered-subset ordering diagnostic and imputes with training-fold medians rather than a missingness flag.

## Coverage by feature family (share of universe name-dates with a value)

| Feature family | Mean coverage | Min feature | Max feature |
|---|---:|---:|---:|
| capital_structure | 67.6% | 31.7% | 86.5% |
| event | 89.6% | 85.4% | 91.8% |
| growth | 68.9% | 28.1% | 86.4% |
| investment | 68.6% | 52.4% | 90.1% |
| leverage | 60.3% | 33.1% | 91.6% |
| profitability | 70.4% | 43.1% | 89.1% |
| quality | 68.1% | 26.0% | 87.0% |
| value | 59.2% | 20.3% | 86.8% |

Mean coverage of the new features in each family, by validation fold:

| Family | fold 0 | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | fold 6 | fold 7 | train only |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| capital_structure | 68.0% | 67.5% | 67.6% | 64.9% | 65.0% | 70.7% | 70.9% | 71.0% | 66.2% |
| event | 89.9% | 88.4% | 90.4% | 89.0% | 88.8% | 92.2% | 92.6% | 92.9% | 87.3% |
| growth | 66.8% | 68.4% | 69.9% | 67.8% | 68.5% | 72.8% | 75.3% | 74.2% | 65.0% |
| investment | 67.7% | 68.2% | 70.2% | 68.7% | 68.1% | 71.4% | 72.2% | 72.0% | 65.4% |
| leverage | 60.4% | 60.1% | 61.3% | 59.9% | 58.9% | 62.0% | 61.6% | 62.5% | 58.8% |
| profitability | 67.8% | 67.9% | 72.6% | 71.9% | 72.5% | 75.1% | 75.9% | 76.2% | 65.0% |
| quality | 68.5% | 68.6% | 69.6% | 63.0% | 66.1% | 71.0% | 72.2% | 73.7% | 65.4% |
| value | 57.8% | 58.3% | 60.7% | 57.8% | 58.8% | 62.2% | 62.4% | 62.9% | 56.7% |

Per-feature first-valid dates and coverage by year and period are in `data/manifests/rich_pit_panel_manifest.json` and `docs/PIT_FEATURE_CATALOG.md`.

## SEC availability

* 58 quarterly archives verified (`docs/LOCAL_DATA_INVENTORY_FINAL.md`); 14,574,206 curated as-reported rows from 369,971 filings and 14,408 CIKs.
* Availability is acceptance time in US Eastern, next session for filings at or after 16:00. Fallback and tag-disagreement rates per fact family: `docs/SEC_TAG_MAP_AUDIT.md`.
* Restatements are preserved as vintages. Real-data truncation test (2019Q1-Q4 cut at 2019-07-01): 150,514 later vintages of facts first reported before the cut, 11,347 amendment rows after it, and every earlier row and both PIT views byte-identical.

## Industry and size

* SIC as of each filing gives 925 dated intervals over 802 CIKs; 99 CIKs (12.3%) change SIC at least once, which is what an as-of-filing field should show (a current-only field would show none).
* Fama-French 12/17/48 come from the Kenneth French SIC files (hashes in `docs/PIT_SECURITY_MASTER_STATUS.md`). There are no GICS sectors anywhere.
* Market cap is present for 86.2%-89.7% of name-dates by fold; it is the input to the value features, but the `log_market_cap` and industry-relative controls are withheld by the gate.

## Limits that remain

* 20-F/40-F filers have no fundamentals (IFRS mapping not built). Delisted names without a recoverable name have none either.
* The universe is the frozen top-250-by-liquidity set; delisting bounds before 2017-10-26 are inferred (`docs/PIT_SECURITY_MASTER_PLAN.md`).
* Shares use the cover-page count where the API supplies one and the balance-sheet count otherwise; multi-class companies sum classes in the cover count (flagged) and are excluded from the bulk balance-sheet count.
* Splits are taken from a table that begins 2014-03-28. Market cap for a split before that date is not restated.
* Cross-sectional ranks are formed among names with a value, so the peer group changes with coverage over time.
