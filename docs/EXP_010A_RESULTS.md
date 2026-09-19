# EXP-010A — ten-seed noise floor (results summary)

Status: **COMPLETE, immutable.** A diagnostic, not model selection; every seed is reported and none is promoted.
Preregistration: [EXP_010A_PREREGISTRATION.md](EXP_010A_PREREGISTRATION.md). Outputs: `experiments/EXP-010A/`.
Holdout (2025-08-26 → 2026-08-28): **untouched**.

## What was run

The frozen EXP-009D deduplicated baseline (26 features, `GradientBoostingRegressor`, 200 rounds, learning rate 0.03,
depth 3, subsample 0.7, min leaf 50) was refit on the eight recorded EXP-006 folds with ten seeds (0–9), unchanged in
everything except the seed. Each seed's predictions were traded with the frozen 5-session, 10%-dropout portfolio at the
half-spread grid 1/3/5/10/20 bp.

## Result: how much does the seed alone move?

| Quantity | Mean | Sample SD | p05 | p95 | p95 − p05 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mean Rank IC | 0.03222 | **0.00158** | 0.03053 | 0.03469 | **0.00416** | 0.03034 | 0.03482 |
| Net Sharpe @ 10 bp | 0.3523 | **0.08165** | 0.2510 | 0.4704 | **0.2194** | 0.2000 | 0.4964 |
| Annualised one-way turnover | 6.876 | **0.0192** | 6.855 | 6.905 | 0.0504 | 6.854 | 6.912 |

Ordering is stable across seeds; portfolio economics are not. Pairwise prediction rank correlation averages 0.9015
(range 0.891–0.910) and top/bottom quintile overlap 0.784 (0.768–0.796). Six of eight folds are positive for nine seeds
and seven for one. Mean fold Rank IC across seeds:

| Fold | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mean IC | −0.0146 | +0.0402 | +0.0545 | +0.0315 | −0.0074 | +0.0324 | +0.0396 | +0.0811 |

## What it means

* A change in Rank IC smaller than about 0.004, or in net Sharpe smaller than about 0.22 (both p95 − p05), is
  indistinguishable from reseeding.
* Ranking quality is tightly determined by the data and features; the *portfolio Sharpe* built on it moves by roughly
  ±0.08 for reasons unrelated to any design change.
* EXP-010A defines **no** pass threshold. Later studies report effects against these numbers, descriptively.
* Nothing is promoted; no seed is "best".

## Limits

The distribution captures reseeding only. It does not include date-sampling uncertainty, data-vintage uncertainty, or
universe survivorship (`docs/PIT_SECURITY_MASTER_PLAN.md`).

## Immutable artifact hashes (SHA-256)

| File | SHA-256 |
|---|---|
| `definition.json` | `a5dc4f6dec1bf7ec97039252a645599e1c92ea6ebfa79f0b32262b698e81c8ca` |
| `config.json` | `0565e0d9af7e5b4a53bd11f1a3ef09e00bda5e2c9d207540c35bd3e79a40c67f` |
| `manifest.json` | `46a569adc94afd7ed52dd560baaa2c95979ee9ea31684dcf969fe6e756f942d9` |
| `metrics.json` | `a7663e9c61f6f5a80654c037e0b279ff2caa317e7ea61c52d410120235c40025` |
| `per_seed_metrics.csv` | `81296585f20d9d6d68d9568e7bc99483b21b1669bcd18c3e691ac90900c28d7c` |
| `fold_metrics.csv` | `f2c4c2c954f662415bdbf27be15a6881d460693f14e57dc974fdf91844a4b4d9` |
| `prediction_hashes.json` | `1ab4e9f285f702b0c5009444ca4f1b6a3a6aae7e87a6d102a8578b8088b88a26` |

Per-seed prediction hashes are in `prediction_hashes.json`; the prediction files themselves are local and git-ignored.
