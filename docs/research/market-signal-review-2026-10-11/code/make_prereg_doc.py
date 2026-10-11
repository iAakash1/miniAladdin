#!/usr/bin/env python3
"""Write docs/EXP_012_PREREGISTRATION.md from the live definition, so the document cannot disagree with the code it registers.

Run from the repository root after any change to a method file (the fingerprint changes with them):

    .venv/bin/python docs/research/market-signal-review-2026-10-11/code/make_prereg_doc.py

Inputs: src/quant/study/exp012.py (definition and fingerprint), data/manifests/reliability_v1_manifest.json, and two committed summaries under
docs/research/market-signal-review-2026-10-11/validation/ (the independent recomputation and the label-shuffled rehearsal). This script is not itself covered by
the fingerprint: the registered object is the document it writes and the method files it lists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from src.quant.study import exp012  # noqa: E402

VALIDATION = REPO / "docs/research/market-signal-review-2026-10-11/validation"


def main() -> None:
    fp = exp012.definition_fingerprint(REPO)
    manifest = json.loads((REPO / "data/manifests/reliability_v1_manifest.json").read_text())
    val = json.loads((VALIDATION / "reliability_validation.json").read_text())
    reh = json.loads((VALIDATION / "rehearsal_summary.json").read_text())
    se = reh["contrast_standard_errors_null_world"]
    methods = "\n".join(f"- `{m}`" for m in exp012.METHOD_SOURCES)
    arms = "\n".join(f"| {k} | {v['model']} | {v['note']} |" for k, v in exp012.ARMS.items())
    confirmatory = "\n".join(f"| {k} | {l} - {r} | {c} | {', '.join(exp012.PLACEBO_OF[k])} |" for k, (l, r, c) in exp012.CONFIRMATORY.items())
    controls = "\n".join(f"- **{k}** {l} - {r}: {c}" for k, (l, r, c) in exp012.CONTROLS.items())
    secondary = "; ".join(f"**{k}** {l} - {r}: {c}" for k, (l, r, c) in exp012.SECONDARY.items())
    sens_rows = "\n".join(f"| {k} | {v['standard_error']:.5f} | {v['mde_80pct_power_single_test']:.4f} | {v['mde_80pct_power_strictest_holm_step']:.4f} |" for k, v in se.items())
    doc = f"""# EXP-012 preregistration - disclosure-process reliability and the value of company information

Definition fingerprint: `{fp}`

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

- Panel: `{exp012.exp011.RICH_DATASET_ID}`, content hash `{exp012.exp011.RICH_CONTENT_HASH[:16]}...`, 139,292 rows, label `fwd_rank_21`, eight recorded folds, ridge alpha 10.
- Reliability source: `data/curated/sec_v3/filings.parquet` (the SEC Financial Statement Data Sets registry; 371,229 filings, sha256 `{manifest['inputs']['filings_sha256'][:16]}...`).
  SEC filings are public records; only derived counts are kept. `prevrpt` is never read.
- Reliability table `{manifest['version']}`: `data/research/derived/reliability_v1.parquet`, sha256 `{manifest['output']['sha256'][:16]}...`,
  {manifest['rows']:,} rows, {manifest['symbols']} ticker strings, {manifest['date_min']} to {manifest['date_max']} (before the holdout). Coverage: {', '.join(f'{k} {v:.1%}' for k, v in manifest['coverage'].items())}.
  Rows without a mapped CIK ({manifest['rows_without_cik']:,}) carry NaN, never zero.
- Availability: a filing is usable from the first session whose close-based decision may use it (`sec_facts.available_session`).
- Validation done before registration: nine unit tests (`tests/quant/test_reliability.py`), including that perturbing filings usable after day d
  cannot move any value at day d, and an independent recomputation of {val['sample_rows']:,} sampled rows by a naive code path with
  {sum(val['mismatch_counts'].values())} mismatches across the four variables (`docs/research/market-signal-review-2026-10-11/validation/`).
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
| `rel_u` (composite) | mean of the oriented cross-sectional ranks of `days_since_report`, `filing_lag_days`, `amended_730`, `lag_deterioration`, `periodic_count_400` (at least {exp012.U_MIN_COMPONENTS} present), ranked again within the date | larger |

Cross-sectional ranks use the repository's `cross_sectional_rank` (percentile in [-1, 1], centred), computed within each date.
Interactions are `int_<f> = f_xs * rel_u_xs` for the 48 fundamentals features.

## 5. Arms

| Arm | Model | Information set |
|---|---|---|
{arms}

## 6. Confirmatory contrasts (one-sided, Holm across the three)

Test statistic: the mean over dates of the paired difference of per-date Spearman rank ICs on identical dates. H0: the mean difference is zero or negative.

| Test | Contrast | Claim | Mapped controls |
|---|---|---|---|
{confirmatory}

Controls (a real information set must beat its placebo; each placebo uses the same variables with the link to the firm destroyed):
{controls}

Secondary, descriptive only (no adjustment, no claim): {secondary}.

## 7. Inference and decision rule

- Newey-West t with 4 lags (ceil(21/5) - 1) on the difference series, as in `ic_summary`; one-sided normal p; Holm across T1-T3.
- 95% interval by moving-block bootstrap over dates (block {exp012.BOOTSTRAP_BLOCK}, {exp012.BOOTSTRAP_DRAWS} draws, seed {exp012.BOOTSTRAP_SEED}); fold counts of positive differences.
- **SUPPORTED** needs: mean difference > 0, Holm p < 0.05, at least {exp012.SUPPORT_RULE['positive_folds_required']} of 8 folds positive, and every mapped control with a positive mean difference.
  **FRAGILE**: Holm p < 0.05 but fewer folds or a placebo matches it. **NOT_SUPPORTED**: otherwise. Placebo fits use {len(exp012.PERMUTATION_SEEDS)} permutation seeds averaged; the shift is {exp012.SHIFT_SESSIONS} sessions.
- **Reference row N0 (pre-declared, no contrast, no adjustment).** The baseline's own 12-1 momentum rank (`mom_252_21_xs`), unfitted, scored on exactly the rows that A1 predicts (missing values
  scored 0), with the same Rank IC, Newey-West statistic and frozen portfolio at 10 bp as every other arm. It anchors the scale: does a fitted model beat the plainest signal in the set?
  Computed after the study by `docs/research/market-signal-review-2026-10-11/code/naive_reference.py` into `experiments/EXP-012/reference_naive.json`.
- Economics (the frozen EXP-010B 21-session portfolio at 10 bp, plus the recorded cost grid) are reported for every arm as exploratory. No inference is drawn from them and
  no result is labelled economic. The EXP-010A noise floor (Rank IC seed SD 0.00158, net Sharpe seed SD 0.0817) is the yardstick for the boosted arms.

## 8. Sensitivity: what the design can detect

A rehearsal of the complete pipeline (all 30 fits, the analysis and the saved artifacts) was run on the final code on 2026-10-12 with the label shuffled across firms within each
date (seed 20261012), so it carries no information about the hypotheses (`docs/research/market-signal-review-2026-10-11/validation/rehearsal_summary.json`). It completed in
{reh['wall_seconds']:.0f} s with {reh['workers']} workers, all {reh['fits']} prediction files finite, the holdout state `{reh['holdout']['state']}` and untouched, and every verdict
{', '.join(sorted(set(reh['verdicts'].values())))}, as it must in a world with no signal. From the Newey-West t of each paired difference series in that run, the standard error of the mean
difference and the smallest effect each test could detect with 80% power (one-sided 5%; the strictest Holm step uses 5%/3) are:

| Test | Standard error of the mean paired Rank IC difference | Smallest detectable difference, single test | Smallest detectable difference, strictest Holm step |
|---|---|---|---|
{sens_rows}

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

{methods}
"""
    (REPO / "docs/EXP_012_PREREGISTRATION.md").write_text(doc)
    print("fingerprint", fp)


if __name__ == "__main__":
    main()
