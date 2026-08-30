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
| Audience | Analysts reading `/quant` and `/terminal/models`, not an automated trading path |
| Registry contents | 71 entries — 0 production, 0 candidates, 34 retired VOID |
| Holdout | 252 sessions, **never opened**; firewall enforces this at fit time |

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

---

## 8. EXP-005 addendum — the sources, and whether they earn their place

EXP-004 established that the corrected pipeline finds nothing in the feature set
it had. That leaves two readings — the signal is not there, or the feature set
never contained it — and EXP-005 separates them by adding one data source at a
time to a fixed price-and-volatility base.

### What was added to the model's inputs

| Family | Source | Point-in-time basis | Residual risk |
|---|---|---|---|
| `estimates` | `eps_estimate`, `sales_estimate` — 7.06M weekly vintages each | **Observation-dated.** A row says what consensus was that Sunday. No gate needed | Revisions NULL across a fiscal rollover, by design |
| `fundamentals` | `income_statement`, `balance_sheet_*`, `cash_flow_statement` | **Period-keyed.** Gated on `earnings_calendar`; 77,277 of 196,879 quarters dropped for want of an announcement | **UNQUANTIFIED restatement risk** |
| `options` | `option_chain`, `volatility_history` | Observation-dated | Coverage begins 2019-02-09 |

Feature count went 67 → 103 registered, 39 → 57 used.

### What the options schema cannot support

Several commonly-cited options signals are **not computable** from this source
and are deliberately not implemented rather than approximated:

* put/call **volume** imbalance — no traded volume column
* **open-interest** imbalance — no open interest column
* dealer **gamma exposure** — needs positioning, which needs OI
* **unusual activity** — needs a volume baseline

What is available: IV level and rank, term structure, skew, per-contract Greeks,
and bid/ask spread as a liquidity proxy. Claiming the others would mean
inventing them.

### The restatement caveat, stated plainly

The statement tables hold one row per (symbol, period) and **no vintage column**.
A restatement overwrites the original irrecoverably. Announcement-gating fixes
*when* a figure becomes readable and does nothing about *which version* is read.
The magnitude cannot be measured from the source.

Consequently: every `fund_*` feature carries `restatement_risk=UNQUANTIFIED`,
they are isolated in EXP-005's arm F, and **any promotion leaning on them must
confront that label rather than inherit it silently**. `src/panel/fundamentals.py`
— SEC companyfacts, with real `filed` dates — is the correct long-term source and
wiring it to the quant panel at scale is open work.

---

## 9. What must still not be claimed

Unchanged from §6 and worth repeating after a study that added three data
sources: **more data is not evidence of more signal.** If the ablation shows a
family does not improve on the base, the honest conclusion is that the family
does not help *in this universe, at this horizon, with these models* — and the
correct action is to stop paying to store it, not to search for a model
specification that makes it look useful.
