# Research Data Architecture

How multi-gigabyte external sources become immutable, checksummed, resumable
local partitions — without downloading the parts nobody needs.

---

## 1. The tiers

```
RAW ─────────────► NORMALIZED ────► POINT-IN-TIME ────► FEATURES ────► TRAINING SET
immutable          canonical         returns, universe   backward       matrix +
checksummed        column names      calendar            windows        manifest
partitioned        typed once                                           content hash
```

Raw data is **never modified**. Every derived artifact is reproducible from it,
and `RawStore.write_partition` refuses an existing key rather than overwriting
one. That refusal is not theoretical: during development two ingestion
processes raced, and the guard rejected the second write instead of corrupting
the partition.

---

## 2. The query-shape constraint

`post-no-preference/stocks.ohlcv` has primary key `(date, act_symbol)`, and the
deployed engine uses the index only for an **equality** predicate on `date`.
Measured against the live API:

| Query shape | Result |
|---|---|
| `date = '2024-01-02' AND act_symbol IN (50 names)` | 50 rows, **0.95 s** |
| `date BETWEEN 4 days AND act_symbol IN (5 names)` | 20 rows, **30.8 s** |
| `act_symbol = 'AAPL' AND date BETWEEN 1 month` | **timeout** |
| `SELECT date FROM ohlcv GROUP BY date` | **timeout** |

Every ingestion therefore partitions on a **single date** and fans out across
dates.

### The alternative, measured and rejected

The CSV export endpoint streams the whole table. Measured at **~271 KB/s**,
which is roughly **1.6 hours** for the ~1.6 GB `ohlcv` table — and it pulls
12,000 symbols to use 250. Date-partitioned SQL fetches only the universe
asked for.

---

## 3. Pagination: keyset, not OFFSET

The API caps every response at 1,000 rows and signals it with
`query_execution_status = "RowLimit"` — **with no continuation token**. A client
that ignores that field returns a truncated answer that looks complete, so
`DoltHubClient.execute` raises `RowLimitExceeded` instead.

For tables that must be read whole, pagination advances on the key, not an
offset. Measured on `stocks.symbol` (24,058 rows, full eight-column
projection), repeated to separate depth cost from the source's response
caching:

| Access | Cold | Repeat |
|---|---|---|
| keyset, any depth | 2.3 s | 3.1 s |
| `OFFSET 1000` | 4.0 s | — |
| `OFFSET 20000` | 47.7 s | **35.7 s** |

`OFFSET n` makes the engine produce and discard `n` rows, and it **stays slow
on repeat** — which is what distinguishes real depth cost from a cold cache.
Keyset pagination is an index seek and is flat wherever it lands.

Ordering is by primary key only. With projection, predicate and depth held
fixed, `ORDER BY act_symbol` measured 2.3 s and 3.7 s across repeats while
`ORDER BY act_symbol, last_seen` measured 5.1 s and 5.2 s. The key is unique,
so a second sort column cannot change the order — it can only cost.

---

## 4. The trading calendar is discovered, not declared

`SELECT date FROM ohlcv GROUP BY date` times out, so the ingestion enumerates
candidate **weekdays** locally and lets the source say which of them traded. A
date returning no rows is recorded as non-trading.

Roughly 4% of requests land on holidays and return empty. That is the measured
cost of not inventing a calendar — and a hardcoded holiday table is wrong the
first time an exchange closes unexpectedly, silently, in a way that reads as
missing data rather than as a closed market.

---

## 5. An empty date and a failed date are never the same thing

An empty date is a holiday. A **failed** date is a hole, and a year partition
written with holes looks exactly like a complete year while every return
spanning a gap is wrong by the size of the gap.

So the ingestion:

1. records errored dates separately from empty ones;
2. retries them once at reduced concurrency after the year's main pass;
3. writes any still-unresolved dates into the manifest under an
   `INCOMPLETE PARTITIONS` note;
4. **refuses to write the partition at all** when unresolved dates exceed
   `MAX_FAILED_DATE_FRACTION` (2%, roughly five sessions a year).

This was not hypothetical. The source returns HTTP 200 with the *body* reading
`query error: http status: 403` under load — so a client classifying on HTTP
status alone sees success and treats a transient rate limit as a permanent
failure. `_TRANSIENT_MARKERS` classifies those, and `execute` retries with
exponential backoff.

---

## 6. Storage

```
data/research/
  raw/<dataset_id>/
    manifest.json            coverage, PIT class, survivorship class, checksums
    part-<year>.parquet      immutable, zstd, written once
  universe/liquid.json       point-in-time monthly membership
  models/registry.json       model registry
  reports/study.json         study output
```

Partitioned by year rather than written as one file, because a raw table is
ingested over hours and grows by date. One file would be rewritten on every
extension, breaking immutability the first time a backfill resumed.

Determinism is load-bearing: rows are sorted `(date, symbol)` with a stable
sort before writing, so two ingestions of identical data produce identical
bytes. `tests/quant/test_datasets.py::test_partition_write_is_deterministic_regardless_of_row_order`
asserts a shuffled input yields the same checksum.

---

## 7. The point-in-time universe

`docs/PANEL.md` §5.1 records that survivorship bias "requires point-in-time
index membership, which has no free source". It is now constructible.

At each month-end, from that month's **whole-market** cross-section:

1. drop ETFs and test issues (`is_etf`, `is_test_issue`);
2. drop names priced below \$5 — sub-\$5 tick sizes make returns
   microstructure rather than information;
3. rank by **3-month trailing-median dollar volume** and take the top *N*;
4. drop names past their `last_seen`.

**Why the trailing median.** Ranking on a single month-end's dollar volume
produced **47.5 entries per rebalance out of 180** — 26% monthly churn, mostly
an earnings date or an index event lifting one day's volume. The trailing
median cut that to **18.8**, and the window is strictly backward-looking so the
point-in-time property is preserved.

### What was built

| Universe size | Unique members ever | Entries per rebalance | Requests per date |
|---|---|---|---|
| 180 | 793 | 18.8 | 2 |
| **250** | **998** | **24.3** | **2** |
| 320 | 1,185 | 27.8 | 3 |

250 was chosen: 39% more names per cross-section than 180 at identical
ingestion cost.

### Verifying it is genuinely survivorship-free

Over 184 monthly snapshots: **793 of 998 names ever eligible are absent from
the final snapshot**. A survivors-only universe would have exactly 250. TWTR is
a member through 2022 and gone after; ATVI through 2023.

**Stated honestly:** at size 250 this is a large-cap universe, and it does *not*
contain SIVB — which ranked **614th** by dollar volume in February 2023, well
outside the top 250. That is a size-threshold consequence, not a survivorship
failure, and it means a study over this universe understates the frequency of
outright failure in the broader market.

**It is not index membership.** It is liquidity-ranked, and describing a study
over it as an index backtest would be a different kind of dishonesty.

---

## 8. Reproducibility

Every dataset manifest records source, repository, table, source version,
retrieval timestamp, schema version, per-partition checksums, row counts, date
ranges, the transformations applied, and both classifications.

Every training matrix records a content hash of its numeric payload, the
dataset versions it drew from, the feature and label lists, guard results, and
per-column coverage.

```bash
python -c "
from src.quant.datasets.store import RawStore
s = RawStore('data/research')
for m in s.list_datasets():
    print(m.dataset_id, s.verify(m.dataset_id)['ok'])
"
```
