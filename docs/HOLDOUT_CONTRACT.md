# HOLDOUT CONTRACT

A binding pre-registration. It is written **before** the holdout is opened and
is not editable afterwards; the preflight hashes it and the receipt records that
hash, so a contract edited after the fact is detectable.

**STATUS: NOT ARMED.** No primary candidate is registered, because the
pre-holdout audit invalidated the evidence that would have selected one. See
`docs/PRE_HOLDOUT_AUDIT.md` §2. This document defines the terms that will apply
when a candidate exists.

---

## HOLDOUT RANGE

| Field | Value |
|---|---|
| Start | **2025-08-28** |
| End | **2026-08-28** |
| Sessions | **252** |
| Universe | `liquid` — top 250 by 3-month trailing-median dollar volume, monthly |
| Observation stride | 5 sessions |
| Expected observations | ~250 symbols × ~50 rebalances |
| Last training-side date | 2025-05-09 (last fold validation end) |
| Separation | 111 sessions between the last validation date and the holdout |

The holdout was carved from the trading calendar **before any fold was
generated**, by `build_plan`, and is returned by no iterator in the validation
package. Reaching it requires an explicit call.

---

## PRIMARY CANDIDATE

**None registered.**

The candidate that would otherwise have been selected — `gradient_boosting` on
`fwd_rank_21`, IC +0.0295, t +2.70 — was fitted on a feature matrix in which 12
of 39 columns carried other rows' values, some from later dates. That result is
void.

When a candidate is registered it must be named here as exactly one:

```
model_id:          <one model>
label:             <one target>
feature_set:       <explicit list, hashed>
hyperparameters:   <explicit, no search>
seed:              <integer>
dataset_version:   <ds-...>
execution_lag:     1 rebalance period
```

**One candidate. Not a shortlist.** A shortlist evaluated on the holdout is a
selection procedure run on the holdout, which is the thing a holdout exists to
prevent.

---

## PRIMARY METRIC

**Mean cross-sectional rank IC over the holdout, with a Newey-West t-statistic
at `ceil(horizon / stride) − 1` lags.**

One metric, declared in advance. Every other number below is a **secondary
diagnostic** and may not be substituted for the primary if the primary
disappoints.

### Secondary diagnostics (reported, never decisive)

* net Sharpe at 1, 3, 5, 10, 20 bp half-spread — **10 bp is the reference**
* gross Sharpe, annualised turnover, cost share of gross
* six-factor alpha intercept and its Newey-West t
* directional edge against the base rate
* `rmse_vs_zero`
* per-regime breakdown, with the imbalance caveat below
* maximum drawdown, hit rate, profit factor

---

## SUCCESS

All of the following, on the holdout, with no exceptions:

1. Mean rank IC **> 0** with Newey-West **|t| > 2.0**.
2. Mean rank IC **exceeds every free baseline** measured on the same holdout —
   momentum, reversal, low-volatility.
3. Net Sharpe **> 0 at a 10 bp half-spread** with `execution_lag_periods = 1`.
4. The sign of the IC **matches the sign observed in validation**. An
   equal-and-opposite result is not a success at any magnitude.

Success promotes the model to `production_candidate` — **not** to `production`.
Production additionally requires the gates in `docs/model-registry.md`.

## FAILURE

Any of:

* Mean rank IC ≤ 0.
* Newey-West |t| ≤ 2.0.
* Net Sharpe ≤ 0 at 10 bp.
* IC below the best free baseline on the same holdout.

Failure is recorded in `RESEARCH_LEDGER.md` and the model is marked `retired`
with the reason. **The pipeline is not repaired and re-run against the same
holdout.**

## INCONCLUSIVE

* Mean rank IC > 0 but |t| ≤ 2.0, **or**
* net Sharpe within ±0.10 of zero at 10 bp.

Inconclusive is recorded as inconclusive. It is **not** rounded toward success,
and it does not license a second holdout run. The correct response is a longer
sample or a different question — both of which require new data, not a new
analysis of this one.

---

## WHAT IS FROZEN

At the moment `--run --confirm-preregistered` is accepted, the following are
fixed and the receipt records a SHA-256 over them:

* dataset version and content hash
* the exact feature list
* model identity and every hyperparameter
* random seed
* transaction-cost model and all its parameters
* `execution_lag_periods`
* universe definition, size and liquidity screens
* quantile count and weighting scheme
* this contract's own text
* the git commit

## AFTER THE HOLDOUT IS OPENED

- **NO** model changes
- **NO** feature changes
- **NO** hyperparameter changes
- **NO** cost-model changes
- **NO** universe changes
- **NO** threshold changes
- **NO** metric substitution
- **NO** re-running for any reason
- **NO** researcher-driven iteration on holdout results

If something fails, the failure is the result. It is recorded, not repaired.

Any subsequent experiment that touches this period is **not** a holdout test and
must be labelled an in-sample refit in the ledger.

---

## SINGLE USE

`src/quant/study/holdout.py` writes `data/research/holdout/RECEIPT.json` on
execution. Its existence blocks every later run. There is no `--force`; the
absence is deliberate and the code says so.

The receipt is written **before** any holdout metric is computed, so an
interrupted run still spends the holdout. That is intentional: a run that got
far enough to load the data has seen it.

---

## KNOWN LIMITATIONS THAT BOUND ANY RESULT

Acknowledged in advance so they cannot be raised afterwards to explain away an
unfavourable outcome:

1. **Regime imbalance.** Across 625 validation-era dates: low-volatility bull
   426, high-volatility bull 136, stress 34, high-volatility bear 19,
   low-volatility bear 10. The holdout period is one year and will not fix this.
   **No claim about bear-market behaviour is admissible from this experiment.**
2. **Borrow cost is not modelled.** Every net figure is optimistic for a
   dollar-neutral book.
3. **Half-spread is assumed, not observed.** The dataset has no bid/ask.
4. **Universe is large-cap.** Top 250 by dollar volume; SIVB ranked 614th in
   February 2023 and is absent. The study understates outright-failure frequency.
5. **Restatement is undetectable.** `eps_history` carries one value per period
   with no vintage column.
6. **One year is 252 sessions and ~50 rebalances.** A Sharpe estimated on 50
   observations has a wide standard error; the minimum-track-record-length
   diagnostic will be reported alongside.

---

## SIGNATURES

| Field | Value |
|---|---|
| Contract version | 1 |
| Written at | 2026-08-30 |
| Armed | **NO** |
| Primary candidate | none — see PRE_HOLDOUT_AUDIT.md §2 |
| Holdout spent | no |
