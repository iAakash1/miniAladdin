# EXP-013 preregistration - which columns carry the EXP-012 T1 gain?

Definition fingerprint: `746182292afc9c80d4cb5cbc9af6c3605c3b8a71dd58ac88c63916f725a6beae`

Parent: EXP-012. Status: **EXPLORATORY - validation folds only - holdout sealed - promotion not assessed.** This document is committed and pushed to the research branch before any arm is fit; the
fingerprint is the SHA-256 of the canonical definition (`src/quant/study/exp013.py`, `DEFINITION`) and of the bytes of every method file in section 12. If the definition or a method file changes after
registration, the gate refuses to run.

## 1. Why this study, and what it is not

EXP-012 returned T1 SUPPORTED (adding six point-in-time columns to the rich set raised ridge Rank IC by +0.00515, Holm p 0.011) with caveats set out in `docs/EXP_012_RESULTS.md`: the gain is negative in the last two
validation years, the shifted placebo keeps about half of it, the boosted model gains nothing, and the six columns are not equal (four are ranks of filing-process variables, one is a count of missing fundamentals,
one is a composite that contains two variables already in the rich set). The question of which of them the gain depends on decides whether T1 is about disclosure behaviour or about something else. This study asks only that.

It is **not** a confirmation of T1, makes no claim of new alpha, and does not use the holdout. The eight folds have been looked at by EXP-006 to EXP-012 (1,029 trials were already on the ledger); this adds
34 ridge fits (16 arms and 18 placebo fits), 3 adjusted contrasts and 22 descriptive ones, and is counted as one more look.

Disclosed before registration: the coefficients of the final EXP-012 A5 model (fitted on all pre-holdout rows) were read. In absolute size the composite ranks 3rd of 82, lateness deterioration 4th, periodic-report
count 14th, amendments in two years 18th, missing-fundamentals count 36th and latest-report-amended 47th. These are in-sample coefficients of a collinear ridge model, not out-of-sample evidence.

## 2. Data

No new data. The frozen rich panel `ds-richpit-ff3d3f556488b7da`, the label `fwd_rank_21`, the eight recorded folds, ridge alpha 10, the EXP-012 reliability table `reliability-v1` (verified by hash before the
run), and the EXP-012 code for placebos and paired inference.

## 3. Arms

All ridge, alpha 10, deterministic. B1 and B5 reproduce EXP-012's A1 and A5 and are gates. Placebo arms replace the named columns of the corresponding add arm with a within-date permutation across firms
(five seeds, averaged) or a 252-session shift within each firm.

| Arm | Features | Description |
|---|---|---|
| B1 | 76 | EXP-012 A1 (rich set), reproduction |
| B5 | 82 | EXP-012 A5 (rich set plus all six columns), reproduction |
| C_amended | 77 | rich set plus rel_amended_730_xs only |
| D_amended | 81 | rich set plus all six columns except rel_amended_730_xs |
| C_latest | 77 | rich set plus rel_latest_amended_xs only |
| D_latest | 81 | rich set plus all six columns except rel_latest_amended_xs |
| C_count | 77 | rich set plus rel_periodic_count_xs only |
| D_count | 81 | rich set plus all six columns except rel_periodic_count_xs |
| C_lagdet | 77 | rich set plus rel_lag_deterioration_xs only |
| D_lagdet | 81 | rich set plus all six columns except rel_lag_deterioration_xs |
| C_missing | 77 | rich set plus rel_missing_xs only |
| D_missing | 81 | rich set plus all six columns except rel_missing_xs |
| C_u | 77 | rich set plus rel_u_xs only |
| D_u | 81 | rich set plus all six columns except rel_u_xs |
| C_P | 80 | rich set plus the four filing-process ranks |
| D_P | 78 | all six columns except the four filing-process ranks |
| XPperm | 80 | C_P with the four filing-process ranks permuted across firms within each date (5 fits) |
| XPshift | 80 | C_P with the four filing-process ranks shifted 252 sessions within each firm |
| XMperm | 77 | C_missing with the missing-fundamentals count permuted across firms within each date (5 fits) |
| XMshift | 77 | C_missing with the missing-fundamentals count shifted 252 sessions within each firm |
| XUperm | 77 | C_u with the composite unreliability rank permuted across firms within each date (5 fits) |
| XUshift | 77 | C_u with the composite unreliability rank shifted 252 sessions within each firm |

## 4. Contrasts

Descriptive family, adjusted together with Holm (the only adjustment; the rest are descriptive and unadjusted): what each group adds to the rich set.

| Contrast | Difference |
|---|---|
| G_P | C_P - B1 |
| G_M | C_missing - B1 |
| G_U | C_u - B1 |

Descriptive: each group against its permuted and shifted placebo (`P_vs_perm`, `P_vs_shift`, and likewise for M and U); each group's removal from B5 (`P_drop`, `M_drop`, `U_drop`); each single column added
(`add_<name>`) and removed (`drop_<name>`); and the total (B5 - B1). Groups: P the four filing-process ranks, M the missing-fundamentals count, U the composite.

## 5. Attribution rule (fixed before any result)

- **gain**: the EXP-012 T1 gain, IC(B5) - IC(B1); if it is not positive nothing is attributed and every group is labelled NO_GAIN
- **add_share**: (IC(add arm) - IC(B1)) / gain
- **drop_share**: (IC(B5) - IC(drop arm)) / gain
- **CARRIES**: resolvable, add_share >= 0.5, drop_share >= 0.5, both placebos beaten (positive mean difference), the permuted-placebo difference has one-sided p < 0.10, and the add arm beats B1 in at least 6 of 8 folds
- **SHARES**: resolvable and not CARRIES, with add_share >= 0.25 or drop_share >= 0.25
- **NOT_CARRYING**: otherwise (including groups whose contribution is too small to resolve; low power is a possible reason and is not distinguished from absence)
- **note**: descriptive labels; the groups overlap through collinearity, so shares need not sum to one; no confirmatory claim is made

## 6. Inference

The same as EXP-012: mean over dates of the paired difference of per-date Spearman Rank ICs; Newey-West with 4 lags; one-sided normal p; 95% moving-block bootstrap interval (block 6,
4000 draws, seed 20261012); positive-fold counts. Economics (the frozen portfolio at 10 bp) are reported for every arm as exploratory and carry no inference.

## 7. What this design can resolve

In EXP-012 the realised standard errors of the paired differences were 0.0019 (T1), 0.0024 (T2) and 0.0017 (T3). At about 0.002 per contrast, the smallest difference detectable with
80% power is 0.0048 for a single test and 0.0057 at the strictest Holm step. The whole T1 gain is +0.00515, so the per-column contributions (a few thousandths at most) are below what a single descriptive contrast
can resolve: **a NOT_CARRYING label may reflect low power and not absence.** The labels are a way of reading the table, not tests.

A rehearsal of the whole pipeline (all 34 fits and the analysis) on a label shuffled across firms within each date (seed 20261012) completed in 86 s with every prediction finite and every group
labelled NOT_CARRYING, as it must in a world with no signal (`docs/research/market-signal-review-2026-10-11/validation/rehearsal_summary_013.json`). The same rehearsal showed why the rule
needs the resolvability condition: the unconditional shares of the noise gain reached 0.86 by chance, and a first draft that labelled on shares alone returned SHARES for two groups.

## 8. Expected outcome, declared in advance

Reading the coefficients above, the prior expectation is that the composite (U) and the lateness deterioration (within P) carry most of the gain, the missing-fundamentals count (M) little, and the amendment ranks almost
none, because those are nearly constant. A CARRIES for U would indicate that the gain largely re-weights the lateness and staleness information already in the rich set and studied in the timeliness literature; a
CARRIES for M would indicate a coverage or age proxy; no CARRIES at all would indicate that the gain is spread across the block or arises from combinations of columns. None of these changes the registered analysis.

## 9. Acceptance gates before any contrast is computed

1. B1 and B5 reproduce EXP-012's A1 and A5 mean Rank IC to 1e-9 (enforced in code, unit-tested; the run aborts otherwise).
2. Every out-of-sample prediction is finite; no decision date is later than 2025-05-09.
3. The reliability table's sha256 equals its manifest; the parent artifacts verify by hash; the holdout guard reports SEALED.

## 10. Not claimed

No confirmation of T1; no claim about the holdout, other universes or horizons; no tuning of any parameter after this registration; nothing promoted. The labels are descriptive.

## 11. Outputs and reproduction

`experiments/EXP-013/`: `definition.json`, `config.json`, `per_arm_metrics.csv`, `fold_metrics.csv`, `paired_tests.csv`, `attribution.json`, `manifest.json`, `checkpoints/` (git-ignored).

```bash
.venv/bin/python -m scripts.quant.exp013 fingerprint        # must equal the fingerprint above
.venv/bin/python -m scripts.quant.exp013 gate               # refuses unless registered and pushed
.venv/bin/python -m scripts.quant.exp013 rehearse           # whole pipeline on a label shuffled within date (no result)
.venv/bin/python -m scripts.quant.exp013 run --workers 6    # the study
```

## 12. Method files covered by the fingerprint

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
- `src/quant/study/exp013.py`
