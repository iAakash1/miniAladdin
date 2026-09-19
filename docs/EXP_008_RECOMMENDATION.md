# EXP-008 recommendation

Decision date: 2026-09-19.

## Recommendation: conditional GO for implementation, NO RUN in this pass

Implement the already preregistered five-cell EXP-008, then require a clean
preflight and an explicit later run decision. Do not alter its hypotheses in
response to the 2026 literature review. No training, holdout access, EXP-007
rerun, or model promotion is authorized by this recommendation.

## Why

1. The problem is measured: overlapping labels leave only about 96 independent
   blocks, while EXP-007 spent 1,029 cumulative trials.
2. EXP-006/007 show positive rank information but weak/unstable net economics;
   turnover and extreme return moments are plausible binding mechanisms.
3. EXP-008 spends only five declared trials and tests those mechanisms without
   another model search.
4. Its outcomes are decision-useful even when negative: if the shorter label
   loses significance and allocators do not reduce MTRL by 10x, further search
   on this dataset should stop.
5. The necessary changes are bounded and testable, but are not implemented yet;
   a result cannot be responsibly scheduled before their leakage and control
   tests pass.

## What not to do

- Do not purchase options data or introduce text features into EXP-008.
- Do not add LambdaRank or rank-buffer variants to its five trials.
- Do not tune allocator parameters, costs, folds, or gates.
- Do not interpret a lower MTRL or positive net Sharpe as production approval.
- Do not open the holdout unless one single development candidate later clears
  every registered gate and the separate holdout contract is deliberately armed.

## After EXP-008

If both hypotheses stop, prioritize new independent information: a PIT security
master, SEC filing-time events, and audited analyst revisions. If EXP-008 makes
the evidence decidable but still not economic, a future **EXP-009** may compare
point regression with date-grouped LambdaRank and a fixed rank-entry/exit
buffer in a small factorial design. That proposal must be preregistered only
after EXP-008 completes, with its own cumulative trial accounting.
