# MODEL-LAB-001 results

Status: **SMOKE GATE COMPLETE — EXPLORATORY — NO CANDIDATE**

Dataset: Rich PIT v2 `ds-richpit2-6368cccdb94c62d0`, using only the pinned
`F0_UNAFFECTED_BASELINE_26` block. Revenue-affected feature sets are blocked.
The final holdout is sealed and untouched. EXP-012 is blocked and not prepared.

Initial development smoke attempts were retained as `INVALID` because the first
inner-window geometry produced only one split and later because method code was
not yet committed. They are implementation evidence, not model evidence.

The clean smoke gate ran from method commit `a11b5e2` with three inner temporal
splits for every selected configuration. It produced 30 complete records and
retained 22 invalid implementation records. There were no runtime failures.

| Family | Fold-0 outer Rank IC | HAC t | Train − validation IC | Result |
|---|---:|---:|---:|---|
| Ridge | -0.0582 | -2.62 | +0.1056 | negative |
| Lasso | -0.0590 | -2.63 | +0.1068 | negative |
| ElasticNet | -0.0587 | -2.63 | +0.1064 | negative |
| Huber | -0.0619 | -2.93 | +0.1091 | negative |
| SGD-Huber | -0.0722 | -3.72 | +0.1173 | negative |
| PCA + Ridge | -0.0481 | -1.74 | +0.0728 | negative |
| PLS | -0.0663 | -2.78 | +0.1057 | negative |
| Random Forest | -0.0424 | -1.87 | +0.3435 | negative; overfit warning |
| Extra Trees | -0.0444 | -1.46 | +0.4897 | negative; overfit warning |
| Histogram boosting | -0.0115 | -0.45 | +0.2479 | negative; overfit warning |

All ten smoke outer evaluations were negative. Histogram boosting was merely
the least negative observation; it is not a winner, a candidate, or evidence
of profitability. The smoke fold is pipeline evidence and cannot establish
fold robustness, economics, stochastic stability, diversity, ablation results,
or multiple-testing-adjusted significance.

Authoritative counts and trial metrics are generated into
`data/manifests/model_lab_summary.json` after each resumable run and rendered in
Quant Lab. This document is updated only from that ledger; negative results and
runtime failures are not removed.

No candidate is eligible or shortlisted during the smoke stage. The next
admissible action is the declared eight-fold screening campaign, followed by
robustness and only then any separately preregistered confirmation design.
