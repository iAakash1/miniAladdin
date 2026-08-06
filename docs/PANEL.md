# The Point-in-Time Factor Panel

> A backtest that uses a factor value before it was knowable is not a
> backtest. It is a leak, and the leak is invisible in the results — it
> makes them look *better*.

The panel is OmniSignal's research substrate: for every (symbol, date) in a
universe, the value of every factor the scoring engine computes, recorded
with the date on which that value became **knowable**.

Before the panel, OmniSignal could answer *"what does the engine say about
NVDA today?"* It could not answer *"what would the engine have said on
2023-06-15, using only what was known on 2023-06-15?"* — and without that
second question there is no way to evaluate whether the engine works.

---

## 1. Why two timestamps

Every row carries two dates, and conflating them is the single most common
way backtests lie.

| Column  | Meaning                                        |
| ------- | ---------------------------------------------- |
| `date`  | the trading day the value **describes**        |
| `as_of` | the day the value became **knowable**          |

For price-derived factors they coincide: a closing price is known at that
close. For fundamentals they diverge by weeks — Q1 revenue *describes*
March and is *knowable* in May, when the filing lands. Restatements diverge
further: a revised figure describes a quarter that closed a year ago.

Every point-in-time read is one predicate:

```
as_of <= T
```

That is the whole schema's reason for existing. A single-timestamp table
cannot express the distinction, which means look-ahead bias is not merely
undetected in it — it is *unrepresentable*, and therefore permanent.

---

## 2. How look-ahead is prevented

Not by discipline. Discipline fails silently.

`PanelBuilder` never hands the scoring engine a full price history. Every
factor computation receives the output of `_pit_window`, and nothing else:

```python
def _pit_window(frame, observed_on, lookback=LOOKBACK_BARS):
    return frame.loc[frame.index.date <= observed_on].tail(lookback)
```

Future bars are not *unused* — they are *absent*. There is no code path in
the builder that could peek, so peeking is not a mistake anyone can make.

Regime detection gets the same treatment. `detect_regimes` accepts a `today`
argument that defaults to the wall clock; the builder passes the
**observation date** instead. Passing the real date would let a 2023 row
inherit 2026's position in the FOMC calendar — a leak that never looks like
a bug, only like unexplained regime drift.

### The test that matters

`tests/test_panel_builder.py::test_appending_future_data_does_not_change_history`

1. Build a panel over Jan–Jun 2023 from a market that ends 2023-06-30.
2. Build the same panel from the same market extended by another year.
3. Assert every historical row is identical.

If any factor peeked forward, the extra bars would change a value for a date
that already existed. A sibling test asserts the same property at the byte
level, via the snapshot content hash.

This was verified by mutation: replacing `_pit_window` with `return frame`
(no truncation) fails 6 tests, including both flagship ones. A look-ahead
test that cannot fail is decoration.

---

## 3. Storage

```
data/panel/
  CURRENT                      text file holding the published snapshot id
  snapshots/
    <snapshot_id>/
      manifest.json            inputs, outputs, provenance
      panel.parquet            the panel itself, zstd-compressed
```

**Wide, not long.** One row per (symbol, date), one column per factor. The
factor set is closed and known; every query wants all factors for a cell;
cross-sectional ranking reads one factor column across all names on a date.
A long table would triple the row count and force a pivot on every read.
Long layout is correct for an open or sparse factor set. Ours is neither.

**Immutable.** `write()` refuses a snapshot id that already exists. Research
results that can be silently rewritten underneath you are not results.

**Atomic.** A build stages into a temporary directory and is promoted with a
single `os.replace`. A killed build leaves a `.staging-*` directory, never a
half-written snapshot that reads as complete. `CURRENT` is swapped the same
way, so a reader never sees a partial pointer.

**Content-addressed.** `snapshot_id` is derived from the build's inputs
(universe, symbols, range, engine version, schema version, factor list), so
requesting the same build twice targets the same id — which is how an
accidental rebuild is detected rather than silently performed.
`content_hash` is the SHA-256 of the Parquet bytes. `verify()` re-hashes and
compares, detecting corruption and tampering.

Determinism is load-bearing here: rows are sorted by `(date, symbol)` with a
stable sort and the Arrow schema is declared explicitly rather than
inferred. Without both, two builds of identical data produce different bytes
and content hashing is worthless. A test asserts that a shuffled input frame
yields an identical hash.

**Parquet, not Postgres.** The panel is append-only analytical data read in
columns — precisely the workload Parquet exists for. It is also the format
DuckDB reads natively, so the Phase 3 query engine lands on top of these
files with no migration. Postgres keeps what it is good at: transactional
user state.

**Null means absent.** Factor columns are nullable and a factor whose inputs
are missing is written `NULL`, never `0.0`. Zero is a value; null is the
absence of one. Conflating them lets missing data masquerade as a neutral
signal, which is how a data outage becomes a "hold" recommendation.

---

## 4. The trailing lookback

`LOOKBACK_BARS = 1260` (~5 years) caps how much history any single
observation sees. This is a **correctness** parameter before it is a
performance one.

The engine's normalizers — `robust_z` and `_robust_daily_sigma` — estimate
their distribution from the *entire* series handed to them. Uncapped, a cell
early in the panel is z-scored against 60 observations and a cell late in it
against 2,500, so the same factor value means different things at different
points in time and time-series comparison is not apples-to-apples. A fixed
trailing window makes the estimator stationary.

1260 matches the `"5y"` range `_provider_loader` requests, so a panel cell
for today sees exactly what the live engine sees for today.

Its direct performance effect is real but small, and is stated here rather
than overclaimed: measured on the scalar path, a 3-symbol × 3200-day build
capped at 1260 bars versus uncapped is worth **~5%** (3124 vs 3275 µs/cell).

Its *indirect* effect is far larger, and was not the reason it was
introduced. The lookback defines the domain in which the vectorized engine
is provably exact, so it now decides whether a build runs at 13,648 cells/s
or 394 — a 29× difference (§7). That makes it the most consequential single
constant in the subsystem, which is worth knowing before anyone tunes it:
raising it widens the fast path but weakens the stationarity argument above;
lowering it does the reverse.

---

## 5. Honest limitations

These are real constraints, stated plainly. None of them is fixed by trying
harder; each needs a data source we do not currently have.

### 5.1 Survivorship bias

`Universe` returns **current** membership, not historical. A panel built
over 2016–2026 using today's mega-cap list contains only companies that
survived to today — which silently inflates every backtest statistic
computed over it, because the failures were never in the sample.

Fixing this requires point-in-time index membership, which has no free
source. Rather than pretend or fabricate, `Universe.members()` already takes
the `as_of` date a real implementation will need, and `Universe.point_in_time`
reports whether membership is genuinely historical (currently always
`False`). No call site changes when a real source arrives.

**Do not report a backtest over these universes as unbiased.**

### 5.2 Vendor history depth

The provider chain's free tiers cap daily history at roughly **501 bars
(~2 years)** regardless of the range requested — the `"5y" → 1830 days`
mapping in `market_vendors.py` is correct, the data simply is not served.

Because `r12_1` (12-1 momentum) needs 253 bars of history, this means:

- the first ~253 observations of any panel have `r12_1 = NULL`;
- usable panel depth today is roughly **one year**, not five.

All seven price factors populate normally once ~253 bars of history are
available. This is a data-plan limitation, not a code defect, and it is the
binding constraint on serious backtesting until a deeper source is added.

### 5.4 FOMC regime is never labelled historically

`FOMC_DECISION_DATES` in `src/scoring/fomc_calendar.py` holds only the
current year's meetings (8 dates, 2026-01-28 → 2026-12-09). For any earlier
observation date, `business_days_to_next_fomc` returns a large number and the
`fomc_window` regime never fires. Every historical panel row therefore
carries `fomc_window = False` — not because no FOMC meeting was near, but
because the calendar cannot say.

`high_volatility` is unaffected and does vary across history.
`earnings_window` never fires either, for the separate reason in §5.3.

`test_fomc_regime_is_never_labelled_for_history` pins this, and fails when a
full historical calendar is added — which is the signal to update this
section.

### 5.3 Price-derived factors only

Seven of fifteen factors are computed today:

| Populated                        | `NULL` pending point-in-time inputs        |
| -------------------------------- | ------------------------------------------ |
| `r12_1` `r63` `r21` `vol_confirm` | `target_upside` `earnings_yield` `pe_gap` |
| `high52_prox` `rel21_vs_spy`     | `pead` `gross_profitability`               |
| `reversal`                       | `net_issuance` `asset_growth` `sentiment`  |

Momentum, reversal and relative strength are computable point-in-time from
OHLCV alone. Fundamental, quality and news factors require filing-date and
publication-date stamps that are not yet wired — and writing them with
today's values against historical dates would be exactly the look-ahead bias
this subsystem exists to prevent.

The columns exist now, so adding them later is a builder change, not a
schema migration. `data_completeness` on every row records what fraction was
actually computed (currently `0.4667` = 7/15).

---

## 6. CLI

```bash
python -m src.panel.cli build --universe dev --start 2025-01-02 --publish
```

| Command   | Purpose                                                |
| --------- | ------------------------------------------------------ |
| `build`   | compute and store a new snapshot                       |
| `list`    | all snapshots, newest first; `*` marks `CURRENT`       |
| `show`    | print rows, optionally as a point-in-time read         |
| `verify`  | re-hash stored bytes against the manifest              |
| `publish` | point `CURRENT` at a snapshot                          |

Useful flags: `--symbols AAPL,MSFT` (overrides `--universe`), `--step N`
(observation stride in trading days; 5 matches the walk-forward validator's
weekly cadence and costs a fifth of the time), `--json`, `--verbose`.

Exit codes are meaningful, because Phase 7 will run `build` unattended:

| Code | Meaning                                              |
| ---- | ---------------------------------------------------- |
| `0`  | success                                              |
| `1`  | usage or runtime error                               |
| `2`  | snapshot already exists — rebuild refused, a no-op   |
| `3`  | integrity verification failed                        |

A point-in-time read from the CLI:

```bash
python -m src.panel.cli show --as-of 2025-02-14 --symbol AAPL
```

```
  snapshot e0dbfd3bc29f4a66  (75 rows total)
  point-in-time read: as_of <= 2025-02-14 → 6 rows visible
```

---

## 7. Performance

`python benchmarks/panel_build.py` — synthetic prices, deliberately: a
benchmark that depends on a vendor measures the vendor's latency, not ours,
and cannot be reproduced by anyone reading the numbers later.

30 symbols × 756 trading days (20,910 cells), Apple silicon:

| Metric                | Scalar        | Vectorized    |
| --------------------- | ------------- | ------------- |
| Build                 | 48.6 s        | **1.53 s**    |
| Per cell              | 2,326 µs      | **73 µs**     |
| Throughput            | 430 cells/s   | **13,648/s**  |

**31× faster, to the last ULP of the same answer.** Storage and read costs
are unchanged by the engine: write 0.016 s, 63 B/cell on disk, 5.1×
compression versus pandas, full read 1.7 ms, three-column projection 0.9 ms,
point-in-time read 2.5 ms.

Throughput is flat across shapes, so the cost is linear in cells:

| Shape              | Cells  | µs/cell | Throughput |
| ------------------ | ------ | ------- | ---------- |
| 30 × 756           | 20,910 | 73.3    | 13,648/s   |
| 100 × 756          | 69,700 | 72.5    | 13,798/s   |
| 60 × 1260          | 72,060 | 79.0    | 12,661/s   |
| 200 × 504          | 89,000 | 72.0    | 13,895/s   |

### Where the speedup came from

Profiling, not guessing. The scalar path called the engine's factor
functions once per (symbol, date), and each call recomputed `pct_change`,
rolling medians and MAD σ over the whole window — ~20,000 Python-level calls
per cell, with `_robust_daily_sigma` alone recomputed about five times per
cell from identical inputs. `src/panel/factors.py` computes each factor once
per symbol as a full time series and reads values off per date.

Two measurements shaped that module and are worth repeating:

- **Medians come from pandas, not NumPy.** `Series.rolling(L).median()` uses
  an incremental skiplist (O(n log L)); an (n, L) window matrix with
  `np.median` is O(n·L). At n=2520, L=1260 that is 0.8 ms versus 44 ms — a
  55× difference for the same answer.
- **MAD cannot use that trick,** because the value subtracted differs per
  window, so it is not a rolling reduction of any fixed series. It needs the
  matrix, with cost contained by splitting the expanding and fixed-width
  regions and by chunking to bounded memory.

### The cliff, stated plainly

The fast path applies only when a symbol's history is **no longer than the
lookback** (1260 bars). Past that, `PanelBuilder` falls back to the scalar
engine and throughput collapses:

| History vs lookback | Throughput  |
| ------------------- | ----------- |
| 1260 bars ≤ 1260    | 11,285/s    |
| 1600 bars > 1260    | 394/s       |

The reason is §7.1 below. With today's vendor depth (~501 bars, §5.2) the
fast path always applies. The uncomfortable part is that the cliff arrives
exactly when deeper history does — that is, when the research platform
finally gets the data it wants. Removing it is a live decision, not an
oversight; see §7.1.

### 7.1 Why the fast path refuses truncated windows

`_rsi_series` starts from `closes.diff()`, which is NaN at the first bar of
whatever series it receives, and `.where(delta > 0, 0.0)` converts that NaN
into a fabricated `0.0`. Inside a *truncated* window the oldest RSI
observation is therefore a 14-bar mean containing one invented zero, and
differs from the same date's global RSI. `robust_z` then takes its median
and MAD over a sample holding that contaminated point.

That point is the oldest element of a sliding window — a per-row
substitution no rolling reduction expresses. So rather than approximate the
engine, `compute_price_factors` raises and the builder falls back.
Bypassing the guard produces up to 1.7e-1 of error across six factors, which
is small enough to survive a lax tolerance and therefore exactly the kind of
divergence that must not be tolerated at all.

**The one-line fix lives in the engine, not here:** if `_rsi_series` left the
absent first delta as NaN instead of fabricating `0.0`, window-local and
global RSI would agree everywhere and the cliff would disappear. Measured
impact of that change on production scoring, over 200 random histories: the
RSI z-component moves by a median of 1.5e-3 and at most 1.2e-2. Small, but
not zero — it changes live scores, so it is flagged for a human decision
rather than made unilaterally.

### 7.2 Content hashes are per-engine

The two engines agree to **1.1e-16** — one unit in the last place, from
floating-point operation order. That is close enough to call the answer the
same and far enough to change the Parquet bytes.

So a snapshot's `content_hash` is reproducible for a *given* engine, not
across engines. The manifest records which ran
(`engine=vectorized:N/scalar:M`), and `omni verify` (Phase 4) must rebuild
with the engine named there.
`test_content_hash_is_reproducible_per_engine_not_across_them` pins both
halves of that statement, and fails if the engines ever become bit-identical
— which would be the signal to delete this section.

## 8. Schema versioning

`PANEL_SCHEMA_VERSION` is recorded in every manifest. A reader that
encounters a version it does not know logs a warning rather than silently
misinterpreting columns.

Bump it when the physical layout changes incompatibly — reordering or
retyping columns, changing null semantics. Adding a factor to
`FACTOR_COLUMNS` also changes `snapshot_id` for every build (the factor list
is part of the id payload), so old and new snapshots coexist under distinct
ids rather than colliding. Old snapshots remain readable; they simply lack
the new column.

`tests/test_panel_schema.py::test_factor_columns_match_engine` enforces the
contract between the engine and the panel by exercising the engine and
comparing the factor names it actually emits against `FACTOR_COLUMNS`.
Add a factor to the engine and forget the panel, and that test fails
immediately — rather than the panel quietly storing a column of nulls that
nobody notices for a month.

---

## 9. Files

| Path                          | Role                                          |
| ----------------------------- | --------------------------------------------- |
| `src/panel/schema.py`         | columns, Arrow schema, manifest, snapshot ids |
| `src/panel/storage.py`        | immutable atomic snapshots, PIT read, verify  |
| `src/panel/builder.py`        | OHLCV → panel, PIT enforced by construction   |
| `src/panel/factors.py`        | vectorized factors; engine is the oracle      |
| `src/panel/windowed.py`       | windowed median / MAD / quantile primitives   |
| `src/panel/universe.py`       | symbol sets, survivorship caveat              |
| `src/panel/cli.py`            | build / list / show / verify / publish        |
| `tests/test_panel_schema.py`  | engine↔panel contract, identity, layout       |
| `tests/test_panel_storage.py` | immutability, atomicity, integrity, PIT read  |
| `tests/test_panel_builder.py` | look-ahead, determinism, degenerate inputs    |
| `tests/test_panel_factors.py` | **oracle: vectorized == scalar engine**       |
| `tests/test_panel_windowed.py`| primitives vs naive reference implementations |
| `benchmarks/panel_build.py`   | build / storage / read measurements           |
