# Model Registry

> No model becomes production merely because it has the highest backtest
> return.

The registry does not store a status field for a human to set. `promote()`
evaluates `PROMOTION_GATES` and **refuses** a transition whose evidence is
absent, returning the specific unmet requirements.

---

## 1. The gates

| Target status | Additionally requires | The failure it blocks |
|---|---|---|
| `experimental` | nothing | — |
| `validated` | walk-forward folds · written methodology · baseline comparison | "it looked good on the training set" |
| `production_candidate` | + cost-aware backtest · factor attribution · **validation numbers clearing `CANDIDATE_THRESHOLDS`** | a strong IC whose turnover eats it; momentum in disguise described as new; **a complete evidence bundle stating the model loses money** |
| `production` | + holdout metrics · regime-stability breakdown · **numbers clearing `PRODUCTION_THRESHOLDS`** | selection on the same folds it is reported against; a model that worked only in the dominant regime |
| `retired` | nothing | — stopping is always allowed |

```python
registry.promote("ridge@1.0:fwd_ret_21", "production")
# PromotionRefused: ridge@1.0:fwd_ret_21 cannot become production:
#   missing metrics on the untouched holdout period,
#   performance broken out by market regime.
#   A model is promoted on evidence, not on the best backtest number.
```

### Two kinds of refusal, and why both are needed

`PROMOTION_GATES` asks whether the required evidence **exists**. The threshold
tables ask what that evidence **says**. A model can satisfy the first and fail
the second, and that is the ordinary case.

Until EXP-004 the numeric bars were only consulted at `production`, and they
read `holdout_metrics` — which is empty by design while the holdout is locked.
The consequence was that a model could arrive with a full, honest evidence
bundle saying it loses money and still be labelled a *production candidate*.

`CANDIDATE_THRESHOLDS` closes that, on validation evidence alone:

| Bar | Source | Why |
|---|---|---|
| \|IC t\| ≥ 2.0 | `walk_forward` | Below this the validation IC is not distinguishable from zero; a holdout cannot confirm what development never established |
| net Sharpe > 0 | `backtest` | After costs and the execution lag |
| **gross Sharpe > 0** | `backtest` | Before any cost. A negative gross Sharpe means the ranking does not survive becoming a book, so no cost assumption can rescue it |
| beats best baseline | `baseline_comparison` | A learned model losing to a free published factor has rediscovered it expensively |

An unrecorded value counts as **unmet** — absent evidence is not passing
evidence. `eligible_for` applies the same bars, so it can never advertise a
status that `promote()` would refuse.

```python
registry.promote("random_forest@2.0:fwd_rank_21", "production_candidate")
# PromotionRefused: supplies the required evidence but its validation numbers
#   do not clear the candidate thresholds:
#   ic_t_stat = 1.911; net_sharpe = -0.598; gross_sharpe = -0.276
```

### Current contents

| | |
|---|---|
| Entries | 71 |
| `experimental` | 37 — 34 from EXP-004 (`@2.0`), 3 from EXP-001 |
| `retired` | 34 — EXP-002 (`@1.0`), **VOID**, retained not deleted |
| `validated` / `production_candidate` / **`production`** | 0 / 0 / **0** |

Every EXP-004 entry is eligible for `validated` and nothing beyond it. A study
is registered under its own `version` so a later run can never overwrite an
earlier one's record — `key` is `model_id@version:label`, and a superseded
study is retired with a reason rather than replaced.

---

## 2. What each entry stores

**Identity** — model id, version, task, label, fingerprint (hyperparameters and
seed, hashed).

**Reproducibility** — dataset version, source dataset manifests, training range,
seed, git commit, and the versions of every dependency that can change a
prediction (numpy, pandas, pyarrow, scikit-learn, scipy, Python).

**Evidence** — walk-forward results, baseline comparison, backtest metrics,
factor attribution, holdout metrics, regime stability.

**Context** — `experiments_run`.

### Why the experiment count is stored

The best of forty experiments is an optimistically biased estimate of that
model's true performance. A registry that stores only the winner destroys the
information needed to discount it, so `experiments_run` travels with the entry
and appears in the leaderboard beside the metric it should temper.

---

## 3. The leaderboard shows what argues against each model

Ordered by out-of-sample mean IC, but every row carries the figures that can
overturn that ordering:

| Column | Why it is there |
|---|---|
| `mean_ic`, `ic_t_stat` | the claim, and whether it is distinguishable from zero |
| `fold_ic_positive_rate` | a model at 0.05 in every fold beats one averaging 0.05 from +0.20 and −0.10 |
| `net_sharpe`, `annualised_turnover`, `cost_share_of_gross` | whether it survives being traded |
| `alpha_t_stat`, `alpha_significant` | whether it is anything more than a factor |
| `experiments_run` | how many were tried before this one |
| `eligible_for` | which statuses its evidence would already support |

A model with a lower IC and a fold-positive rate of 0.9 is usually the better
choice than one at 0.75, and the table has to make that visible rather than
sorting it away.

---

## 4. Storage

`data/research/models/registry.json`, written atomically — a half-written
registry is worse than none. Round-tripping is asserted in
`tests/quant/test_models.py`.

---

## 5. Reading it

```bash
curl localhost:8000/api/ml/registry | jq '.leaderboard'
```

`promotion_gates` is emitted verbatim from the code, so what the UI shows as a
requirement is exactly what is enforced.
