# Replication candidate: implementable efficient frontier

| Item | Assessment |
|---|---|
| Original paper | [Machine Learning and the Implementable Efficient Frontier](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4187217), Jensen, Kelly, Malamud & Pedersen, SSRN 2024, published in the Review of Financial Studies 2026 |
| Hypothesis | Learning portfolio weights under trading costs improves the net implementable frontier |
| Original data/target | Large characteristic-based equity panel; economic portfolio objective |
| Original model | ML maps characteristics to weights with costs embedded; produces economic feature importance |
| Evaluation | Net portfolio frontier and implementation economics |
| Data we have | Frozen signals, cost sweep, allocator and risk engines |
| Data we lack | Equity bid/ask history, impact, borrow costs and the paper's licensed characteristic panel |
| Feasible substitute | Fixed no-trade/rank-buffer portfolio rule on frozen predictions |
| Exact reproduction | None beyond cost-first evaluation principles |
| Approximation | Post-model rule instead of end-to-end economic loss |
| Compute/storage | LOW for portfolio replay; HIGH if end-to-end optimizer is attempted |
| Complexity | HIGH for faithful replication; LOW-MEDIUM for buffer substitute |
| Leakage risk | Tuning cost penalty/portfolio constraints on validation outcomes |
| Licensing risk | Original data likely licensed; method paper accessible |
| Recommended ID | `EXP-009-TURNOVER`; defer end-to-end loss to later experiment |

The simple substitute is preferable because it identifies whether turnover is
binding without confounding predictor and optimizer.
