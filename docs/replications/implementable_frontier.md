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
| Original compute | Official repo: 12 model jobs at 32 CPU/~75 GB/≤5 h each; portfolio jobs use ~25–70 GB and up to 2 d 16 h; Slurm arrays |
| Original result | Net-of-cost frontier improves when the model internalizes implementation; final-paper numeric claims are not reproduced here because the lawful full text was unavailable |
| MacBook plan | Reuse only the economic framing and frozen turnover/cost reports; portfolio replay takes minutes |
| Kaggle plan | Do not attempt exact workflow: ~29 GB host RAM and 12 h sessions are below author requirements |
| Estimated data preparation | Weeks plus licensed JKP/WRDS inputs and optional Markit short fees for faithful replication |
| Complexity | HIGH for faithful replication; LOW-MEDIUM for buffer substitute |
| Leakage risk | Tuning cost penalty/portfolio constraints on validation outcomes |
| Licensing risk | WRDS/Markit data; official repository has no license, so it is reference-only |
| Recommendation | **ADAPT PRINCIPLE ONLY**; reject exact replication on Mac and Kaggle |

The simple substitute already answered the question: EXP-009A cut turnover
66% and moved net Sharpe from −0.102 to +0.390 without changing predictions.
An end-to-end economic loss would now confound a confirmed portfolio mechanism
with model selection and cannot be justified by available compute/data.
