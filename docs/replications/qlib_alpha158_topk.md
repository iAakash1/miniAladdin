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
| Compute/storage | Portfolio replay on frozen predictions; minutes, negligible storage |
| Complexity | LOW |
| Leakage risk | Close-price label/execution semantics; zero-filling missing inputs |
| Licensing risk | Qlib code Apache-2.0; data provenance varies and should not be imported |
| Recommended ID | Portfolio cell inside `EXP-009-TURNOVER` |

Do not add Qlib as a dependency or migrate the project.
