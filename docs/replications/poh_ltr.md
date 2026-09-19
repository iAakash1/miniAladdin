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
| Original compute | Not reported; models include RankNet, LambdaMART, ListNet and ListMLE |
| Original result | Best reported Sharpe 2.156 gross, monthly, with no transaction costs; no strong boosted-regression comparator |
| MacBook plan | None beyond archived EXP-009B, which completed four eight-fold cells in 628 s CPU |
| Kaggle plan | None; GPU is not the missing ingredient |
| Estimated data preparation | None for local approximation; exact CRSP NYSE history is licensed |
| Complexity | MEDIUM |
| Leakage risk | Incorrect grouping across dates; ordinal-label transformation; overlapping horizon |
| Licensing risk | Algorithms open; local input licenses unchanged |
| Recommendation | **REJECT NEXT CYCLE** after EXP-009B |

That stop rule fired. LambdaMART produced ΔIC −0.0139 and net Sharpe −0.32;
pairwise produced ΔIC +0.0001 and net Sharpe +0.30 versus +0.46 for its matched
control. Neither improved ordering or turnover. Do not reopen EXP-009 or tune
relevance bins after seeing the null.
