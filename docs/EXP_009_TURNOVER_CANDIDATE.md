# EXP-009 candidate: turnover-aware construction

Status: design candidate only; not run.

## Evidence and observed failure

EXP-006 has 20.15x annual turnover and net Sharpe -0.102 at 10 bp despite gross
Sharpe 0.384. Qlib's official `TopkDropoutStrategy` demonstrates a fixed
hold/replace mechanism. [Bianchi & Zheng](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6359140)
report 24--45% turnover reduction from an uncertainty-based no-trade region,
and [Jensen et al.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217)
optimize an implementable frontier with trading costs. The evidence supports a
portfolio-layer test before a more complicated predictor.

## Primary candidate

Use the same predictions and portfolio constraints. Enter a long at or above
the 90th percentile and retain it until below the 80th; enter a short at or
below the 10th and retain it until above the 20th. Fill vacancies by current
rank. The 90/80/10/20 values are examples until preregistered; they may not be
searched after results are visible.

## Candidate cells

1. Immediate top/bottom quantile replacement control.
2. Fixed entry/exit rank buffer.
3. Fixed top-k/drop-d rule using one declared drop count.
4. Fixed exponential prediction smoother with one declared half-life.

Minimum-delta trades, holding-period constraints, cost-aware loss and rebalance
frequency are documented alternatives, not extra cells. Adding them would
require a later experiment because testing all of them is a parameter search.

## Metrics and attribution

Primary: net Sharpe at 10 bp and annual turnover. Secondary: gross Sharpe,
breakeven half-spread, cost share of gross, retained-name rate, rank/prediction
stability, capacity proxy, exposure drift, drawdown, factor alpha and each fold.
Report implementation shortfall separately from predictive IC; portfolio rules
cannot claim to improve prediction.

Promotion requires lower turnover and better net Sharpe without concentrating
the book or violating exposure/position constraints. A favorable rule remains
experimental and cannot change production silently.
