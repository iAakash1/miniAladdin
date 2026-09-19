# EXP-009B preregistration — a ranking objective against a matched point-regression control

**Status: FROZEN. Registered before any ranker has been scored on real data.**
EXPERIMENTAL — PROMOTION NOT ASSESSED. Baseline commit `ee20529`.

Committed and pushed to `origin/main` **before** execution.
`python -m scripts.quant.exp009b run` refuses to run unless this file embeds the
definition fingerprint below, is committed unchanged, and its commit is an ancestor of
`origin/main` (`src/quant/study/prereg.py`, tested against a real temporary git
repository). The fingerprint covers the definition **and the source of every method
file**, including the study module itself: any later change to any of them moves the
fingerprint and blocks the run until a visible, dated amendment is added below.

## 1. What was known when this was written

* EXP-006's frozen gradient-boosting predictions, and the EXP-009A results
  (`docs/EXP_009_RESULTS.md`): top-k dropout with a 10% drop budget was
  `MECHANISM_CONFIRMED` and is the frozen turnover mechanism.
* **An outcome-free validity check was run before registering:** the sklearn
  `GradientBoostingRegressor`, refit through the new pipeline (rebuilt pre-holdout
  dataset `ds-491d761b9f2a6fc4`, the recorded EXP-006 folds, training-fold median
  imputation), reproduces EXP-006's 100,246 frozen predictions with a **maximum absolute
  difference of 0.0**. The dataset and the split are therefore the ones EXP-006 used.
* A timing run of five LambdaMART iterations on the largest training fold (no metric
  computed). The rankers have otherwise been exercised **only on synthetic data** in
  unit tests: finite-difference gradients, exact equality of the `l2` objective with
  sklearn's, query discipline.
* **No ranker has been scored on any real prediction.**

## 2. Question

**Q-B.** On identical data, folds, features, tree learner, hyper-parameters and seed, does
a ranking objective order the cross-section better than a squared-error objective — and if
it does, does the improvement reach net performance under the turnover mechanism
EXP-009A froze, or is it bought by re-ordering the book every week?

A better Rank IC is not "accuracy" and is not profit. The design keeps ordering,
stability and economics separate because the literature's ranking gains are gross of costs.

## 3. Cells

Everything below is identical in every cell except the objective. The boosting loop is
written in `src/quant/models/ranking.py`; the repository declines a third boosting
library and LightGBM cannot load without a system OpenMP runtime. With
`subsample = 1.0` the `l2` objective reproduces sklearn's `GradientBoostingRegressor`
to 1e-9 (unit-tested), which is what licenses calling it a control.

| Cell | Objective | Role |
|---|---|---|
| `R0_sklearn_gb` | sklearn `GradientBoostingRegressor` | **validity gate only** (must reproduce the frozen predictions to 1e-9); not a trial |
| `R1_boosted_l2` | squared error on the continuous rank label | **control** |
| `R2_boosted_lambdamart` | pairwise logistic loss, pairs weighted by \|ΔNDCG\|; linear gains, log₂ discount, whole list, σ = 1 | ranker 1 |
| `R3_boosted_pairwise` | pairwise logistic loss, uniform pair weights | ranker 2 |

Hyper-parameters (the repository's own `GradientBoostedTrees` defaults, not tuned):
200 rounds, learning rate 0.03, depth 3, subsample 0.7, min leaf 50, seed 0, friedman_mse
trees, Newton leaf values. **No hyper-parameter search of any kind.** Dataset
`ds-491d761b9f2a6fc4` (452,524 rows, returns-panel sha256
`d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e`, capped 2025-05-09),
the 27 frozen `C_base` features, target `fwd_rank_21`, universe-only rows, the eight
folds recovered from EXP-006's recorded plan (first validation 2017-05-05, last 2025-05-09).

**Queries.** One query per prediction date; pairs form only inside a date. **Relevance
labels** are the within-date quintile of the forward return —
`clip(floor((rank + 1)/2 × 5), 0, 4)` — fixed now, depending only on the label's scale,
matching the five buckets the portfolio holds the extremes of. The within-quintile ordering
is discarded on purpose; the book does not use it. **Ties:** score ties are broken by row
order (stable). **Group size** ≈ 250 names. **Weighting:** none beyond the pair weights.
**Truncation:** none (the whole list).

**Not run:** LightGBM/XGBoost (not installed), ListNet/ListMLE, a two-sided (both-tail)
NDCG training objective, neural rankers, any search. The two rankers are the two the
position-weighting question needs: one top-weighted (LambdaMART), one position-agnostic.

## 4. Metrics

* **Ordering (no portfolio):** pooled per-date Rank IC (Newey-West, 4 lags), ICIR, fold IC
  for all 8 folds, worst fold, positive-fold count; NDCG@50 at the long end and at the short
  end (relevance and score reversed); mean realised rank of the 50 names predicted best and
  worst and their spread.
* **Stability:** mean rank correlation between consecutive dates over shared names;
  top-quintile and bottom-quintile retention one date later.
* **Portfolio (both constructions, primary 10 bp, sweep 1/3/5/10/20):** the immediate-
  replacement control and the frozen top-k dropout — gross/net Sharpe, annualised turnover,
  max drawdown, cost share, break-even half-spread, per-fold metrics.
* **Diagnostics (not criteria):** train IC and the train–validation gap, prediction
  dispersion (native units, not comparable across objectives), deflated Sharpe
  (163 cumulative trials), fit seconds per fold.

## 5. Criteria (per ranker, against `R1_boosted_l2`)

| ID | Criterion |
|---|---|
| **Validity** | dataset id and returns-panel hash equal the values above **and** the sklearn refit reproduces the frozen predictions to 1e-9. Otherwise INVALID and nothing is reported. |
| **O1** ordering | paired per-date Rank-IC difference (ranker − control) > 0 with one-sided HAC lower bound (Bartlett, 4 lags, z = 1.96 = 1 − 0.05/2) > 0 |
| **O2** consistency | IC difference > 0 in ≥ 6 of 8 folds **and** worst-fold IC ≥ control's − 0.005 |
| **O3** stability | consecutive-date rank correlation, top-group retention and bottom-group retention each ≥ control's − 0.02 |
| **E1** economics | under top-k dropout: annualised turnover ≤ 1.10 × the control's **and** the paired block-bootstrap (block 8, 10,000 draws, seed 0) one-sided lower bound of Δ net Sharpe at 10 bp, level 1 − 0.05/2, is > 0 |

**Classification:** `ORDERING_AND_NET_IMPROVED` = O1∧O2∧O3∧E1 (retain as the BASE for
EXP-009C); `ORDERING_IMPROVED_NOT_ECONOMIC` = O1∧O2∧O3∧¬E1 (**not a success**: an
ordering gain that does not survive costs); `ORDERING_IMPROVED_UNSTABLE` = O1∧¬(O2∧O3);
`NO_ORDERING_GAIN` = ¬O1.

**Carry-forward.** The BASE model for EXP-009C is the `ORDERING_AND_NET_IMPROVED` ranker
with the larger IC difference; if none, BASE is the sklearn `GradientBoostingRegressor` (the
frozen point-regression baseline). **Nothing is promoted.**

## 6. Inference, trials, compute

HAC and block-bootstrap, never IID (labels overlap ~76%). The 0.05 family level is split
across the two rankers. **Trials:** 160 (through EXP-009A) + 3 (control and two rankers)
= **163**. Compute: CPU only, single-threaded per model (determinism), four models in
parallel, expected ≈10–15 minutes wall. Outputs in `experiments/EXP-009B/`: definition,
manifest (preregistration hash and commit, definition fingerprint, dataset id and content
hash, feature-list hash, git commit, package versions, seed, folds, compute, output
sha256s), metrics, per-cell predictions and portfolio period files. No licensed raw data.

## 7. Governance

Holdout untouched: firewall engaged, window widened to the earliest start EXP-006 recorded
anywhere (2025-08-26 in the plan, 2025-08-28 in the contract) through 2026-08-28; the dataset
ends 2025-05-09. No override. No production change. Negative results are results: a
ranker that fails is reported with the others and no parameter is adjusted afterwards.

## 8. What this cannot show

That LightGBM's lambdarank would behave the same (a different tree learner); that a
both-tail objective would do better; that ranking helps at another horizon or universe; or
that a better ordering is profitable — only E1 speaks to that, on one frozen sample.

## 9. Recorded predictions (made before any ranker is scored)

1. **No ranker meets O1.** Any IC difference will be within ±0.005 and inside the HAC
   noise; the literature's gains were against weak baselines and gross of costs.
2. `R2_boosted_lambdamart` will be **worse than the control on the short end** (NDCG@50 short)
   because its pair weights are top-heavy; `R3_boosted_pairwise` will be closest to the control.
3. Binning the label into five grades will cost a little IC relative to the continuous-label
   regression; the rankers' train–validation gaps will be similar to the control's.
4. My probability that at least one ranker is `ORDERING_AND_NET_IMPROVED`: about 10–15%.

## 10. Amendments

None.

Definition fingerprint: `a23850117183e15c130c8c1645a858a356110eb5a466c9ad8863f99bd9763f42`
