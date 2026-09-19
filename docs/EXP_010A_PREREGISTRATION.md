# EXP-010A preregistration — multi-seed noise floor

Date registered: 2026-09-19  
Status: **EXPERIMENTAL — NOISE DIAGNOSTIC — PROMOTION NOT ASSESSED**  
Definition fingerprint: `0b18e0ad7d90905988988a8cdd8d9251522000d7503d41045096c639bf64bba0`

## Question

How much variation in ordering and portfolio economics is caused purely by the
random seed in OmniSignal's existing model specification? This study measures
the noise floor before another model or data family is judged. It does not
select a seed, tune a model, promote anything, or access the sealed holdout.

## Frozen data and split

- Dataset: `ds-491d761b9f2a6fc4`.
- Dataset content hash: `7deb8601ae7a34074cade997397f1947`.
- Rows: 452,524; last included date: 2025-05-09.
- Returns-panel SHA-256: `d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e`.
- Target: within-date `fwd_rank_21`.
- Split: the exact eight EXP-006 walk-forward folds reused by EXP-009D. The
  first validation date is 2017-05-05 and the final validation date is
  2025-05-09. Imputation is refit on each training fold only.
- Universe: point-in-time liquid-universe members only.
- Sealed holdout: the stricter recorded window, 2025-08-26 through 2026-08-28.
  It is armed in the shared firewall before data load and must be recorded as
  `"touched": false`.

## Frozen features

Feature-list SHA-256: `205d2e2b2debdb177e382657a597489b67a5e9e62f386958118de64f8a872fbf`.

The 26 post-EXP-009D features are:

1. `acceleration_xs`
2. `dist_52w_high_xs`
3. `ma_gap_xs`
4. `mom_21_xs`
5. `mom_252_21_xs`
6. `mom_63_xs`
7. `reversal_5_xs`
8. `trend_strength_63_xs`
9. `downside_vol_63_xs`
10. `vol_21_xs`
11. `vol_63_xs`
12. `vol_ratio_xs`
13. `amihud_21_xs`
14. `log_dollar_volume_21_xs`
15. `volume_shock_xs`
16. `market_drawdown`
17. `market_mom_21`
18. `market_mom_252`
19. `market_vol_21`
20. `market_vol_63`
21. `market_vol_percentile`
22. `rates_change_63`
23. `rates_curvature`
24. `rates_level`
25. `rates_short`
26. `rates_slope`

`max_drawdown_252_xs`, the exact anti-duplicate tested by EXP-009D, is absent.
No SEC, analyst, earnings, options, new macro, or neutralization input enters
this experiment.

## Frozen model and seeds

The estimator is `sklearn.ensemble.GradientBoostingRegressor`, reached through
the repository's `GradientBoostedTrees` wrapper and shared walk-forward runner.
Its exact parameters are:

- `n_estimators=200`
- `learning_rate=0.03`
- `max_depth=3`
- `subsample=0.7`
- `min_samples_leaf=50`
- `random_state=seed`

The seeds are exactly `0, 1, 2, 3, 4, 5, 6, 7, 8, 9`. There is no search,
retuning, early stopping, or choice of a preferred seed.

## Frozen portfolio and costs

The portfolio rule is EXP-009A's selected top-k dropout rule: long and short
quintiles with a 10% drop fraction. The EXP-009A engine is unchanged: one
rebalance-period execution lag, 0.5 gross exposure per leg, 10% maximum name
weight, one-way turnover, 1 bp commission, and the existing impact model.
Half-spread costs are evaluated at exactly 1, 3, 5, 10, and 20 bp. The primary
reporting point is 10 bp; no cost is selected after seeing outcomes.

## Metrics frozen before execution

For each seed, report mean Rank IC, four-lag Newey-West/HAC t-statistic, ICIR,
all eight fold ICs, positive-fold count, worst-fold IC, mean cross-sectional
prediction dispersion, prediction-rank correlation to seed 0, long/short
portfolio overlap to seed 0, annualized one-way turnover, gross Sharpe, net
Sharpe at every registered cost, net maximum drawdown, and cost share of gross.

Across seeds, report mean, sample standard deviation, median, minimum, maximum,
5th percentile, 95th percentile, and the 95th-minus-5th percentile range for
Rank IC, net Sharpe at 10 bp, and annualized turnover. Also report every
pairwise prediction-rank correlation, every pairwise portfolio overlap, their
distributions, and the same distribution of fold IC separately for each fold.

The results define a descriptive stochastic noise floor. Later effects must be
reported against both the sample standard deviation and the 90% range. This
study defines no automatic pass threshold and never selects the best seed.

## Execution, restart safety, and outputs

`run` is refused unless this document and every registered method source match
the fingerprint, are clean, are committed, and this document's commit is an
ancestor of `origin/main`. Each completed seed is written as an atomic Parquet
checkpoint followed by an atomic metadata receipt containing the definition
fingerprint, dataset hash, prediction hash, row count, fold count, and timing.
A matching checkpoint is resumed; a mismatch aborts rather than mixing runs.

The tracked evidence directory is `experiments/EXP-010A/` and contains
`definition.json`, `config.json`, `manifest.json`, `metrics.json`,
`per_seed_metrics.csv`, `fold_metrics.csv`, and `prediction_hashes.json`.
Per-row checkpoint predictions remain ignored. Completion requires all ten
seeds, all eighty folds, valid input hashes, an armed/clear holdout firewall,
and a final `EXP-010A COMPLETE` log line. No result implies promotion.
