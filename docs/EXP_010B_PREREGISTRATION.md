# EXP-010B — horizon / rebalance-cadence study (preregistration)

Definition fingerprint: `ff9eb7df02abe08f5f8bb3c2e162d872b8de58d9545ac1290fe498fcaded2133`

Status: **EXPERIMENTAL — CADENCE STUDY — NO RETRAINING — PROMOTION NOT ASSESSED.**
Parent: EXP-010A (ten-seed noise floor). This document is committed and pushed before the study is run.
The fingerprint is the SHA-256 of the canonical definition in `src/quant/study/exp010b.py` and of the bytes of every
method file listed in §14; the runner refuses to start if any of them differ from what was registered.

## 1. Question

The model is trained to rank a **21-session** forward return, but EXP-006 through EXP-010A rebuild the book every **5**
sessions. Does rebuilding it every 21 sessions — the horizon the model was trained on — improve net economics or reduce
turnover, using *identical predictions and identical portfolio rules*?

This is a portfolio/execution study. Nothing is refit, no label is changed, and no new target is created.

## 2. Disclosure: one exploratory look before this registration

While implementing the schedule and alignment I ran a prototype of the B1 arm on **seed 0 only** and saw its output
(net Sharpe at 10 bp about 0.75, one-way annualised turnover about 2.34, against B0's 0.42 and 6.89 for that seed).
That run was a mistake in process: it should have been a synthetic check. It is disclosed so that the registration is read
with the correct weight:

* the schedule, alignment and eligibility rules (§4–§5) were fixed by the requirement that **B0 reproduce EXP-010A
  exactly** and by the calendar semantics in the task, not by any B1 result;
* the interpretation thresholds (§10) were written **after** that glimpse. They are expressed as sign counts and in units
  of EXP-010A's own noise floor, were not tuned to that output, and are deliberately not stricter or looser than a
  reader would choose without it — but they cannot be called blind;
* no other B1 economics were computed. The runner has still not been executed on the real study.

## 3. Inputs (frozen)

| Input | Value |
|---|---|
| Predictions | the ten EXP-010A files `experiments/EXP-010A/checkpoints/seed_00..09_predictions.parquet` (local, git-ignored) |
| Rows / dates per seed | 100,246 rows; 404 prediction dates, 2017-05-05 → 2025-05-09, every gap exactly 5 sessions |
| Dataset | `ds-491d761b9f2a6fc4`, content hash `7deb8601ae7a34074cade997397f1947` |
| EXP-010A definition fingerprint | `0b18e0ad7d90905988988a8cdd8d9251522000d7503d41045096c639bf64bba0` |
| Frozen 5-session returns panel | sha256 `d1f10c93dc747b949429aaba390e87a8412b1a79cdf8f672c15c68cacba0919e` |
| Daily returns panel (this study) | 2,264,756 rows, sha256 `5f00d3dfc0e6b624d231dc86d52e001aab34c0be313a9226cb91f279057e3001` |
| Trading calendar (this study) | 3,366 sessions 2012-01-03 → 2025-05-09, sha256 `b39ca1cdd13415b48a598270a56fcade03638286b5ba421d9a718e588327f538` |

Prediction hashes (EXP-010A `_prediction_hash`; each file is refused unless it matches):

| Seed | sha256 |
|---:|---|
| 0 | `127555e4ab24152b6fe266ea98310b18799a605b099ebe590852052c314cf945` |
| 1 | `ea4eeda09baa745cc34ba04455ea44c68ed28581b9e7153cd939cdc98948718b` |
| 2 | `c83c0e96a307db62d15e146dc1020a4527eab57a538c9fcd449618a9ee0bcd9e` |
| 3 | `5fcc520c209b2e8c39af4cf2000f2935a74bc9105a79e387919d2841aec2367e` |
| 4 | `8dccd3c6e43ef42b1f5295d2bb3844c420223226be04ac110c7a0dd02a22fa05` |
| 5 | `d63cb41f7426a075f7573e7e027a9e7aada9ae2e6ec47e94e1ec26637918b5c9` |
| 6 | `7fcb0d76935ef1f25d282a22c49457dadef39f3b029284f0ae9ad110259fc9a4` |
| 7 | `ae7813459def634b8cc59f773a07283090d0d55ed8f6d5ff932e3e2400549104` |
| 8 | `f3bf17f7d012e04dfe7f72dc89df003c54706b783217f49f8202ee7d2c442e0d` |
| 9 | `f50289c57e893e9046e00628b582b7648c6ec22885af57c6fddea24619ffeb0e` |

Committed EXP-010A artifacts (byte-identical or the run aborts):

| File | sha256 |
|---|---|
| `definition.json` | `a5dc4f6dec1bf7ec97039252a645599e1c92ea6ebfa79f0b32262b698e81c8ca` |
| `config.json` | `0565e0d9af7e5b4a53bd11f1a3ef09e00bda5e2c9d207540c35bd3e79a40c67f` |
| `manifest.json` | `46a569adc94afd7ed52dd560baaa2c95979ee9ea31684dcf969fe6e756f942d9` |
| `metrics.json` | `a7663e9c61f6f5a80654c037e0b279ff2caa317e7ea61c52d410120235c40025` |
| `per_seed_metrics.csv` | `81296585f20d9d6d68d9568e7bc99483b21b1669bcd18c3e691ac90900c28d7c` |
| `fold_metrics.csv` | `f2c4c2c954f662415bdbf27be15a6881d460693f14e57dc974fdf91844a4b4d9` |
| `prediction_hashes.json` | `1ab4e9f285f702b0c5009444ca4f1b6a3a6aae7e87a6d102a8578b8088b88a26` |

A checkpoint is regenerated **only** if it is missing or fails its hash, and only by running the unmodified EXP-010A
runner (`python -m scripts.quant.exp010a run`). EXP-010B never refits and never edits EXP-010A.

The daily panel is rebuilt with the same `DatasetBuilder` EXP-009A used, at a one-session step. Its rows on the
5-session grid dates hash identically to the frozen 5-session panel above (452,524 rows); this is checked on every run.
It is capped at 2025-05-09; the latest forward return it holds ends before the holdout.

## 4. Arms

| Arm | Rebalance step | Forward return traded |
|---|---:|---|
| **B0** | every 5 sessions | `fwd_ret_5` |
| **B1** | every 21 sessions | `fwd_ret_21` |

Exactly two arms. No 10/15/20/22/42-session cadence is run or evaluated, and no other phase of the 21-session cycle.

## 5. Calendar and alignment

**Schedule.** The calendar is the global observed trading calendar (a date is a session because price bars exist for it),
capped at 2025-05-09. The first rebalance for both arms is the first prediction date plus five sessions (2017-05-12);
after it the schedule is `sessions[i0 + k·step]` while the session is ≤ 2025-05-09. It is not month-end, not a
28-calendar-day jump, and not random. A missing ticker is absent from that date's book and never moves the schedule.

| Arm | Rebalances | First | Last | Session gaps |
|---|---:|---|---|---|
| B0 | **403** | 2017-05-12 | 2025-05-09 | all exactly 5 |
| B1 | **96** | 2017-05-12 | 2025-04-17 | all exactly 21 |

**Signal.** A 21-session cadence cannot land on the 5-session prediction grid (21 is not a multiple of 5). The signal for
a name at rebalance *t* is that name's latest frozen prediction dated **≤ *t* − 5 sessions** — the same one-period,
5-session information delay that B0 already receives from the engine's lag. For B1 the signal is therefore 5–9 sessions
old (5 to 9 depending on where *t* falls between grid dates); for B0 it is exactly 5 for continuously listed names.

**Eligibility.** A name is tradable at *t* if it is in the point-in-time universe at *t*, was scored on the latest
prediction date ≤ *t*, has a signal under the rule above, and has a finite forward return for the arm's horizon
(rows with a NaN forward return are dropped by the engine before ranking, identically in both arms).

**Stale re-entrants.** A name that leaves and re-enters the universe receives its latest *older* signal, exactly as the
engine's per-symbol shift does in EXP-010A. About 2.2% of B0 name-dates carry such a stale signal. It is reported per
arm (`share_signals_older_than_nominal`), not hidden.

**Engine.** `execution_lag_periods = 0`; the delay is applied by the alignment, identically for both arms.

**B0 must reproduce EXP-010A.** Through this alignment, B0's gross Sharpe, net Sharpe, annualised turnover, net maximum
drawdown and cost share at every cost must equal the committed EXP-010A per-seed values to 1e-9. The dry-run confirmed
a maximum absolute gap of 0.0 at 10 bp for all ten seeds. If the full-grid check fails the run aborts.

## 6. Portfolio and costs (unchanged between arms)

Long/short quintiles, top-k dropout with a 10% drop fraction (`{"rule": "topk_dropout", "quantiles": 5, "drop_fraction":
0.10}`), max weight 0.10, min 10 names, capital $1,000,000, commission 1 bp, impact coefficient 0.1, half-spread grid
**1 / 3 / 5 / 10 / 20 bp** (primary **10 bp**). The two arms differ only in `rebalance_step_sessions` (annualisation
252/5 vs 252/21) and the matching forward-return column. The drop budget is *per rebalance*, so the same 10% per rebalance
is a lower per-session churn at 21 sessions; that is the mechanism under test, not a confound.

## 7. Metrics

Per seed and arm: gross Sharpe; net Sharpe at all five costs; annualised one-way turnover; cost share of gross; net and
gross maximum drawdown; average completed holding duration (rebalances and sessions); names changed per rebalance;
number of rebalances; gross and net total return and CAGR; long- and short-leg membership retention; effective number of
names and maximum weight; eligible names; signal age (median, p95, maximum, share older than nominal).

## 8. Paired comparison

For each seed, **B1 − B0** for every metric above. Primary paired metrics: net Sharpe at 10 bp, annualised turnover, gross
Sharpe, net maximum drawdown, cost share of gross. Across the ten seeds: mean, median, sample SD, min, max, p05, p95, and
the count of seeds in each direction. `net_max_drawdown` is negative, so a positive difference is a *shallower* drawdown.
All ten seeds are always included; no seed is selected.

## 9. Fold and period economics

A rebalance belongs to the fold of the latest frozen prediction date at or before it (for B0 this is the row's own
date). Per seed, arm and fold: number of periods, annualised gross and net return, net Sharpe, annualised turnover, mean
cost. Across seeds, per fold: the B1 − B0 median and the number of seeds positive, printed next to EXP-010A's mean fold
Rank IC (−0.0146, +0.0402, +0.0545, +0.0315, −0.0074, +0.0324, +0.0396, +0.0811). Leave-one-fold-out: the pooled paired
net-Sharpe difference is recomputed per seed with one fold removed.

## 10. Interpretation rule (applied mechanically)

Unit *u* = EXP-010A's net-Sharpe seed sample SD, **0.081651**. It is a scale for "material", not a significance test;
EXP-010A defines no pass threshold and none is invented after seeing EXP-010B.

* **Turnover materially reduced:** median per-seed relative change in annualised turnover ≤ **−25%** and turnover lower in
  **all 10** seeds.
* **Net-Sharpe status** (paired, 10 bp): **IMPROVED** if the median difference ≥ *u* and at least 9 of 10 seeds are
  positive; **DEGRADED** if the median ≤ −*u*; otherwise **PRESERVED**.
* **Fold-robust:** for every fold, the seed-median leave-one-fold-out net-Sharpe difference stays > 0 when the status is
  IMPROVED, and > −*u* when PRESERVED.
* **Gross-equivalent:** |median paired gross-Sharpe difference| < *u*.

| Label | Condition |
|---|---|
| `ECONOMICALLY_IMPROVED` | turnover materially reduced AND status IMPROVED or PRESERVED AND fold-robust |
| `TURNOVER_REDUCED_SIGNAL_LOST` | turnover materially reduced AND status DEGRADED |
| `CADENCE_EQUIVALENT` | turnover NOT materially reduced AND status PRESERVED AND gross-equivalent |
| `NO_STABLE_ECONOMIC_GAIN` | every other outcome, including a gain that depends on a single fold |

Whatever the label, promotion is **NOT ASSESSED**; a label is a statement about this cadence comparison on this data, not
a model decision.

## 11. Limits stated in advance

* The ten-seed distribution captures model-seed noise only. Date-sampling uncertainty is not tested, and a 21-session
  book has 96 observations against 403, so its Sharpe and drawdown are estimated from far fewer, coarser points.
* Drawdown on 21-session periods cannot see the intra-period path and is mechanically shallower than on 5-session periods.
* Only one phase of the 21-session cycle (fixed by the frozen first date) is evaluated.
* Completed-spell holding duration excludes spells still open at the last date.
* Universe, delisting and survivorship caveats of the frozen dataset (`docs/PIT_SECURITY_MASTER_PLAN.md`) apply unchanged.

## 12. Holdout rule

The sealed holdout **2025-08-26 → 2026-08-28** is not read, scored, or used to choose anything. The firewall window is
armed before any data is read, the runner asserts the holdout state is `SEALED`, every prediction file and the panel pass
`assert_clear`, and the manifest must contain `"holdout": {"touched": false}`. The latest forward return used ends 2025-06-10.

**Firewall reporting.** EXP-010A's manifest showed `touched: false`, `engaged: true`, `window.active: true`, 171 checks and
yet `contract_armed: false` / `NOT_ARMED`. That is consistent and safe: "armed" refers to the *unsealing* contract in
`docs/HOLDOUT_CONTRACT.md`, so `contract_armed=false` means the holdout evaluation has **not** been authorised, and
`engaged=true` means the firewall is blocking. Only the wording was ambiguous. The status now also carries an explicit
`holdout_state` (`SEALED` here) and `holdout_access` (`BLOCKED`); blocking behaviour is unchanged, EXP-010A's records are not
rewritten, and the fix is its own commit (`0f02e8a`, reporting only).

## 13. Outputs (`experiments/EXP-010B/`)

`definition.json`, `config.json` (arms, costs, both rebalance schedules, folds), `manifest.json`, `metrics.json`,
`per_seed_cadence.csv`, `fold_cadence.csv`, `paired_differences.csv`. No per-row predictions or panels are written.

## 14. Method files covered by the fingerprint

`src/quant/backtest/engine.py`, `src/quant/backtest/rules.py`, `src/quant/backtest/costs.py`,
`src/quant/pit/calendar.py`, `src/quant/study/firewall.py`, `src/quant/study/exp009a.py`, `src/quant/study/exp009b.py`,
`src/quant/study/exp010a.py`, `src/quant/study/exp010b.py`.

## 15. Commands

```bash
python -m scripts.quant.exp010b fingerprint   # prints the fingerprint above
python -m scripts.quant.exp010b gate          # requires this file committed and an ancestor of origin/main
python -m scripts.quant.exp010b dry-run       # inputs, calendar, hashes, B0 reproduction; no B1 economics
python -m scripts.quant.exp010b run           # the study (the owner runs this)
python -m scripts.quant.exp010b summary
```

Any change to the definition or a method file after this commit requires a new fingerprint and a new registration.
