# EXP-011 — rich point-in-time data value (results summary)

Status: **COMPLETE, immutable.** Validation-period evidence only. **Promotion NOT ASSESSED; nothing promoted.** Holdout (2025-08-26 → 2026-08-28): **untouched**
(`"touched": false`, firewall state `SEALED`). Preregistration: [EXP_011_PREREGISTRATION.md](EXP_011_PREREGISTRATION.md) (commit `679596a`, fingerprint
`d5dd80d26131641efd8d3deda3526680fc08c8578957e69e7600ee53e6f4d9aa`). Outputs: `experiments/EXP-011/` (recorded in commit `bf6ee12`; run on a clean tree at
`926660d`, 6 workers, 1,769 s wall time). This document only summarises those files; nothing was recomputed, re-fitted or altered in writing it.

## 1. Question

Does a richer, genuinely point-in-time company information set improve **cross-sectional ordering** beyond the 26-feature price/liquidity/macro baseline,
with the target, folds, model classes, imputation and downstream portfolio held fixed?

## 2. Registered design

A 2×2 crossing two feature sets with two model classes, so data value is isolated before model complexity. Target `fwd_rank_21`; the eight recorded EXP-006
folds; `FoldImputer` fitted inside each training fold; no hyper-parameter search; no other model; economics from the frozen EXP-010B 21-session (B1)
implementation, 10% dropout, half-spread grid 1/3/5/10/20 bp. The interpretation rule is ordering-only and was fixed before any result existed (§18).

## 3. Arms

| Arm | Features | Model | Fits | Source |
|---|---|---|---|---|
| **E0** | baseline 26 | Ridge, alpha 10.0 | 1 deterministic fit per fold | fitted |
| **E1** | baseline 26 + 50 PIT = 76 | Ridge, alpha 10.0 | 1 deterministic fit per fold | fitted |
| **E2** | baseline 26 | `GradientBoostingRegressor` (frozen EXP-010A settings) | seeds 0–9 | the ten frozen EXP-010A predictions, hash-verified, not refit |
| **E3** | 76 | `GradientBoostingRegressor` (same settings) | seeds 0–9 | fitted |

## 4. Dataset identity

`ds-richpit-ff3d3f556488b7da`, content hash `ff3d3f556488b7daa20bbbeab49d1f0abad9a869976b593f211cf92b6eb7c5da`, feature-list hash
`7212297bc55a45f66ffceb3548000e899773e1959e365b266fb477f24d8b8614`, baseline-values hash `f48c47f02da6407e060ca52ff1745935a99c0898fa5a7ce3fa6df3c5d7d5906e`.
139,292 in-universe name-dates, 762 securities, 2014-04-03 → 2025-05-09; every panel check in the manifest is `true`. Each arm produced 100,246 predictions
over 404 dates and 8 folds. Immutable output hashes are in §22.

## 5. The 76-feature panel

26 unchanged baseline features plus 50 documented PIT characteristics: profitability 11, investment 8, value 8, leverage 6, growth 6, quality 5, capital
structure 3, event 3 (`docs/PIT_FEATURE_CATALOG.md`). Computed at each filing's acceptance time from as-reported SEC facts (`sec-core-facts-v3`), cross-sectionally
ranked among names with a value. The seven CONTROL features (size, industry-relative) were **withheld** because `security_master_pit = false`. Mean coverage
of the new features is about 67.7%; 88.7% of prediction rows (88,949 of 100,246) have at least 20 of them and a trusted identity (§11).

## 6. Primary ordering results (mean Rank IC over 404 dates)

| Arm | Mean Rank IC | HAC t (4 lags) | ICIR | Positive folds | Worst fold IC |
|---|---:|---:|---:|---:|---:|
| E0 Ridge, baseline | 0.00533 | 0.36 | 0.029 | 6 / 8 | −0.0583 |
| E1 Ridge, rich | 0.01488 | 1.35 | 0.110 | 7 / 8 | −0.0616 |
| E2 boosted, baseline (10 seeds) | 0.03222 (SD 0.00158) | 2.92 | 0.219 | 6.1 | −0.0152 |
| E3 boosted, rich (10 seeds) | 0.03167 (SD 0.00179) | 2.83 | 0.234 | 6.7 | −0.0419 |

Two things to read together: the rich features raise the *Ridge* model's ordering, yet the rich Ridge (0.0149) remains far below the frozen boosted baseline
(0.0322); and the *boosted* model does not gain from them.

## 7. Linear pair: E1 − E0 (rich vs baseline, Ridge)

ΔIC = **+0.00955** = **2.30** EXP-010A Rank-IC p95−p05 ranges = **6.04** EXP-010A seed SDs. Positive in **6 of 8** folds. Preregistered status:
**`IMPROVES`** (ΔIC ≥ 0.004156 and > 0 in ≥ 5 of 8 folds). Prediction rank correlation E1–E0: 0.418. Ridge is deterministic, so this is **one** fit per fold with no seed
distribution; the EXP-010A SDs (a boosting reseed measure) are only a descriptive yardstick here, not a Ridge noise floor.

## 8. Boosted pair: E3 − E2 (rich vs baseline, gradient boosting, per seed)

Median ΔIC **−0.00076**, mean −0.00055 (SD 0.00218, range −0.00448 to +0.00185); positive in **4 of 10** seeds, negative in 6. Relative to EXP-010A noise: median
**−0.18** ranges, **−0.48** seed SDs. Preregistered status: **`NO_DETECTABLE_CHANGE`** (a gain needed median ΔIC ≥ 0.004156 with ≥ 9 of 10 seeds positive; a loss the
mirror). The HAC t-statistic fell in 7 of 10 seeds. Worst-fold IC deepened in 10 of 10 seeds (−0.0152 → −0.0419 on average). Prediction rank correlation E3–E2: 0.355–0.375
(mean 0.366), i.e. the new features changed the boosted predictions substantially without improving their ordering.

## 9. Fold-by-fold ΔIC (rich − baseline)

| Fold (validation window) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Linear** E1 − E0 | +0.0670 | +0.0052 | +0.0574 | +0.0024 | **−0.0985** | +0.0257 | −0.0011 | +0.0158 |
| **Boosted** E3 − E2, seed median | +0.0534 | −0.0057 | +0.0309 | −0.0310 | −0.0362 | +0.0155 | −0.0200 | −0.0168 |
| Boosted seeds positive (of 10) | 10 | 3 | 10 | **0** | **0** | 10 | **0** | **0** |
| EXP-010A mean fold IC (context) | −0.0146 | +0.0402 | +0.0545 | +0.0315 | −0.0074 | +0.0324 | +0.0396 | +0.0811 |

The linear gain is positive in six folds but includes **one very adverse fold** (fold 4, −0.0985, the 2021-05 → 2022-05 window) and a marginally negative fold 6. The boosted
pair is better in folds 0, 2 and 5 in every seed and **worse in folds 3, 4, 6 and 7 in every seed**; only 3 of 8 folds have a positive seed-median. Fold ICs are means of
about 50 dates and are noisy; they are context, not tests.

## 10. Leave-one-fold-out

*Boosted (recorded in `metrics.json`; the preregistered robustness input):* the seed-median ΔIC with each fold removed is −0.0093, +0.0001, −0.0048, +0.0039, +0.0042, −0.0032, +0.0014, +0.0020 (fold 0 → 7 removed).
Not every value is positive and only 3 of 8 fold medians are positive, so **`boosted_fold_robust = false`**.

*Linear (derived here by arithmetic on the recorded fold ΔICs; approximate, because folds are treated as equal-weight; not part of the preregistered rule):* the mean fold ΔIC is +0.0092;
with each fold removed it is +0.0010, +0.0098, +0.0024, +0.0102, +0.0246, +0.0069, +0.0107, +0.0083. **Removing fold 0 leaves +0.0010 and removing fold 2 leaves +0.0024, both below the 0.004156 range**:
the linear improvement is concentrated in folds 0 and 2. This does not change the preregistered label; it limits how far the label can be read.

## 11. Covered-subset diagnostic (rows with ≥ 20 of the 50 new features and a trusted identity; 88,949 of 100,246 rows, the same rows for every arm)

| Arm | Rank IC, covered rows | | Rank IC, all rows |
|---|---:|---|---:|
| E0 | 0.00195 | | 0.00533 |
| E1 | 0.01444 | Δ +0.01249 | 0.01488 |
| E2 | 0.03418 | | 0.03222 |
| E3 | 0.02818 | Δ **−0.00599**, negative in 10 of 10 seeds | 0.03167 |

The Ridge gain survives on covered rows (+0.0125). For the boosted pair the gap is *larger* on covered rows (−0.0060, all ten seeds negative) than on all rows (−0.0006): where the new features actually exist, the rich boosted model ordered
worse than the baseline boosted model, so the null boosted result is not an artefact of missing data diluting a real gain.

## 12. Prediction rank correlations

E1–E0 **0.418**. E3–E2 by seed: 0.375, 0.359, 0.355, 0.370, 0.366, 0.370, 0.372, 0.360, 0.368, 0.364.

## 13. Portfolio economics (descriptive; **not** part of the classification)

Frozen EXP-010B B1 implementation, 10 bp primary. Boosted arms are means over ten seeds; Ridge arms are single fits.

| Arm | Net Sharpe | Gross Sharpe | Annualised turnover | Net max drawdown | Cost share of gross | Net CAGR |
|---|---:|---:|---:|---:|---:|---:|
| E0 Ridge, baseline | +0.035 | +0.082 | 2.216 | −0.316 | 0.573 | −0.5% |
| E1 Ridge, rich | **−0.343** | −0.256 | 2.292 | −0.316 | n/a (gross return negative) | −3.0% |
| E2 boosted, baseline | **+0.641** (SD 0.142) | +0.699 | 2.332 | −0.117 | 0.088 | +7.5% |
| E3 boosted, rich | **+0.493** (SD 0.062) | +0.555 | 2.287 | −0.185 | 0.113 | +5.1% |

Net Sharpe by half-spread (E0 / E1 / E2 / E3): 1 bp +0.063 / −0.291 / +0.676 / +0.530; 3 bp +0.056 / −0.303 / +0.668 / +0.522; 5 bp +0.050 / −0.314 / +0.660 / +0.514; 10 bp +0.035 / −0.343 / +0.641 / +0.493;
20 bp +0.004 / −0.400 / +0.602 / +0.452.

**The rich boosted model did not improve downstream economics.** E3 − E2: net Sharpe median −0.150 (mean −0.148, ≈ −1.8 EXP-010A seed SDs), worse in 8 of 10 seeds; gross Sharpe worse in 9 of 10; net drawdown deeper in 10 of 10;
turnover essentially unchanged (−0.046). **The Ridge ordering gain did not carry into economics either:** E1 − E0 net Sharpe −0.378 and gross Sharpe −0.337, from a weak baseline. A stronger Ridge Rank IC therefore does not erase — and
here runs opposite to — the economic picture; ordering by mean Rank IC and top/bottom-quintile economics are different measurements. E2 reproduces the EXP-010B B1 result (mean net Sharpe 0.641).

## 14. Comparison with the EXP-010A noise floor

| Quantity | EXP-010A scale | EXP-011 effect | In noise units |
|---|---|---|---|
| Rank IC | seed SD 0.001583; p95−p05 0.004156 | linear ΔIC +0.00955 | +6.04 SDs; +2.30 ranges |
| Rank IC | as above | boosted median ΔIC −0.00076 | −0.48 SDs; −0.18 ranges |
| Net Sharpe @10 bp | seed SD 0.081651; p95−p05 0.219416 | boosted median Δ −0.150 | ≈ −1.8 SDs; ≈ −0.68 ranges (descriptive; economics are never labelled) |

The boosted ordering change is well inside reseed noise; the linear change is far outside it, but Ridge has no reseed distribution and the yardstick belongs to a different model class.

## 15. Numerical warning audit

The Ridge runs (E0/E1) repeatedly emitted `RuntimeWarning`s ("divide by zero", "overflow" and "invalid value encountered in matmul"). Numerical RuntimeWarnings were emitted by the underlying matrix-multiplication path on this
environment. Post-run audits confirmed all stored predictions, model coefficients and transformed feature matrices used in evaluation were finite. The warnings therefore did not result in discarded or non-finite predictions, but remain an
environment caveat.

What was checked, and by whom: (a) **verified again while writing this document, read-only, from the stored prediction files:** all 12 files (E0, E1, and E3 seeds 0–9) contain 100,246 of 100,246 finite predictions, with 0 NaN, 0 +Inf and 0 −Inf; and
(b) **reported by the post-run audit** (its script and outputs are not stored in `experiments/EXP-011/`, and it was not re-executed here because that would mean refitting): for every fold, in-sample and validation Ridge predictions were finite; the maximum absolute
Ridge coefficient was about 0.02–0.058; standardised features were finite, the largest validation z-score being about 55.6 for `market_vol_21` in fold 2. A date-constant market feature shifts every name's prediction equally on a given date and so
cannot change within-date ranks in exact arithmetic; this is an observation about the model form, not an explanation of the warnings' origin. No upstream NumPy/BLAS issue is cited and none is claimed as the cause. The warnings are preserved here rather than suppressed.

## 16. PIT and security-master limitations

`security_master_pit = false` (trusted identity 91.8–95.0% by fold against a preregistered 95%); size and industry controls were withheld; foreign 10-K/10-Q-less issuers (4.2–7.1% of name-dates by fold) and delisted names whose identity cannot be recovered have no
new features; names about to exit are less often resolved (trusted 85.3% vs 93.6%, on 109 exiting rows), so missingness is weakly informative about delisting; share counts use a labelled weighted-average proxy where no cover-page or balance-sheet count exists; ALFRED macro vintages are
`BLOCKED_EXTERNAL_FRED_KEY`; universe, survivorship and pre-2017 delisting caveats of the frozen dataset apply. Details: `docs/PIT_SECURITY_MASTER_STATUS.md`, `docs/RICH_PIT_PANEL_AUDIT.md`.

## 17. Holdout status

The sealed holdout (2025-08-26 → 2026-08-28) was not read, scored or used; the panel ends 2025-05-09; the manifest records `"holdout": {"touched": false}` with state `SEALED`. This close-out read only the recorded outputs.

## 18. Interpretation (preregistered rule, applied mechanically)

Boosted pair `NO_DETECTABLE_CHANGE`; linear pair `IMPROVES`; boosted not fold-robust → label **`IMPROVES_ONLY_LINEAR`** (`economics_labelled: false`, `best_seed_selected: false`, `promotion: NOT ASSESSED`).
The registered 50-feature PIT extension produced a detectable cross-sectional ordering improvement under the preregistered Ridge specification, but no detectable ordering gain under the frozen `GradientBoostingRegressor` specification, and it did not improve downstream economics for either model class.

## 19. What can be claimed

* Under Ridge alpha 10.0 on these folds, adding these 50 PIT characteristics raised mean Rank IC from 0.0053 to 0.0149, positive in 6 of 8 folds, by more than the EXP-010A reseed range.
* Under the frozen boosting settings, the same features produced no detectable ordering change (median ΔIC −0.0008, 4 of 10 seeds positive), a worse covered-subset IC in 10 of 10 seeds, and lower validation economics than the frozen baseline.
* The results are conditional on this feature construction, this universe and sample, these folds and the coverage limits in §16.

## 20. What cannot be claimed

* That fundamentals (or richer data) improve prediction in general, or improve all models.
* That the rich features are useful to the model that performs best (they did not help it), or that the rich Ridge is a candidate: it sits far below the baseline boosted model in ordering and lost money in validation economics.
* That the linear gain is uniform: it is concentrated in folds 0 and 2 and reverses sharply in fold 4.
* That OmniSignal is profitable, that any portfolio has expected returns, or anything about the sealed holdout.
* That a null boosted result shows fundamentals carry no information: it shows these 50 characteristics, on this sample, added none the frozen boosting model could exploit.
* That the numerical warnings are definitively harmless for a known upstream reason.

## 21. Promotion status

**NOT ASSESSED for every arm.** No model, feature set or portfolio is promoted; no seed is selected; the holdout remains sealed. The next-step decision is recorded separately in `docs/NEXT_RESEARCH_DECISION_2026.md` and is not made here.

## 22. Immutable artifact hashes (SHA-256)

| File | SHA-256 |
|---|---|
| `definition.json` | `1558a14ee1d0bc003a00f90c06622bb5efcfa5410ff23a3cef85ed0420bc0b80` |
| `config.json` | `0bfb44b3da97d8720be075f18e8c2a4f38b847097162bbfa5948d7154905892b` |
| `manifest.json` | `8e0ba944ed056f94413b485ce93fe955b0186ec1d295c0b495124b464aaa5ec0` |
| `metrics.json` | `b3afb10c277ef16237a0d6e9b937e3bed746da42d7ed05647287e56df256d7f3` |
| `per_arm_metrics.csv` | `47b0c80cef7578f8e07ae0d43c887f247a41335fb08c1e8c3350475122fab1ba` |
| `fold_metrics.csv` | `2ce90f4c2db82a0e886a11c556fd363469a13e087f53ea71b46335114568f868` |
| `paired_differences.csv` | `d42e6962eed5bf240ff9d80539f9ad8d2b96fc6635027761f4d62bbc9f4c0510` |
| `prediction_hashes.json` | `a7b8117debee8fd393593d90a5df4eb0509b4b59f2b01b6020fa5abbf5b43416` |

Per-arm/seed prediction hashes are in `prediction_hashes.json`; the prediction files are local and git-ignored.
