# EXP-012 preregistration - disclosure-process reliability and the value of company information

Definition fingerprint: `f9d76d2f3d68512ca613eea3b9263f297238101b5a97cdd1c966a72f3638e7ee`

Parent: EXP-011. Status: **EXPLORATORY - validation folds only - holdout sealed - promotion not assessed.** This document is committed
and pushed to the research branch before any new arm is fit; the fingerprint is the SHA-256 of the canonical definition
(`src/quant/study/exp012.py`, `DEFINITION`) and of the bytes of every method file in section 15. If the definition or a method file
changes after registration, the gate refuses to run.

Authority: the owner's instructions of 2026-10-11/12 ask for new, separately registered work and keep the holdout sealed. That is
the character of Direction A in `NEXT_RESEARCH_DECISION_2026.md` (no holdout, no promotion). It does not choose Direction B.

## 1. Disclosure of prior looks

The eight folds below have been used by EXP-006, EXP-007, EXP-009, EXP-010A/B and EXP-011. EXP-007 records 1,029 cumulative trials. This
study therefore cannot be a clean confirmation, and is labelled exploratory whatever it finds. It adds **3 confirmatory tests, 5
controls, 3 secondary contrasts and 30 model fits** (24 ridge of which 17 are placebo fits, and 6 boosted). The rest of the design is
held fixed to keep the number of degrees of freedom this study adds as small as it can be.

One further look is disclosed. While testing the script for the naive reference of section 7 on the rows of the label-shuffled rehearsal, the Rank IC of the baseline's 12-1 momentum rank
against the real label was computed once over the 404 dates (mean 0.0204). That reference enters no contrast and informed no design choice; it is recomputed from the registered run's own rows.

## 2. Question

Does the reliability of the filings a fundamentals-based signal is computed from carry incremental information about cross-sectional
returns, directly or as a moderator of the fundamentals signals, once the information set is otherwise held fixed?

Mechanism. Fundamentals features are computed from one filing. If that filing is old, was filed late, has had to be amended, or belongs
to a firm that files irregularly or later than it used to, the signal describes the firm less well and the model should lean on it less.

Prior art, read at abstract level or from verified metadata only (`docs/research/market-signal-review-2026-10-11/06_PRIOR_ART_AND_NOVELTY.md`).
The idea that the strength of a signal depends on how uncertain the information behind it is has a long record: Zhang 2006 (*Journal of
Finance*, 10.1111/j.1540-6261.2006.00831.x), Francis, LaFond, Olsson and Schipper 2007 (*Journal of Business Finance & Accounting*,
10.1111/j.1468-5957.2007.02030.x), and Chan, Chan, Jegadeesh and Lakonishok 2001 (NBER w8308) on earnings quality. That timeliness of
filing predicts returns is reported by Bannouh, Geng and Peeters 2019 (SSRN 10.2139/ssrn.3432446: faster filers earn a premium) and by Brooks,
Cheng, Liu and Yu 2023 (SSRN 10.2139/ssrn.4536648). Amendments and restatements are studied as events, for example Palmrose, Richardson
and Scholz (SSRN 10.2139/ssrn.265009) and Dechow, Ge, Larson and Sloan 2011 (10.1111/j.1911-3846.2010.01041.x). Missing characteristics in
asset-pricing panels are treated by Freyberger, Hoeppner, Neuhierl and Weber 2024 (*Review of Financial Studies*, 10.1093/rfs/hhae003).
None is claimed as replicated here. This study does not claim the idea is new: the audit rates its novelty low to medium. Its contribution,
if any, is a point-in-time, vendor-free reconstruction of the reliability variables from the SEC filing registry, a design in which a real
effect must beat placebos built from the same variables, and a cost-aware, noise-floor-anchored evaluation of whether ridge and boosted
learners gain from them.

## 3. Data and provenance

- Panel: `ds-richpit-ff3d3f556488b7da`, content hash `ff3d3f556488b7da...`, 139,292 rows, label `fwd_rank_21`, eight recorded folds, ridge alpha 10.
- Reliability source: `data/curated/sec_v3/filings.parquet` (the SEC Financial Statement Data Sets registry; 371,229 filings, sha256 `4e62004745eebd9b...`).
  SEC filings are public records; only derived counts are kept. `prevrpt` is never read.
- Reliability table `reliability-v1`: `data/research/derived/reliability_v1.parquet`, sha256 `042ac1fc12957f25...`,
  139,292 rows, 874 ticker strings, 2014-04-03 to 2025-05-09 (before the holdout). Coverage: amended_730 91.8%, latest_report_amended 91.8%, periodic_count_400 91.8%, lag_deterioration 91.0%.
  Rows without a mapped CIK (8,967) carry NaN, never zero.
- Availability: a filing is usable from the first session whose close-based decision may use it (`sec_facts.available_session`).
- Validation done before registration: nine unit tests (`tests/quant/test_reliability.py`), including that perturbing filings usable after day d
  cannot move any value at day d, and an independent recomputation of 4,000 sampled rows by a naive code path with
  0 mismatches across the four variables (`docs/research/market-signal-review-2026-10-11/validation/`).
  A first version of that check disagreed on 35 rows of `periodic_count_400` because it windowed on acceptance date instead of availability
  date; the window is defined on availability date and the check was corrected, not the table.
- Information content, computed from the features alone with no return or label (`docs/research/market-signal-review-2026-10-11/data_quality_report.md`):
  `amended_730` is non-zero in 3.5% of the non-missing rows, `latest_report_amended` in 0.2%, `periodic_count_400` equals 4 or 5 in 98%, and only
  `lag_deterioration` is continuous (long right tail, ranked before use). The new block is therefore informative mainly through
  `lag_deterioration` and a small set of rows. This bounds what the study can detect.

## 4. Variables

| Variable | Definition (all point-in-time) | Direction of "less reliable" |
|---|---|---|
| `filing_lag_days`, `days_since_report` | already in the rich panel (EXP-011) | larger |
| `amended_730` | amendments to periodic reports usable in the trailing 730 days | larger |
| `latest_report_amended` | latest original periodic report already amended | 1 |
| `periodic_count_400` | original periodic reports usable in the trailing 400 days | smaller |
| `lag_deterioration` | latest filing lag minus the median of the previous four of the same kind | larger |
| `rel_missing` | count of missing fundamentals features in the row | larger |
| `rel_u` (composite) | mean of the oriented cross-sectional ranks of `days_since_report`, `filing_lag_days`, `amended_730`, `lag_deterioration`, `periodic_count_400` (at least 3 present), ranked again within the date | larger |

Cross-sectional ranks use the repository's `cross_sectional_rank` (percentile in [-1, 1], centred), computed within each date.
Interactions are `int_<f> = f_xs * rel_u_xs` for the 48 fundamentals features.

## 5. Arms

| Arm | Model | Information set |
|---|---|---|
| A0 | ridge | EXP-011 E0 reproduction |
| A1 | ridge | EXP-011 E1 reproduction (rich) |
| A2 | ridge | rich minus its two reliability variables |
| A3 | ridge | baseline plus the two existing reliability variables only |
| A4 | ridge | baseline plus the new reliability block only |
| A5 | ridge | rich plus the new block (main effects) |
| A6 | ridge | A5 plus fundamentals x unreliability interactions |
| P0 | ridge | A5 with the new block permuted across firms within each date |
| P0s | ridge | A5 with the new block shifted 252 sessions within each firm |
| P1 | ridge | A6 with the new block (and so the interactions) permuted across firms within each date |
| P2 | ridge | A6 with the new block (and so the interactions) shifted 252 sessions within each firm |
| P3 | ridge | A1 with filing_lag_days and days_since_report permuted across firms within each date |
| G1 | gradient_boosting | secondary: boosted rich arm (EXP-011 E3 settings) |
| G2 | gradient_boosting | secondary: boosted rich arm plus the new block |

## 6. Confirmatory contrasts (one-sided, Holm across the three)

Test statistic: the mean over dates of the paired difference of per-date Spearman rank ICs on identical dates. H0: the mean difference is zero or negative.

| Test | Contrast | Claim | Mapped controls |
|---|---|---|---|
| T1 | A5 - A1 | the new reliability block adds to the rich information set | C1, C2 |
| T2 | A6 - A5 | reliability moderation of the fundamentals adds to the main effects | C3, C4 |
| T3 | A1 - A2 | the two existing reliability variables contribute within the rich set | C5 |

Controls (a real information set must beat its placebo; each placebo uses the same variables with the link to the firm destroyed):
- **C1** A5 - P0: A5 beats the permuted-block placebo (mean of five permutations)
- **C2** A5 - P0s: A5 beats the time-shifted placebo
- **C3** A6 - P1: A6 beats the permuted-block placebo (mean of five permutations)
- **C4** A6 - P2: A6 beats the time-shifted placebo
- **C5** A1 - P3: A1 beats the placebo for its two existing reliability variables (mean of five permutations)

Secondary, descriptive only (no adjustment, no claim): **S1** A4 - A0: the new block alone adds to the baseline; **S2** A3 - A0: the two existing variables alone add to the baseline; **S3** G2 - G1: a boosted learner gains from the new block (mean over three seeds).

## 7. Inference and decision rule

- Newey-West t with 4 lags (ceil(21/5) - 1) on the difference series, as in `ic_summary`; one-sided normal p; Holm across T1-T3.
- 95% interval by moving-block bootstrap over dates (block 6, 4000 draws, seed 20261012); fold counts of positive differences.
- **SUPPORTED** needs: mean difference > 0, Holm p < 0.05, at least 6 of 8 folds positive, and every mapped control with a positive mean difference.
  **FRAGILE**: Holm p < 0.05 but fewer folds or a placebo matches it. **NOT_SUPPORTED**: otherwise. Placebo fits use 5 permutation seeds averaged; the shift is 252 sessions.
- **Reference row N0 (pre-declared, no contrast, no adjustment).** The baseline's own 12-1 momentum rank (`mom_252_21_xs`), unfitted, scored on exactly the rows that A1 predicts (missing values
  scored 0), with the same Rank IC, Newey-West statistic and frozen portfolio at 10 bp as every other arm. It anchors the scale: does a fitted model beat the plainest signal in the set?
  Computed after the study by `docs/research/market-signal-review-2026-10-11/code/naive_reference.py` into `experiments/EXP-012/reference_naive.json`.
- Economics (the frozen EXP-010B 21-session portfolio at 10 bp, plus the recorded cost grid) are reported for every arm as exploratory. No inference is drawn from them and
  no result is labelled economic. The EXP-010A noise floor (Rank IC seed SD 0.00158, net Sharpe seed SD 0.0817) is the yardstick for the boosted arms.

## 8. Sensitivity: what the design can detect

A rehearsal of the complete pipeline (all 30 fits, the analysis and the saved artifacts) was run on the final code on 2026-10-12 with the label shuffled across firms within each
date (seed 20261012), so it carries no information about the hypotheses (`docs/research/market-signal-review-2026-10-11/validation/rehearsal_summary.json`). It completed in
1022 s with 6 workers, all 30 prediction files finite, the holdout state `SEALED` and untouched, and every verdict
NOT_SUPPORTED, as it must in a world with no signal. From the Newey-West t of each paired difference series in that run, the standard error of the mean
difference and the smallest effect each test could detect with 80% power (one-sided 5%; the strictest Holm step uses 5%/3) are:

| Test | Standard error of the mean paired Rank IC difference | Smallest detectable difference, single test | Smallest detectable difference, strictest Holm step |
|---|---|---|---|
| T1 | 0.00102 | 0.0025 | 0.0030 |
| T2 | 0.00231 | 0.0057 | 0.0068 |
| T3 | 0.00021 | 0.0005 | 0.0006 |

For comparison, EXP-011 found the whole set of 50 SEC-derived characteristics worth +0.0096 Rank IC to ridge. T1 could therefore detect a block worth about a quarter to a third of
that, T2 only an addition worth more than half of it, so T2 is weak by design and a null on T2 is weak evidence. T3 compares two sets that differ by two columns: its standard error is small and
so is the effect it can be expected to find.

## 9. Expected outcome, declared in advance

Given the information content in section 3 and the sensitivity above, the most likely result is NOT_SUPPORTED on T1 and T2. A supported T3 would replicate, inside a machine-learning
ranking, the reported value of filing timeliness (Bannouh et al.; Brooks et al.). Neither outcome changes the registered analysis, the stopping rule (there is none: the study is run once, in full) or the
reporting: every contrast, control and secondary contrast is reported whatever it shows.

## 10. Acceptance gates before any new result is read

1. Arms A0 and A1 reproduce EXP-011 E0 and E1 mean Rank IC to 1e-9. Enforced in code (`acceptance_checks`, unit-tested): the run aborts before any contrast is computed if either
   difference exceeds the tolerance. Confirmed on the unmodified pipeline on 2026-10-12 before registration (differences 3e-17 and 4e-17).
2. Every out-of-sample prediction is finite, and no decision date is later than 2025-05-09. Enforced in the same function.
3. The reliability table's sha256 equals its manifest (`attach_reliability`); the parent artifacts verify by hash; the holdout guard reports SEALED.

## 11. What would count as failing

Every confirmatory contrast not supported, or supported only by an arm that its own placebo reproduces, is a clear negative result and is reported as such. A null on T1-T3 with
a positive A4 - A0 would say the reliability variables carry information that the rich set already contains. Nothing here is a production candidate and nothing is promoted.

## 12. Not claimed

No claim of novelty beyond section 2; no claim about the sealed holdout; no claim about other universes, periods or horizons; no tuning of ridge alpha, the composite, the windows or the
placebos after this registration. The saved artifacts are research artifacts, not production models.

## 13. Outputs

`experiments/EXP-012/`: `definition.json`, `config.json`, `per_arm_metrics.csv`, `fold_metrics.csv`, `paired_tests.csv`, `metrics.json`, `manifest.json`, `reference_naive.json` (the pre-declared reference N0, written after the study), `checkpoints/` (predictions and receipts, git-ignored), `model/` (artifacts, git-ignored).

## 14. Reproduction

```bash
.venv/bin/python -m src.quant.pit.reliability build          # reliability table (seconds)
.venv/bin/python -m scripts.quant.exp012 fingerprint         # must equal the fingerprint above
.venv/bin/python -m scripts.quant.exp012 gate                # refuses unless registered and pushed
.venv/bin/python -m scripts.quant.exp012 run --workers 6     # the study
```

Apple silicon, 12 cores, Python 3.12, scikit-learn 1.7.2, pandas 2.3.3, numpy 2.2.6. Ridge arms take seconds; boosted arms minutes. `docs/research/market-signal-review-2026-10-11/09_REPRODUCIBILITY_PLAN.md` has the full chain.

## 15. Method files covered by the fingerprint

- `src/quant/pit/reliability.py`
- `src/quant/study/exp012.py`
- `src/quant/validation/runner.py`
- `src/quant/models/linear.py`
- `src/quant/models/trees.py`
- `src/quant/models/base.py`
- `src/quant/pit/rich_panel.py`
- `src/quant/backtest/engine.py`
- `src/quant/backtest/rules.py`
- `src/quant/study/exp010a.py`
- `src/quant/study/exp010b.py`
- `src/quant/study/exp011.py`
