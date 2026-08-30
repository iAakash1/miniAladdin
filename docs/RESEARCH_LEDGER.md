# Research Ledger

Every experiment, in order, with whether it was allowed to influence model
selection. The last column is the one that matters: an experiment marked **YES**
has consumed some of the validation set's independence, and the running count
is the multiple-testing exposure that any significance claim must be discounted
against.

Append-only. Entries are never edited or removed — a superseded result gets a
new row saying so.

---

## Ledger

### EXP-001 — first end-to-end study (12 models)

| Field | Value |
|---|---|
| Git SHA | pre-`3d393f0` (working tree, uncommitted) |
| Dataset | `ds-e691b48ca49deb16` precursor, 2014-04-01 → 2026-08-30 |
| Feature version | 39 features (28 cross-sectional + 11 macro) |
| Models | 12: 5 baselines, 4 linear, 3 tree |
| Hyperparameters | fixed defaults, no search |
| Train / validation | 8 expanding folds, 252-session validation, 26-session gap |
| Holdout | untouched |
| Result | killed mid-run (OOM at 12 workers); partial |
| Decision | rerun with 6 workers |
| Reason | memory estimate omitted tree-ensemble peak allocation |
| **Influenced model selection?** | **YES** — partial results were seen before EXP-002's model list was fixed |

### EXP-002 — expanded ladder (17 models, 2 targets)

| Field | Value |
|---|---|
| Git SHA | `3d393f0` |
| Dataset | `ds-e691b48ca49deb16`, content hash `09f5ec8b…`, 506,374 rows / 977 symbols / 625 dates |
| Feature version | 39 used of 67 built |
| Models | 17 — zero, historical-mean, 5 factor passthroughs, OLS, 2 ridges, lasso, elastic net, GB, RF, HistGB, ExtraTrees, GB-deep |
| Hyperparameters | fixed in advance in `models/factory.py`; **no search performed** |
| Seed | 0 |
| Train / validation | 8 expanding folds; purge 21 + embargo 5 |
| Holdout | untouched |
| Runtime | 2,299 s, 6 workers, M4 Pro |
| Headline | `gradient_boosting` / `fwd_rank_21`: IC +0.0295, NW t +2.70, net SR +0.03 |
| Decision | **VOID** |
| Reason | **EXP-003 found that 12 of 39 features were misaligned by an as-of join defect.** All learned-model results invalid. The three single-feature baselines survive |
| **Influenced model selection?** | **YES** — and the influence is now known to be based on corrupted evidence |

**Surviving valid results from EXP-002** (single-feature passthroughs, unaffected):

| Model | `fwd_ret_21` IC | `fwd_rank_21` IC | NW t |
|---|---|---|---|
| `baseline_low_volatility` | +0.0209 | +0.0209 | +0.90 |
| `baseline_momentum` | +0.0158 | +0.0158 | +0.88 |
| `baseline_reversal` | +0.0015 | +0.0015 | +0.17 |

Neither baseline is significant at |t| > 2.

### EXP-003 — pre-holdout audit (no training)

| Field | Value |
|---|---|
| Git SHA | `5f0aa37` → this entry's commit |
| Dataset | unchanged |
| Models | **none trained** |
| Method | two-build contamination probe; AST scan for random splitters; scope audit of every fitted transform; PIT claim verification |
| Findings | (1) `merge_asof` index reset misaligned 12 features across rows and dates; (2) backtest traded at the close it observed; (3) test fixtures could not fail; (4) 3 regimes below 60 dates |
| Fixes | `_asof_aligned`; `execution_lag_periods` default 1; 3 regression tests; `check_contamination` gate; AST splitter detection |
| Verification | 465,090 pre-holdout rows, all 67 features identical with and without the holdout |
| Decision | **EXP-002 void; holdout NOT armed** |
| Reason | no candidate worth pre-registering exists on corrected evidence |
| **Influenced model selection?** | **NO** — no model was fitted, scored or ranked |

### EXP-004 — clean re-run on the corrected pipeline

| Field | Value |
|---|---|
| Git SHA | (this entry's commit) |
| Definition | `src/quant/study/experiment.py::exp_004`, fingerprint `5ac00830d9f01a25` |
| Dataset | `ds-e691b48ca49deb16`, content hash `fffb3fde0afc36b95fc93d5b5e54f226` |
| | 506,374 rows / 977 symbols / 625 dates / 2014-04-01 onward |
| Feature version | 39 used of 67 built (28 cross-sectional + 11 macro) |
| Models | 17 — **unchanged from EXP-002 on purpose** |
| Targets | `fwd_rank_21` (**primary, declared in advance**), `fwd_ret_21` |
| Hyperparameters | fixed defaults; **no search** |
| Seed | 0 |
| Walk-forward | 8 expanding folds, 252-session validation, purge 21 + embargo 5 |
| **Execution lag** | **1 rebalance period** (EXP-002 used 0, which is not achievable) |
| Cost sweep | 1, 3, 5, 10, 20 bp; **10 bp declared primary** |
| Holdout | **NOT TOUCHED.** 2025-08-28 → 2026-08-28; last fold ends 2025-05-09 |
| Integrity | truncation invariance CLEAN at 3 cutoffs, all strictly pre-holdout |
| Negative controls | shuffled-within-date (blocking), permuted-symbols (blocking), shifted-forward (**diagnostic — reclassified, see below**) |
| Multiple testing | discounted against **80 cumulative** evaluations, not 34 |
| Decision | see `docs/EXP-004.md` |
| **Influenced model selection?** | **YES, as validation evidence only.** It does not authorise holdout access; that requires arming the contract |

Design deliberately held constant from EXP-002 so that the pipeline fix is the
only moving part. Two things changed, both corrections rather than choices: the
execution lag, and the trial count used for the significance correction.

**Methodological change made during EXP-004, recorded rather than made quietly.**
The first attempt aborted: `shifted_forward` produced IC +0.0271 (t +2.00) on a
target displaced 4 rebalance periods, and the runner refused to fit any model.
A diagnostic then measured the same displacement against passthrough baselines
that provably cannot leak — `mom_252_21_xs` and `vol_63_xs` are backward rolling
windows with no fitting, no join and no as-of merge:

| model | real target IC | shifted target IC | retained | shuffled |
|---|---|---|---|---|
| `baseline_momentum` | +0.0158 | +0.0194 | **122%** | +0.0007 |
| `baseline_low_volatility` | +0.0209 | +0.0127 | 61% | +0.0050 |

A leak-free model retaining its IC on a displaced target means the control was
measuring **horizon persistence**, not contamination: 12-1 momentum is documented
to act over 3-12 months, so a target 20 sessions further out is still inside the
window it operates over. `shifted_forward` was therefore reclassified from a
blocking control to a reported diagnostic. `shuffled_within_date` and
`permuted_symbols` remain blocking and both passed (-0.0035 and -0.0009).

This is a change to a gate and is disclosed as one. It was made on independent
measurement from a model that cannot leak, not because the gate was
inconvenient — but a reader should weigh it knowing the gate had already fired.
Artifact: `experiments/EXP-004/shift_diagnostic.json`.

**Three further defects were found and fixed during EXP-004**, none of which
affected its results:

| Defect | Effect | Status |
|---|---|---|
| Controls built their calendar from the strided panel | `build_plan` refused outright — controls would otherwise have used different folds than the models | fixed, regression test |
| `build_feature_audit()` did not import the feature modules | emitted a well-formed audit reporting **zero** features | fixed, now raises on empty |
| `production_candidate` checked evidence existence but no numbers | a model with a complete bundle saying it loses money could be labelled a candidate | fixed — `CANDIDATE_THRESHOLDS` |

**Result — NO EVIDENCE OF EDGE.**

| Gate | Best model (`random_forest`, `fwd_rank_21`) |
|---|---|
| IC t-statistic | +1.91 — **fails** \|t\| > 2 |
| vs best free baseline | +0.0238 vs +0.0209 — a 0.003 gap, neither significant |
| Gross Sharpe | **−0.28 — loses before any cost** |
| Net Sharpe @ 10 bp | −0.60 |
| Six-factor alpha t | −1.34 |
| Deflated Sharpe p (80 trials) | 0.000 |
| Only quotable regime (267 dates) | IC +0.007, t +0.54 |

Correcting the join defect cost the learned models 17-56% of their IC and flipped
every linear model's sign, while the three unaffected passthrough baselines
reproduced **bit-identically** — confirming the invalidation scope was drawn
correctly. EXP-002's headline was roughly half contamination.

**Holdout decision: DO NOT ARM.** There is no candidate for a holdout to confirm.
`HOLDOUT_CONTRACT.md` remains NOT ARMED; production models remain **0**.

Registry: 34 entries at version `2.0` (`experimental`); EXP-002's 34 entries at
version `1.0` retired as VOID rather than overwritten, per rule 4 below.

---

## Multiple-testing exposure

| Study | Configurations | Targets | Evaluations | Counts against significance |
|---|---|---|---|---|
| EXP-001 | 12 | 1 | 12 | yes |
| EXP-002 | 17 | 2 | 34 | yes |
| EXP-003 | 0 | 0 | 0 | no |
| EXP-004 | 17 | 2 | 34 | yes |
| **Running total** | | | **80** | |

Any deflated-Sharpe calculation on these validation folds must use a trial
count of **at least 80**. EXP-002 discounted against its own 17 and therefore
understated the correction it needed — and it already rejected every candidate.
EXP-004 discounts against the full 80, which is set in its definition rather
than counted afterwards.

---

## Rules

1. **Append only.** A superseded entry gets a new row, never an edit.
2. **Every entry declares selection influence.** If results were seen before a
   subsequent design decision, the answer is YES even when the decision felt
   independent.
3. **Trial counts accumulate across studies** on the same validation folds.
   Resetting the count because the code changed is how multiple-testing bias
   is laundered.
4. **A void result stays in the ledger.** Deleting EXP-002 would erase the
   exposure it created.
5. **The holdout appears here exactly once**, when spent, with its receipt hash.

---

## Reproducing any entry

```bash
git checkout <git sha>
python -m scripts.quant.local_backfill --stage all
python -m scripts.quant.backfill --stage universe --universe-size 250
python -m scripts.quant.study --start 2014-04-01 --all-labels --seed <seed>
```

The dataset `content_hash` must match the entry. If it does not, either the raw
partitions or the feature code moved, and `study.json → dataset.source_datasets`
identifies which.
