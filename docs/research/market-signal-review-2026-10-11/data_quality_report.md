# Data quality report: reliability_v1 and its inputs

Date of checks: 2026-10-12. Table: `data/research/derived/reliability_v1.parquet` (sha256 `042ac1fc12957f25...`, 139,292 rows). Source: the SEC filing registry
(`data/curated/sec_v3/filings.parquet`, 371,229 filings, sha256 `4e62004745eebd9b...`). Code: `src/quant/pit/reliability.py`. Nothing in this report depends on any return or label.

## Result in one paragraph

The table is built correctly by every check applied (independent recomputation, invariants, unit tests with deliberate mutations) and is point in time by construction. It is
**thin in information**: three of its four variables are almost constant, and 8.2% of rows are missing. That is a property of the data, not a defect of the build, and it bounds
what any study using it can detect.

## Checks and outcomes

| Check | Outcome |
|---|---|
| One row per (date, symbol), merged onto the panel with `validate="one_to_one"`; row count unchanged | passed (139,292) |
| Date range inside the validation period; last date before the sealed holdout (starts 2025-08-26) | 2014-04-03 to 2025-05-09, passed |
| The table's sha256 equals the manifest; the study refuses to run otherwise | enforced in `attach_reliability` |
| Independent recomputation: 4,000 sampled rows by a deliberately naive code path (plain pandas filtering on the raw registry instead of the production `searchsorted` windows; the availability rule is shared with production and has its own tests), four variables | 16,000 comparisons, 0 mismatches (`validation/reliability_validation.json`) |
| Invariants: counts non-negative, flag binary, dates before the holdout, rows match the panel | all true |
| Unit tests (`tests/quant/test_reliability.py`, 9 tests), including: perturbing any filing usable after day d cannot move a value at day d; an amendment counts from its own acceptance time; a filing accepted after the close is usable only from the next session; NaN, never zero, before history | pass |
| Mutation checks: (1) make filings visible one session early; (2) let the placebo skip rebuilding the interactions | each broke the intended tests, then the files were restored |
| `prevrpt` is never read | enforced by a unit test (`test_prevrpt_is_never_read`) |
| First validation disagreed with the table on 35 rows of `periodic_count_400` | the check had windowed on acceptance date; the table windows on availability date by design. The check was corrected, not the table, and the rule is written in the preregistration |
| Numerical warnings: `RuntimeWarning: overflow / invalid value encountered in matmul` during scikit-learn prediction | spurious on this platform (numpy 2.x with Apple Accelerate): inputs and coefficients are finite and the prediction equals an explicit sum to 2e-17; every prediction is also checked for finiteness at run time |

## Coverage

Share of rows with a value, by calendar year of the decision date:

| Year | Rows | amended_730, latest_report_amended, periodic_count_400 | lag_deterioration |
|---|---|---|---|
| 2014 | 9,702 | 88.2% | 87.0% |
| 2015 | 12,499 | 90.5% | 89.4% |
| 2016 | 12,500 | 91.7% | 91.0% |
| 2017 | 12,744 | 92.3% | 91.9% |
| 2018 | 12,389 | 90.7% | 89.9% |
| 2019 | 12,280 | 91.9% | 90.9% |
| 2020 | 12,507 | 92.4% | 91.5% |
| 2021 | 12,451 | 90.2% | 89.0% |
| 2022 | 12,733 | 92.6% | 92.0% |
| 2023 | 12,492 | 93.4% | 93.4% |
| 2024 | 12,500 | 94.0% | 93.7% |
| 2025 | 4,495 | 93.7% | 92.1% |
| **All** | **139,292** | **91.77%** | **91.00%** |

The 11,469 missing rows are 8,967 with no mapped CIK (6.4% of the table) and 2,502 with a CIK but no usable filing history on that date. Coverage rises over time, as the
CIK mapping and filing history improve; it never falls below 87%. Whether missingness is related to firm age or listing status has not been tested; `rel_missing_xs` (the count of missing fundamentals) is a model input, and missing values are median-imputed inside each training fold.

## Distributions (non-missing rows)

| Variable | n | mean | sd | min | 1st | median | 99th | max | share at the modal value |
|---|---|---|---|---|---|---|---|---|---|
| `amended_730` | 127,823 | 0.040 | 0.234 | 0 | 0 | 0 | 1 | 5 | 96.5% are 0 (3,939 rows 1; 303 rows 2; 160 rows 3; 32 rows 4; 4 rows 5) |
| `latest_report_amended` | 127,823 | 0.0023 | 0.047 | 0 | 0 | 0 | 0 | 1 | 99.8% are 0 (about 297 rows are 1) |
| `periodic_count_400` | 127,823 | 4.34 | 0.58 | 0 | 3 | 4 | 5 | 7 | 4 reports: 59.9%; 5: 37.9%; fewer than 4: 2.2% |
| `lag_deterioration` | 126,754 | -0.48 | 4.96 | -49 | -12.5 | -1 | 11 | 352.5 | continuous; 7.1% are exactly 0 |

Consequences, stated before any outcome is seen:

1. `latest_report_amended` is non-zero in about 0.2% of rows and `amended_730` in 3.5%. A cross-sectional rank of a variable that is 97% to 99.8% one value carries almost no
   cross-sectional information on most dates; the new block is informative on a small subset and through `lag_deterioration`.
2. `lag_deterioration` has a long right tail (maximum 352.5 days). The model sees its cross-sectional rank, which bounds the influence of the tail.
3. The design's power is limited. The preregistration's sensitivity section converts the paired standard errors measured on a label-shuffled run into the smallest effect each test can reject.

## Known limitations (not defects)

- The registry holds only filings with financial statements. Notices of late filing (NT 10-K / NT 10-Q), non-reliance 8-Ks (Item 4.02), and amendments that are only a Part III
  addendum are not in it. The amendments counted are re-filed financial reports. A study of the full disclosure process needs EDGAR's complete submission index.
- The amendment variables use the amendment's own acceptance time, so they describe what an observer could see on the decision date. They cannot tell why a report was amended.
- `symbol` is not a stable identity; the join to filings is by CIK. 874 distinct ticker strings map to 762 securities.
- The universe is the project's top liquid US equities (about 250 names per date), not all filers: smaller firms, where amendments and late filing are more common, are absent.
  Results cannot be generalised to them.
- SEC data are as-filed and carry no official checksums; the project's hashes are self-recorded at download time (`data/manifests/sec_download_manifest.json`).

## Reproduction

```bash
.venv/bin/python -m src.quant.pit.reliability build    # about 10 s; rewrites the table and the manifest
.venv/bin/python docs/research/market-signal-review-2026-10-11/code/validate_reliability.py
.venv/bin/python -m pytest tests/quant/test_reliability.py -q
```
