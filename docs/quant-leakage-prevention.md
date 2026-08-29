# Leakage Prevention

Look-ahead bias does not announce itself. It makes results **better**, which
means the incentive to look for it runs backwards, and it survives review
because nothing in the output is obviously wrong. This document lists every
leak the pipeline is built to prevent, the mechanism that prevents it, and the
test that would fail if the mechanism were removed.

---

## 1. The standard: structural, not procedural

`src/panel/builder.py` states the principle this layer inherits:

> Look-ahead bias is normally a discipline: remember not to peek. Discipline
> fails silently and the failure is invisible in the output.

Wherever possible the future is made **absent** rather than merely unused. Where
that is not possible, a guard asserts the property from outside and is itself
tested against a deliberately broken implementation — because a leakage test
that cannot fail is decoration.

---

## 2. The leaks, and what stops each one

### 2.1 Temporal leakage in a feature

**Mechanism.** Every feature is a backward window: `rolling(...)`, `shift(n)`
for positive `n`, `cumprod`. Never `shift(-n)`, never `center=True`.
`min_periods` always equals the full window.

**Guard.** `assert_no_future_dependence` builds twice, perturbing only
post-cutoff source data, and asserts every pre-cutoff value is bit-identical —
**and** that the perturbation was observable after the cutoff, so a builder
that ignored its input could not pass.

**Tests.** `test_no_registered_feature_depends_on_the_future` runs it over all
16 per-symbol features. `test_the_leakage_guard_actually_catches_a_leak` and
`test_a_negative_shift_in_a_feature_is_caught` prove a centred mean and a
`shift(-1)` both fail.

**A subtlety worth recording.** The perturbation uses **distinct factors per
column**. A uniform scale cancels exactly inside a ratio: `amihud_21` is
`|return| / dollar_volume`, so scaling both by 3 leaves it unchanged and the
guard would report "the future changed nothing" — true, and proof of nothing.
The `guard_is_live` check caught this during development.

### 2.2 Corporate-action leakage

**Mechanism.** Returns, not back-adjusted prices:

```
r_t = (close_t · k_t + d_t) / close_{t-1} − 1
```

Every term is dated `t`. A back-adjusted series shows a 2015 value that depends
on a 2020 split and is *structurally incapable* of being point-in-time.

**Tests.** `test_returns_use_only_actions_dated_on_or_before_the_bar` appends a
2030 split and asserts no historical return moves.
`test_split_does_not_create_a_fake_return` asserts 4:1 reads as 0%, and its
sibling asserts that **without** the split record it reads as −75% — so the
first test is not vacuous.

**A hard limit, enforced.** `stocks.split` has no ex-date before **2014-03-28**
while `ohlcv` starts 2011-01-03. Returns before that are split-contaminated, so
`CORPORATE_ACTION_COVERAGE_START` clamps the build and records the clamp in the
manifest. It costs 3.2 of 15.6 available years.

### 2.3 Publication-date leakage — the earnings case

**The measurement.** `eps_history` is keyed by `period_end_date` with no
announcement date. Verified on AAPL:

| Source | Field | Value |
|---|---|---|
| `eps_history` | `period_end_date` | 2026-06-30 |
| `earnings_calendar` | `date` | 2026-07-30 |
| | `when` | After market close |

Using the table as-is inserts the quarter's result **30 days** before it was
public. Median reporting lag across 105,710 matched events is **37 days**
(p05 22, p95 127).

**Mechanism.** `build_earnings_events` joins to `earnings_calendar` with
`merge_asof(direction="forward")`, and a period with no matching announcement is
**dropped** — never backfilled with an average lag. `attach_earnings_features`
then merges backward on `available_from`, so a row dated `d` can only see events
available at or before `d`.

**The session rule.** `when` distinguishes before-open from after-close, and the
difference is a whole trading session. Measured availability lag: before-open
**+0 days**, after-close **+1 day**, missing **+1 day** (conservative). Treating
all prints as same-day would grant free foresight on roughly half of them.

**Not built:** `days_to_next_earnings`. A schedule is published in advance, but
`earnings_calendar` records only *that* a print happened on a date, never when
that date was first announced — and it contains **263 future-dated rows**. There
is no column from which the announcement-of-the-announcement is recoverable, so
the feature does not exist.

### 2.4 Non-point-in-time sources

**Mechanism.** The catalog classifies every source, and
`DatasetBuilder._admit` **refuses** a `NOT_POINT_IN_TIME` source as a feature
input. Overriding requires a named waiver that is recorded in the manifest and
surfaced by the API.

`earnings.income_statement` is barred: its `date` is a period marker, no filing
date exists anywhere in the schema, and the repository already holds genuinely
point-in-time fundamentals with real SEC `filed` dates in
`src/panel/fundamentals.py`.

**Test.** `test_a_non_point_in_time_source_is_refused_as_a_feature`.

### 2.5 Revision leakage

`french_factors_daily` is rebuilt when CRSP is revised. Classified
`PUBLICATION_LAGGED` and **barred from features**; admitted only for
attribution, which is explicitly retrospective — revision moves the benchmark's
history, not the strategy's realised returns.

CPI, unemployment and GDP are **not ingested at all**, because using them
honestly needs a vintage database (ALFRED). The Treasury curve is used precisely
because it is *not* revised.

### 2.6 Normalisation leakage

**Mechanism.** `FoldImputer` is constructed **inside** the fold loop and fitted
on training rows only. Hoisting it out is a small, real leak that improves
results slightly and leaves no trace, so it is made structurally impossible
rather than avoided by care.

**Test.** `test_imputer_statistics_come_from_the_training_fold_only`.

### 2.7 Universe leakage

**Mechanism.** Cross-sectional statistics require an explicit universe;
`cross_sectional_frame` raises without one. Membership is decided from each
month's whole-market cross-section and resolved as "latest rebalance at or
before the date".

**Guard.** `assert_universe_is_point_in_time` fails a universe that never loses
a member — membership that only grows is a survivor list with a date column.

**Measured.** 793 of 998 ever-eligible names are absent from the final snapshot.

### 2.8 Split leakage between train and validation

**Mechanism.** Purge equal to the label horizon, plus a separate embargo for
serial correlation. They are distinct parameters because they answer distinct
questions.

**Tests.** `test_every_walk_forward_fold_has_a_gap_covering_the_label_horizon`,
`test_an_insufficient_gap_is_refused`, `test_holdout_is_outside_every_fold`.

### 2.9 Target leakage

**Mechanism.** Two checks: name overlap between features and labels, and
|correlation| ≥ 0.999 which catches a renamed label or an invertible transform.

**Test.** `test_target_leakage_is_detected_by_name_and_by_correlation`.

### 2.10 Stale-data leakage

Option snapshots have irregular cadence (48 distinct dates in 2019, 259 in 2025)
and sometimes fall on non-trading days. Attaching them uses backward
`merge_asof` — `direction="nearest"` would happily match Monday to Tuesday —
with a **21-day staleness cap**. Beyond it the feature is NULL rather than
forward-filled forever, because an unbounded fill turns a data gap into a
confident flat signal.

### 2.11 Selection leakage

Not a data leak but the same class of error. Every configuration is logged;
`ExperimentLog.distribution()` reports the population, not just the maximum;
Deflated Sharpe takes the **trial count**; PBO measures whether in-sample
selection predicts out-of-sample rank. Hyperparameters are fixed in advance and
the holdout is untouched.

---

## 3. What remains unprotected

Stated because an unlisted limitation is indistinguishable from an absent one.

| Risk | Status |
|---|---|
| Restatement of `eps_history` | The table holds one value per period. If a figure was later restated, the current value is what is read. There is no vintage column, so this cannot be detected from within the dataset. |
| `symbol` descriptive fields | Name, exchange and `is_etf` are current values applied to history. Only `last_seen` is genuinely historical. |
| Pre-2017 delisting dates | `symbol.last_seen` starts 2017-10-26; earlier exits are inferred only from a name leaving the cross-section. `coverage_class` reports `partial`. |
| Announcement-of-announcement | Not recoverable — see 2.3. |
| Vendor IV methodology | Unpublished. IV is a vendor measurement, not a reconstructible quantity. |
| Survivorship below the liquidity threshold | The universe is top-250 by dollar volume. SIVB ranked 614th in Feb 2023 and is therefore absent — a size-threshold consequence, not a survivorship failure, but it means the study understates the frequency of outright failure. |

---

## 4. Running the leakage suite

```bash
python -m pytest tests/quant/test_leakage.py -v
```

34 tests. The ones that matter most are the paired ones: for every assertion
that a correct implementation passes, there is a sibling asserting a broken one
fails.
