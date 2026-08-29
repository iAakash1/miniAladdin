# Modeling Methodology

What is predicted, from what, how it is validated, and what was fixed in
advance so that it could not be tuned afterwards.

---

## 1. The decisions made before any model ran

These are recorded here because the value of a research result depends on when
the decisions were made. A hyperparameter chosen after seeing validation
scores, or a model added once the others disappointed, produces a number that
looks like a measurement and is a selection.

| Decision | Fixed in advance | Where |
|---|---|---|
| Feature set | 16 per-symbol + 16 cross-sectional + 11 macro | `features/registry.py` |
| Feature *direction* hypothesis | recorded per feature before testing | `FeatureDefinition.direction` |
| Label set | 9 labels across 4 horizons | `labels/__init__.py` |
| Model set | 5 baselines + 4 linear + 3 tree | `scripts/quant/study.py::model_factories` |
| Hyperparameters | conservative defaults, never tuned on validation | `models/trees.py`, `models/linear.py` |
| Walk-forward geometry | expanding, 252-session validation, 756-session minimum train | `study.py` defaults |
| Purge and embargo | label horizon + 5 sessions | `walkforward.py` |
| Holdout | final 252 sessions, untouched | `build_plan` |
| Cost assumptions | 1 bp commission, 5 bp half-spread, sqrt impact | `backtest/costs.py` |

`Direction` is worth singling out. Each feature records the sign of its
*hypothesised* relationship before it is tested, so a factor that works with
the opposite sign is visibly a surprise rather than retroactively "what we
expected".

---

## 2. Features

Sixteen per-symbol features, each computed from a **backward-looking window
only**, with `min_periods` always set to the full window — a 252-day momentum
computed from 30 observations is a different statistic wearing the same column
name, and it appears exactly where walk-forward training begins.

### Price and momentum

| Feature | Lookback | Rationale |
|---|---|---|
| `mom_21` | 21 | One month; also the leg excluded from 12-1 |
| `mom_63` | 63 | Quarter momentum |
| `mom_252_21` | 252 | 12-1 momentum. The skipped month keeps short-horizon reversal out (Jegadeesh & Titman 1993) |
| `reversal_5` | 5 | Short-horizon reversal, negated so the hypothesis is positive (Lehmann 1990) |
| `acceleration` | 84 | Separates a strengthening trend from a decaying one at equal total return |

### Volatility

`vol_21`, `vol_63`, `downside_vol_63`, `vol_ratio`, `max_drawdown_252`.
Downside deviation divides by the **full** window, not the count of negative
days, so it is downside deviation rather than the standard deviation of a
filtered sample.

### Liquidity

`log_dollar_volume_21`, `volume_shock`, `amihud_21`. Dollar volume rather than
share volume because it is continuous through splits with no adjustment.
Amihud (2002) illiquidity is logged for the same reason dollar volume is:
the raw values span six orders of magnitude, and a linear model fed them is
fitting the largest two names.

### Structure

`dist_52w_high` (George & Hwang 2004), `trend_strength_63`, `ma_gap`. All
computed from the point-in-time return **index**, not raw close, so a split
does not manufacture a new "high".

### Why the list is short

`src/research/redundancy.py` already measures the participation ratio of the
factor correlation matrix and reports that the engine's seven price factors
carry far fewer than seven independent bets. Adding a fifth momentum horizon
does not add a fifth signal; it adds a fifth vote for the same one. The brief
warned against 500 correlated indicators, and this repository had already
measured why.

### Macro

Treasury level, slope, curvature, quarterly change and the short rate — the
Litterman-Scheinkman decomposition rather than seven raw tenors, because
almost all of a yield curve's variation lives in three factors and carrying
all seven adds collinearity, not information.

Plus six market-regime descriptors built from the **equal-weighted aggregate of
the point-in-time universe itself**. That choice matters: the aggregate
includes names that later failed, so its 2023 drawdown contains the regional
banks. An index proxy reconstructed from current membership would not, and
would understate exactly the stress the feature exists to detect.

**Every macro feature carries `availability_lag_sessions = 1`.** The Treasury
curve for a day is published that evening; a model forming a view during the
day has the previous session's curve. Getting this wrong is a one-session leak
that looks like nothing and is worth a surprising amount of spurious accuracy,
because rates move with the same news equities do.

### Cross-sectional normalisation

Each per-symbol feature is additionally ranked within its date's **point-in-time
universe**, producing a `_xs` column in `[-1, 1]`. The universe is a mandatory
argument; `cross_sectional_frame` raises without it. Standardising against
"whatever rows happen to be loaded" produces a value whose meaning depends on
the query, and is quietly survivorship-biased because the names that happen to
load are the ones that still have data.

Winsorisation at the 1st/99th percentile happens **before** standardising, not
after. A single 900% return in a 180-name cross-section moves the mean by 5%
and the standard deviation by far more; clipping afterwards leaves the damage
already in the moments.

---

## 3. Labels

Nine labels, so that "which horizon is predictable" is a measurement rather
than an assumption.

| Label | Horizon | Kind | Why it is in the set |
|---|---|---|---|
| `fwd_ret_1` | 1 | regression | The honest control. Daily returns are near-unpredictable; a model that appears to predict them is far more likely to be leaking |
| `fwd_ret_5` | 5 | regression | Short enough that reversal is still live |
| `fwd_ret_21` | 21 | regression | The existing engine's design horizon — directly comparable |
| `fwd_ret_63` | 63 | regression | Where fundamental signals are usually claimed to act |
| `fwd_vol_21` | 21 | regression | Volatility clusters, so this is the label most likely to carry real signal |
| `fwd_mae_21` | 21 | regression | Maximum adverse excursion — what a stop-loss responds to |
| `fwd_mfe_21` | 21 | regression | Paired with MAE, describes the path not just its end |
| `fwd_dir_21` | 21 | classification | Interpretable, and calibration is measurable on it |
| `fwd_rank_21` | 21 | ranking | **The one that matters most** |

### Why the rank label matters most

Predicting a name's absolute return means predicting the market's return plus
the name's relative move. The first term dominates the variance and is close to
unpredictable at these horizons. Predicting the cross-sectional **rank** removes
it. A model can be useless at the first and useful at the second — and this
repository's own factor research already reports that separation.

### The cost, stated

A label with horizon `h` is **NULL for the last `h` sessions** of every series.
Filling it, or quietly shortening the horizon at the end, changes what the model
trained on exactly where the newest data is — which is where a walk-forward's
final window lives.

---

## 4. Models

### Baselines, in the same code path

| Baseline | What it isolates |
|---|---|
| `baseline_zero` | Predicts 0. On a 21-day horizon this is close to optimal in squared error, and it is what embarrasses RMSE comparisons |
| `baseline_historical_mean` | Training-fold mean. The gap to zero measures how much performance is simply the market rising |
| `baseline_mom_252_21_xs` | 12-1 momentum, ranked. **The bar.** A learned model that cannot beat it has rediscovered a 1993 factor expensively |
| `baseline_reversal_5_xs` | Short-horizon reversal |
| `baseline_vol_63_xs` | Low-volatility effect (negated volatility rank) |

Every baseline implements the same `Model` interface, is evaluated by the same
walk-forward driver, and appears in the same leaderboard table. A baseline in a
separate code path with separate metrics is a rhetorical baseline.

The passthrough baselines are marked `scale_free = True`, so the driver
suppresses MAE, RMSE and R² for them. Their output is a factor value, not a
return, and printing an RMSE against a return invites a comparison that means
nothing.

### Learned models

**Linear** — OLS, ridge (α=10), lasso (α=0.0005), elastic net (α=0.0005,
l1=0.5). Not a warm-up act: on a wide, correlated, low-signal matrix a
regularised linear model is frequently the best model. OLS is included as the
overfitting control — it is *expected* to validate worse than ridge, and that
gap is the cleanest demonstration that regularisation is doing real work.

**Trees** — gradient boosting (depth 3, subsample 0.7, `min_samples_leaf` 50),
random forest (depth 8), histogram gradient boosting. Conservative by default
because forward returns have very low signal-to-noise and the flexibility that
finds a genuine interaction also memorises noise. `n_jobs=1` throughout:
threaded histogram construction reorders floating-point accumulation, which
breaks reproducibility, and these datasets are small enough that the cost is
seconds.

**Classification** — L2 logistic regression, returning the positive-class
*probability* rather than a hard label, so calibration and abstention remain
computable.

### The imputer is refitted every fold

`FoldImputer` is constructed **inside** the fold loop and fitted on training
rows only. Hoisting it out — computing medians and scales once over the whole
sample — is a small, real leak: the validation fold's distribution informs the
transform applied to it. It improves results slightly and leaves no trace, so
it is made structurally impossible rather than avoided by discipline.

---

## 5. Validation

Expanding-window walk-forward. Never a random split — panel rows are
non-exchangeable in time, and a 21-session label sampled every 5 sessions
shares 16 of its 21 days with its neighbour, so a random split puts rows
sharing 76% of their outcome on both sides of the boundary.

```
train ──────────────┤ purge (21) ├ embargo (5) ┤ validation (252) ─────
```

Purge covers the label's reach; embargo covers serial correlation, which
persists past the horizon. They are separate parameters so a result's
sensitivity to each can be stated.

**The holdout is not a fold.** Reserved before any fold is generated, returned
by no iterator, evaluated by nothing in the validation package. Once used it is
spent, and this document records when.

### Metrics, and why they disagree

| Metric | What it says | Where it misleads alone |
|---|---|---|
| RMSE, MAE | magnitude accuracy | dominated by unpredictable variance; almost every model loses to zero |
| `rmse_vs_zero` | ratio to predicting nothing | **>1.00 means negative magnitude skill** whatever the ordering does |
| Directional accuracy | sign agreement | must be read against the **base rate**, never 50% |
| `directional_edge` | accuracy minus the majority-class rate | the only one of the three readable alone |
| Rank IC | ordering within each date's cross-section | the metric a long/short book actually needs |
| `ic_ir` | mean IC over its dispersion | closest thing a signal has to a Sharpe |
| Calibration / ECE | stated confidence vs realised frequency | a miscalibrated confidence should not be shown to anyone |

Every IC t-statistic is **Newey-West corrected** with
`ceil(horizon / step) − 1` lags, reusing `src/research/cross_section.py`'s
existing implementation rather than a second copy — so the two research
surfaces in this repository cannot report different significance for the same
series. At horizon 21 and stride 5 that is 4 lags, and ignoring them inflates
the t-statistic by roughly a factor of two.

---

## 6. Defences against data mining

| Bias | Defence |
|---|---|
| Look-ahead | `guards.assert_no_future_dependence` — perturb the future, assert the past is bit-identical, **and** assert the perturbation was felt |
| Target leakage | name overlap plus \|corr\| ≥ 0.999 |
| Split leakage | purge + embargo, verified per fold |
| Survivorship | point-in-time universe; a universe that only grows fails the guard |
| Normalisation leakage | `FoldImputer` fitted per fold on training rows |
| Universe leakage | cross-sectional statistics require an explicit universe |
| **Multiple comparisons** | every experiment logged; `distribution()` reports the population, and Deflated Sharpe takes the trial count |
| Test-set tuning | untouched holdout; hyperparameters fixed in advance |
| Overfitting the selection | Probability of Backtest Overfitting over all configurations |

### Deflated Sharpe, implemented correctly

The threshold under the null is

```
E[max SR] ≈ sqrt(V[SR]) · [ (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) ]
```

The `sqrt(V[SR])` factor is **not optional**. Dropping it — which is easy to do
— expresses the threshold in units of a standard normal rather than of a Sharpe
estimate, and for N=200 produces an expected maximum near 20 annualised: a bar
no strategy could clear, which would declare everything insignificant. The
implementation prefers the dispersion of the actual trials and falls back to
the estimator's sampling variance, recording which was used in
`variance_source`.

Validated in `tests/quant/test_validation.py`: the best of 60 pure-noise runs
has a Sharpe of ~1.17 and is significant at `trials=1`, and correctly
**insignificant** at `trials=60`.

### What is deliberately not implemented

**White's Reality Check** and **Hansen's SPA**. Both require a stationary
bootstrap over the full set of candidate return series with a correctly chosen
block length, and getting the block length wrong silently changes the answer.
Shipping a version that produces a plausible number under conditions nobody
checked would be worse than the gap. This is a known limitation.

---

## 7. Results

Study results — every model, every label, winners and failures — are produced by

```bash
python -m scripts.quant.study --all-labels
```

and rendered at `/terminal/models` and `/api/ml/labels/{label}`. The findings
narrative is in `docs/research-report.md`.

The expected outcome is worth stating in advance so it cannot be reframed
later: **most configurations will show no statistically useful signal, and the
momentum baseline will be hard to beat.** That is the result the literature
predicts, and reporting it is the point of building the measurement apparatus.
