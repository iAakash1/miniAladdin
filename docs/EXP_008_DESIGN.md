# EXP-008 design and implementation contract

Status: **PRE-REGISTERED; NOT IMPLEMENTED; NOT RUN.** Design audit date:
2026-09-19.

The binding registration is `docs/EXP-008.md`, written 2026-09-01. This file
does not replace or expand it. The literature review occurred after that
registration, so adding LambdaRank, rank buffers, new features, or new gates to
EXP-008 would be outcome-aware protocol drift. Those ideas are candidates for
a separately numbered future experiment.

## Decision question

Can the existing evidence become statistically decidable without model search
by (H1) removing horizon overlap or (H2) reducing the extreme return-distribution
moments through a fixed portfolio allocator?

## Frozen inputs

- Model: EXP-007 selected `hist_gradient_boosting`, configuration
  `9d1651c56782`; no hyperparameter changes.
- Features: `C_base`, exactly as registered; no new source or feature pruning.
- Universe and folds: the frozen PIT liquid universe and eight expanding folds.
- Execution: one-period lag, 21-session purge where applicable, five-session
  embargo, and 10 bp half-spread.
- Holdout: sealed; the training/evaluation path must reject holdout-dated rows.
- Randomness: existing fixed seed and deterministic configuration ordering.

## H1: non-overlapping label

Implement `fwd_rank_5`: within-date cross-sectional rank of the five-session
forward return, with the same eligibility and missing-return policy as
`fwd_rank_21`. Five sessions match the evaluation cadence, eliminating label
overlap. This creates a new dataset version/hash; it must never overwrite the
EXP-006/007 manifest.

One and only one fit/evaluation is authorized: frozen model + `C_base` +
`fwd_rank_5`. Prediction: IC falls but its t-statistic may hold or rise because
the effective independent sample rises. Stop H1 if the t-statistic is below
+2.0.

Required tests before the run:

1. Synthetic five-session return/rank arithmetic.
2. Truncation invariance at three pre-holdout cutoffs.
3. No label whose forward window touches purge, embargo, or holdout.
4. Same-date rank range/tie/missingness behavior.
5. Dataset hash changes when and only when the new label/schema changes.

## H2: portfolio distribution

Apply four fixed allocators to the unchanged frozen EXP-007 signal:

1. `equal_weight` control;
2. `inverse_volatility`;
3. `volatility_target`;
4. `minimum_variance`.

Position caps and the existing turnover constraint are inherited. No allocator
parameter is tuned. Each must consume the same prediction rows and available-
at-the-time risk data, and must use the same lag/cost engine. Stop H2 unless
minimum track-record length falls by at least one order of magnitude. If it
remains 1,000+ periods against 403 available, the evidence is still undecidable.

Required tests before the run:

- Allocators cannot read realized forward returns or post-rebalance covariance.
- Equal weight reproduces the registered control bit-for-bit.
- Infeasible optimization returns an explicit failure, never implicit equal
  weights or zeros.
- Position, gross/net exposure, turnover and covariance-date constraints are
  asserted for every rebalance.

## Trial accounting and gates

| Item | Count |
|---|---:|
| H1 | 1 |
| H2 | 4 |
| New trials | **5 maximum** |
| Prior cumulative trials | 1,029 |
| Cumulative after run | 1,034 |
| Expected max absolute t under null | 3.39 |

Any sixth configuration voids this registration. The ten registered gates
remain unchanged: IC t-stat, gross and net Sharpe, best-baseline comparison,
overfit gap, search-size survival, factor alpha, turnover, deflated Sharpe, and
selection information. Report every gate, fold, cost point, skew, kurtosis,
MTRL and PBO whether favorable or not. H1 and H2 are not combined into a sixth
"best" portfolio.

## Interpretation table

| H1 | H2 | Permitted conclusion |
|---|---|---|
| Pass | Pass | Development evidence is more decidable; still not production and holdout remains a separate decision |
| Pass | Stop | Overlap was binding; allocator stabilization was not |
| Stop | Pass | Distribution/portfolio layer was binding; shorter label lost too much signal |
| Stop | Stop | Existing dataset cannot support a promotable result; acquire independent data rather than search |

No outcome authorizes promotion by itself. A passing development candidate
would still require the separate holdout contract and production gates.

## Explicit exclusions

No EXP-007 rerun, hyperparameter search, feature-family sweep, options/text
ingestion, LambdaRank, buffer tuning, cost selection, fold change, threshold
change, or holdout access. Literature-supported grouped ranking and turnover
buffers belong in a future preregistration only after EXP-008 concludes.
