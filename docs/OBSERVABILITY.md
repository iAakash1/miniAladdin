# Observability

> Four separate times while optimising this repository, answering "where did
> the time go?" required writing a throwaway instrumentation script. That is
> the symptom this subsystem treats.

---

## 1. What was missing

`VendorStats` already tracked `avg_latency_ms` and `max_latency_ms` per
vendor, cumulative since process start. That answers *"is this vendor
alive?"*. It cannot answer any of the questions that actually came up:

| Question | Why the old stats could not answer it |
| --- | --- |
| Where did the dashboard's 25 s go? | Per-vendor totals, no per-request attribution |
| Which operation is slow? | Stats aggregated across all operations of a vendor |
| How bad is the tail? | Only mean and max — the mean of a bimodal distribution describes nothing that happened |
| Is it slow *now*? | Cumulative since boot; a vendor fixed an hour ago looks broken forever |
| Did the fan-out actually parallelise? | Nothing measured concurrency at all |

The mean is the specific trap. A cache hit at 0.4 ms and a vendor exhausting
its retries at 18 s average to ~900 ms — a latency no user ever experienced.
`test_the_average_hides_what_percentiles_reveal` pins that as an assertion
rather than leaving it as an anecdote.

---

## 2. Two surfaces

```python
from src import observability

# process-wide: "what is slow, in general"
observability.registry.snapshot()          # GET /api/metrics

# one request: "where did *this* request's time go"
with observability.profiled("GET /api/dashboard") as run:
    ...
run.report()
```

Every FastAPI request is profiled automatically by the existing logging
middleware, which now emits:

```
rid=a1b2 GET /api/dashboard -> 200 in 17019ms (work 42269ms, 2.5x parallel, 0ms unattributed)
```

### Why flat attribution and not a span tree

This backend fans provider calls across eight threads, so sibling spans
*overlap*. A tree showing a 4 s parent containing six 3 s children is not
describing nesting, it is describing parallelism, and the arithmetic beneath
it stops meaning anything.

A flat accumulator keyed by `name{labels}` stays honest under concurrency and
answers both questions directly:

- **Where did the time go** — total ms per label, sorted, with shares.
- **Was it parallel** — `work_ms / wall_ms`. Near 1 means serialised. This is
  the number that would catch a fan-out silently degrading back into a loop,
  which no per-vendor average could ever reveal.

`unattributed_ms` is wall time no instrumented span claimed. A large value is
a prompt to instrument something, not a rounding error.

---

## 3. Design decisions

**Fixed log-spaced buckets, not sampling.** A reservoir gives exact
percentiles for a *sample*; buckets give approximate percentiles for *every*
observation in constant memory and constant time. The pathological calls are
rare, and rare is exactly what sampling loses. Accuracy is verified against
NumPy's exact percentile in `test_percentiles_track_an_exact_reference` —
within one bucket width, always.

Bounds are **inclusive upper bounds** (`bisect_left`): 25.0 ms belongs to the
`(10, 25]` bucket. Estimates are clamped to the observed `[min, max]`, since
no percentile can lie outside the data.

**Bounded cardinality.** Each label combination allocates a permanent series,
so labels must be closed sets — vendor, operation, outcome. **Never a
ticker.** `MAX_SERIES = 512` is a hard backstop that degrades the metrics
loudly rather than leaking until the process dies, and `_metrics_path()`
collapses `/api/research/AAPL` to `/api/research/:param` for the same reason.

**One lock per series, not one registry-wide lock.** A global lock would
serialise exactly the concurrency this repository just built. Measured, that
choice costs nothing (§4).

**One recording path.** `registry.observe()` writes to both the global
histogram and the live request. An earlier version had `timer` attribute to
the request while direct `observe` calls did not, which produced a request
report reading `work 0ms, parallelism 0.0x` while the global metrics looked
perfect. Two write paths for one fact is how instrumentation lies.

---

## 4. Overhead

Instrumentation that costs more than it reveals is a net loss, so it is
measured rather than asserted (`benchmarks/observability.py`, 200,000
iterations):

| Operation | Cost |
| --- | --- |
| `Histogram.record` | **0.194 µs** |
| `registry.observe` (4 labels) | 0.895 µs |
| `request.record` | 0.170 µs |
| `Histogram.record`, 8 threads contending | **0.189 µs** |
| `percentile` read | 0.819 µs |
| Bare loop baseline | 0.025 µs |

Contended recording is **no slower than single-threaded** (0.189 vs
0.194 µs), which validates the per-series lock: at eight threads there is no
measurable contention.

Instrumenting one 300 ms provider call costs **0.0003%** of it. That is why
this is on in production rather than behind a flag nobody remembers to enable
before the incident they needed it for.

`registry.observe` is 4.6× the raw record — label-key string formatting — and
is deliberately **not** optimised. At 0.0003% of the thing being measured,
caching keys would be complexity bought with nothing.

---

## 5. What it found immediately

First cold dashboard run with attribution working:

```
wall 17019 ms | work 42269 ms | parallelism 2.48x | unattributed 0 ms

vendor.call{operation=call,outcome=ok,vendor=fred}       15 calls   16244 ms   38.4%
vendor.call{operation=http,outcome=error,vendor=fmp}      3 calls    7507 ms   17.8%
vendor.call{operation=http,outcome=ok,vendor=twelvedata}  8 calls    4818 ms   11.4%
vendor.call{operation=http,outcome=ok,vendor=polygon}     5 calls    4125 ms    9.8%
vendor.call{operation=http,outcome=error,vendor=marketstack}       2643 ms    6.3%
vendor.call{operation=http,outcome=error,vendor=twelvedata}        1995 ms    4.7%
vendor.call{operation=http,outcome=error,vendor=polygon}           1844 ms    4.4%

counters: vendor.cooldown{fmp}=3, vendor.cooldown{twelvedata}=1,
          vendor.rate_limited{polygon}=12, vendor.rate_limited{twelvedata}=3
```

Three findings, none of which were visible before:

1. **~33% of all work is spent on vendor calls that fail.** 13,989 ms of
   14 s across fmp, marketstack, twelvedata and polygon — time spent
   discovering that a vendor is broken, then falling through.
2. **FRED is the single largest cost at 38.4%** — and those calls *succeed*.
   15 sequential-ish series at ~1.1 s each. Not a failure problem; a volume
   problem.
3. **12 polygon rate-limit rejections in one dashboard load.** The fan-out's
   worker bound was chosen to prevent exactly this, and it is still
   happening — so the bound is not the binding constraint, the vendor's
   30 rpm across ~32 calls is.

Each of those is a concrete, measured lead. None of them was actionable
before this subsystem existed, and (1) and (3) contradict assumptions made
earlier in this repository's optimisation work.

---

## 6. Reading it in production

```bash
curl -s https://<backend>/api/metrics | jq '.timings | to_entries
  | sort_by(-.value.p95_ms) | .[:10]'
```

`GET /api/metrics?reset=true` starts a fresh window — the answer to
"cumulative counters never forget".

`GET /api/providers/health` remains the vendor liveness view (configured,
cooling down, success rate). The two are complementary: health says *whether*
a vendor works, metrics say *what it costs*.

---

## 7. Backwards compatibility

Additive only. No response schema changed, no existing endpoint altered.
`VendorStats` is untouched and `/api/providers/health` returns exactly what
it did — the new percentiles live alongside it rather than replacing it,
because the two answer different questions.

Rollback is deleting `src/observability/` and three call sites: the
middleware profile, `_observe` in `providers/base.py`, and the
`contextvars.copy_context()` in `providers/parallel.py`. Nothing else depends
on it.
