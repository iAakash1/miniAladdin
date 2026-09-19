# EXP-011 — does richer point-in-time company information improve cross-sectional ranking? (preregistration)

Definition fingerprint: `d5dd80d26131641efd8d3deda3526680fc08c8578957e69e7600ee53e6f4d9aa`

Status: **EXPERIMENTAL — DATA-VALUE STUDY — PROMOTION NOT ASSESSED — NOT RUN.**
Parent: EXP-010B. This document is committed and pushed before any arm is fit. The fingerprint is the SHA-256 of the canonical
definition in `src/quant/study/exp011.py` and of the bytes of every method file listed in §15; the runner refuses to start if any differ.

## 1. Question

Does a richer, genuinely point-in-time company information set improve **cross-sectional ordering** beyond the existing 26-feature
price/liquidity/macro panel, holding the target, the folds, the model classes, the imputation and the downstream portfolio fixed?

The discipline: **data value is isolated before model complexity.** Two feature sets are crossed with two model classes; the model is
never changed together with the data.

## 2. What has and has not been looked at

* No EXP-011 arm has been fit. No new feature has been scored against any return, in any period. The rich-panel audit reports
  coverage, identity resolution and missingness only.
* The only real-data model fit performed on the rich panel is a **timing benchmark**: one gradient-boosting fit per feature set on the
  fold-0 *training* rows, timed and discarded, with no prediction and no score.
* The rules in §10 were written before any rich-versus-baseline result existed. They are expressed in EXP-010A's own noise floor.
* The frozen EXP-010A predictions (arm E2) and the frozen EXP-010B portfolio are inputs, already public in the repository.

## 3. Arms

| Arm | Features | Model | Seeds | Source |
|---|---|---|---|---|
| **E0** | baseline 26 | Ridge, alpha 10.0 | 1 (deterministic) | fitted here |
| **E1** | baseline 26 + 50 PIT characteristics = 76 | Ridge, alpha 10.0 | 1 (deterministic) | fitted here |
| **E2** | baseline 26 | `GradientBoostingRegressor` (frozen) | 0–9 | **the ten frozen EXP-010A prediction files, hash-verified, not refit** |
| **E3** | 76 | `GradientBoostingRegressor` (same hyper-parameters) | 0–9 | fitted here |

No XGBoost, LightGBM, MLP or other model is run; there is no model zoo. Ridge alpha 10.0 is the pre-existing EXP-006 Ridge
configuration and is not searched. Boosting hyper-parameters are EXP-010A's (200 rounds, learning rate 0.03, depth 3, subsample 0.7,
min leaf 50); there is no hyper-parameter search. Ridge has one deterministic fit per fold, so it has **no** seed distribution.

Target `fwd_rank_21`, unchanged. Folds: the eight recorded EXP-006 folds, unchanged. Imputation: `FoldImputer` fitted independently on
each training fold (standardising for Ridge); missing values are never zeros.

## 4. Data (new immutable dataset; `ds-491d761b9f2a6fc4` is untouched)

| | |
|---|---|
| Dataset | `ds-richpit-ff3d3f556488b7da` |
| Content hash | `ff3d3f556488b7daa20bbbeab49d1f0abad9a869976b593f211cf92b6eb7c5da` |
| Feature-list hash (76 names) | `7212297bc55a45f66ffceb3548000e899773e1959e365b266fb477f24d8b8614` |
| Baseline-values hash (26 columns) | `f48c47f02da6407e060ca52ff1745935a99c0898fa5a7ce3fa6df3c5d7d5906e` |
| Rows / securities / tickers | 139,292 in-universe name-dates / 762 / 874, 2014-04-03 → 2025-05-09 |
| Built | from commit `fefc5af` on a clean tree; a second independent build produced a byte-identical Parquet file |
| Manifest | `data/manifests/rich_pit_panel_manifest.json`; catalog `docs/PIT_FEATURE_CATALOG.md`; audit `docs/RICH_PIT_PANEL_AUDIT.md` |

The 26 baseline columns are passed through **unchanged** (values hashed above). The 50 new characteristics are, by family: profitability 11,
investment 8, value 8, leverage 6, growth 6, quality 5, capital structure 3, event 3 — each defined in the catalog with formula, inputs,
timestamp rule, first valid date and measured coverage. Cross-sectional ranks (`_xs`) are formed among names with a value on each date.

**Withheld:** the seven CONTROL features (`log_market_cap` and six industry-relative characteristics), because `security_master_pit` is false
(§12). No industry or size neutralisation is applied anywhere in EXP-011.

Point-in-time basis: SEC Financial Statement Data Sets, 58 archives verified, `sec-core-facts-v3` (14,574,206 as-reported rows), availability at
EDGAR acceptance time in US Eastern with the after-close next-session rule; restatements are preserved as vintages and truncation invariance is tested
on real data. Macro vintages (ALFRED) are `BLOCKED_EXTERNAL_FRED_KEY`; the baseline rates features are unchanged.

## 5. Portfolio (frozen; not retuned)

Every arm's predictions are traded with the **EXP-010B B1 implementation**: rebalance every 21 sessions on the global calendar, the signal is
the latest prediction at least 5 sessions old, long/short quintiles with top-k dropout 10%, commission 1 bp, impact 0.1, half-spread grid
1/3/5/10/20 bp (primary 10 bp). Cadence, dropout and costs are **not** changed and no alternative is run.

## 6. Metrics

Ordering, per arm and seed: mean Rank IC, HAC t-statistic (4 lags), ICIR, the eight fold ICs, positive-fold count, worst fold. Economics (B1 only): gross
Sharpe, net Sharpe at 1/3/5/10/20 bp, annualised one-way turnover, cost share of gross, net maximum drawdown. Diagnostics: Rank IC on the **covered subset**
(rows with at least 20 of the 50 new features present and a trusted identity) and prediction-rank correlations E1–E0 and E3–E2.

## 7. Paired comparisons

| Comparison | Definition | Pairing |
|---|---|---|
| Data value, boosted | E3 − E2 | seed by seed, 0–9 |
| Data value, linear | E1 − E0 | one deterministic pair |
| Model value, baseline | E2(seed) − E0 | per seed |
| Model value, rich | E3(seed) − E1 | per seed |
| Interaction | (E3 − E2)(seed) − (E1 − E0) | per seed |

Statistics over seeds: mean, median, sample SD, min, max, p05, p95. Every effect is also expressed in EXP-010A seed SDs and p95−p05 ranges,
descriptively. Fold ΔIC and leave-one-fold-out medians are reported.

## 8. Noise context (EXP-010A, descriptive)

Rank-IC seed SD **0.001583**, p95−p05 **0.004156**; net-Sharpe seed SD **0.081651**, p95−p05 **0.219416**; turnover seed SD 0.019217. These are the scale
against which effects are read. No pass threshold is derived from them after the fact.

## 9. Diagnostics stated in advance

* **Coverage-matched ordering:** Rank IC restricted to covered rows, for every arm, so a difference cannot be produced purely by which rows have data.
* **Survivorship through missingness:** the panel audit measured that names about to exit are less often resolved (identity trusted 85.3% versus 93.6%,
  on 109 exiting rows). Models see missing values, not flags; the covered-subset diagnostic exists because this association is not zero.

## 10. Interpretation rule (applied mechanically; ordering only)

Unit: the EXP-010A Rank-IC p95−p05 range, **0.004156**. Economics are reported and **never labelled**.

* **Pair status.** Boosted pair: **IMPROVES** if the median paired ΔIC ≥ 0.004156 **and** ΔIC > 0 in at least 9 of 10 seeds; **DEGRADES** is the mirror
  (≤ −0.004156 and < 0 in at least 9 of 10); otherwise **NO_DETECTABLE_CHANGE**. Linear pair (one fit): **IMPROVES** if ΔIC ≥ 0.004156 and ΔIC > 0 in at least
  5 of 8 folds; **DEGRADES** if ≤ −0.004156 and < 0 in at least 5 of 8 folds; otherwise NO_DETECTABLE_CHANGE.
* **Fold-robust (boosted pair).** The seed-median fold ΔIC is > 0 in at least 5 of 8 folds **and** every leave-one-fold-out median ΔIC is > 0.

| Label | Condition |
|---|---|
| `RICH_DATA_IMPROVES_ORDERING` | boosted IMPROVES and fold-robust, and the linear pair also IMPROVES |
| `IMPROVES_ONLY_WITH_BOOSTING` | boosted IMPROVES and fold-robust, linear NO_DETECTABLE_CHANGE |
| `IMPROVES_ONLY_LINEAR` | linear IMPROVES, boosted neither IMPROVES nor DEGRADES |
| `NO_DETECTABLE_ORDERING_GAIN` | neither pair IMPROVES or DEGRADES |
| `RICH_DATA_DEGRADES_ORDERING` | at least one pair DEGRADES and none IMPROVES |
| `MIXED` | one pair IMPROVES and the other DEGRADES, or boosted IMPROVES but is not fold-robust |

A label is a statement about this comparison on this data. **Promotion is NOT ASSESSED** for every label; nothing is promoted, no seed is selected.

## 11. Limits stated in advance

* Ten seeds capture model-seed noise only; date-sampling uncertainty is not tested.
* Ridge is one deterministic fit; the linear pair has no seed distribution.
* The 50 new features exist only where an identity link graded A or B exists; foreign 10-K/10-Q-less issuers and unresolved delisted names have none.
* Share counts use the cover-page count where available, the balance-sheet count otherwise, and a labelled weighted-average proxy only where neither exists; splits are known from 2014-03-28.
* The universe, delisting bounds and survivorship caveats of the frozen dataset apply unchanged.
* A null result does **not** show that fundamentals carry no information: it shows that these 50 characteristics, on this universe and sample, added no detectable ordering beyond the baseline at this noise level.

## 12. Security-master status (why controls are withheld)

`security_master_pit = false`, computed from thresholds written before measurement: trusted identity is 91.8–95.0% by validation fold against 95%
(contradicted 0.2–1.1%, no 10-K/10-Q 4.2–7.1%, unresolved 0.0–1.6%); market cap of identified names is 90.8–95.1% (the 90% size threshold is met, but the size gate
also requires the master gate). Details: `docs/PIT_SECURITY_MASTER_STATUS.md`.

## 13. Holdout rule

The sealed holdout **2025-08-26 → 2026-08-28** is not read, scored, or used. The firewall is armed before any data is read, the runner asserts state
`SEALED`, the rich panel ends 2025-05-09, every prediction file passes `assert_clear`, and the manifest must contain `"holdout": {"touched": false}`.

## 14. Compute and commands

The models are scikit-learn (CPU). Measured: one gradient-boosting fit on the fold-0 training rows took 14.1 s with 26 features and 43.2 s with 76 (3.06×);
EXP-010A's eight-fold fit averaged 267 s per seed, so a rich seed is estimated at about 13.6 minutes.

| Where | Estimate | Note |
|---|---|---|
| **Mac (12 cores, 24 GB)** — recommended | Ridge arms about 1 minute; ten boosted seeds about 136 minutes of CPU, i.e. **about 30–45 minutes wall time with 6 workers**; analysis 3–5 minutes | independent single-threaded fits, deterministic |
| Kaggle | no GPU benefit (scikit-learn is CPU-only); expect roughly 1.5–3 hours on two independent CPU workers | provided so the pipeline is reproducible, not because it is faster |

```bash
python -m scripts.quant.exp011 fingerprint            # prints the fingerprint above
python -m scripts.quant.exp011 gate                   # requires this file committed and an ancestor of origin/main
python -m scripts.quant.exp011 dry-run                # verifies every pin and hash; fits nothing
caffeinate -dimsu .venv/bin/python -m scripts.quant.exp011 run --workers 6   # the study (the owner runs this)
python -m scripts.quant.exp011 summary
```

Kaggle (independent workers, not DDP; refuses without an explicit licence acknowledgement because the panel contains price-derived features from
sources whose terms are not yet reviewed):

```bash
python -m scripts.quant.export_kaggle_experiment --experiment EXP-011 --workers 2 --acknowledge-data-license
# upload artifacts/kaggle/EXP-011 as a private dataset; run kaggle_worker.py per worker id as in README_KAGGLE.md
python -m scripts.quant.import_kaggle_results --results results_worker0/results results_worker1/results
```

Imported results are rejected unless the definition fingerprint, dataset hash, feature hash, arm, seed, all eight folds, commit, device, runtime,
package versions (numpy, pandas, scikit-learn equal to those recorded in EXP-010A) and the prediction hash all verify.

## 15. Method files covered by the fingerprint

`src/quant/validation/runner.py`, `src/quant/models/linear.py`, `src/quant/models/trees.py`, `src/quant/models/base.py`, `src/quant/pit/rich_panel.py`,
`src/quant/features/pit_fundamentals.py`, `src/quant/pit/pit_coverage.py`, `src/quant/backtest/engine.py`, `src/quant/backtest/rules.py`,
`src/quant/study/exp009a.py`, `src/quant/study/exp009b.py`, `src/quant/study/exp010a.py`, `src/quant/study/exp010b.py`, `src/quant/study/exp011.py`.

Any change to the definition or a method file after this commit requires a new fingerprint and a new registration. The cadence question is closed for this research cycle.
