# Experiment Ledger

Every configuration evaluated, including the ones that lost. The population is
recorded rather than the maximum, because the best of N experiments is an
optimistically biased estimate of that configuration's true performance, and a
ledger that stores only the winner destroys the information needed to discount
it.

---

## 1. What is recorded per run

`data/research/reports/study.json` carries, for every label:

| Field | Content |
|---|---|
| `dataset` | version, content hash, rows, symbols, dates, source manifests, guard report, per-column coverage |
| `machine` | CPU brand, physical/logical cores, memory, platform, Python version |
| `git_commit` | resolved HEAD at run time |
| `dependency_versions` | numpy, pandas, pyarrow, scikit-learn, scipy, Python |
| `seed` | the single seed every model was constructed with |
| `walk_forward_plan` | every fold's train/purge/validation boundaries, embargo, holdout |
| `fold_rows` | observations and symbols per fold, so a thin fold is visible |
| `leaderboard` | one row per configuration, sorted, **nothing filtered** |
| `experiment_distribution` | best, median, worst, count above zero, and the population size |
| `experiments.results` | full per-model record including failures |
| `backtests` | gross and net metrics per model |
| `cost_sensitivity` | net Sharpe at 1, 5, 10, 20 bp half-spread |
| `factor_attribution` | six-factor regression per model |
| `regime_performance` | metrics broken out by regime, per model |
| `significance` | deflated Sharpe and minimum track record length |
| `probability_of_backtest_overfitting` | CSCV over all configurations |
| `timing` | wall clock, worker count, frame size, cores used |

---

## 2. The model ladder

Fixed in `src/quant/models/factory.py::default_specs` **before** any result was
seen. The ordering is the argument: each rung has to earn its place over the one
below it.

| Level | Configurations |
|---|---|
| 0 | `baseline_zero` |
| 1 | `baseline_historical_mean` |
| 2 | `baseline_momentum`, `baseline_reversal`, `baseline_low_volatility`, `baseline_earnings_surprise`, `baseline_iv_premium` |
| 3 | `ols`, `ridge`, `ridge_strong`, `lasso`, `elastic_net` |
| 4 | `gradient_boosting`, `random_forest`, `hist_gradient_boosting`, `extra_trees` |
| — | `gradient_boosting_deep` — the overfitting control |

### The two deliberate controls

**`ols`** carries no regularisation. On a wide, correlated matrix it is
*expected* to validate worse than ridge, and that gap is the cleanest available
demonstration that regularisation is doing real work rather than being assumed
to.

**`gradient_boosting_deep`** (depth 8, 500 trees, learning rate 0.1, no
subsampling, `min_samples_leaf=5`) is built to overfit. Its train-versus-
validation IC gap demonstrates that the diagnostic *works on a model designed to
trigger it*, which is what makes the diagnostic trustworthy when applied to the
others.

### The two new baselines

`baseline_earnings_surprise` and `baseline_iv_premium` pass through a single
cross-sectionally ranked feature, unfitted. They exist so that "does the model
add value over the options data" and "over the earnings data" are separate,
answerable questions rather than a single undifferentiated comparison against
momentum.

---

## 3. Hyperparameters, and why they were not tuned

Every value is a conservative default fixed in advance:

| Model | Setting | Reason |
|---|---|---|
| ridge | α = 10 | moderate shrinkage |
| ridge_strong | α = 200 | tests whether *more* shrinkage helps, which on a low-signal target it often does |
| lasso / elastic net | α = 0.0005 | selects without eliminating everything |
| gradient boosting | depth 3, lr 0.03, subsample 0.7, leaf 50 | standard low-signal-to-noise defaults |
| random forest | depth 8, leaf 50, max_features 0.5 | variance reduction |
| extra trees | depth 10, leaf 50 | random splits — tests whether optimised splits are fitting noise |

Tuning these against the validation folds and then reporting those folds would
consume the very data that makes the report meaningful. The honest alternatives
were a nested inner-loop search (expensive, and the outer estimate is still
biased by the search) or fixed defaults reported as fixed. The second was
chosen, and it is recorded here so nobody later mistakes these numbers for
optimised ones.

**Consequence, stated plainly:** these results are a lower bound on what tuned
models could achieve. They are not a claim that no configuration performs
better. What they *are* is an unbiased estimate of what these configurations
achieve out of sample.

---

## 4. Determinism

Seed 0 throughout. Every model is `n_jobs=1`, and parallelism is placed across
models rather than inside them — threaded accumulation reorders floating-point
operations, and two runs with the same seed would then differ in the last bits.

`tests/quant/test_models.py::test_same_seed_gives_identical_predictions`
asserts bit-identical predictions across the whole model set.

Reproducing a run:

```bash
python -m scripts.quant.study --start 2014-04-01 --all-labels --seed 0
```

The dataset's `content_hash` should match; if it does not, either the raw
partitions changed or the feature code did, and the manifest's
`source_datasets` says which.

---

## 5. Reading the leaderboard honestly

Four columns matter more than the sort order:

* **`train_ic_gap`** — mean train IC minus mean validation IC. Large and
  positive means the model memorised the training fold.
* **`fold_ic_positive_rate`** — a model at 0.05 in every fold is a different
  proposition from one averaging 0.05 out of +0.20 and −0.10.
* **`rmse_vs_zero`** — above 1.00 means it predicts magnitude worse than
  predicting nothing, whatever its ordering does.
* **`experiments_run`** — the population the winner was selected from.

And two that can overturn everything above them: **`net_sharpe`** against
`gross_sharpe`, and **`alpha_t_stat`** from the six-factor regression.
