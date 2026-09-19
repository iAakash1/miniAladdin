# EXP-009C preregistration — point-in-time analyst-revision features added to the base set

**Status: FROZEN. Registered before either arm has been scored on real data.**
EXPERIMENTAL — PROMOTION NOT ASSESSED. Baseline commit `45be238`.

Committed and pushed to `origin/main` **before** execution. `src/quant/study/exp009c.py` refuses to run
unless this file embeds the definition fingerprint below, is committed unchanged, and its commit is an
ancestor of `origin/main` (`src/quant/study/prereg.py`). The fingerprint covers the definition **and the
bytes of every method file**, including the analyst feature construction and the study module: any later
change moves it and blocks the run until a dated amendment is added below.

## 1. What was known when this was written

* EXP-009A: top-k dropout with a 10% drop budget is the frozen turnover mechanism.
* EXP-009B: both rankers were `NO_ORDERING_GAIN`; by its preregistered carry-forward rule the **BASE model
  is the sklearn `GradientBoostingRegressor`** (EXP-006's frozen point-regression baseline).
* **The analyst data audit is finished and is outcome-free** (`docs/ANALYST_DATA_FORENSICS.md`, go/no-go in §6):
  every required PIT check passes, including a cross-table timing test against announcement dates (the
  "Current Quarter" label rolls a median 4 days *after* the report; consensus equals the realised EPS on only
  5.7% of events) and three real-data gates run before registration (truncation invariance, future
  perturbation over 352,161 rows, strict attach over 34,090 rows). Coverage of the eight features was measured
  (86-91% for the 4-week revision from 2019; 69-72% for the 13-week; ≥ 95% for dispersion and coverage).
* **Neither arm has been scored on any real prediction.** The features and the runner have been exercised only
  on synthetic data in unit tests and end-to-end smoke tests.
* Prior: low. EXP-005's ablation was negative; the only 2026 paper finding predictive value in analyst revisions
  (Cao, Tao, Wang & Yin, *Review of Finance*) needs analyst identity, which this data does not contain, so it is
  **not** being reproduced here.

## 2. Question and isolation

**Q-C.** Holding the model, hyper-parameters, seed, folds, imputation, target and portfolio logic fixed, does adding
eight point-in-time analyst-revision features to the 27 frozen `C_base` features improve the ordering of the
cross-section, and does any improvement survive costs under the frozen turnover mechanism?

**Only the analyst feature family changes.** No earnings, options, fundamentals, sector neutralisation, second
model, different buffer, different horizon or different target is added. Different information would be a
separate later experiment.

## 3. The two arms (identical except the feature set)

| | BASE | ARM |
|---|---|---|
| Features | the 27 frozen `C_base` features | the same 27 + the 8 analyst features below |
| Model | sklearn `GradientBoostingRegressor`, repository defaults (200 rounds, learning rate 0.03, depth 3, subsample 0.7, min leaf 50), seed 0 | identical |

Dataset `ds-491d761b9f2a6fc4` (returns-panel sha256 `d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e`,
capped 2025-05-09); target `fwd_rank_21`; universe-only rows; the eight folds recovered from EXP-006's recorded plan;
training-fold median imputation. **No hyper-parameter search, no feature search.** The BASE arm must reproduce
EXP-006's frozen `gradient_boosting` predictions to 1e-9 (validity gate).

### The eight analyst variables — fixed now, from the data cadence and the literature, not from results

Source: the local `eps_estimate` and `sales_estimate` vintage tables, **FY1 ("Current Year") only**, rows dated
through 2025-05-09. Construction: `src/quant/features/analyst_pit.py` (25 leakage tests).

| Variable | Definition | Lookback |
|---|---|---|
| `analyst_eps_rev_4w` | (consensus(t) − consensus(t−28d)) / \|consensus(t−28d)\| | prior vintage within ±3 days of t−28d |
| `analyst_eps_rev_13w` | same, 91 days | ±5 days |
| `analyst_sales_rev_4w` | same on the sales consensus | 28 ±3 days |
| `analyst_sales_rev_13w` | same on the sales consensus | 91 ±5 days |
| `analyst_eps_dispersion` | (high − low) / \|consensus\|, **NULL when `count` < 2** | none |
| `analyst_eps_coverage` | the vendor `count` | none |
| `analyst_eps_coverage_chg_13w` | count(t) − count(t−91d) | 91 ±5 days |
| `analyst_eps_rev_acceleration` | 4-week revision now − 4-week revision one step earlier (three consensus points, one period) | 28 + 28 days, ±3 each |

* **Horizons** are the two the revisions literature uses (a month and a quarter) expressed as calendar lookbacks
  because the vintage cadence is weekly only from 2019. **No other window (1w, 2w, 8w, …) will be tried.**
* **Fiscal rollover:** a revision is computed only where `period_end_date` is unchanged across the comparison;
  otherwise NULL. **Stale vintage:** a vintage older than 45 days is not attached. **Same-day vintages:** a panel row
  sees only vintages dated strictly before it. **Near-zero denominators** (|consensus| < 0.05) give NULL.
* **Missingness:** missing stays missing until the fold's imputer, which replaces it with the training fold's
  median of the (centred rank) feature. Each feature is ranked within the universe on its date, so a fully missing
  cross-section stays NULL. Coverage and missingness by year and by fold are recorded in the manifest.
* **Not created:** analyst stickiness, recommendation changes, target-price revisions and individual forecast
  errors, which need data the tables do not hold (`NOT REPRODUCIBLE`).

## 4. Which folds can speak

The analyst tables begin 2017-10-26. A fold is **evaluable** iff its training window holds at least 24 months of
analyst history — a function of the recorded plan, fixed now: **folds 3, 4, 5, 6, 7** (validation 2020-05 → 2025-05).
Folds 0-2 are reported descriptively and enter no criterion; the run aborts as INVALID if the rule does not
yield exactly this set.

## 5. Gates (before any model is trained)

1. Rebuilt dataset id and returns-panel hash equal the values above.
2. **Analyst PIT gates on the real data** at cutoff 2022-12-31: truncation invariance; rewriting every later
   vintage changes no earlier feature; strict attach (no feature from a vintage dated on or after its row).
   **If any fails, the outcome is `BLOCKED_DATA_QUALITY`, nothing is trained and no metric is computed.**
3. The BASE arm reproduces the frozen EXP-006 predictions to 1e-9.

## 6. Metrics

Rank IC (pooled over evaluable folds and over all folds), HAC t, ICIR, fold IC for all eight folds, worst
evaluable fold, positive folds, NDCG@50 at both ends, mean realised top/bottom rank and spread, stability
(consecutive-date rank correlation, top/bottom retention); under **both** portfolio constructions (immediate
replacement and the frozen top-k dropout): gross and net Sharpe at 1/3/5/10/20 bp, annual turnover, cost
share, max drawdown, break-even half-spread, names replaced and holding spell, per-fold economics; the
analyst block's share of split-gain importance (descriptive — importance is not value); incremental coverage.

## 7. Criteria (ARM against BASE, evaluable folds only)

| ID | Criterion |
|---|---|
| **O1** ordering | paired per-date Rank-IC difference (ARM − BASE) > 0 with one-sided HAC lower bound (Bartlett, 4 lags, z = 1.645) > 0 |
| **O2** consistency | IC difference > 0 in at least **4 of the 5** evaluable folds and worst evaluable-fold IC ≥ BASE's − 0.005 |
| **E1** economics | under top-k dropout at 10 bp: annualised turnover ≤ 1.10 × BASE's **and** the paired block-bootstrap (block 8, 10,000 draws, seed 0) one-sided lower bound of Δ net Sharpe, level 0.95, is > 0 |

**Classification:** `ANALYST_VALUE_CONFIRMED` = O1∧O2∧E1; `ANALYST_ORDERING_ONLY` = O1∧O2∧¬E1;
`ANALYST_NO_RELIABLE_VALUE` = otherwise; `BLOCKED_DATA_QUALITY` = any PIT gate fails. No intermediate
"promising" class. A single arm, so one-sided α = 0.05 with no family split. **Nothing is promoted.**

## 8. Inference, trials, compute, outputs

HAC and block-bootstrap, never IID. **Trials:** 163 (through EXP-009B) + 1 = **164**. CPU only; two sklearn fits,
expected ≈ 10-15 minutes. `experiments/EXP-009C/`: definition, manifest (preregistration hash and commit,
fingerprint, dataset id and hash, PIT-gate results, coverage, git commit, package versions, seed, compute, output
sha256s), metrics, per-arm predictions and period files. No licensed raw data.

## 9. Governance and limitations

Holdout untouched (firewall engaged; window widened to the earliest start recorded, 2025-08-26 → 2026-08-28; the
dataset ends 2025-05-09). No override. No production change. A null result is a result; nothing is adjusted after
seeing it. **What this cannot show:** that analyst information is useless (a different vendor, monthly vintages,
analyst identity, or other horizons were not tried); that the vendor's timestamps are exactly what they appear to
be (inferred, not documented); or anything about folds 0-2. **Artifact risk:** 13-week features are null in the first
months of each year (fiscal rollover), a calendar pattern a tree could learn as if it were signal; coverage
by year is reported so this is visible.

## 10. Recorded predictions (made before either arm is scored)

1. The PIT gates pass (they already have on the real data).
2. The classification will be `ANALYST_NO_RELIABLE_VALUE` (my probability ≈ 75%); `ANALYST_VALUE_CONFIRMED`
   about 5-10%; `ANALYST_ORDERING_ONLY` the remainder.
3. The evaluable-fold IC difference will be within ±0.005 and inside the HAC noise.
4. The analyst block will take a non-trivial share of split-gain importance (10-25%) — a tree spends splits on any
   available feature — and that share will not indicate value.

## 11. Amendments

None.

Definition fingerprint: `c447097e732bed6d902ea6ae7852ccaf64bb52082254ca33dacc587004cd384e`
