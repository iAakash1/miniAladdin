# Current quant research audit

Audit date: 2026-09-19. This is a read-only reconstruction of the frozen
research record. EXP-007 was not rerun, EXP-006 was not promoted, and the
sealed 2025-08-28--2026-08-28 holdout was not opened.

## Executive finding

EXP-006 detects a small cross-sectional ordering signal, but not an investable
strategy under its registered implementation. Gradient boosting achieves
Rank IC 0.02895 (Newey-West t 2.66), while the long/short portfolio has gross
Sharpe 0.384 and **net Sharpe -0.102 at 10 bp half-spread**. Annual turnover is
20.15x and costs consume 126.6% of gross return. This is both a weak-signal and
a portfolio-construction/cost problem; it is not evidence that the score is
ready for production.

## Dataset and split reconstruction

| Item | Frozen value |
|---|---:|
| Dataset version | `ds-491d761b9f2a6fc4` |
| Panel | 506,374 rows, 977 symbols, 625 dates |
| Feature/label count | 103 features, 9 labels |
| EXP-006 model inputs | 27 `C_base` features |
| Validation predictions | 100,246 rows, 754 symbols, 404 dates |
| Validation span | 2017-05-05--2025-05-09 |
| Holdout | 2025-08-28--2026-08-28, sealed |
| Walk-forward | 8 expanding folds; 756-session minimum train; 252-session validation |
| Leakage controls | 21-session purge; 5-session embargo; 1-period execution lag |
| Evaluation cadence | every 5 sessions |

The universe is point-in-time and liquidity ranked: non-test, non-ETF common
equities with price at least $5, selected monthly as the top 250 by trailing
three-month median dollar volume. It is not an index-membership universe.
There are 184 monthly universe snapshots (2011-01-31--2026-07-31), 998 unique
securities, and 906 securities that later exit. Delisting coverage before
2017-10-26 is incomplete. Sector and point-in-time market-cap distributions
cannot be reconstructed from the frozen experiment artifact and are therefore
not claimed.

The 21-session label is evaluated every five sessions, so adjacent outcomes
overlap for 16 of 21 sessions (76.2%). A 404-date validation series spans
roughly 96 non-overlapping 21-session blocks, not 404 independent bets. Newey-
West inference and block-aware resampling are mandatory.

## Target audit

`fwd_rank_21` is a within-date cross-sectional rank outcome. In the frozen
predictions it ranges from -0.992 to 1.000, has mean 0.0040, median 0.0040,
standard deviation 0.5773, and is close to uniform by construction. The panel
has no duplicate date/symbol rows. Typical cross-sections have about 250 names
(the first has 14).

Median per-symbol lag-one target autocorrelation is 0.667 and prediction
autocorrelation is 0.637, primarily reflecting overlapping horizons. Consecutive
predicted-quintile retention is 48.95%; top-quintile retention is 60.58% and
bottom-quintile retention 64.20%. Mean cross-sectional prediction dispersion
is only 0.0454. Pooled prediction/target Spearman correlation is 0.0291.

The target is defensible for ranking research but mismatched to the ultimate
net-return objective: it is magnitude-insensitive, has no direct transaction-
cost penalty, and creates frequent boundary crossings. Future work should test
an explicitly ranked objective and a separately identified turnover-control
layer rather than interpreting small rank changes as economic gains.

## Feature audit

EXP-006 used price trend/reversal, volatility, liquidity, market regime, and
rates features only. It did **not** use the locally available statements,
earnings, analyst estimates, or options histories.

Rebuilding only the already-frozen pre-holdout panel found no constant
`C_base` columns. Apparent 30--31% coverage for cross-sectional columns is a
universe-membership mask on the broad panel, not 70% missingness among eligible
names. Macro coverage is 99.25--100%.

Material redundancy:

| Pair | Spearman/Pearson relationship | Finding |
|---|---:|---|
| `dist_52w_high_xs`, `max_drawdown_252_xs` | -1.000 | Exact duplicate axis; retain one |
| `mom_63_xs`, `trend_strength_63_xs` | 0.953 | Near duplicate |
| `downside_vol_63_xs`, `vol_63_xs` | 0.915 | Strong overlap |
| `vol_21_xs`, `vol_63_xs` | 0.853 | Strong overlap |
| `ma_gap_xs`, `mom_63_xs` | 0.831 | Strong overlap |
| `amihud_21_xs`, `log_dollar_volume_21_xs` | -0.788 | Same liquidity axis |
| `rates_short`, `rates_slope` | -0.903 Spearman | Macro collinearity |
| `market_vol_21`, `market_vol_percentile` | 0.816 | Regime overlap |

Split-gain importance is dominated by `market_mom_252` (0.094),
`rates_change_63` (0.075), `market_drawdown` (0.068), `vol_63_xs` (0.063),
`log_dollar_volume_21_xs` (0.056), `rates_curvature` (0.054), and
`market_vol_63` (0.053). This importance is neither causal nor stable under
correlation. EXP-006 did not run out-of-fold permutation importance, SHAP
stability, or a feature-family ablation. Running them now against the same
validation set would spend additional research degrees of freedom and is not
silently treated as preregistered evidence.

## Model and economic audit

| Model/result | Rank IC | NW t | Net result / interpretation |
|---|---:|---:|---|
| Gradient boosting | 0.02895 | 2.66 | Gross SR 0.384; net SR -0.102 at 10 bp |
| Deep GB control | 0.0313 | 2.76 | Train gap +0.729; net SR -0.862; unusable |

Gradient-boosting fold mean IC is 0.0301 (standard deviation 0.0332; minimum
-0.0200; maximum 0.0804), with six of eight folds positive. Train IC is
0.1909, a large train/validation gap. Net Sharpe changes monotonically from
0.169, 0.108, 0.048, -0.102, to -0.403 at 1/3/5/10/20 bp half-spreads.
Factor alpha t-statistic is 0.047. These numbers reject promotion.

The model registry included simple baselines, OLS/ridge/lasso/elastic net,
random forest, extra trees, histogram GB and sklearn GB. It did not test a
date-grouped learning-to-rank loss or a transaction-cost-aware objective.

## Point-in-time and survivorship findings

- Earnings availability uses the calendar date: before-market releases become
  available that session and after-market releases the next session.
- Analyst estimates are vintage dated. Their revision history and coverage
  must be audited before use in a new model.
- Statement rows have no restatement vintage field. Historical-as-reported
  status is therefore **unknown**, not point-in-time certified.
- Delisting dates are partial before 2017-10-26.
- Vendor options implied-volatility methodology and historical revision policy
  are undocumented locally.
- Live news timestamps need exchange-session alignment before research use.

An earlier as-of merge contamination was correctly declared and the affected
historical results voided. EXP-006 followed the repaired preflight. That event
is a reason to require source-level availability timestamps and a leakage
fixture for every new feature family.

## Required next actions

1. Do not promote EXP-006 or select a production model.
2. Freeze the present metrics as the comparison baseline.
3. Remove only the mathematically exact duplicate axis in the next registered
   design; treat all other pruning as a trial.
4. Make grouped ranking and turnover control separately identifiable.
5. Improve source provenance before adding restatement-sensitive fundamentals
   or vendor-derived options features.
6. Judge success on walk-forward stability and net economics, never headline
   IC alone.

## Status update — 2026-09-20

* EXP-010A (noise floor) and EXP-010B (21-session cadence, `ECONOMICALLY_IMPROVED`, validation only, disclosed seed-0 prototype exposure) are complete and immutable: `docs/EXP_010A_RESULTS.md`, `docs/EXP_010B_RESULTS.md`. The cadence question is closed for this cycle.
* The as-reported SEC foundation is verified and rebuilt (`sec-core-facts-v3`; defects of the previous store in `docs/SEC_TAG_MAP_AUDIT.md`). The PIT security master is built and graded (`docs/PIT_SECURITY_MASTER_STATUS.md`); `security_master_pit` is **false** (trusted identity 91.8-95.0% by fold vs 95%).
* A new immutable dataset, `ds-richpit-ff3d3f556488b7da` (76 features), exists (`docs/RICH_PIT_PANEL_AUDIT.md`). EXP-011 compares it with the 26-feature baseline under a 2x2 design and is preregistered, **not run** (`docs/EXP_011_PREREGISTRATION.md`).
* Nothing is promoted; the holdout is sealed. Full engineering status: `docs/OMNISIGNAL_SYSTEM_HEALTH.md`, `docs/OMNISIGNAL_FULL_SYSTEM_AUDIT_2026.md`.

## Status update — EXP-011 complete (2026-09-20)

EXP-011 (rich PIT data value, 2x2 with Ridge and gradient boosting) is complete and immutable: label **`IMPROVES_ONLY_LINEAR`** (`docs/EXP_011_RESULTS.md`). The registered 50-feature PIT extension produced a detectable ordering improvement under the preregistered Ridge specification (Rank IC 0.0053 → 0.0149; positive in 6 of 8 folds; concentrated in folds 0 and 2; adverse in fold 4) but no detectable ordering gain under the frozen gradient-boosting specification (median ΔIC −0.0008; not fold-robust), and it did not improve downstream validation economics for either model class. Nothing is promoted, the holdout is sealed, and the data limits above (`security_master_pit = false`, ALFRED blocked, controls withheld) are unchanged. The next step is an owner decision, not an automatic one: `docs/NEXT_RESEARCH_DECISION_2026.md`. The 2026-09-20 status item above that calls EXP-011 preregistered-only is superseded by this one.
