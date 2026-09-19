# EXP-009 results

Running record of the EXP-009 program. Each section is written after its run and
is not edited afterwards except to append a dated correction. Everything is
**EXPERIMENTAL — PROMOTION NOT ASSESSED**; the sealed holdout
(2025-08-28 → 2026-08-28) has not been read, scored or used for any decision.
The final synthesis is in `docs/EXP_009_FINAL_ANALYSIS.md` when complete.

| Study | Status | Preregistration |
|---|---|---|
| **EXP-009A** turnover-aware portfolio construction | **Executed 2026-09-19** | `docs/EXP_009A_TURNOVER_PREREGISTRATION.md`, commit `155e976` (pushed before execution) |
| **EXP-009B** ranking objective vs matched point-regression control | **Executed 2026-09-19** | `docs/EXP_009B_LTR_PREREGISTRATION.md`, commit `d633b1b` (pushed before execution) |
| **EXP-009C** analyst-revision arm (BASE vs BASE + 8 PIT analyst features) | **Executed 2026-09-19** | `docs/EXP_009C_ANALYST_PREREGISTRATION.md`, commit `47d6f67` (pushed before execution) |

---

## EXP-009A — turnover-aware portfolio construction on frozen EXP-006 predictions

### What was run

The frozen 100,246 out-of-sample gradient-boosting predictions were turned into
books by five constructions and traded through the unchanged backtest engine and
cost model (10 bp half-spread primary; 1/3/5/10/20 bp sweep): the immediate-
replacement **control**, two **rank-hysteresis** widths (Novy-Marx & Velikov
sS rule), **top-k dropout** (10% drop budget), and a **4-rebalance minimum hold**.
No model was refit, no prediction altered.

* Run at commit `155e976` (`git_dirty: false`), Python 3.12.11 and the project
  `.venv` (numpy 2.2.6, scipy 1.18.1 — the versions EXP-006 recorded), 12 CPUs,
  121.6 s wall, seed 0, 10,000 bootstrap draws, 160 cumulative trials counted for
  deflation.
* **Validity gate passed:** the control reproduced all eight recorded EXP-006
  numbers to relative 1e-9 (periods 403; turnover 20.14859; gross Sharpe 0.38444;
  net Sharpe −0.10218; cost share 1.26607; …). The rebuilt returns panel matched
  EXP-006's labels on all 404 dates.
* **Holdout untouched:** firewall engaged (contract NOT ARMED), window
  2025-08-28 → 2026-08-28, `touched: false`, 0 breaches, 0 overrides.
* Outputs: `experiments/EXP-009A/` — `definition.json`, `manifest.json`,
  `metrics.json`, `summary.parquet`, per-cell `periods_*.parquet` and
  `membership_*.parquet`, `turnover_diagnostics.json`, and the post-hoc
  `robustness_exploratory.json`. (`exp009a.py` gained `run_robustness` after the
  run; the manifest's `module_sha256` is the version that executed.)

### Headline (net of costs at a 10 bp half-spread)

| Cell | Ann. one-way turnover | vs control | Gross Sharpe | Net Sharpe | Net CAGR | Cost share of gross | Net max DD | Break-even half-spread |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A** control (immediate) | 20.15 | 1.000 | 0.384 | −0.102 | −2.21% | 127% | −28.8% | 6.6 bp |
| B 20/30 hysteresis | 15.84 | 0.786 | 0.328 | −0.082 | −1.69% | 125% | −25.5% | 6.9 bp |
| B 20/40 hysteresis | 12.84 | 0.637 | 0.320 | −0.032 | −0.97% | 110% | −21.9% | 8.6 bp |
| **C** top-k dropout (10%) | **6.90** | **0.342** | 0.541 | **+0.390** | **+4.69%** | **28%** | **−14.3%** | **50.2 bp** |
| D minimum hold (4) | 11.58 | 0.575 | 0.546 | +0.286 | +3.02% | 48% | −14.3% | 26.4 bp |

Net Sharpe across the cost sweep:

| Cell | 1 bp | 3 bp | 5 bp | 10 bp | 20 bp |
|---|---:|---:|---:|---:|---:|
| A control | +0.169 | +0.108 | +0.048 | −0.102 | −0.403 |
| B 20/30 | +0.154 | +0.101 | +0.049 | −0.082 | −0.343 |
| B 20/40 | +0.175 | +0.129 | +0.083 | −0.032 | −0.261 |
| C | +0.477 | +0.458 | +0.438 | **+0.390** | **+0.293** |
| D | +0.443 | +0.408 | +0.373 | +0.286 | +0.112 |

### Preregistered criteria and classification

| Cell | T1 turnover ratio (≤0.70) | T2 gross retention (≥0.75) | T3 net-Sharpe bootstrap lower bound (>0) | T4 folds improved (≥6/8) | Classification |
|---|---|---|---|---|---|
| B 20/30 | 0.786 — fail | 0.771 — pass | −0.071 — fail | 5/8 — fail | **INSUFFICIENT_TURNOVER_CUT** |
| B 20/40 | 0.637 — pass | **0.696 — fail** | −0.049 — fail | 5/8 — fail | **EDGE_LOST** |
| C top-k 10% | 0.342 — pass | 1.497 — pass | **+0.176 — pass** | 7/8 — pass | **MECHANISM_CONFIRMED** |
| D min-hold 4 | 0.575 — pass | 1.413 — pass | −0.013 — fail (narrowly) | 6/8 — pass | **NO_RELIABLE_NET_GAIN** |

Per the preregistered carry-forward rule, **C_topk_dropout_10 is the mechanism
frozen for EXP-009B/C.** Nothing is promoted.

### Where the net gain comes from (paired, versus control)

| Cell | Δ net, bp/period (HAC t) | Δ gross, bp/period (HAC t) | Δ cost, bp/period (HAC t) | Δ net Sharpe [95% bootstrap CI] |
|---|---:|---:|---:|---:|
| B 20/30 | +0.76 (+0.59) | −2.34 (−1.82) | −3.10 (−45.0) | +0.021 [−0.060, +0.121] |
| B 20/40 | +2.01 (+1.11) | −3.11 (−1.71) | −5.12 (−49.1) | +0.071 [−0.034, +0.228] |
| C | +13.73 (+2.41) | +5.07 (+0.89) | −8.65 (−37.7) | +0.492 [+0.209, +0.844] |
| D | +10.27 (+1.50) | +4.22 (+0.61) | −6.06 (−32.9) | +0.388 [+0.021, +0.798] |

* **The cost saving is real and mechanical** (t ≈ −33 to −49 for every cell; it
  could not have been otherwise, which is why cost is not a criterion by itself).
* **The gross difference is not statistically distinguishable from zero for any
  cell** (|t| ≤ 1.8). For C and D the point estimate is *positive*
  (+5.1 and +4.2 bp/period); for B it is negative (−2.3 and −3.1).
  What the data support is "**no evidence the gross edge was lost**" for C and D
  and "**some evidence it was partly lost**" for B — not "gross edge improved".
* Net improvement of C over the control is significant after the family
  correction (bootstrap lower bound +0.176), largely because ~63% of the
  13.7 bp gain is the cost saving.

### Robustness (post-hoc, exploratory — labelled as such, changes no classification)

`experiments/EXP-009A/robustness_exploratory.json`.

* **Which leg.** Long-leg contribution: control 24.6 bp/period, C 28.7, D 28.7,
  B40 21.3; short leg (negative is a cost): control −14.3, C −13.4, D −14.3, B40
  −14.2. The C/D gross gain is mostly in the long leg.
* **Two thin dates (2019-09-17, 2020-02-17) do not matter:** excluding them the
  gross ratio to control is 1.52 (C) and 1.61 (D); net Sharpe C 0.37, D 0.33.
* **One fold does matter.** Fold 5 (2022-05-05 → 2023-05-04) carries the
  gross-gain headline: C earns 65.3 bp/period gross there against the control's
  14.4, and it supplies 54% of C's total net gain. **Excluding fold 5, C keeps
  84% of the control's gross return (gross Sharpe 0.443 vs 0.501) and D keeps
  89% (0.592 vs 0.501); net Sharpe C 0.205, D 0.111, control −0.183, B40 −0.028.**
  So "gross edge retained" survives the exclusion (C and D still clear the 0.75
  bar); "gross edge increased by 50%" does not.
* **Fold-by-fold (net Sharpe), control vs C:**

| Fold | Period | Control | C |
|---:|---|---:|---:|
| 0 | 2017-05 → 2018-05 | −1.21 | −0.68 |
| 1 | 2018-05 → 2019-05 | +0.97 | +0.96 |
| 2 | 2019-05 → 2020-05 | −0.51 | −0.02 |
| 3 | 2020-05 → 2021-05 | +0.71 | +1.34 |
| 4 | 2021-05 → 2022-04 | −1.84 | −1.36 |
| 5 | 2022-05 → 2023-05 | +0.05 | +0.96 |
| 6 | 2023-05 → 2024-05 | −0.48 | −0.04 |
| 7 | 2024-05 → 2025-05 | +0.48 | +1.07 |

  C improves the net mean in 7 of 8 folds and lowers the loss in the bad ones,
  but it is **not** positive in every fold (folds 0, 2, 4, 6 remain ≤ 0) and
  fold 4 is still −1.36.
* **Exposure and holdings.** Gross exposure 0.999 and net exposure 0.000 in every
  cell. C keeps breadth identical to the control (49.5 names per leg) and holds
  names for a mean 7.4 rebalances (control 2.5); it replaces 13% of names per
  rebalance (control 40%). B and D widen the book (65 and 71 names per leg). The
  mean predicted percentile of longs falls from 0.90 (control) to 0.81 (C) and
  0.77 (D): the retained names sit deeper in the ranking, yet gross return did
  not fall — an observation this study does not explain.
* **Capacity proxy.** p95 participation at $1M is ≤ 0.008% of daily dollar
  volume in every cell; scaling to 1% p95 participation would take ≥ $130M. The
  constraint at this scale is cost, not liquidity.

### What this does and does not establish

**Established (in this frozen sample):**
1. Turnover can be cut by roughly two thirds (C) without any measurable loss of
   gross edge; a 4-week minimum hold cuts it 43% likewise.
2. The literature-anchored buffer (Novy-Marx & Velikov sS rule, 2:1) was **not**
   the answer here: it removed 36% of turnover but cost ≈30% of gross return
   (EDGE_LOST), and net stayed negative.
3. Cost fragility is gone for C: break-even half-spread rises from 6.6 bp to
   50 bp, and net Sharpe stays positive at 20 bp.

**Not established:**
1. That the signal became stronger. The model, and its Rank IC of 0.029, are
   unchanged; the gross Sharpe (0.54 for C) is a point estimate whose gain over
   0.38 is not significant (HAC t 0.89) and depends on one fold.
2. That C has skill after multiple testing. Its net Sharpe 0.39 has a **deflated
   probability of 0.24** (160 trials; not significant), a six-factor alpha of
   t = 1.34, and a fold pattern with four non-positive folds. It is a
   cost-survivable version of a weak signal, not evidence of a strong one.
3. That the result generalises. One set of frozen predictions, one universe, one
   period; C was the best of four cells evaluated on the same data, and although
   T3 is Bonferroni-corrected across the four, the *level* of its Sharpe is not.
4. Implementability: spread is assumed, there is no borrow cost, impact is a
   square-root proxy.

### Calibration of the recorded predictions

| Prediction (made before running) | Outcome |
|---|---|
| 1. T1 met by B40 and C; B30 and D "may" fall short | B40 ✓, C ✓, B30 fell short ✓; **D also met T1** (−43%) ✗ |
| 2. T2 is the binding criterion; C most likely to fail it | T2 was binding for B40 only. **C had the highest retention (1.50).** ✗ |
| 3. Best net Sharpe < ~0.35 | **C +0.39** ✗ (D +0.29 inside) |
| 4. P(at least one MECHANISM_CONFIRMED) ≈ 50%, most likely B40 | One cell confirmed ✓; it was **C, not B40** ✗ |

The surprises are concentrated where the literature anchor (B) underperformed
and the simple Qlib-style bounded-replacement rule (C) and the horizon-matched
minimum hold (D) did better. That is a reason to treat the ranking of cells as
provisional, not a finding about which mechanism is "right".

### Decision (per the preregistered decision rule and the program's decision tree)

* Turnover reduction improves net → **freeze the mechanism: C_topk_dropout_10**
  for EXP-009B and EXP-009C, reported alongside the immediate-replacement
  control so that ranking-loss and analyst comparisons are not confounded by the
  portfolio rule.
* B (hysteresis) turnover cut destroys gross edge (B40) or is insufficient (B30) →
  **rejected** for this signal.
* D is **not confirmed** on the preregistered criterion (T3 lower bound −0.013)
  but is close and directionally the same as C; it is not carried forward and is
  not re-tested with new parameters in this program.
* **Promotion: NOT ASSESSED.** EXP-006 remains not promotable; production models
  remain zero.

### Reproduction

```bash
.venv/bin/python -m scripts.quant.exp009a gate         # preregistration pushed?
.venv/bin/python -m scripts.quant.exp009a run          # refused without it
.venv/bin/python -m scripts.quant.exp009a robustness   # exploratory, post-hoc
```

---

## EXP-009B — a ranking objective against a matched point-regression control

### What was run, and the integrity record

Three boosted-tree models that differ **only in the objective** — squared error on the continuous
rank label (`R1`, the control), LambdaMART (`R2`), and a position-agnostic pairwise loss (`R3`) —
plus a refit of scikit-learn's `GradientBoostingRegressor` (`R0`) as a validity gate. Same dataset
`ds-491d761b9f2a6fc4`, same 27 frozen features, same eight folds recovered from EXP-006's plan,
same imputation, hyper-parameters (200 rounds, learning rate 0.03, depth 3, subsample 0.7, min leaf
50), seed 0. No search of any kind. Both rankers were classified exactly by the frozen rules.

| Check | Result |
|---|---|
| Manifest present, generated artifacts hashed | ✓ 14 output files; every recorded sha256 re-verified, 0 mismatches |
| Preregistration lineage | ✓ document sha256 `42cfe2ce…069c`, commit `d633b1b` (ancestor of `origin/main` when the run started), run at commit `d633b1b`, `git_dirty: false` |
| Definition fingerprint | ✓ `a2385011…3f42`, equal to the value embedded in the preregistration and recomputed after the run |
| Dataset id / returns-panel hash | ✓ `ds-491d761b9f2a6fc4` / `d1f10c93…919e` |
| 27 frozen `C_base` features | ✓ feature-list sha256 `43a60caa…7b94`; identical to EXP-006's `features_used` |
| Folds | ✓ the eight recorded EXP-006 folds; first validation 2017-05-05, last validation end **2025-05-09** |
| **Validity gate** | ✓ **R0 reproduces EXP-006's 100,246 frozen predictions with max absolute difference 0.0** |
| Seed / software | ✓ seed 0; Python 3.12.11, numpy 2.2.6, pandas 2.3.3, scipy 1.18.1, scikit-learn 1.7.2, pyarrow 18.1.0 (the versions EXP-006 recorded) |
| **Holdout** | ✓ **`touched: false`**, firewall engaged (contract NOT ARMED), 0 breaches, 0 overrides; window 2025-08-26 → 2026-08-28 (the widest EXP-006 recorded anywhere) was not read for any purpose |
| Compute | CPU only, 12 cores, 4 workers, **628 s wall**; 16-58 s per fold for R0/R1 and 31-109 s for R2/R3 (≈2x the L2 loop); no GPU |

### Classification (the frozen rules, applied exactly)

| Ranker | O1 ordering | O2 consistency | O3 stability | E1 economics | **Classification** |
|---|---|---|---|---|---|
| R2 LambdaMART | ✗ (ΔIC −0.0139; lower bound −0.038) | ✗ (3 of 8 folds better) | ✓ | ✗ | **NO_ORDERING_GAIN** |
| R3 pairwise | ✗ (ΔIC +0.0001; lower bound −0.0065) | ✗ (2 of 8 folds better) | ✓ | ✗ | **NO_ORDERING_GAIN** |

*LambdaMART lowered mean Rank IC and failed the economic criterion; pairwise ranking showed no
statistically supported ordering improvement.* **No ranker is retained.** Per the preregistered
carry-forward rule, the BASE for EXP-009C is the sklearn `GradientBoostingRegressor` (R0), the frozen
point-regression baseline. Nothing is promoted.

### Ordering (portfolio-free; 404 dates, 100,246 predictions)

| Cell | Mean Rank IC | HAC t | ICIR | Positive dates | Fold IC (0…7) | Worst / best fold | Positive folds | NDCG@50 long / short | Top / bottom realised rank | Spread |
|---|---:|---:|---:|---:|---|---|---:|---|---|---:|
| R0 sklearn (gate) | 0.02895 | 2.66 | 0.199 | 61.4% | −.019 .037 .046 .024 −.009 .041 .035 .076 | −.019 / .076 | 6 | .521 / .527 | +.023 / −.026 | .049 |
| **R1 L2 control** | **0.03204** | **2.94** | 0.219 | 59.9% | −.011 .051 .042 .025 −.000 .036 .036 .077 | −.011 / .077 | 6 | .524 / .527 | +.028 / −.026 | .053 |
| R2 LambdaMART | 0.01814 | 1.63 | 0.130 | 53.0% | .030 −.012 .036 .044 .037 .001 −.005 .015 | −.012 / .044 | 6 | .513 / .516 | +.012 / −.013 | .025 |
| R3 pairwise | 0.03213 | 2.68 | 0.203 | 59.4% | −.013 .048 .049 .048 −.007 .028 .036 .067 | −.013 / .067 | 6 | .522 / .529 | +.026 / −.029 | .055 |

Prediction dispersion (mean cross-sectional SD, **native units — not comparable across objectives**):
R1 0.045, R2 0.129, R3 0.110. Train IC → train-validation gap: R1 0.190 → 0.158; R3 0.195 → 0.163;
**R2 0.065 → 0.047** — LambdaMART is *underfitting* under the frozen 200-round, 0.03-rate configuration;
this is a property of the configuration, which was not tuned and is not changed here.

### Paired statistics (frozen: HAC Bartlett 4 lags, z = 1.96, block-8 bootstrap, 10,000 draws, seed 0)

| | Δ mean Rank IC (ranker − control) | HAC t | One-sided lower bound | Bootstrap 95% CI | Folds better |
|---|---:|---:|---:|---|---:|
| R2 LambdaMART | −0.01390 | −1.12 | −0.03815 | [−0.0395, +0.0116] | 3 / 8 |
| R3 pairwise | +0.00009 | +0.03 | −0.00654 | [−0.0065, +0.0075] | 2 / 8 |

Δ NDCG@50 (long / short): R2 −0.011 / −0.011; R3 −0.002 / +0.002. Δ realised-rank spread: R2 −0.029; R3 +0.001.

### Stability — a ranker is not better if it gains IC by reshuffling the book

| Cell | Rank correlation between consecutive dates | Top-quintile retention | Bottom-quintile retention | Rank turnover (mean \|Δ percentile\|) |
|---|---:|---:|---:|---:|
| R1 control | 0.685 | 0.599 | 0.649 | 0.156 |
| R2 LambdaMART | 0.665 | 0.711 | 0.708 | 0.119 |
| R3 pairwise | 0.716 | 0.624 | 0.655 | 0.149 |

Neither ranker gains IC by churning: R3 is marginally *more* stable than the control, and R2's higher
retention comes with lower IC and a weaker top/bottom spread (the retention of a less informative ordering).
Both pass O3, and neither passes O1.

### Portfolio economics (10 bp half-spread primary)

**Under the frozen EXP-009A top-k-dropout construction:**

| Cell | Gross Sharpe | Net Sharpe 1 / 3 / 5 / **10** / 20 bp | Annual turnover | Cost share | Max DD | Break-even | Names replaced per rebalance | Mean spell |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| R0 sklearn | 0.541 | +.477 / +.458 / +.438 / **+.390** / +.293 | 6.90 | 28% | −14.3% | 50.2 bp | 13.2% | 7.4 |
| **R1 control** | 0.607 | +.544 / +.524 / +.505 / **+.457** / +.361 | 6.92 | 25% | −13.1% | 57.5 bp | 13.3% | 7.4 |
| R2 LambdaMART | −0.175 | −.237 / −.257 / −.276 / **−.324** / −.420 | 6.85 | undefined (gross < 0) | −41.6% | negative | 13.1% | 7.5 |
| R3 pairwise | 0.458 | +.389 / +.368 / +.347 / **+.295** / +.190 | 6.87 | 36% | −18.6% | 38.1 bp | 13.2% | 7.5 |

**Under immediate replacement (the EXP-006 construction):**

| Cell | Gross Sharpe | Net Sharpe 1 / 3 / 5 / **10** / 20 bp | Annual turnover | Cost share | Max DD | Break-even | Names replaced | Mean spell |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| R0 sklearn | 0.384 | +.169 / +.108 / +.048 / **−.102** / −.403 | 20.15 | 127% | −28.8% | 6.6 bp | 39.7% | 2.5 |
| R1 control | 0.358 | +.138 / +.077 / +.016 / **−.137** / −.442 | 20.52 | 138% | −29.6% | 5.5 bp | 40.5% | 2.5 |
| R2 LambdaMART | −0.184 | −.318 / −.355 / −.391 / **−.484** / −.668 | 16.52 | undefined | −58.8% | negative | 32.4% | 3.0 |
| R3 pairwise | 0.247 | −.002 / −.072 / −.142 / **−.316** / −.663 | 19.65 | 228% | −42.6% | 0.9 bp | 38.8% | 2.6 |

Paired net-Sharpe difference at 10 bp (ranker − control), block bootstrap, lower bound at level 0.975:
under top-k dropout R2 −0.78 (95% CI −1.45 … −0.10; lower bound −1.45), R3 −0.16 (−0.46 … +0.08); under
immediate replacement R2 −0.35 (−0.98 … +0.23), R3 −0.18 (−0.66 … +0.35). **E1 fails for both** (lower
bound ≤ 0; the turnover ratios, 0.99, are inside the 1.10 limit — a ranking loss is not a turnover control,
as the listwise paper's own turnover suggested).

### Fold economics — does one period dominate?

Net return, bp per period, under top-k dropout (gross in parentheses); **bold** = better than the control (the control column carries no bold).

| Fold | Period | R1 control | R2 LambdaMART | R3 pairwise |
|---:|---|---|---|---|
| 0 | 2017-05 → 2018-05 | −4.0 (+1.0) | **−2.0** (+2.7) | −5.6 (−0.7) |
| 1 | 2018-05 → 2019-05 | +19.7 (+23.9) | +6.6 (+10.7) | **+20.5** (+24.6) |
| 2 | 2019-05 → 2020-05 | −4.3 (+1.2) | −26.3 (−20.9) | **−0.7** (+4.7) |
| 3 | 2020-05 → 2021-05 | +32.9 (+36.8) | +4.3 (+8.4) | **+35.9** (+39.8) |
| 4 | 2021-05 → 2022-04 | −15.9 (−12.1) | **−9.7** (−5.7) | **−14.0** (−10.2) |
| 5 | 2022-05 → 2023-05 | +56.7 (+60.8) | −26.9 (−23.1) | +16.8 (+20.8) |
| 6 | 2023-05 → 2024-05 | −4.6 (−0.7) | −10.1 (−6.3) | −9.9 (−5.9) |
| 7 | 2024-05 → 2025-05 | +23.0 (+27.0) | −8.5 (−4.6) | +18.1 (+22.1) |

* **Fold 5 is the single largest contributor.** Under top-k dropout the *control's* positive result leans on that
  one period (+56.7 bp), as EXP-009A found for the sklearn cell. Fold 5 is also the largest single contributor to
  each ranker's net difference from the control: 48% of the total for LambdaMART; for pairwise, whose other folds
  roughly offset one another, 94%. One period should not be read as the result.
* **IC and net do not move together per fold.** LambdaMART has a *higher* fold IC than the control in folds 0, 3
  and 4 (+0.030, +0.044, +0.037), yet in fold 3 its net is far lower (+4.3 vs +32.9 bp): an ordering measured by
  rank correlation across 250 names is not the ordering of the 50 names each leg trades.
* The same table under immediate replacement is in `experiments/EXP-009B/posthoc_descriptive.json`
  (per-fold gross, net, turnover, IC and whether each fold improved on the control, for every cell).

### The noise floor

R0 and R1 differ *only* in the tree learner's bagging implementation (sklearn's selection-sampling mask versus
mine; with `subsample = 1.0` they agree to 1e-9). Yet R1 − R0 is **+0.0031 mean Rank IC** and **+0.067 net
Sharpe** under top-k dropout (−0.035 under immediate replacement). That is the size of the change produced by
nothing but a different random subsample — larger than the R3 − R1 IC difference (+0.0001) and comparable to
the differences the paper-level effects would have to clear. Any single-fit IC comparison in this program has
this uncertainty; the frozen criteria (HAC, 6-of-8 folds, block bootstrap) exist to keep it from being read as signal.

### Calibration of the recorded predictions

| Prediction | Outcome |
|---|---|
| 1. No ranker meets O1; any IC difference within ±0.005 | **Half right.** No ranker met O1 ✓; R3's difference was +0.0001 ✓; R2's was **−0.0139**, far outside ±0.005 ✗ |
| 2. LambdaMART worse than the control on the short end; pairwise closest to the control | ✓ R2 NDCG@50 short −0.011 (and long −0.011); R3 closest (−0.002 / +0.002) |
| 3. Binning costs a little IC; similar train-validation gaps | **Wrong for R2:** its train IC is 0.065 vs 0.190 — a much smaller gap (underfit), and a large IC loss. Right for R3 (no loss, same gap) |
| 4. P(at least one ORDERING_AND_NET_IMPROVED) ≈ 10-15% | ✓ none |

### Validation of the custom ranker (non-outcome-based; nothing here touched a real prediction)

The repository implemented the ranking objective itself, so its correctness rests on mathematics and controlled
examples. After the run: (A) finite-difference gradient **and** Hessian tests pass; (B) the pairwise training loss
falls monotonically across boosting rounds on a controlled ordering (and by more than 15%); (C) a spy on the
gradient call confirms **one call per prediction date and never a union** — no pair can cross dates; (D)
gradients are invariant to row order within a query; (E) with `subsample = 1.0` the squared-error objective equals
sklearn's `GradientBoostingRegressor` to 1e-9; (F) a fixed seed reproduces predictions exactly and another seed
does not; (G) two hand-calculated examples (tied scores, one relevant item) fix the signs and magnitudes:
pairwise residual ±0.5, Hessian 0.25; LambdaMART residual ±0.1845351232, Hessian 0.0922675616.
(H) **Against the primary description** — Burges, *From RankNet to LambdaRank to LambdaMART: An Overview*
(Microsoft Research TR-2010-82, §7, read from the PDF): λ_ij = −σ|ΔZ_ij|/(1 + e^{σ(s_i − s_j)}), ∂²C/∂s_i² =
Σσ²|ΔZ_ij|ρ_ij(1 − ρ_ij), leaf step = Σ(lambda)/Σ(second derivative) — these are the implemented equations.
Two differences are recorded rather than hidden: the paper's NDCG uses gain 2^l − 1 whereas EXP-009B
preregistered **linear** gains (a change of the utility, not of the equations); and the code adds a small
stabiliser to the leaf denominator (one mean-row hessian) that the preregistration's text ("Newton leaf values")
did not spell out — it is in the fingerprinted source but is not in Burges's formula. **No implementation bug was found; the
frozen result stands and no amendment is required.** (`tests/quant/test_ranker_validation.py`,
`tests/quant/test_ranking_models.py`.)

### What this does and does not establish

**Established, on this data, for this frozen configuration:**
1. A LambdaMART objective with linear NDCG gains, whole-list pairs and 200 shallow rounds **did not improve** the
   cross-sectional ordering; it reduced mean Rank IC by 0.014 (HAC t −1.1; not significant either way) and made the
   traded book lose money gross (Sharpe −0.18 immediate, −0.18 top-k) — while underfitting (train IC 0.065).
2. A position-agnostic pairwise loss produced an ordering **statistically indistinguishable** from squared error
   (ΔIC +0.0001) but, in the book, a lower net Sharpe (−0.16 under top-k dropout; not significant).
3. The ranking objective did not lower turnover (ratios 0.99), consistent with the listwise literature.

**Not established:** that ranking objectives do not work — LightGBM/XGBoost implementations, a two-sided or
differently-gained objective, more rounds for LambdaMART, or another horizon were not tried and are not
tried here. The differences between R0 and R1 (a bagging seed) are as large as most of these effects.

### Decision

* **No ranker retained.** Both are `NO_ORDERING_GAIN`; no "promising" intermediate is recorded.
* **BASE for EXP-009C = R0, the sklearn `GradientBoostingRegressor`** (the preregistered fallback).
* Promotion: **NOT ASSESSED**. EXP-006 remains not promotable; production models remain zero.
* Artifacts: `experiments/EXP-009B/` — definition, manifest, metrics, four prediction files, eight period files,
  `posthoc_descriptive.json` (exploratory; `src/quant/study/exp009b_report.py`).

---

## EXP-009C — point-in-time analyst-revision features added to the base set

### What was run, and the integrity record

Two sklearn `GradientBoostingRegressor` fits (repository defaults, seed 0) that differ **only in the feature set**:
`BASE` = the 27 frozen `C_base` features; `ARM` = those plus eight point-in-time analyst features (EPS revision at
4 and 13 weeks, sales revision at 4 and 13 weeks, dispersion, analyst count, 13-week count change, revision
acceleration — each ranked within the universe on its date). Fixed by the preregistration, not chosen from results:
no other window, no search. Folds 3-7 are the only evaluable ones (24 months of analyst history in training).

| Check | Result |
|---|---|
| Preregistration lineage | ✓ commit `47d6f67` (ancestor of `origin/main` when the run started); run at commit `42b1e29`, **`git_dirty: false`** |
| Definition fingerprint / dataset / panel hash | ✓ `c447097e…384e` / `ds-491d761b9f2a6fc4` / `d1f10c93…919e` |
| **Analyst PIT gates on the real data** | ✓ truncation invariance; rewriting every vintage after 2022-12-31 changed no earlier feature (352,161 rows); strict attach (34,090 attached rows, none from a vintage on or after its row) |
| BASE reproduces the frozen EXP-006 predictions | ✓ max absolute difference **0.0** over 100,246 rows |
| Evaluable folds | ✓ `[3, 4, 5, 6, 7]` — exactly the preregistered set |
| **Holdout** | ✓ **`touched: false`**, firewall engaged, 0 breaches, 0 overrides |
| Artifacts | ✓ 8 output files hashed, 0 mismatches; seed 0; Python 3.12.11, numpy 2.2.6, pandas 2.3.3, scipy 1.18.1, scikit-learn 1.7.2 |
| Compute | CPU only, 12 cores, **666 s** wall, two sequential single-process fits, no GPU |

### Classification

**`ANALYST_NO_RELIABLE_VALUE`.** O1 ✗ (ΔIC −0.0099; lower bound −0.0315); O2 ✗ (2 of 5 evaluable folds improved); E1 ✗
(net-Sharpe lower bound −1.15). *Adding the analyst features did not improve the ordering on the folds that can speak,
and lowered mean Rank IC there; the change in net performance under the frozen turnover mechanism was negative and not
distinguishable from zero.* The PIT gates passed, so this is a result and not `BLOCKED_DATA_QUALITY`.

### Ordering (evaluable folds 3-7: 252 dates)

| | Mean Rank IC | HAC t | ICIR | Positive dates | Positive folds (of 5) | Worst evaluable fold | NDCG@50 long / short | Realised-rank spread |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| BASE | **0.03349** | 2.41 | 0.223 | 59.5% | 4 | −0.0091 | .522 / .528 | 0.052 |
| ARM | 0.02362 | 1.67 | 0.171 | 54.0% | 3 | −0.0145 | .517 / .525 | 0.041 |

All 8 folds (fold IC, folds 0…7): BASE −.019 .037 .046 .024 −.009 .041 .035 .076; ARM −.019 .051 .075 −.015 −.004 .076
.031 .029. Pooled over all eight folds: BASE 0.02895 (t 2.66), ARM 0.02798 (t 2.65) — **not** a preregistered
comparison (folds 0-2 lack analyst history in training) and shown only so the reader can see the full picture.

Paired (evaluable folds, HAC Bartlett 4 lags, z = 1.645; block bootstrap): ΔIC **−0.0099**, SE 0.0132, t −0.75, one-sided lower
bound −0.0315, bootstrap 95% CI [−0.040, +0.017], 75% of resamples ≤ 0. Folds better: 2 of 5 (folds 4 and 5).

Stability: rank correlation between consecutive dates BASE 0.702 → ARM 0.807; top-quintile retention 0.610 → 0.713;
bottom 0.669 → 0.721. **The analyst block made the ordering more persistent and no more informative** —
the persistence a slow-moving feature (an analyst count, a quarterly revision) gives, with no gain in IC.

### Portfolio economics (10 bp primary; net Sharpe at 1 / 3 / 5 / 10 / 20 bp) — full sample, all eight folds

**Under the frozen top-k-dropout policy** (the criterion E1 is evaluated on folds 3-7 only, per the preregistration):

| | Gross Sharpe | Net Sharpe 1 / 3 / 5 / **10** / 20 bp | Annual turnover | Cost share | Max DD | Break-even |
|---|---:|---|---:|---:|---:|---:|
| BASE | 0.541 | +.477 / +.458 / +.438 / **+.390** / +.293 | 6.90 | 28% | −14.3% | 50.2 bp |
| ARM | 0.469 | +.413 / +.395 / +.378 / **+.335** / +.250 | 6.78 | 29% | −23.5% | 49.1 bp |

**Under immediate replacement:**

| | Gross Sharpe | Net Sharpe 1 / 3 / 5 / **10** / 20 bp | Annual turnover | Cost share | Max DD | Break-even |
|---|---:|---|---:|---:|---:|---:|
| BASE | 0.384 | +.169 / +.108 / +.048 / **−.102** / −.403 | 20.15 | 127% | −28.8% | 6.6 bp |
| ARM | 0.420 | +.140 / +.061 / −.018 / **−.215** / −.608 | 17.32 | 151% | −27.3% | 4.5 bp |

Paired net-Sharpe difference under top-k dropout, evaluable folds, ARM − BASE: **−0.23** (95% CI −1.31 … +0.33;
one-sided lower bound −1.15); turnover ratio 0.98. ARM's drawdown under the frozen policy is markedly worse
(−23.5% vs −14.3%).

### Fold economics — no consistent direction

Net return, bp per period, under top-k dropout (gross in parentheses). Folds 0-2 are **not evaluable** (shown
for completeness, in a lighter role).

| Fold | Period | Evaluable | BASE | ARM | IC BASE → ARM |
|---:|---|:-:|---|---|---|
| 0 | 2017-05 → 2018-05 | no | −6.1 (−1.1) | −6.3 (−1.4) | −.019 → −.019 |
| 1 | 2018-05 → 2019-05 | no | +15.0 (+19.2) | +21.2 (+25.4) | +.037 → +.051 |
| 2 | 2019-05 → 2020-05 | no | −0.5 (+4.9) | +21.3 (+26.6) | +.046 → +.075 |
| 3 | 2020-05 → 2021-05 | yes | +24.7 (+28.6) | −8.8 (−4.9) | +.024 → −.015 |
| 4 | 2021-05 → 2022-04 | yes | −26.0 (−22.2) | −23.5 (−19.8) | −.009 → −.004 |
| 5 | 2022-05 → 2023-05 | yes | +61.4 (+65.3) | **+89.5 (+93.5)** | +.041 → +.076 |
| 6 | 2023-05 → 2024-05 | yes | −0.7 (+3.3) | −4.4 (−0.6) | +.035 → +.031 |
| 7 | 2024-05 → 2025-05 | yes | +19.3 (+23.2) | −6.4 (−2.6) | +.076 → +.029 |

The analyst features move individual folds a great deal in **both** directions (fold 5 +28 bp; fold 3 −34 bp; fold 7
−26 bp) and net to nothing. The larger fold-2 improvement is in a non-evaluable fold and is **not** counted — including
it after seeing it would be exactly the selection the preregistration forbids.

### Importance, coverage and missingness

* Analyst block share of split-gain importance: **16.6%** (within the recorded 10-25%). The most-used analyst feature is
  `analyst_eps_coverage_xs` (the analyst count, rank 3 overall at 0.060) — a proxy for firm size and attention, not for
  revision information. **Importance is not value**: trees spend splits on any available feature.
* Coverage on in-universe rows (non-null): 4-week EPS revision 76% (2018), 86-91% (2019-24); 13-week 56-72% and lower
  in early-year months (fiscal rollover) — the calendar-dependent missingness the preregistration flagged; dispersion
  95-99%. Nothing before 2017-10. Per-year and per-feature coverage is in the manifest.

### Calibration of the recorded predictions

| Prediction | Outcome |
|---|---|
| 1. PIT gates pass | ✓ |
| 2. `ANALYST_NO_RELIABLE_VALUE` (≈ 75%) | ✓ |
| 3. ΔIC within ±0.005 and inside the HAC noise | **Half right:** inside the noise ✓ (t −0.75); magnitude −0.0099 is larger than ±0.005 ✗ |
| 4. Analyst block takes 10-25% of importance; not indicative of value | ✓ 16.6% |

### What this does and does not establish

**Established:** with these eight point-in-time features, on five folds with two-plus years of analyst history, the
gradient-boosted ordering did not improve (ΔIC −0.010, not significant) and the frozen book's net economics did not
improve. The data passed every PIT check; a null result on clean data is not a data-quality failure.

**Not established:** that analyst information is useless. This vendor's data, weekly cadence, FY1 only, no analyst
identity, no recommendation or target-price data, 3.5 fewer years of history than the price features, and one
model were tested. The literature's positive result (analyst stickiness) is **NOT REPRODUCIBLE** with this data and
was not attempted. Folds 0-2 cannot speak.

### Decision

* `ANALYST_NO_RELIABLE_VALUE` — **the analyst features are not carried forward**; they stay unregistered in the global
  feature registry. A negative result is recorded as one.
* Promotion: **NOT ASSESSED**. Artifacts: `experiments/EXP-009C/`.
