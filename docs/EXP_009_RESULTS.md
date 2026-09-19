# EXP-009 results

Running record of the EXP-009 program. Each section is written after its run and
is not edited afterwards except to append a dated correction. Everything is
**EXPERIMENTAL — PROMOTION NOT ASSESSED**; the sealed holdout
(2025-08-28 → 2026-08-28) has not been read, scored or used for any decision.
The final synthesis is in `docs/EXP_009_FINAL_ANALYSIS.md` when complete.

| Study | Status | Preregistration |
|---|---|---|
| **EXP-009A** turnover-aware portfolio construction | **Executed 2026-09-19** | `docs/EXP_009A_TURNOVER_PREREGISTRATION.md`, commit `155e976` (pushed before execution) |
| EXP-009B date-grouped learning to rank | Pending | — |
| EXP-009C analyst-revision arm | Pending (PIT audit first) | — |

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
