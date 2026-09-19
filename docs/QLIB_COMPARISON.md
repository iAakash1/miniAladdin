# Microsoft Qlib comparison

Review date: 2026-09-19. Sources: the [Qlib paper](https://arxiv.org/abs/2009.11189),
[official repository](https://github.com/microsoft/qlib), official benchmark
configs and documentation. This is a methodology review, not a migration plan.

## What Qlib actually supplies

- A dataset-handler abstraction for feature/label expressions, preprocessing,
  train/validation/test segments and cached binary data.
- `Alpha158`: 158 formulaic daily price/volume features. `Alpha360`: rolling
  raw price/volume windows. These are not analyst/fundamental PIT datasets.
- Reference models including linear, LightGBM, XGBoost, CatBoost, MLP, TFT,
  ALSTM, ensemble and temporal-adaptation examples.
- Workflow records for prediction, IC/Rank IC analysis, portfolio backtests and
  experiment artifacts.
- `TopkDropoutStrategy`: hold a top-k set and replace only a configured number
  of names, a concrete turnover-stability mechanism.
- Enhanced-indexing examples with a risk model and benchmark constraints.

The official dynamic LightGBM/Alpha158 example uses CSI300, training
2008--2014, validation 2015--2016 and test 2017--2020. It predicts a forward
return with MSE, holds top 50 and drops 5, and configures 5 bp opening plus
15 bp closing cost and a minimum fee. These are example assumptions, not proof
that the same model or costs fit US equities.

## Benchmark evidence and caveats

Qlib's official benchmark table shows that LightGBM is competitive with or
better than several deeper models on Alpha158/360; TFT does not universally
dominate. That supports using tabular boosting as a serious baseline. The
published benchmark is China/CSI300 data, not OmniSignal's liquid-US universe.
Its community/Yahoo datasets can omit VWAP and some examples fill missing
features with zero—behavior OmniSignal must not copy for analyst/options/event
features. A public GitHub issue also demonstrates that changing label execution
price from close to open can materially change results. Execution semantics are
part of the research design.

## Gap comparison

| Capability | Qlib | OmniSignal | Adopt? |
|---|---|---|---|
| Feature/label expression engine | Broad formula DSL, Alpha158/360 | Typed registry with explicit source/PIT notes | Keep OmniSignal registry; borrow composable metadata ideas |
| Dataset/version artifacts | Cached handlers and recorders | Content hashes, manifests, firewall | Keep; OmniSignal's PIT source metadata is stronger for this study |
| Model breadth | Very broad | Deliberately bounded sklearn ladder | Use Qlib results as baselines, not dependency justification |
| Temporal evaluation | Fixed and rolling workflows | Expanding walk-forward, purge, embargo, sealed holdout | OmniSignal is stricter for overlapping labels |
| Ranking | Rank metrics and top-k strategy; default LightGBM example uses MSE | Rank target but point-regression loss | Test date-grouped LTR separately in EXP-009 |
| Turnover | Top-k dropout/drop count | Immediate quantile replacement in research backtest | Adopt the concept as a preregistered rank buffer |
| Costs | Configurable open/close/minimum costs | Half-spread sweep, no borrow/impact | Add borrow/impact/capacity when data permits |
| Risk controls | Enhanced indexing/risk-model examples | Portfolio/risk engine separate from research backtest | Connect only through identified allocator tests |
| PIT fundamentals/events | Not supplied by Alpha158 itself | Local event/estimate/statement sources with explicit gates | Do not regress to generic data handling |
| Missing values | Some examples use fillna behavior | Missing remains null and coverage is measured | Keep OmniSignal fail-honest policy |

## Ideas worth adopting

1. A `TopkDropoutStrategy`-like entry/exit buffer as a frozen portfolio-layer
   ablation, with turnover and net metrics reported.
2. A standard record bundle tying signals, metrics, portfolio analysis and
   configuration to one fingerprint.
3. Broad model interface compatibility so one date-grouped ranker can be tested
   without rewriting folds or the cost engine.
4. Seed/repeat reporting for stochastic models.

## Ideas not to adopt

- Do not migrate the repository or add Qlib as a dependency for EXP-009.
- Do not import China benchmark results as expected US performance.
- Do not copy fill-with-zero policies or close-price execution assumptions.
- Do not adopt dozens of models, Alpha158 wholesale, or Qlib's community data
  simply to increase model count.
- Do not use Qlib's benchmark split in place of the existing purge, embargo,
  cumulative trial accounting and sealed holdout.

The practical conclusion is narrow: Qlib validates the engineering value of a
reproducible model-to-backtest workflow and a top-k dropout rule. OmniSignal
already has stronger PIT governance; it should borrow those two ideas, not the
framework.
