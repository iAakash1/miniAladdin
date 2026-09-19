# Replication candidate: Qlib Alpha158 + top-k dropout concepts

| Item | Assessment |
|---|---|
| Original project | [Microsoft Qlib](https://github.com/microsoft/qlib), [platform paper](https://arxiv.org/abs/2009.11189) |
| Hypothesis | Standardized price/volume factors plus reproducible workflow and stable top-k construction form strong baselines |
| Original data | CSI300/CSI500 China daily data; Alpha158 formulaic factors |
| Target/model | Forward return, commonly LightGBM MSE in official example |
| Original evaluation | Fixed train/valid/test; IC/Rank IC and TopkDropout backtest; example costs 5 bp open/15 bp close |
| Data we have | Better-governed PIT US panel, 16 price-family + macro base features, fixed cost sweep |
| Data we lack | Same China universe/data and full Alpha158 inputs such as reliable VWAP |
| Feasible substitute | Preserve OmniSignal features; reproduce only top-k/drop-d behavior and workflow artifact linkage |
| Exact reproduction | Strategy state machine can be matched; not the performance benchmark |
| Approximation | Different market, universe, feature set, split and costs |
| Original compute | Hardware/runtime not reported. Official benchmark values are means over 20 seeds |
| Original result | On Alpha158, linear Rank IC/IR 0.0472/0.921 beats several deep models; DoubleEnsemble leads IR at 1.343. TopkDropout bounds replacements by construction |
| MacBook plan | Keep independently implemented top-k dropout; portfolio replay 2–20 min |
| Kaggle plan | None for portfolio logic; optional only for later independent model seeds |
| Estimated data preparation | No new preparation for portfolio rule; exact China benchmark is not the US research question |
| Complexity | LOW |
| Leakage risk | Close-price label/execution semantics; zero-filling missing inputs |
| Licensing risk | Qlib repository is MIT; community data provenance varies and should not be imported |
| Recommendation | **KEEP ADAPTATION**, not framework migration |

EXP-009A confirmed the relevant mechanism: the independently implemented 10%
top-k dropout rule reduced turnover 66% and produced positive net economics at
the registered 10 bp cost. Do not add Qlib as a dependency or migrate the
project.
