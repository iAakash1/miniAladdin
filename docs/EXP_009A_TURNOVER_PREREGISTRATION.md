# EXP-009A preregistration — turnover-aware portfolio construction on frozen EXP-006 predictions

**Status: FROZEN. Registered before any treatment cell has been evaluated.**
EXPERIMENTAL — PROMOTION NOT ASSESSED. Baseline commit `176d6b7`.

This document is committed and pushed to `origin/main` **before** EXP-009A is
executed. `python -m scripts.quant.exp009a run` refuses to run unless this file
embeds the definition fingerprint below, is committed unchanged, and its commit
is an ancestor of `origin/main` (`src/quant/study/exp009a.py::prereg_gate`,
tested against a real temporary git repository). Any later change to the frozen
definition, to `src/quant/backtest/rules.py` or to `src/quant/backtest/engine.py`
changes the fingerprint and blocks the run until a visible, dated amendment is
added below.

## 1. What was known when this was written

* The control (cell A) is EXP-006's recorded gradient-boosting backtest, already
  reproduced exactly in `docs/TURNOVER_FAILURE_ANALYSIS.md`: 403 periods, one-way
  turnover 0.399774 per rebalance (20.1486x annualised), gross Sharpe 0.38444, net
  Sharpe −0.10218 at 10 bp, cost share of gross 1.2661.
* The turnover decomposition (same document) was computed **from predictions and
  held sets only; it read no forward return**. It shows 48.9% of turnover is
  one-quintile boundary movement, 8.7% full reversal, about 8% forced
  universe/price exits.
* **No treatment cell (B, C, D) has been scored on any return.** The rules were
  exercised only on synthetic data in unit tests. Cell parameters below come from
  the literature anchors named beside them, not from any outcome on this data.

## 2. Frozen inputs

| Item | Value |
|---|---|
| Parent experiment | EXP-006 (never modified) |
| Predictions | `experiments/EXP-006/predictions_fwd_rank_21.parquet`, model `gradient_boosting`, target `fwd_rank_21` |
| File sha256 | `d7616f54c3f65f74558c9d186640c9fab123acff99cd95525e43dabc13eea747` (recomputed at run time and recorded) |
| Model-rows sha256 | `9d78f8fae7e94fd82e47731d2157259b19209402e9520d29d5b88c45980a6910` |
| Rows / symbols / dates | 100,246 / 754 / 2017-05-05 to 2025-05-09 (403 backtest periods after the 1-period lag) |
| Forward returns | Rebuilt `fwd_ret_5` panel from the local raw store, capped at 2025-05-09; content sha256 `d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e`; must pass the label-identity check (rank of rebuilt `fwd_ret_21` = stored `fwd_rank_21` on every date) |
| Models refit | **None.** No prediction is altered. |
| Engine | `engine.run_backtest` unchanged in behaviour for the control; optional `weight_rule` hook added (no effect when unset; tested) |
| Cost model | `SimpleCostModel`: commission 1 bp, half-spread 10 bp primary (sweep 1/3/5/10/20), impact 0.1·√(traded notional / daily dollar volume), capital $1,000,000 |
| Timing | rebalance every 5 sessions; positions from the prediction one rebalance earlier (`execution_lag_periods=1`); forward return `fwd_ret_5` |
| Book | equal-weight long/short, 0.5 gross long / 0.5 gross short, per-name cap 0.10, `min_names` 10 |
| Turnover | one-way = Σ\|Δw\|/2 per rebalance, annualised ×50.4 |
| Sealed holdout | 2025-08-28 → 2026-08-28 (from `experiments/EXP-006/metrics.json` and `docs/HOLDOUT_CONTRACT.md`); **not read, scored or used**; firewall armed and asserted on predictions, panel, periods and membership |

## 3. Hypothesis

**H-A.** A portfolio rule that holds close substitutes instead of trading across a
hard cutoff lowers turnover materially while retaining most of the gross edge, so
that net performance improves for a reason other than "it trades less".

Cost falls with turnover by construction, so a net improvement alone is not
evidence. The tests below separate the three things that matter: the turnover cut,
the gross edge retained, and the paired uncertainty of the net difference.

## 4. Cells (exactly one parameter set per family; nothing tuned)

Entry in every treatment is the baseline's bucket definition (`pd.qcut` on
`rank(method="first")`, 5 buckets), so an entrant is always a name the baseline
would also hold. A rule differs from the control only in what it **retains**.

| Cell | Rule | Parameters | Anchor |
|---|---|---|---|
| **A_immediate** | hold exactly the top/bottom quintile every rebalance | — | control = EXP-006 |
| **B_hysteresis_40** | enter top (bottom) 20%; retain until the name leaves the top (bottom) **40%** | `retain_fraction=0.40` | Novy-Marx & Velikov (2016) sS buy/hold spread: 10%/20% on deciles for mid-turnover strategies (2:1); scaled to quintiles. Primary B cell |
| **B_hysteresis_30** | same, retain to the top (bottom) **30%** | `retain_fraction=0.30` | milder 3:2 band (the brief's 80/70 example); dose-response companion — a second B cell, counted as a trial, not a replacement |
| **C_topk_dropout_10** | hold k names per leg (k = baseline bucket size); replace at most `max(1, round(0.10·k))` worst incumbents per rebalance, only for a better non-held candidate | `drop_fraction=0.10` | Qlib benchmark `topk=50, n_drop=5`; a quintile of the 250-name universe is 50 names, so the same 10% |
| **D_min_hold_4** | baseline entry; a name cannot be sold on rank until held for 4 rebalances | `min_hold_periods=4` | 4 × 5 = 20 sessions ≈ the 21-session label horizon |

**Rule details (all frozen; see `src/quant/backtest/rules.py`, unit-tested):**

* *Hysteresis:* `band = max(round(retain_fraction × N), 1)`; long set = (incumbent
  longs inside the top `band` by rank) ∪ (baseline top bucket); short set mirrors.
  The two bands cannot overlap because `retain_fraction < 0.5`.
* *Dropout:* per leg, `held` = incumbents still in the cross-section (forced exits
  are not counted against the budget); candidates = best-ranked non-held names
  excluding names held on the other side; `today` = first `n_drop + refill`
  candidates where `refill = max(k − |held|, 0)`; sell the incumbents in the bottom
  `n_drop` of `held ∪ today` ranked by score; buy the best candidates up to
  `|sold| + refill`; if `k` shrank, sell extra lowest-ranked. First rebalance =
  baseline book. A name held on one side cannot be a candidate on the other in the
  same rebalance (a flip takes two rebalances; conservative).
* *Minimum hold:* age counted in rebalances a name has been held on a side; locked
  while `age < 4`; a locked name keeps its side and cannot also be entered on the
  other; a name absent from the cross-section is a forced exit regardless.
* *All rules:* absent from the cross-section ⇒ forced exit, never carried; legs
  equal-weighted at 0.5 gross with the engine's cap; ties by `rank(method="first")`;
  a rule reads scores and prior weights only — never a return (tested by permuting
  forward returns and asserting identical weights). The two thin dates
  (2019-09-17: 174 names; 2020-02-17: 14 names) are traded as-is by every cell.

Not run in this study: the exponential score smoother in
`docs/EXP_009_TURNOVER_CANDIDATE.md`, a change of rebalance cadence, and any
combination of rules. Combinations and other levers are separate experiments.

## 5. Metrics

* **Primary:** net Sharpe at 10 bp; annualised one-way turnover.
* **Reported for every cell:** gross and net return, gross and net Sharpe, net CAGR,
  max drawdown, cost share of gross, break-even half-spread, full cost sweep
  (1/3/5/10/20 bp), names replaced per rebalance, average completed holding spell,
  mean predicted percentile of longs/shorts (rank capture), breadth and effective
  N, max weight, capacity proxy (trade size / same-day dollar volume, p95),
  six-factor alpha t-statistic, deflated Sharpe, **per-fold metrics for all 8
  folds**, membership history (`membership_<cell>.parquet`), period returns.
* Additionally reported: largest single-fold share of the total net gain (dominance
  by one period is a warning, not a criterion).

## 6. Preregistered criteria (per treatment cell)

| ID | Criterion |
|---|---|
| **Validity** | The control reproduces EXP-006's recorded gradient-boosting backtest (periods, mean and annualised turnover, gross and net Sharpe, cost share, net CAGR, total cost) within relative 1e-9. **If not, the run is INVALID and no treatment is reported.** |
| **T1** turnover cut | annualised one-way turnover ≤ 0.70 × control (cut ≥ 30%; the literature average for the sS rule is about 41%) |
| **T2** gross retention | mean gross period return ≥ 0.75 × control's |
| **T3** net gain | paired circular moving-block bootstrap (block 8 periods, 10,000 draws, seed 0) of Δ(net Sharpe at 10 bp, treatment − control): the one-sided lower bound at level 1 − 0.05/4 = 0.9875 is > 0 |
| **T4** fold consistency | the cell's mean net period return exceeds the control's in at least 6 of the 8 folds |

**Classification** (deterministic function of the numbers; `classify_cell`):
`MECHANISM_CONFIRMED` = T1∧T2∧T3∧T4; `EDGE_LOST` = T1∧¬T2 (turnover falls but the
gross edge is destroyed — reject, however good net looks); `INSUFFICIENT_TURNOVER_CUT`
= ¬T1; `NO_RELIABLE_NET_GAIN` = T1∧T2∧(¬T3∨¬T4).

**Carry-forward.** If more than one cell is `MECHANISM_CONFIRMED`, the one with the
highest T2 retention ratio is frozen as the turnover mechanism for EXP-009B/C
(ties: fewer parameters). If none is, no mechanism is frozen and EXP-009B/C use the
control construction. **Nothing is promoted.**

**Descriptive only (not criteria):** whether net Sharpe > 0 at 10 bp, cost share,
break-even spread, drawdown, alpha t, deflated Sharpe, capacity. A positive net
Sharpe at a single assumed spread is not viability.

## 7. Inference and multiplicity

Labels are 21 sessions evaluated every 5, so consecutive observations share ~76% of
their horizon; inference is HAC (Newey-West, Bartlett, 4 lags) and block-bootstrap,
never IID. The family alpha (0.05) is Bonferroni-split over the 4 treatment cells
for T3. Cumulative evaluation count for deflation: 156 (through EXP-006) + 4 = **160**.
All cells use the same predictions and returns, so their net differences are
positively correlated; four cells are not four independent looks, but they are
counted as four.

## 8. Outputs (new namespace; EXP-006 is never written)

`experiments/EXP-009A/`: `definition.json`, `manifest.json` (preregistration
sha256 and commit, definition fingerprint, input file/rows/panel hashes, git commit
and dirty flag, module/rules hashes, seed, wall time, CPU count, platform, python,
firewall status), `metrics.json`, `summary.parquet`, `periods_<cell>.parquet`,
`membership_<cell>.parquet`, plus the committed
`turnover_diagnostics.json`. No licensed raw data, no absolute paths, no
credentials. Compute: CPU only; expected minutes.

## 9. Governance

* Holdout untouched; firewall engaged; no override; the contract remains NOT ARMED.
* No production model changes; no promotion; no live trading; no Qlib dependency
  (the top-k idea is re-implemented independently; Qlib is MIT and is cited).
* Negative results are results. A cell that fails is reported with the others; no
  parameter is adjusted after any outcome. A different width or drop count would be
  a new, separately registered experiment with its own trial count.

## 10. What this study cannot show

* It cannot show the signal is strong: it holds the model fixed, and the gross
  Sharpe is 0.38.
* It cannot show the buffered book is implementable: half-spread is assumed, there
  is no borrow or short-availability cost, and impact is a square-root proxy.
* It cannot separate turnover savings from staleness in any way except through T2.
* One frozen prediction set, one universe, one period; no out-of-sample confirmation
  beyond the eight folds already used to build the predictions.

## 11. Recorded predictions (made before any treatment is run)

1. T1 will be met by **B_hysteresis_40** and **C_topk_dropout_10**; B_hysteresis_30
   and D_min_hold_4 may fall short of a 30% cut (48.9% of turnover is adjacent-band
   movement; a narrower buffer or a minimum hold reaches less of it).
2. **T2 (gross retention) is the binding criterion.** C, which holds names longest,
   is the cell most likely to fail it.
3. Net Sharpe at 10 bp for the best cell will be positive but modest — I expect below
   about 0.35 — and will not change the conclusion that this is a low-Sharpe book.
4. My probability that at least one cell is `MECHANISM_CONFIRMED` is roughly 50%,
   most likely B_hysteresis_40.

These are recorded so a later reader can see how well calibrated the reasoning was.
They do not alter the criteria.

## 12. Amendments

None.

Definition fingerprint: `d59f60494560d0b0a62e3edcadd069366bd47f4e5aa1bc5564e1247c14b2d0a6`
