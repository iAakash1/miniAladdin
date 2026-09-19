# Replication candidate: Gu–Kelly–Xiu tabular asset pricing

| Item | Assessment |
|---|---|
| Original paper | [Empirical Asset Pricing via Machine Learning](https://doi.org/10.1093/rfs/hhaa009), Gu, Kelly & Xiu, RFS 2020 |
| Hypothesis | Nonlinear ML extracts OOS cross-sectional return information from firm characteristics and macro interactions |
| Original data | CRSP/Compustat-style US panel; about 30k stocks, 1957--2016, 94 characteristics plus macro states |
| Target/model | Next-month excess returns; linear regularization, trees and neural nets |
| Evaluation/result | Temporal OOS predictive and portfolio comparisons; nonlinear models outperform linear baselines in the paper's setting |
| Data we have | PIT price/liquidity/macro, eight consensus-estimate, four earnings, eight options and ten statement features |
| Data we lack | Comparable 94-characteristic history, CRSP delisting returns, Compustat vintage history, long market-cap/sector master |
| Feasible substitute | Existing 57-feature registry after removing unsafe statement versions; liquid PIT universe |
| Exact reproduction | Model/evaluation taxonomy and cross-sectional normalization principles only |
| Approximation | Shorter 2012+ sample, top-250 liquid US universe and different features |
| Original compute | Hardware/runtime not reported in the paper. Monthly panel is about 30k unique stocks, ~6,200 per month and >900 inputs after characteristic–macro interactions |
| Original result | Trees and neural nets lead several gross OOS comparisons; model-dependent monthly turnover is roughly 110–130%; the paper does not charge transaction costs |
| MacBook plan | Build 60–120 PIT features in streaming Parquet, then run regularized linear + one boosted tree; 10 min–3 h depending model/seeds |
| Kaggle plan | Only optional CUDA boosting after a measured Mac run; two independent seed workers, 20–90 min planning range |
| Estimated data preparation | 3–8 engineering days for SEC facts/security identity plus formula/coverage validation; 1–4 h for a full panel materialization |
| Complexity | MEDIUM |
| Leakage risk | Statement restatements, market-cap/identifier history |
| Licensing risk | Original data requires WRDS; the authors also share a derived characteristic dataset and simulation-only Matlab code (no license), whose redistribution terms were not verified; local open substitutes are not equivalent. No transaction costs are charged in the paper. |
| Recommendation | **ADAPT** as EXP-011 only after EXP-010A/B and the PIT data build; never claim exact replication |

Recommendation: use GKX as a feature taxonomy, baseline architecture and
reporting standard, not as a performance replication claim. Keep the proven
top-k dropout layer fixed so the experiment identifies information gain.
