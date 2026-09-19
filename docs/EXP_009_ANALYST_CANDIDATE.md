# EXP-009 candidate: analyst revisions

Status: candidate feature-family study; feature preparation already exists;
not run in this pass.

## Evidence

Analyst revision effects are longstanding. Recent peer-reviewed
[analyst-stickiness evidence](https://doi.org/10.1093/rof/rfag022) finds that
some analyst-level revisions predict more strongly, while
[Campbell et al.](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4495297)
show that most ML earnings-forecast specifications fail to beat analysts. The
family is relevant, but naive complexity is not.

## Local feasibility

The local EPS and sales estimate tables each hold 7,060,412 weekly vintage rows
from 2017-10-26, with zero duplicate vintage keys. Consensus is 4.60% null for
EPS and 12.30% for sales. They contain consensus/range/count and period end but
not analyst id, target price, recommendation or intraday publication timestamp.

Already implemented in `src/quant/features/estimates.py`:

- `est_eps_rev_4w`, `est_eps_rev_13w`;
- `est_sales_rev_4w`, `est_sales_rev_13w`;
- EPS dispersion, analyst count/change, expected growth.

The builder differences backward vintages only, nulls fiscal-roll changes and
caps staleness at 45 days. Missing values remain null.

## Candidate hypothesis and design

A small revision-only arm adds incremental rank information after the frozen
base when tested independently, not mixed with options and statements. Compare
base versus base + the eight registered estimate features under the same fixed
model/objective; if LTR is selected by an earlier stage, freeze it before this
ablation. Do not select individual estimate features on validation results.

Primary metrics are delta Rank IC and delta net Sharpe with fold-paired block
confidence intervals; also report coverage by date, coverage/size exposure,
turnover and performance around fiscal rollovers. The prior EXP-005 estimate
arm fell from IC 0.0290 to 0.0229, so the prior is cautious and a repeat without
a materially different preregistered question is not justified.

What cannot be tested locally: analyst-level stickiness, revision breadth by
analyst, target-price revision, recommendation changes and forecast age within
a week. Those require IBES/FactSet/LSEG-like detail or a verified substitute.
