# Validation Methodology

Why the split looks the way it does, and what each part of it defends against.

---

## 1. Random splits are invalid here, twice over

A random train/test split assumes rows are exchangeable. These are not, for two
independent reasons — and either alone is disqualifying.

**Time.** Training on 2022 and testing on 2018 asks whether a model fitted with
knowledge of the future predicts the past. Nobody has that question.

**Overlap.** A 21-session label sampled every 5 sessions means consecutive
observations of the same name share **16 of their 21 days**. A random split
therefore puts rows sharing 76% of their outcome on both sides of the boundary,
so the "test" set is substantially the training set. This is the single largest
source of illusory skill in equity ML, and it produces results that look
excellent and reproduce nowhere.

---

## 2. The geometry

```
|<----------- train (expanding) ----------->|<-purge->|<-emb->|<-- validation -->|
                                        train_end                        252 sessions
```

```mermaid
gantt
    title Expanding walk-forward, 21-session label
    dateFormat YYYY-MM
    axisFormat %Y
    section Fold 0
    train        :2014-04, 32M
    purge+embargo:crit, 2016-12, 2M
    validate     :active, 2017-02, 12M
    section Fold 3
    train        :2014-04, 68M
    purge+embargo:crit, 2019-12, 2M
    validate     :active, 2020-02, 12M
    section Fold 7
    train        :2014-04, 116M
    purge+embargo:crit, 2023-12, 2M
    validate     :active, 2024-02, 12M
    section Holdout
    never touched:done, 2025-02, 12M
```

**Expanding, not rolling, by default.** It is what a live system does — retrain
on everything available. `scheme="rolling"` is implemented and tested; when
rolling beats expanding, the honest reading is that the relationship changed,
not that the model improved.

---

## 3. Purge and embargo are different things

| Parameter | Covers | Size |
|---|---|---|
| **Purge** | the label's own reach — a label observed on the last training day is realised `horizon` sessions later | = label horizon (21) |
| **Embargo** | serial correlation in features and returns, which persists past the horizon | 5 sessions |

They are separate parameters, not one combined number, because a result's
sensitivity to each is a different question. Combined gap: **26 sessions**.

Following López de Prado, *Advances in Financial Machine Learning* (2018), ch. 7.

`assert_split_is_purged` verifies the gap fold by fold, and
`test_an_insufficient_gap_is_refused` proves the check fails when the gap is
too small.

---

## 4. The holdout is not a fold

`WalkForwardPlan.holdout` is carved off **before** any fold is generated,
returned by no iterator, and evaluated by nothing in the validation package.
Reaching it requires an explicit call, so using it is a decision that appears
in the transcript.

Once used it is spent. Selection inevitably consumes the validation folds —
that is what selection is — and the holdout exists so one period remains that
no decision touched.

**Status: unspent.** No model has passed the registry gates that would justify
spending it.

---

## 5. Metrics, and why they are reported together

| Metric | Answers | Fails alone because |
|---|---|---|
| RMSE / MAE | magnitude accuracy | dominated by unpredictable variance; nearly every model loses to zero |
| `rmse_vs_zero` | is it better than predicting nothing | — this is the honest framing of the above |
| directional accuracy | sign agreement | must be read against the **base rate**, never 50% |
| `directional_edge` | accuracy minus majority class | the only one of the three readable alone |
| **rank IC** | ordering within each date's cross-section | the metric a long/short book needs |
| `ic_ir` | mean IC over its dispersion | the closest thing a signal has to a Sharpe |
| `train_ic_gap` | did it memorise the training fold | **the overfitting diagnostic** |
| `fold_ic_positive_rate` | consistency | distinguishes 0.05-every-fold from +0.20/−0.10 |

### The Newey-West correction

Overlapping labels make consecutive IC observations dependent, and the naive
t-statistic on them is inflated — typically by about a factor of two. Lags are
`ceil(horizon / step) − 1`: at horizon 21 and stride 5 that is **4 lags**.

The implementation is `src/research/cross_section.newey_west_tstat`, **reused
rather than rewritten**, so the factor-lab surface and the ML surface cannot
report different significance for the same series.

---

## 6. Corrections for having tried many things

| Test | Question |
|---|---|
| Deflated Sharpe | does it beat the best of *N* zero-skill runs? |
| Probability of Backtest Overfitting | does in-sample selection predict out-of-sample rank? |
| Minimum Track Record Length | how many periods before this Sharpe separates from zero? |
| Blocked bootstrap | interval on IC allowing for dependence |

The bootstrap uses a **moving-block** resample. An i.i.d. bootstrap on
dependent observations produces an interval far too narrow — understating
uncertainty in exactly the flattering direction.

Deflated Sharpe validated in `tests/quant/test_validation.py`: the best of 60
pure-noise runs has a Sharpe of ~1.17 and is significant at `trials=1`, and
correctly **insignificant** at `trials=60`.

**Not implemented:** White's Reality Check and Hansen's SPA. Both need a
stationary bootstrap with a correctly chosen block length; getting it wrong
silently changes the answer, and a misimplemented significance test is worse
than none because it launders the same bias through a formula that looks
rigorous.

---

## 7. What a result has to clear

1. Mean rank IC distinguishable from zero at |t| > 2 **after** Newey-West.
2. Better than the best free baseline — momentum, reversal, low-volatility,
   earnings surprise, IV premium.
3. `train_ic_gap` small enough that the model is not simply memorising.
4. `fold_ic_positive_rate` high enough that it is not one lucky fold.
5. Net Sharpe positive at a **10 bp** half-spread, not only at 1 bp.
6. A six-factor alpha intercept, or an explicit description as a return difference.
7. Deflated Sharpe significant against the **actual** trial count.
8. Performance not confined to a single regime.

Failing any of these is a finding and is reported as one.

---

## 8. The twenty failure modes, and where each is controlled

Added for EXP-005. "fires" marks a control that has actually caught something in
this repository — six have, which is the argument for keeping the rest.

| # | Failure | Controlled by | Fired? |
|---|---|---|---|
| 1 | Feature leakage | Truncation invariance at 3+ cutoffs, real builder | yes |
| 2 | Survivorship bias | Whole-market monthly cross-sections + universe guard | yes |
| 3 | Look-ahead via fundamentals | `earnings_calendar` announcement gate | yes |
| 4 | Look-ahead via options | Backward as-of, 21-session staleness cap | — |
| 5 | Publication vs period-end | Catalog class `PUBLICATION_LAGGED` | **yes** |
| 6 | Restatement contamination | **UNRESOLVED** — see §10 | open |
| 7 | Universe selection leakage | Trailing dollar volume only; `in_universe` per date | — |
| 8 | Corporate-action leakage | Returns from unadjusted prices + ex-dated actions | — |
| 9 | Normalisation leakage | `FoldImputer` fitted inside the fold loop | — |
| 10 | Target leakage | `require_chronological` on labels and price features | **yes** |
| 11 | Cross-sectional leakage | Ranks fitted per date within the PIT universe | — |
| 12 | Scaling outside the fold | As 9; fit scope asserted in `test_leakage.py` | — |
| 13 | Hyperparameter leakage | No search; fixed defaults in the frozen definition | — |
| 14 | Model-selection leakage | Primary target declared in advance; holdout untouched | — |
| 15 | Multiple-testing inflation | Cumulative ledger count; DSR against 139 | — |
| 16 | Cost optimism | 1/3/5/10/20 bp sweep; gross reported beside net | — |
| 17 | Turnover error | Turnover and cost share per model | — |
| 18 | Signal/execution timing | `execution_lag_periods >= 1`, enforced in `__post_init__` | **yes** |
| 19 | Regime-selection bias | 200-date floor; thin regimes report INSUFFICIENT | **yes** |
| 20 | Future data in rolling features | Row-order guard via `require_chronological` | **yes** |

---

## 9. The holdout firewall (EXP-005)

Before EXP-005 the holdout was defended at one entry point: the runner refused
to execute the holdout experiment unarmed. That did nothing about the way a
holdout actually gets spent — someone builds a panel that extends past the
cutoff, fits something, and sees the number before realising. By then it is gone.

`src/quant/study/firewall.py` moves the guard to where holdout **rows** meet
code. `FIREWALL.assert_clear` runs at the walk-forward plan and again on the
train and validation frames of **every fold, immediately before the fit**. A
breach raises `HoldoutBreach` — not a `ValueError`, deliberately, because a
breach is never something a caller should catch and continue past.

It lifts only when `docs/HOLDOUT_CONTRACT.md` is armed by a human editing a
tracked file, or through `FIREWALL.override(reason)`, which requires a reason and
logs at WARNING. There is **no environment variable**:
`QUANT_DISABLE_HOLDOUT_FIREWALL` raises if set, so a hopeful export fails loudly
rather than silently doing nothing.

`tests/quant/test_firewall.py` plants a corrupted plan whose last validation
window slides into the reserved period and asserts the fit is refused. A guard
that has never been shown to fire is a comment.

---

## 10. What is still open

**Restatement contamination is not solved.** The statement tables hold one row
per (symbol, period) and no vintage column, so a later correction overwrites the
original irrecoverably. Announcement-gating fixes *when* a figure becomes
readable; it does nothing about *which version* is read. The magnitude cannot be
measured from the source.

The mitigations are honest rather than sufficient: every affected feature is
marked `restatement_risk=UNQUANTIFIED`, they are isolated in EXP-005's arm F so
their contribution can be discounted separately, and any promotion leaning on
them has to confront the label. The real fix is `src/panel/fundamentals.py` —
SEC companyfacts carries a real `filed` date per fact and resolves each period to
the most recent filing visible on a given date — and wiring it to the quant panel
at scale is recorded as future work, not as done.
