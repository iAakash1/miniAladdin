# Data dictionary (EXP-012 and the reliability table)

Scope: every table or column that the registered study reads or writes. The long catalogue of the 57 feature definitions in the rich point-in-time panel is
`docs/PIT_FEATURE_CATALOG.md`; the machine-readable registry of all signals, research and live, is `signals.csv` in this folder.

## 1. Source: SEC filing registry (read only)

`data/curated/sec_v3/filings.parquet`, 371,229 filings, built from the SEC Financial Statement Data Sets (public US government data; see `datasets.csv` L01).

| Column | Type | Meaning | Used as |
|---|---|---|---|
| `adsh` | string | accession number, unique per filing | tie-break in sorting |
| `cik` | integer | SEC central index key; the join key to the panel | firm identity |
| `form` | string | form type; the study uses 10-K, 10-Q, 10-KT, 10-QT (originals) and 10-K/A, 10-Q/A, 10-KT/A, 10-QT/A (amendments) | original or amendment; annual or quarterly |
| `period` | integer yyyymmdd | fiscal period end covered by the report | lag and amendment matching |
| `accepted_at` | timestamp | EDGAR acceptance time | availability, lag |
| `prevrpt` | flag | says a report was *later* amended | **never read** (describes the future of the filing) |

Availability rule: a filing accepted before the close of a session is usable in a close-based decision on that session, otherwise from the next session
(`src/quant/pit/sec_facts.py: available_session`). All windows below are measured in availability days.

## 2. Stored derived table: `data/research/derived/reliability_v1.parquet`

139,292 rows, one per (date, symbol) of the rich panel; sha256 and coverage in `data/manifests/reliability_v1_manifest.json`. Missing values are NaN, never zero.
NaN means the firm has no filing history in the registry on that date or has no mapped CIK (8,967 rows, 6.4% of the table, have no mapped CIK; a further 2,502 rows have a CIK but no usable filing history).

| Column | Type | Definition | Range seen | Mean | Share zero | Coverage |
|---|---|---|---|---|---|---|
| `date` | date | decision date (every 5th session) | 2014-04-03 to 2025-05-09 | | | 100% |
| `symbol` | string | ticker as in the panel; not a stable identity, CIK is | | | | 100% |
| `amended_730` | float (count) | amendments to periodic reports usable in the trailing 730 days | 0 to 5 | 0.040 | 96.5% | 91.77% |
| `latest_report_amended` | float (0/1) | 1 if the latest original periodic report has already been amended by the decision date | 0 to 1 | 0.0023 | 99.8% | 91.77% |
| `periodic_count_400` | float (count) | original periodic reports usable in the trailing 400 days | 0 to 7 (60% are 4, 38% are 5) | 4.34 | 0% | 91.77% |
| `lag_deterioration` | float (days) | days from period end to acceptance of the latest original report, minus the median of the same lag over the previous four originals of the same kind (annual or quarterly); positive means later than usual | -49 to 352.5 (1st to 99th percentile -12.5 to 11) | -0.48 | 7.1% | 91.00% |

Note on information content: three of the four variables are close to constants (97% to 99.8% of the non-missing rows share one value). The study is therefore
informative mainly through `lag_deterioration` and through the rare rows in which an amendment or a shortfall appears. This limits power and is stated in the
preregistration's sensitivity section and in `data_quality_report.md`.

## 3. Model inputs built in memory (not stored)

`attach_reliability` in `src/quant/study/exp012.py` adds these to the validated rich panel at load time. Cross-sectional rank is the repository's `cross_sectional_rank`
(percentile in [-1, 1], centred) computed within each date over the names in the universe on that date.

| Column | Formula | Orientation (higher means less reliable) |
|---|---|---|
| `rel_amended_730_xs` | cross-sectional rank of `amended_730` | yes |
| `rel_latest_amended_xs` | cross-sectional rank of `latest_report_amended` | yes |
| `rel_periodic_count_xs` | cross-sectional rank of `periodic_count_400` | no (fewer reports is worse; the composite flips its sign) |
| `rel_lag_deterioration_xs` | cross-sectional rank of `lag_deterioration` | yes |
| `rel_missing_xs` | cross-sectional rank of `rel_n_missing`, the count of missing fundamentals features (of 48) in the row | yes |
| `rel_u_xs` | mean of the oriented ranks of `days_since_report_xs`, `filing_lag_days_xs`, `rel_amended_730_xs`, `rel_lag_deterioration_xs` and -`rel_periodic_count_xs` (at least 3 present), ranked again within the date | yes |
| `int_<f>` (48 columns) | `f_xs * rel_u_xs` for each fundamentals feature `f` | not applicable |

## 4. Inputs from the rich panel (read only)

`ds-richpit-ff3d3f556488b7da` (content hash `ff3d3f556488b7da...`), 139,292 rows, 91 columns, 762 securities (the reliability manifest counts 874 distinct ticker strings, because a ticker is not a stable identity), 2014-04-03 to 2025-05-09.

| Group | Columns | Notes |
|---|---|---|
| keys | `date`, `symbol`, `cik`, `in_universe` | only in-universe rows are scored |
| label | `fwd_rank_21` | cross-sectional rank of the forward 21-session return; the only target |
| baseline | 26 price, liquidity and macro features | the EXP-011 E0 set |
| fundamentals | 48 PIT characteristics (profitability, investment, value, leverage, growth, quality, capital structure, event) | the rich set minus its two reliability variables |
| existing reliability | `filing_lag_days_xs`, `days_since_report_xs` | already in the rich set; the subject of T3 |

## 5. Outputs (`experiments/EXP-012/`)

| File | Content |
|---|---|
| `definition.json` | the canonical definition whose SHA-256, together with the method files, is the registered fingerprint |
| `config.json` | arms with their feature lists, the eight folds, the cost grid |
| `per_arm_metrics.csv` | one row per (arm, seed): `mean_rank_ic`, `hac_t_stat`, `ic_ir`, `positive_fold_count`, `worst_fold_ic`, covered-subset IC, and the B1 portfolio's gross and net (10 bp) Sharpe, turnover, drawdown and cost share |
| `fold_metrics.csv` | mean rank IC per (arm, seed, fold) |
| `paired_tests.csv` | per contrast: `dates`, `mean_diff`, `hac_t`, `p_one_sided`, `boot95_low`, `boot95_high`, `positive_folds`, `fold_diffs` |
| `metrics.json` | all of the above plus Holm-adjusted p-values and verdicts |
| `manifest.json` | identity of the run: git commit and cleanliness, registration commit, fingerprint, acceptance checks, holdout state, dependency versions, wall time, output SHA-256s |
| `checkpoints/` | per (arm, seed) predictions with a receipt; git-ignored |
| `model/A1.joblib`, `model/A5.joblib` | research artifacts (rich set; rich plus new block) |

A model artifact is a dict with: `arm`, `definition_fingerprint`, `dependency_versions`, `experiment`, `features` (the exact column order), `imputer` (a
`FoldImputer` fitted on the training rows), `label`, `model` (ridge, alpha 10), `reliability_version`, `status` ("RESEARCH ARTIFACT - NOT FOR PRODUCTION -
PROMOTION NOT ASSESSED"), `trained_rows`, `trained_through` (2025-05-09). `python -m scripts.quant.exp012 infer` refuses missing columns and infinite values and
imputes NaN as in training.
