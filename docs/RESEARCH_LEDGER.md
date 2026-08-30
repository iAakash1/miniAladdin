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

---

## Multiple-testing exposure

| Study | Configurations | Targets | Evaluations | Counts against significance |
|---|---|---|---|---|
| EXP-001 | 12 | 1 | 12 | yes |
| EXP-002 | 17 | 2 | 34 | yes |
| EXP-003 | 0 | 0 | 0 | no |
| **Running total** | | | **46** | |

Any future deflated-Sharpe calculation on these validation folds must use a
trial count of **at least 46**, not the 17 that EXP-002 reported. EXP-002's own
deflated Sharpe was therefore *understated* in severity — and it already
rejected every candidate.

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
