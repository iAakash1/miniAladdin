# Pre-Holdout Audit

**Verdict: the holdout must NOT be opened. The prior validation results are
invalid, and there is currently no candidate worth pre-registering.**

The audit found a defect that scrambled 12 of the 39 features used in the
study. It has been fixed and the fix is proven, but every learned-model result
produced before the fix is void. Spending a single-use holdout to test a
candidate selected on corrupted evidence would waste it.

---

## 1. The finding that stops the holdout

### What was wrong

`pandas.merge_asof` discards the left frame's index and returns a fresh
`RangeIndex`. Both as-of joins — options and earnings — did this:

```python
left   = out.sort_values("_date")                 # panel arrives SYMBOL-major
merged = pd.merge_asof(left, right, ...)          # index reset to 0..n-1
merged = merged.sort_index()                      # NO-OP on a RangeIndex
out[name] = merged[name].to_numpy()               # date-sorted values ->
                                                  # symbol-major rows
```

`sort_index()` was intended to restore the caller's row order. It cannot: the
index it sorts was replaced by the merge. Values were written back **positionally
into a differently-ordered frame**.

### Proof

A three-symbol panel with a constant, distinct IV per symbol:

| symbol | should receive | actually received |
|---|---|---|
| AAA | `[0.10]` | `[0.10, 0.50, 0.90]` |
| BBB | `[0.50]` | `[0.90, 0.10, 0.50]` |
| CCC | `[0.90]` | `[0.50, 0.90, 0.10]` |

Every symbol received every other symbol's value.

### Why it is a leak and not merely noise

The panel is symbol-major; sorting by date permutes it globally. A row dated
2014 could therefore receive a value belonging to a row dated 2026. The
misassignment is not local, so **future information travelled backwards**.

### How it was found

Not by reading. By building the point-in-time dataset twice — once over the
full range, once truncated strictly before the holdout — and comparing every
pre-holdout row:

```
BEFORE FIX: 24 of 67 features had different NULL patterns
            (all 12 options/earnings features + their 12 cross-sectional ranks)
AFTER FIX:  465,090 pre-holdout rows, all 67 features identical
```

That probe is now `check_contamination` in the preflight, so it runs as a gate
rather than as a one-off.

### Why the existing tests missed it

`tests/quant/test_earnings_options.py` used **single-symbol frames already in
date order**, where sorting by date is the identity and the misalignment is
invisible. The tests passed against broken code. Three regression tests now use
a multi-symbol, symbol-major panel and a shuffled-order invariance check; all
three fail against the old implementation.

This is the more important lesson: the test fixture, not the assertion, was the
weakness.

---

## 2. Scope of invalidation

39 features were used; **12 were scrambled** (8 options, 4 earnings, plus their
cross-sectional ranks).

| Result | Uses scrambled features | Status |
|---|---|---|
| `baseline_momentum` (+0.0158) | no — `mom_252_21_xs` only | **VALID** |
| `baseline_reversal` (+0.0015) | no — `reversal_5_xs` only | **VALID** |
| `baseline_low_volatility` (+0.0209) | no — `vol_63_xs` only | **VALID** |
| `baseline_zero`, `baseline_historical_mean` | no (constant) | VALID, no IC defined |
| `baseline_earnings_surprise`, `baseline_iv_premium` | yes — their own feature | **INVALID** |
| `ols`, `ridge`, `ridge_strong`, `lasso`, `elastic_net` | yes — all 39 | **INVALID** |
| `gradient_boosting`, `random_forest`, `hist_gradient_boosting`, `extra_trees`, `gradient_boosting_deep` | yes — all 39 | **INVALID** |

**The headline result — `gradient_boosting` on `fwd_rank_21`, IC +0.0295,
t +2.70, net Sharpe +0.03 — is void.** It is not "probably still roughly right".
A model trained on a matrix where a quarter of the columns carried other rows'
values, some of them from the future, tells us nothing about the matrix as
intended.

Per the standing instruction, the study has **not** been silently re-run.

### What survives

The three single-feature baselines are unaffected and remain the reference
points. Low-volatility (+0.0209) and momentum (+0.0158) are the bar any future
model must clear.

---

## 3. Second finding: execution timing was not achievable

**Status: fixed.**

The backtest formed positions from a signal computed on date `t`'s close and
earned the return from `t` onward — trading at the close it had just observed.
That close is not knowable until the session ends.

`BacktestConfig.execution_lag_periods` now defaults to **1**: the signal from
period `t` is acted on in period `t + 1`. At the 5-session stride that is a
full trading week, which is *more* conservative than a realistic close-to-next-open
fill, and deliberately so — a signal surviving it survives any plausible fill.
Lag 0 remains available and is pre-registered as a diagnostic only, so the more
flattering number can never be the one chosen afterwards.

The shift is applied **per symbol**; a global shift would hand one name's signal
to another. The first observation of each symbol is dropped rather than filled.

---

## 4. Point-in-time audit

| Claim | Status | Evidence |
|---|---|---|
| Delisted securities represented | **PROVEN** | SIVB closes 267.83 → 106.04 then stops the day trading halted; `financial_status='Bankrupt'`. Universe: 998 members ever, 793 absent today |
| Corporate actions applied at ex-date only | **PROVEN** | `r_t = (close_t·k_t + d_t)/close_{t-1} − 1`; appending a 2030 split changes no historical return |
| Splits do not fabricate returns | **PROVEN** | 4:1 reads 0%; without the record it reads −75% (both asserted) |
| Split coverage gap enforced | **PROVEN** | Records start 2014-03-28; builder clamps and records the clamp |
| Earnings available only after publication | **PROVEN** | `eps_history` joined to `earnings_calendar`; measured leak was 30 days; before-open +0, after-close +1, missing +1 |
| Unmatched periods dropped, not estimated | **PROVEN** | 51,884 of 157,594 dropped; no average lag substituted |
| Options cannot leak forward | **PROVEN** | Backward as-of with a 21-day staleness cap; invariance test appends a later snapshot |
| Macro respects publication | **PROVEN** | Treasury lagged one session at source |
| Revised series barred from features | **PROVEN** | Fama-French classified `PUBLICATION_LAGGED`; attribution only |
| No global fit anywhere | **PROVEN** | Every `.fit` is per-fold (`FoldImputer`, models) or expanding (k-means regimes); every rank/z-score is per date |
| Universe is point-in-time | **PROVEN** | Selected from each month's whole-market cross-section; 3-month trailing median; a never-shrinking universe fails the guard |
| **XBRL restatement handling** | **UNKNOWN** | `eps_history` holds one value per period with no vintage column. If a figure was later restated, the restated value is what is read. **Not detectable from within the dataset.** Not replaced with an assumption |
| **Pre-2017 delisting dates** | **PARTIAL** | `symbol.last_seen` starts 2017-10-26; earlier exits inferred only from a name leaving the cross-section |
| **Vendor IV methodology** | **UNKNOWN** | Unpublished. IV is a vendor measurement, not a reconstructible quantity |
| **Announcement-of-announcement** | **UNKNOWN** | No column records when a reporting date was first published, so `days_to_next_earnings` is not built |

`UNKNOWN` appears four times and is not resolved by assumption anywhere.

---

## 5. Cross-sectional and time-series transform audit

Every fitted or aggregating operation in `src/quant/`, with its scope:

| Operation | Location | Scope | Verdict |
|---|---|---|---|
| model `.fit()` | linear, trees | **per training fold** | correct |
| `FoldImputer` median + scale | `models/base.py` | **per training fold** | correct — constructed inside the fold loop, so hoisting it is structurally impossible |
| k-means regime fit | `regime/__init__.py` | **expanding window**, labels the next block only | correct |
| winsorise → z-score | `features/cross_section.py` | **per date**, within PIT universe | correct |
| rank (`pct=True`) | `features/cross_section.py` | **per date**, within PIT universe | correct |
| rank label | `labels/__init__.py` | **per date**, within PIT universe | correct |
| `qcut` quantile buckets | `backtest/engine.py` | **per rebalance date** | correct |
| rolling std / mean / rank | `features/price.py`, `macro.py` | **backward window**, `min_periods` = full | correct |
| trailing-median liquidity | `pit/universe.py` | **backward 3 snapshots** | correct |

No global fit, no PCA, no target encoding, no feature selection anywhere. **28
features require fitting; all 28 are the per-date cross-sectional ranks**, a
scope strictly narrower than a fold.

Cross-sectional transforms take the universe **explicitly**;
`cross_sectional_frame` raises without it rather than defaulting to whatever
rows are loaded.

---

## 6. Walk-forward audit

8 expanding folds, 252-session validation, purge 21 + embargo 5 = **26-session
gap**, holdout **2025-08-28 → 2026-08-28** (252 sessions).

Verified programmatically by the preflight:

* `no_fold_reaches_holdout` — every fold ends strictly before the holdout. Last
  validation ends **2025-05-09**, 111 sessions clear.
* `folds_chronological_and_purged` — chronological, non-overlapping, gap ≥ 26 everywhere.
* `no_random_splitter` — AST scan of 53 modules finds no `train_test_split`,
  `KFold`, `ShuffleSplit`, `GridSearchCV` or relatives imported or called.

Per-fold train/validation boundaries, observation counts, symbol counts and
timings are in `study.json` under `fold_rows`.

---

## 7. Model-selection bias

Answered honestly:

* **How were the 17 configurations chosen?** Fixed in
  `models/factory.py::default_specs` before any result was seen — a complexity
  ladder from zero-prediction to an over-parameterised control.
* **Were configurations added after seeing results?** Yes, once. The 17-model
  ladder replaced an earlier 12-model set, adding `ridge_strong`, `extra_trees`,
  `gradient_boosting_deep`, `baseline_earnings_surprise` and
  `baseline_iv_premium`. The additions were motivated by *coverage* (an
  overfitting control, a second regularisation strength, one baseline per new
  data source), not by observed scores — but the earlier results had been seen,
  so this is disclosed rather than claimed clean.
* **Were feature sets changed after seeing results?** No.
* **Were hyperparameters tuned on validation?** **No.** Every value is a
  conservative default; no search was run.
* **Is the best model selected on the data it is evaluated on?** **Yes.** The
  leaderboard ranks by validation IC and the top row is called "best". That is
  selection on the evaluation set, and it is precisely why a holdout exists.

**Multiple-testing exposure: 17 configurations × 2 targets = 34 evaluations**,
plus the earlier 12-model run on the same folds. The deflated Sharpe already
rejected every candidate at 17 trials; the true trial count is higher.

---

## 8. Cost-model audit

| Component | Assumed or observed | Included |
|---|---|---|
| Commission | assumed, 1 bp of notional | yes |
| Half-spread | **ASSUMED** — the dataset carries no bid/ask | yes |
| Market impact | modelled, `coef · sqrt(traded / daily dollar volume)` | yes |
| Slippage beyond spread + impact | not modelled | **no** |
| Borrow cost on the short leg | not modelled | **no** |
| Turnover | computed per rebalance from weight deltas | yes |

Costs are charged **per rebalance on traded notional**, not deducted annually;
a position held unchanged is free.

**Not modelled, and it matters:** the short leg of a dollar-neutral book incurs
borrow cost, which for a 20×/year-turnover book on mid-caps is not negligible.
Its absence makes every net figure **optimistic**. Recorded here rather than
buried.

Sensitivity is reported at **1, 3, 5, 10 and 20 bp** — the contract pre-registers
**10 bp** as primary, which is neither the most nor least favourable.

Impact behaves correctly with size: at \$1M capital total cost is 8.7 bp; at
\$500M it is 66.8 bp, dominated by impact. Capacity is therefore a separate
question from Sharpe and is not claimed.

---

## 9. Regime robustness — advisory failure

Over 625 observation dates:

| Regime | Dates | Usable? |
|---|---|---|
| low-volatility bull | 426 | yes |
| high-volatility bull | 136 | yes |
| stress | 34 | **no** |
| high-volatility bear | 19 | **no** |
| low-volatility bear | 10 | **no** |

Three of five regimes fall below the 60-date threshold. **Bear-market evidence
rests on 29 dates in total.** The preflight raises this as an advisory: it does
not invalidate a result, but it bounds what the result covers. Any claim about
bear behaviour is anecdote.

This is a property of the 2014–2026 sample, not of the code, and cannot be
fixed by method.

---

## 10. Feature importance is diagnostic only

No feature was added, removed or reweighted on the basis of validation-period
importance. The ablation study and the importance-stability comparison called
for in the audit brief are **deferred**: running them now would consume the same
validation folds a second time and deepen the selection bias already recorded
in §7. They belong to the next study, on the fixed pipeline, with their trial
count declared in advance.

---

## 11. What changed in this audit

| Change | Reason |
|---|---|
| `_asof_aligned` in options and earnings | `merge_asof` index reset caused cross-row and cross-time value assignment |
| 3 regression tests with multi-symbol, symbol-major, shuffled panels | The old fixtures could not fail |
| `BacktestConfig.execution_lag_periods`, default 1 | Positions were formed at the close the signal was computed from |
| `check_contamination` two-build probe | Turns the one-off investigation into a standing gate |
| AST-based random-splitter detection | The substring version flagged its own banned-token list |
| `src/quant/audit/`, `src/quant/study/holdout.py` | Preflight gates and a single-use, refusing runner |

Nothing was re-run. No model was trained. The holdout was not touched.

---

## 12. What must happen before a holdout is defensible

1. Re-run the study on the fixed pipeline, with the trial count declared in
   advance and recorded in `RESEARCH_LEDGER.md`.
2. Confirm the new results with `execution_lag_periods = 1`.
3. Select **one** primary candidate from the new evidence and freeze it in
   `HOLDOUT_CONTRACT.md`.
4. Run `python -m src.quant.study.holdout --preflight` and clear every blocking
   gate.
5. Only then `--run --confirm-preregistered`.

The current answer to "is there a robust signal?" is **not yet measured**. The
apparatus for measuring it is now, as far as this audit can establish, correct.
