# Deployment Contract

**Nothing is deployed.** This document specifies the contract a model would
have to satisfy, and the gates it has not yet passed.

---

## 1. Why nothing is deployed

The registry refuses promotion without evidence, and no model currently has it:

```python
registry.promote("ridge@1.0:fwd_ret_21", "production")
# PromotionRefused: cannot become production: missing metrics on the untouched
#   holdout period, performance broken out by market regime.
#   A model is promoted on evidence, not on the best backtest number.
```

Promotion to `production` requires, in addition to walk-forward results and a
baseline comparison: a cost-aware backtest, a factor attribution, holdout
metrics, and a regime breakdown. The holdout is deliberately untouched, and
spending it is a decision that should be made once and recorded.

---

## 2. The read path, which exists today

`/api/ml/*` is **read-only over offline artifacts**. It never trains, never
backtests, never ingests. A page load must not be able to start a walk-forward —
the same reason `backtest_service.peek_cached` exists.

| Endpoint | Returns |
|---|---|
| `GET /api/ml/capabilities` | per-capability availability with a reason and a remediation |
| `GET /api/ml/datasets` | catalog, including what is excluded and why |
| `GET /api/ml/features` | every definition with lookback, lag, PIT status |
| `GET /api/ml/overview` | dataset, universe, regime, per-label verdicts |
| `GET /api/ml/labels/{label}` | every model evaluated — losers included |
| `GET /api/ml/registry` | status and the evidence each model still lacks |
| `GET /api/ml/provenance/{label}/{model}` | vendor observation → model output |

When no study exists these report `unavailable` with the command that would
produce one. They do not compute a cheap approximation, because a reader cannot
tell a placeholder from a result.

---

## 3. The prediction contract, if a model ever passes

Specified now so the shape is agreed before the pressure to ship exists.

```jsonc
{
  "symbol": "AAPL",
  "as_of": "2026-08-28",              // the last session the model could see
  "model_id": "ridge",
  "model_version": "1.0",
  "dataset_version": "ds-e691b48ca49deb16",
  "horizon_sessions": 21,

  "expected_rank": 0.34,              // cross-sectional, in [-1, 1]
  "prediction_interval": [-0.51, 0.72],
  "kind": "MODEL_PREDICTED",

  "confidence": {
    "value": 0.41,
    "components": [                   // decomposed, never a bare number
      {"name": "historical_fold_ic", "value": 0.28, "methodology": "..."},
      {"name": "regime_compatibility", "value": 0.55, "methodology": "..."},
      {"name": "feature_coverage",    "value": 0.81, "methodology": "..."}
    ]
  },

  "regime": {"label": "low_vol_bull", "model_performance_here": "weak"},
  "abstain": false,
  "abstain_reason": null,

  "top_features": [                   // MODEL EXPLANATION, not causation
    {"name": "mom_252_21_xs", "contribution": 0.11}
  ],
  "caveat": "An association within a fitted model, not a causal effect.",

  "out_of_sample": {"mean_ic": 0.012, "ic_t_stat": 1.4, "folds": 8}
}
```

### Rules the contract enforces

* **No `expected_return` in currency or percent.** These are cross-sectional
  rank models; emitting a return would imply a magnitude claim the
  `rmse_vs_zero` results do not support.
* **No bare confidence number.** `confidence.components` is mandatory.
* **`abstain` is a first-class field.** A model with insufficient feature
  coverage, or in a regime where it has no measured performance, returns
  `abstain: true` and no prediction — not a low-confidence guess.
* **`kind` is always `MODEL_PREDICTED`**, so the UI can never render it in the
  same weight as an observed close.
* **Historical performance and the current prediction are separate objects.**
  `out_of_sample` describes the model; it is never presented as the confidence
  of this prediction.

---

## 4. The gates before any of this ships

1. A model passes `production` in the registry — including the holdout, spent once.
2. Its six-factor alpha is significant, or the product describes it as a return difference.
3. Net Sharpe survives the 10 bp spread assumption, not only the 1 bp one.
4. Inference latency is measured, and the model artifact loads without the
   training dependencies where possible.
5. The artifact is versioned under `data/research/models/<id>/<version>/` with
   feature schema, preprocessing, metrics and metadata.
6. A rollback path exists: the previous version stays addressable.

None of these has been done, because gate 1 has not been passed.

---

## 5. Runtime separation

`requirements.txt` does not contain scikit-learn or scipy. The web process
serving research pages does not import them, and `/api/ml/capabilities` reports
`learned_models: unavailable` where they are absent rather than failing at
import — the same explicit-degradation pattern the provider fabric uses.

Training dependencies belong in a separate requirements file, installed only
where a study runs.

---

## 6. The quant API (EXP-005)

| Endpoint | Purpose |
|---|---|
| `GET /api/quant/status` | Deployment state + holdout firewall state |
| `GET /api/quant/experiments` | Every study, void ones marked and retained |
| `GET /api/quant/experiments/{id}` | Leaderboard with verdicts, ablation, controls, regimes |
| `GET /api/quant/latest` | Newest completed non-void study |
| `GET /api/quant/features` | Feature registry with lookbacks and directions |
| `GET /api/quant/datasets` | Catalog in three tiers: admissible, **gated**, excluded |
| `GET /api/quant/symbol/{s}` | Company-page panel — refuses without a production model |

No endpoint exposes a filesystem path, a credential, or arbitrary execution, and
none trains: a page load must not be able to start a walk-forward.

The `gated` tier is the one that is easy to omit and matters most. A source keyed
by fiscal period is admissible only behind a publication gate; reporting only
`excluded` would imply everything else is unconditionally safe to read as-dated.

### Deployment states

```
NO_MODEL      nothing promoted; no prediction is served      <- current
EXPERIMENTAL  models validated, none clears the candidate bars
CANDIDATE     clears development gates; holdout not spent
PRODUCTION    holdout spent, thresholds cleared, promoted
```

Read from the **model registry**, deliberately independent of any leaderboard: a
spectacular research result cannot move it, because only a registry promotion
can. `/quant` renders the state at full weight rather than in a footnote, and
`/api/quant/symbol/{s}` returns an explicit disclosure instead of a number.

### The candidate gate that was missing

`PROMOTION_GATES` verified that evidence *existed*; numeric bars were consulted
only at `production`, and those read the locked holdout. So a model could arrive
with a complete, honest evidence bundle stating that it loses money and still be
labelled a production candidate — EXP-004's best model is exactly that bundle.

`CANDIDATE_THRESHOLDS` now applies validation-side bars at candidacy: |IC t| ≥ 2,
net Sharpe > 0, **gross Sharpe > 0**, and beating the best baseline. An
unrecorded value counts as unmet. `eligible_for` applies the same bars, so it
cannot advertise a status `promote()` would refuse.
