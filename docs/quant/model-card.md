# Model Card — OmniSignal Cross-Sectional Return Models

A model card for a family of models, none of which is currently in production.
That is the finding, not a gap in the document.

---

## 1. Status

| Field | Value |
|---|---|
| Intended use | Cross-sectional research: ranking a liquid US equity universe over a 21-session horizon |
| Deployment status | **Not deployed.** No model has passed the registry's `production` gate |
| Registry gate outstanding | holdout metrics and regime-stability evidence for any candidate |
| Audience | Analysts reading `/terminal/models`, not an automated trading path |

There is no live-order path anywhere in this codebase, and none is planned in
this phase.

---

## 2. Intended and unintended use

**Intended.** Comparing the out-of-sample rank information in a set of features
against baselines that are free. Answering "does this add anything over
momentum" with a number and a confidence interval.

**Not intended, and the system will not support it:**

* A buy/sell recommendation. The models output an expected cross-sectional
  rank, not a decision.
* A position size. Prediction and allocation are separate layers by design.
* Anything at a horizon other than the one a model was fitted for.
* Anything outside the liquidity-ranked universe it was trained on. A top-250
  by dollar volume universe says nothing about micro-caps.
* A statement about a single name. These are cross-sectional models; the unit
  of validity is the ranking, not the individual prediction.

---

## 3. Training data

| Property | Value |
|---|---|
| Source | 4 local Dolt clones + Kenneth French library |
| Universe | `liquid` — top 250 by 3-month trailing-median dollar volume, monthly |
| Universe members ever | 998, of which 793 are absent from the final snapshot |
| Period | 2014-04-01 onward (clamped by corporate-action coverage) |
| Observation stride | 5 sessions |
| Features | 39 (28 cross-sectional ranks + 11 macro) |
| Labels | `fwd_ret_21`, `fwd_rank_21` |
| Splits | 8 expanding walk-forward folds, 252-session validation, 26-session gap |
| Holdout | final 252 sessions, untouched |

**Deliberately excluded from training:** `earnings.income_statement` (no filing
date), the Fama-French factors (revised; attribution only), any macro series
subject to revision (CPI, unemployment, GDP).

---

## 4. Evaluation

Primary metric is **rank IC** — the per-date Spearman correlation between the
prediction and the realised forward return — with a **Newey-West** t-statistic
correcting for the label overlap that a 21-session horizon at a 5-session
stride creates (4 lags; ignoring them roughly doubles the naive t).

Reported alongside, always:

* `rmse_vs_zero` — above 1.00 means worse magnitude accuracy than predicting nothing
* `directional_edge` — accuracy minus the majority-class base rate, never against 50%
* `train_ic_gap` — the overfitting diagnostic
* `fold_ic_positive_rate` — consistency across folds
* net Sharpe at four spread assumptions
* six-factor alpha with its t-statistic
* Deflated Sharpe against the trial count
* Probability of Backtest Overfitting

---

## 5. Known limitations

**Universe.** Liquidity-ranked, not an index. At size 250 it is large-cap: SIVB
ranked 614th by dollar volume in February 2023 and is therefore absent. The
study understates the frequency of outright failure in the broader market.

**Corporate actions.** Split records begin 2014-03-28, which is why the study
starts there and not at the 2011 start of price history. 3.2 of 15.6 available
years are unused.

**Earnings coverage.** `earnings_calendar` starts 2020-01-22, so earnings
features are structurally absent from the first four folds.

**Options coverage.** Chain and volatility history start 2019-02-09 with
irregular cadence (48 distinct dates in 2019 against 259 in 2025). Mean option
feature coverage across the full period is 0.34.

**Restatement.** `eps_history` holds one value per period. If a figure was
later restated, the restated value is what is read; there is no vintage column
and this cannot be detected from within the dataset.

**Vendor measurements.** Implied volatility and Greeks come from an unpublished
model. They are measurements, not reconstructible quantities.

**Costs.** The half-spread is an assumption, not an observation — the price
data carries no bid/ask. It is the largest single uncertainty in every net
figure, which is why results are reported across a sweep rather than at one
value.

**Regime imbalance.** Measured regime distribution over 625 observation dates:
low-volatility bull 426, high-volatility bull 136, stress 34, high-volatility
bear 19, low-volatility bear 10. Any statement about bear-market behaviour rests
on 29 dates and should be treated as anecdote.

---

## 6. What must not be claimed

* That a feature **causes** returns. Coefficients and split-gain importances are
  associations within a fitted model.
* That a positive backtest is **alpha**, unless the six-factor intercept is
  significant — and `backtest/attribution.py` is the only place that is computed.
* That directional accuracy above 50% is skill. The base rate is the comparison.
* That in-sample performance says anything about future performance.
* That the models are **validated** in any sense beyond the specific universe,
  period, horizon and cost assumptions recorded here.

---

## 7. Reproducing

```bash
python -m scripts.quant.local_backfill --stage all
python -m scripts.quant.backfill --stage universe --universe-size 250
python -m scripts.quant.study --start 2014-04-01 --all-labels --seed 0
```

`study.json` records the git commit, dependency versions, machine profile, seed
and dataset content hash. A rebuild that produces a different hash means either
the raw partitions or the feature code changed, and `source_datasets` says which.
