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
| Compute/storage | CPU; fixed models in hours; current frozen panel fits locally; <5 GB new artifacts |
| Complexity | MEDIUM |
| Leakage risk | Statement restatements, market-cap/identifier history |
| Licensing risk | Original data requires WRDS; the authors also share a derived characteristic dataset and simulation-only Matlab code (no license), whose redistribution terms were not verified; local open substitutes are not equivalent. No transaction costs are charged in the paper. |
| Recommended ID | `EXP-009-GKX-LITE` only after core EXP-009, because broad feature comparisons already exist in EXP-005 |

Recommendation: use GKX as a baseline architecture and reporting standard, not
as a performance replication claim.
