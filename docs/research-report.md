# Research Report — Cross-Sectional Return Prediction

> **SUPERSEDED — the learned-model results below are VOID.**
>
> A pre-holdout audit found that `pandas.merge_asof` discards the left index,
> so both as-of joins wrote values back positionally into a differently-ordered
> frame. 12 of the 39 features used here carried other rows' values, some from
> later dates. Every model that consumed the full feature set is invalidated;
> the three single-feature baselines (`baseline_momentum`,
> `baseline_reversal`, `baseline_low_volatility`) are unaffected and remain
> valid. See [`PRE_HOLDOUT_AUDIT.md`](PRE_HOLDOUT_AUDIT.md).
>
> This document is retained unedited. Deleting it would erase the
> multiple-testing exposure it created, which is recorded in
> [`RESEARCH_LEDGER.md`](RESEARCH_LEDGER.md).

> Generated from `data/research/reports/study.json` by
> `scripts/quant/report.py`. Every figure is read from the artifact; none
> is transcribed. A report whose numbers are retyped drifts from the run
> it describes, and the drift is always flattering.

**Run.** git `1f6cb24f8fbc` · seed 0 · 2026-08-29T19:55:52 · 2299.2s

## 1. The question

Given only what was knowable at time *T*, can a model rank a liquid US
equity cross-section better than a factor published in 1993 — and does
the answer survive transaction costs, factor attribution, regime
changes, and the number of models tried?

## 2. Dataset

| Property | Value |
|---|---|
| Version | `ds-e691b48ca49deb16` |
| Content hash | `09f5ec8bc79bc3b033ee551252e4e6b6` |
| Rows | 506,374 |
| Symbols | 977 |
| Observation dates | 625 |
| Period | 2014-04-01 → 2026-08-30 |
| Stride | 5 sessions |
| Features available | 67 |
| Features used | 39 |
| Leakage guards | 7/7 passed |

### Sources

| Dataset | Rows | Coverage | Point-in-time | Survivorship |
|---|---|---|---|---|
| `dolthub_stocks_ohlcv` | 2,910,092 | 2012-01-03 → 2026-08-28 | point_in_time | complete |
| `dolthub_stocks_split` | 3,993 | 2014-03-28 → 2026-08-21 | point_in_time | complete |
| `dolthub_stocks_dividend` | 494,438 | 1970-01-19 → 2026-08-21 | point_in_time | complete |
| `dolthub_rates_us_treasury` | 9,158 | 1990-01-02 → 2026-08-28 | point_in_time | complete |
| `dolthub_options_volatility_history` | 691,007 | 2019-05-10 → 2026-08-28 | point_in_time | partial |
| `dolthub_options_chain_daily` | 1,918,396 | 2019-02-09 → 2026-08-28 | point_in_time | partial |
| `dolthub_earnings_eps_history` | 168,473 | None → None | publication_lagged | partial |
| `dolthub_earnings_calendar` | 117,601 | 2020-01-22 → 2026-10-01 | publication_lagged | partial |

### Universe

`liquid` — 998 names ever eligible across 184 monthly rebalances, 906 membership exits.

* Liquidity-ranked, not index membership. Do not describe a study over this universe as an index backtest.
* Survivorship-free by construction: membership is selected from each month's whole-market cross-section, so names that later delisted are present in the months they were liquid.
* Screens: non-ETF, non-test-issue, close >= 5.0, top 250 by 3-month trailing-median dollar volume (trailing window only), dropped after symbol.last_seen.
* coverage_class is 'partial' before 2017-10-26, where symbol.last_seen has no data and delisting is inferred only from a name leaving the cross-section.

## 3. Regime distribution

| Regime | Observation dates |
|---|---|
| low_vol_bull | 426 |
| high_vol_bull | 136 |
| stress | 34 |
| high_vol_bear | 19 |
| low_vol_bear | 10 |

Boundaries are fixed constants, not fitted, so they cannot have been
chosen to suit a result. The imbalance is itself a finding: any
statement about bear-market behaviour rests on the smallest buckets
and should be read as anecdote.

## 4. Results

### `fwd_ret_21` — 21-session horizon

8 expanding folds · 21-session purge + 5-session embargo · holdout 2025-08-28 → 2026-08-28 (**untouched**)

| Model | val IC | train IC | gap | NW t | folds+ | rmse/0 | gross SR | net SR | alpha t | DSR p |
|---|---|---|---|---|---|---|---|---|---|---|
| `gradient_boosting` | +0.0218 | +0.1190 | +0.0972 | +2.26 | 62.5% | +1.01 | +0.18 | -0.27 | -0.50 | +0.00 |
| `gradient_boosting_deep` | +0.0215 | +0.5866 | +0.5651 | +1.93 | 100.0% | +1.02 | +0.66 | +0.08 | +0.46 | +0.01 |
| `baseline_low_volatility`* | +0.0209 | +0.0181 | -0.0032 | +0.90 | 50.0% | — | -0.26 | -0.32 | -1.03 | +0.00 |
| `random_forest` | +0.0193 | +0.2589 | +0.2398 | +1.37 | 75.0% | +1.00 | +0.48 | +0.12 | +0.60 | +0.01 |
| `baseline_momentum`* | +0.0158 | +0.0092 | -0.0065 | +0.88 | 62.5% | — | +0.09 | -0.01 | +0.47 | +0.01 |
| `baseline_reversal`* | +0.0015 | +0.0074 | +0.0060 | +0.17 | 50.0% | — | +0.16 | -0.59 | -1.77 | +0.00 |
| `hist_gradient_boosting` | -0.0002 | +0.2017 | +0.2022 | -0.02 | 62.5% | +1.01 | -0.08 | -0.48 | -1.50 | +0.00 |
| `baseline_earnings_surprise`* | -0.0015 | -0.0042 | -0.0028 | -0.46 | 50.0% | — | +0.04 | -1.51 | -4.43 | +0.00 |
| `baseline_iv_premium`* | -0.0051 | -0.0077 | -0.0025 | -1.43 | 12.5% | — | -0.09 | -1.57 | -4.63 | +0.00 |
| `extra_trees` | -0.0068 | +0.3308 | +0.3380 | -0.41 | 62.5% | +1.00 | -0.48 | -0.70 | -1.61 | +0.00 |
| `ols` | -0.0088 | +0.0240 | +0.0328 | -0.75 | 75.0% | +1.06 | -0.03 | -0.49 | -0.86 | +0.00 |
| `ridge` | -0.0090 | +0.0238 | +0.0328 | -0.77 | 75.0% | +1.06 | -0.04 | -0.49 | -0.86 | +0.00 |
| `ridge_strong` | -0.0093 | +0.0237 | +0.0331 | -0.80 | 75.0% | +1.05 | -0.08 | -0.53 | -0.95 | +0.00 |
| `lasso` | -0.0165 | +0.0166 | +0.0332 | -1.21 | 75.0% | +1.03 | -0.39 | -0.86 | -2.22 | +0.00 |
| `elastic_net` | -0.0183 | +0.0206 | +0.0390 | -1.38 | 75.0% | +1.04 | -0.17 | -0.59 | -1.02 | +0.00 |
| `baseline_zero`* | — | — | — | — | — | +1.00 | — | — | — | — |
| `baseline_historical_mean`* | — | — | — | — | — | +1.00 | — | — | — | — |

`*` = baseline (no fitting). Sorted by validation IC; **nothing filtered**.

**Selection context.** 15 configurations evaluated. Best +0.0218, median -0.0015, worst -0.0183, 6 above zero.

**Probability of backtest overfitting:** +0.10. The configuration chosen in-sample landed in the bottom half out-of-sample 10% of the time. Near 0.5 means in-sample selection carries no information about out-of-sample rank; below ~0.2 is where selection is doing real work.

**Verdict.** Signal survives significance but NOT costs: gross Sharpe +0.18, turnover 18.0x/yr, costs 254% of gross, net Sharpe -0.27.

**Cost sensitivity — `gradient_boosting`.** The half-spread is an
assumption, not an observation; the sweep shows where the result stops
surviving.

| half-spread | gross SR | net SR | net CAGR | turnover |
|---|---|---|---|---|
| 1.0 bp | +0.18 | -0.11 | -1.4% | +18.00 |
| 5.0 bp | +0.18 | -0.27 | -2.8% | +18.00 |
| 10.0 bp | +0.18 | -0.47 | -4.6% | +18.00 |
| 20.0 bp | +0.18 | -0.87 | -8.0% | +18.00 |

**Regime breakdown — `gradient_boosting`.**

| regime | observations | mean IC | t | note |
|---|---|---|---|---|
| high_vol_bear | 2,249 | +0.0600 | +1.90 |  |
| high_vol_bull | 21,065 | +0.0257 | +0.96 |  |
| low_vol_bear | 2,500 | +0.1729 | +11.37 |  |
| low_vol_bull | 66,221 | +0.0089 | +0.89 |  |
| stress | 8,211 | +0.0600 | +2.67 |  |

### `fwd_rank_21` — 21-session horizon

8 expanding folds · 21-session purge + 5-session embargo · holdout 2025-08-28 → 2026-08-28 (**untouched**)

| Model | val IC | train IC | gap | NW t | folds+ | rmse/0 | gross SR | net SR | alpha t | DSR p |
|---|---|---|---|---|---|---|---|---|---|---|
| `gradient_boosting` | +0.0295 | +0.1903 | +0.1608 | +2.70 | 75.0% | +1.00 | +0.36 | +0.03 | +0.44 | +0.01 |
| `random_forest` | +0.0285 | +0.3200 | +0.2916 | +2.30 | 75.0% | +1.00 | -0.25 | -0.48 | -0.94 | +0.00 |
| `gradient_boosting_deep` | +0.0270 | +0.7468 | +0.7199 | +2.52 | 75.0% | +1.03 | -0.17 | -0.56 | -1.38 | +0.00 |
| `hist_gradient_boosting` | +0.0254 | +0.3011 | +0.2758 | +2.19 | 75.0% | +1.00 | +0.14 | -0.23 | -0.22 | +0.00 |
| `extra_trees` | +0.0242 | +0.4236 | +0.3995 | +1.80 | 75.0% | +1.00 | -0.00 | -0.29 | -0.58 | +0.00 |
| `baseline_low_volatility`* | +0.0209 | +0.0181 | -0.0032 | +0.90 | 37.5% | — | -0.26 | -0.32 | -1.03 | +0.00 |
| `baseline_momentum`* | +0.0158 | +0.0092 | -0.0065 | +0.88 | 75.0% | — | +0.09 | -0.01 | +0.47 | +0.01 |
| `ridge` | +0.0061 | +0.0429 | +0.0367 | +0.45 | 62.5% | +1.00 | -0.27 | -0.61 | -1.26 | +0.00 |
| `ridge_strong` | +0.0060 | +0.0429 | +0.0367 | +0.44 | 62.5% | +1.00 | -0.29 | -0.63 | -1.31 | +0.00 |
| `ols` | +0.0060 | +0.0430 | +0.0369 | +0.44 | 62.5% | +1.00 | -0.27 | -0.61 | -1.26 | +0.00 |
| `elastic_net` | +0.0059 | +0.0425 | +0.0365 | +0.41 | 62.5% | +1.00 | -0.28 | -0.61 | -1.24 | +0.00 |
| `lasso` | +0.0054 | +0.0418 | +0.0363 | +0.36 | 50.0% | +1.00 | -0.30 | -0.61 | -1.26 | +0.00 |
| `baseline_reversal`* | +0.0015 | +0.0074 | +0.0060 | +0.17 | 62.5% | — | +0.16 | -0.59 | -1.77 | +0.00 |
| `baseline_earnings_surprise`* | -0.0015 | -0.0042 | -0.0028 | -0.46 | 50.0% | — | +0.04 | -1.51 | -4.43 | +0.00 |
| `baseline_iv_premium`* | -0.0051 | -0.0077 | -0.0025 | -1.43 | 25.0% | — | -0.09 | -1.57 | -4.63 | +0.00 |
| `baseline_zero`* | — | — | — | — | — | +1.00 | — | — | — | — |
| `baseline_historical_mean`* | — | — | — | — | — | +1.00 | — | — | — | — |

`*` = baseline (no fitting). Sorted by validation IC; **nothing filtered**.

**Selection context.** 15 configurations evaluated. Best +0.0295, median +0.0061, worst -0.0051, 13 above zero.

**Probability of backtest overfitting:** +0.11. The configuration chosen in-sample landed in the bottom half out-of-sample 11% of the time. Near 0.5 means in-sample selection carries no information about out-of-sample rank; below ~0.2 is where selection is doing real work.

**Verdict.** Returns are explained by factor exposure. Intercept is not distinguishable from zero (t = 0.44). The return series is explained by its factor exposures — largest loading rmw at -0.36. This is a return difference, not alpha.

**Cost sensitivity — `gradient_boosting`.** The half-spread is an
assumption, not an observation; the sweep shows where the result stops
surviving.

| half-spread | gross SR | net SR | net CAGR | turnover |
|---|---|---|---|---|
| 1.0 bp | +0.36 | +0.15 | 1.2% | +20.66 |
| 5.0 bp | +0.36 | +0.03 | -0.5% | +20.66 |
| 10.0 bp | +0.36 | -0.12 | -2.5% | +20.66 |
| 20.0 bp | +0.36 | -0.42 | -6.5% | +20.66 |

**Regime breakdown — `gradient_boosting`.**

| regime | observations | mean IC | t | note |
|---|---|---|---|---|
| high_vol_bear | 2,249 | +0.0275 | +0.44 |  |
| high_vol_bull | 21,065 | +0.0235 | +0.97 |  |
| low_vol_bear | 2,500 | -0.0410 | -0.68 |  |
| low_vol_bull | 66,221 | +0.0234 | +2.09 |  |
| stress | 8,211 | +0.1163 | +2.98 |  |

## 5. Conclusion

### `fwd_ret_21` — best model `gradient_boosting`

| Requirement | Result |
|---|---|
| IC distinguishable from zero (|t| > 2) | PASS |
| beats the best free baseline | PASS |
| net Sharpe > 0 after costs | **FAIL** |
| net Sharpe > 0.5 (economically useful) | **FAIL** |
| six-factor alpha significant | **FAIL** |
| survives the trial count (deflated Sharpe > 0.95) | **FAIL** |

Passed 2 of 6.

### `fwd_rank_21` — best model `gradient_boosting`

| Requirement | Result |
|---|---|
| IC distinguishable from zero (|t| > 2) | PASS |
| beats the best free baseline | PASS |
| net Sharpe > 0 after costs | PASS |
| net Sharpe > 0.5 (economically useful) | **FAIL** |
| six-factor alpha significant | **FAIL** |
| survives the trial count (deflated Sharpe > 0.95) | **FAIL** |

Passed 3 of 6.

### Finding

**NO MODEL DEMONSTRATES ROBUST INCREMENTAL PREDICTIVE VALUE.**

The tree ensembles produce a rank IC that is statistically
distinguishable from zero after a Newey-West correction, and it does
exceed the free factor baselines. That is a real measurement and it
is not nothing.

It is also not tradeable. The signal requires roughly 20x annual
turnover to harvest, and at a 5 bp half-spread transaction costs
consume most or all of the gross return — the `cost_share_of_gross`
figures in the backtest tables are the decisive numbers, not the IC.
The six-factor intercept is not distinguishable from zero, so what
remains is a **return difference**, not alpha. And the deflated Sharpe
says the result does not survive being selected from the number of
configurations actually tried.

**No model is promoted. Nothing is deployed.** This is a successful
research outcome: the apparatus measured what it was built to
measure and returned an honest negative.

## 6. Reproducibility

| Field | Value |
|---|---|
| git commit | `1f6cb24f8fbc2385eef164fd8e444cde06f687f6` |
| seed | 0 |
| numpy | 2.2.6 |
| pandas | 2.3.3 |
| pyarrow | 18.1.0 |
| sklearn | 1.7.2 |
| scipy | 1.18.1 |
| python | 3.12.11 |
| machine | Apple M4 Pro · 12 cores |

```bash
python -m scripts.quant.local_backfill --stage all
python -m scripts.quant.backfill --stage universe --universe-size 250
python -m scripts.quant.study --start 2014-04-01 --all-labels --seed 0
```

## 7. Limitations

* observation stride 5 sessions, applied after feature computation so lookback windows remain in trading days
* 21 symbol(s) skipped for fewer than 260 sessions
* cross-sectional columns (_xs) normalised within point-in-time universe membership only; names outside the universe on a date carry NULL there
* macro features carry a one-session availability lag applied at source
* 8 option feature(s) attached as-of (latest snapshot at or before each date, 21-day staleness cap)
* 4 earnings feature(s) attached from the announcement's availability date, honouring before-open vs after-close; periods with no matching announcement are dropped

Full treatment in [`docs/quant/model-card.md`](quant/model-card.md) and
[`docs/quant-leakage-prevention.md`](quant-leakage-prevention.md).
