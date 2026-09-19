# Replication candidate: cross-sectional learning to rank

| Item | Assessment |
|---|---|
| Original paper | [Building Cross-Sectional Systematic Strategies by Learning to Rank](https://arxiv.org/abs/2012.07149), Poh, Lim, Zohren & Roberts |
| Hypothesis | Pairwise/listwise structure improves asset ordering versus sorting point forecasts |
| Original data/target | CRSP NYSE common stocks 1980-2019; price-based momentum inputs; 21-day volatility-normalised return learned as ranks |
| Original model | Modern pairwise/listwise LTR; paper reports about threefold Sharpe improvement over the best heuristic ranking (2.16 vs 0.70), **gross of transaction costs**, monthly, NYSE 1980-2019, momentum-only |
| Evaluation | Temporal OOS systematic-strategy backtests |
| Data we have | Date-grouped US stock panel, continuous `fwd_rank_21`, fixed folds/cost engine |
| Data we lack | Exact same market/instrument panel and complete original implementation assumptions |
| Feasible substitute | LightGBM LambdaRank and XGBoost pairwise with each date as one query |
| Exact reproduction | Grouping discipline and rank-versus-point comparison |
| Approximation | Different market, target horizon, features, costs and portfolio |
| Compute/storage | CPU, <24 GB; three fixed cells; predictions/metrics <2 GB |
| Complexity | MEDIUM |
| Leakage risk | Incorrect grouping across dates; ordinal-label transformation; overlapping horizon |
| Licensing risk | Algorithms open; local input licenses unchanged |
| Recommended ID | Primary `EXP-009-LTR` candidate |

Stop if rank stability/worst-fold evidence and net performance do not improve;
do not tune NDCG or relevance bins after observing results.
