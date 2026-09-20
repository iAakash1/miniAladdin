# MODEL-LAB-001 protocol

Status: **EXPLORATORY**. This is not EXP-012 and cannot promote a model.

## Question

Which predeclared model families extract stable cross-sectional ordering from
the point-in-time panel, after hyperparameters are selected only inside each
outer training window?

## Fixed elements

- Target: `fwd_rank_21`.
- Outer evaluation: the eight recorded EXP-006 temporal folds.
- Inner selection: three expanding temporal splits inside each outer training
  window, each with 65 sessions of validation and a 21-session purge plus
  five-session embargo (six sampled observation dates).
- Portfolio economics: the frozen 21-session cadence, 10% top-k dropout,
  long/short construction, constraints and 1/3/5/10/20 bp half-spread grid.
- Holdout: 2025-08-26 through 2026-08-28, sealed. No runner override exists.
- Seeds: stochastic robustness uses the full fixed set 0 through 9. No seed is
  selected.

## Data integrity boundary

The campaign currently admits only `F0_UNAFFECTED_BASELINE_26` from Rich PIT v2
`ds-richpit2-6368cccdb94c62d0`. Its pinned content hash is
`3141e8d2a6635c66def0d20dbef0f4dd6bebd88b5d828f48f204b3ccea1a6e15`.
It contains none of the 14 revenue-dependent features identified by the
outcome-firewalled EXP-011 mapping audit. Fundamental feature sets remain
blocked until the replication/data decision is resolved.

## Selection and evaluation

For each family and outer fold:

1. Evaluate every declared configuration on the three inner temporal splits.
2. Select by mean inner Rank IC only.
3. Refit that configuration on the complete outer training window.
4. Transform and evaluate outer validation once.
5. Store the inner trials, outer trial, hashes, timings, warnings and failures.

Outer validation never selects a hyperparameter. Imputation, scaling and
dimension reduction are refit inside each training split.

The smoke stage executes inner selection on fold 0 only. It does not score the
outer validation window. Outer evaluation begins only after the complete
declared family grid is available to the screening/outer-walk-forward stage.

## Stop conditions

Leakage, PIT violation, corrupted/misaligned data, holdout access, broken
lineage, irreproducibility, invalid evaluation or genuine resource exhaustion
stop execution. Weak, negative or economically unusable results do not.

## Candidate eligibility (declared before the complete campaign)

Eligibility requires positive mean outer Rank IC, no catastrophic fold
dependence, an acceptable train-validation gap (no `OVERFIT_WARNING` at 0.15),
stable stochastic distribution where applicable, clean leakage guards and
reproducible artifacts. This is a filter, not a winner score. Any eligible
configuration still requires separately preregistered replication.
