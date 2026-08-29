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
| `production_candidate` | + cost-aware backtest · factor attribution | a strong IC whose turnover eats it; momentum in disguise described as new |
| `production` | + holdout metrics · regime-stability breakdown | selection on the same folds it is reported against; a model that worked only in the dominant regime |
| `retired` | nothing | — stopping is always allowed |

```python
registry.promote("ridge@1.0:fwd_ret_21", "production")
# PromotionRefused: ridge@1.0:fwd_ret_21 cannot become production:
#   missing metrics on the untouched holdout period,
#   performance broken out by market regime.
#   A model is promoted on evidence, not on the best backtest number.
```

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
