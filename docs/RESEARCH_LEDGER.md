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

### EXP-005 — does any additional data source add information over price?

**Pre-registered.** Arms, models, metrics and trial count were fixed in
`src/quant/study/experiment.py::exp_005` and committed **before** the run. No arm
may be added after results are seen.

| Field | Value |
|---|---|
| Definition | `exp_005`, fingerprint `3f63b2b53a2a9419` |
| Question | EXP-004 found nothing in the feature set it had. Is the signal absent, or was the feature set? |
| Targets | `fwd_rank_21` only — `fwd_ret_21` was settled by EXP-004 and re-running it would double the trial count to re-answer it |
| Models | 17 on the full set + 6 per arm |
| Arms | 7, a ladder: each adds ONE family to a fixed base |
| Hyperparameters | fixed defaults; **no search** |
| Seed | 0 |
| Execution lag | 1 rebalance period |
| Cost sweep | 1, 3, 5, 10, 20 bp; 10 bp primary |
| Holdout | **NOT TOUCHED**, and now enforced at fit time by `study/firewall.py` |
| Evaluations | 17 + 42 = **59 declared**, 80 prior, **139 cumulative** |
| **Influenced model selection?** | **YES, as validation evidence only.** Does not authorise holdout access |

**New data brought into the panel.** Feature count 67 → 103 registered, 39 → 57
used. Two families had never been tested in this repository:

| Family | Rows | Point-in-time basis |
|---|---|---|
| `estimates` | 7,060,412 EPS + 7,060,412 sales vintages | **Observation-dated** — no gate required |
| `fundamentals` | 270,925 income + 284k×3 balance + 176,631 cash flow | **Period-keyed** — announcement gate required |

**A catalog reclassification, recorded because it weakens a prior refusal.**
`dolthub_earnings_income_statement` was classed `NOT_POINT_IN_TIME` and BARRED.
It is now `PUBLICATION_LAGGED`. The data did not change; the gate did.
`features/fundamentals.py` joins every period forward to its first
`earnings_calendar` announcement and drops any period without one — 77,277 of
196,879 quarters, all pre-2020. That is the mechanism already governing
`eps_history`, and two tables of the same shape now carry the same class.

The **timing** leak is closed. The **restatement** leak is not: one row per
period, no vintage column, so a correction overwrites the original
irrecoverably. Every `fund_*` feature is marked `restatement_risk=UNQUANTIFIED`
and isolated in arm F so its contribution can be discounted separately.

**Defects found and fixed while building EXP-005**, none affecting results:

| Defect | Effect | Status |
|---|---|---|
| `_admit` read the catalog but ignored the ingested manifest status | a partition ingested `not_point_in_time` was admitted on an optimistic catalog entry, and the contradiction was recorded rather than raised | fixed — stricter of the two wins |
| No runtime guard on holdout rows | the CLI refused the holdout *experiment*; nothing stopped a panel that ran past the cutoff from being fitted | fixed — `HoldoutFirewall`, asserted per fold before every fit |
| `build_feature_audit()` never imported the feature modules | emitted a clean, well-formed audit reporting **zero** features | fixed — raises on empty |
| `deflated_sharpe_probability` read at the wrong nesting in the service | rendered as an em dash; an absent correction looked identical to an uncomputed one | fixed, with a regression test |
| Three quant tables rendered outside a scroll container | wide tables pushed the page instead of scrolling internally | fixed |

**Negative controls** (run before any model was fitted):

| Control | IC | t | Role | Result |
|---|---|---|---|---|
| `shuffled_within_date` | −0.0037 | −1.07 | blocking | **PASS** |
| `permuted_symbols` | see artifact | | blocking | **PASS** |
| `shifted_forward` | +0.0170 | +1.30 | diagnostic | PASS |

`shifted_forward` fell from t +2.00 (EXP-004) to +1.30 with the larger feature
set, consistent with the horizon-persistence reading recorded under EXP-004
rather than with contamination.

**Integrity:** truncation invariance CLEAN at 3 cutoffs, 1,097,673 rows × 103
features, every cutoff strictly before the holdout.

**Result — NO. No additional data source adds information over price.**

Seven arms, six models each, same folds and seed; only the feature columns move.

| Arm | Features | Best IC |
|---|---|---|
| `A_price` | 8 | +0.0145 |
| `B_price_vol` | 13 | +0.0139 |
| **`C_base`** (price+vol+volume+macro) | **27** | **+0.0290** |
| `D_base_options` | 35 | +0.0275 |
| `E_base_estimates` | 35 | +0.0229 |
| `F_base_fundamentals` | 41 | +0.0124 |
| `G_all` | 57 | +0.0151 |

Contrast against `C_base`, which is the peak:

| Source added | mean ΔIC | models improved |
|---|---|---|
| options (8 GB, 116.5M rows) | −0.0060 | **1 / 6** |
| analyst estimate revisions | −0.0037 | **2 / 6** |
| earnings + statement fundamentals | −0.0210 | **0 / 6** |
| all four together | −0.0179 | **0 / 6** |

The best feature set is the smallest useful one. On the full 57-feature set the
only \|t\| > 2 belongs to the deliberately over-parameterised control (train gap
+0.718); the best genuine learned model is `random_forest` at t +0.89, losing to
two free baselines. Gross Sharpe is negative for every learned model — they lose
before costs. Alpha t is negative for all but `baseline_momentum` (+0.44). PBO
0.071; every deflated-Sharpe probability 0.000 against 139 trials.

Regime: in the only bucket with enough dates to quote (low-vol bull, 267 dates)
the best model scores IC +0.0019 at t +0.17. The two t-statistics above 2.0 sit
on 85 and 33 dates.

**A reporting defect in this study, disclosed.** The first pass wrote every arm's
IC and a blank for every arm's t-statistic: `_run_ablation` read the leaderboard's
field names off `pooled_ic`, where the t-statistic is `t_stat`. The fits were
correct; only the transcription was wrong. `scripts/quant/rerun_ablation.py`
recomputes the block and **refuses to merge unless every mean IC reproduces
exactly**. The trial count does not move — re-running a fixed pre-registered
configuration to recover a mis-transcribed metric adds no selection freedom.

**The one number that needs care.** `C_base` gradient_boosting reaches
**t = +2.66** — the strongest statistical result in five studies, and not from
the overfit control. It is nonetheless not evidence: it is the maximum of 42 arm
configurations, and the expected maximum of 139 zero-skill configurations is
**≈ 2.62**. It clears neither the 42-test Bonferroni threshold (3.24) nor the
139-test one (3.57), its t swings from +0.24 to +2.66 across feature sets, and no
backtest was run on the arms so it has never been costed. Recorded as the best
available **hypothesis** for a future pre-registered experiment with its own
trial budget — not as a candidate.

**Holdout decision: DO NOT ARM.** After 139 cumulative evaluations there is still
no candidate for a holdout to confirm. Production models remain **0**.

Full detail: `docs/EXP-005.md`.

---

## Multiple-testing exposure

| Study | Configurations | Targets | Evaluations | Counts against significance |
|---|---|---|---|---|
| EXP-001 | 12 | 1 | 12 | yes |
| EXP-002 | 17 | 2 | 34 | yes |
| EXP-003 | 0 | 0 | 0 | no |
| EXP-004 | 17 | 2 | 34 | yes |
| EXP-005 | 17 + 7x6 arms | 1 | 59 | yes |
| **Running total** | | | **139** | |

Any deflated-Sharpe calculation on these validation folds must use a trial
count of **at least 139**. EXP-002 discounted against its own 17 and therefore
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
