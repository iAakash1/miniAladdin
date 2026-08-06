# Concurrency

> The dashboard was never slow. It was *serialised* — and the whole cost
> landed on the users least able to absorb it: the ones who arrived with a
> cold cache.

OmniSignal's backend spends almost all of its wall-clock time waiting on
vendors. This document covers the one primitive that addresses that, where it
is applied, and the constraints that shaped it.

---

## 1. The measurement that started it

`get_dashboard()` instrumented cold, on a laptop, against live vendors:

| | Value |
| --- | --- |
| Wall clock | **43.6 s** |
| Provider calls | 32, sequential |
| Time inside provider calls | 43.6 s — **100%** |
| Same call, warm cache | **0.000 s** |

The handler itself did no meaningful work. It waited 32 times in a row, and
every one of those waits was for an answer that had nothing to do with the
previous one. Macro series 7 does not depend on macro series 6.

Warm was already instant, so this was never a caching problem. It was a
*shape* problem.

---

## 2. `src/providers/parallel.py`

```python
outcomes = map_concurrent(fetch, items, workers=8, label="sectors")
rows = values(outcomes)          # successful, non-None, in input order
```

Four guarantees, each with a test that fails without it:

| Guarantee | Why it matters |
| --- | --- |
| **Input order** | The dashboard renders ordered lists. Completion order would make identical requests return different bodies. |
| **Error isolation** | A failing vendor must not empty the whole board. The sequential loops tolerated a `None` per card; the replacement must too. |
| **Bounded concurrency** | See §3 — this is the one that protects answer *quality*, not just politeness. |
| **Batch deadline** | One dead socket must not hold a user request open. |

### Why bounded, and not one thread per item

`RateLimiter.try_acquire` is **non-blocking**. When a vendor's token bucket
is empty it raises `VendorError` immediately instead of waiting, and the
fallback chain moves to the next vendor down.

So an unbounded burst would not merely be rude to the vendor — it would
convert slow *successes* into instant *failures*, silently demoting answers
to a worse source while looking faster on a stopwatch. That is the worst
possible trade: a benchmark improvement that degrades the product.

`DEFAULT_WORKERS = 8` is not a guess. Measured on the dashboard's real call
shape (`benchmarks/provider_fanout.py`):

| Workers | Time | Speedup |
| ------- | ---- | ------- |
| 2 | 7.64 s | 1.81× |
| 4 | 5.54 s | 2.49× |
| **8** | **4.13 s** | **3.35×** |
| 12 | 4.06 s | 3.40× |
| 16 | 3.83 s | 3.61× |

Eight captures **93% of the maximum achievable speedup at half the burst
pressure of 16**. Past it the curve is flat, because the largest fan-out
group only has 14 items — more workers cannot help a group smaller than the
pool.

### The bug that made the timeout decorative

The first implementation used `with ThreadPoolExecutor(...) as pool:`. Its
`__exit__` calls `shutdown(wait=True)`, which blocks until every worker
finishes — *including the hung one the timeout exists to escape*. The
timeout parameter was real; its effect was zero.

The fix is an explicit `shutdown(wait=False, cancel_futures=True)` in a
`finally`. `test_a_hung_item_cannot_pin_the_request_open` fails against the
original version, which is the only reason to believe the fix works.

---

## 3. Why threads and not `async`

FastAPI runs these handlers in a threadpool over blocking I/O, deliberately
(CLAUDE.md, docs/AUDIT.md H3), and every vendor adapter is synchronous
`requests`. Threads match the model already in place. Going async would mean
a second HTTP client, a second set of vendor adapters, and two code paths
through the fallback chain — a large rewrite to remove waits that threads
already remove.

The provider layer was built for this: `InMemoryCache`, `RateLimiter`,
`VendorStats` and the circuit state are each lock-guarded, and `SingleFlight`
coalesces concurrent duplicate keys. This primitive adds concurrency; it does
not add sharing that was not already thread-safe.

---

## 4. Where it is applied

### 4.1 Dashboard — three fan-outs

14 macro series, 11 sector ETFs, 5 index quotes. Measured live:

| | Before | After |
| --- | --- | --- |
| Wall clock (cold) | 43.6 s | **25.5 s** |
| Serial-equivalent | 43.6 s | 70.0 s |
| Speedup vs its own serial cost | 1.0× | **2.75×** |
| Peak concurrent calls | 1 | 8 (bound holds) |

Two honest caveats:

- The two runs are **not directly comparable**. Repeated cold measurements
  pushed several vendors into cooldown, which is why the serial-equivalent
  *grew* from 43.6 s to 70.0 s between them. The trustworthy figure is the
  within-run ratio (2.75×), not the difference between runs.
- 25.5 s is still bad. The remaining cost is not serialisation any more — it
  is slow and failing vendors, where the chain spends 6 s × 3 attempts before
  falling through. That is a different subsystem (vendor health and
  fast-failing), and it is now the dominant term.

### 4.2 Research — speculative cache warming

`research_ticker` makes nine provider calls; seven are independent (news
needs the company name that `get_company` resolves). Rather than rewrite a
469-line handler to thread seven results through it,
`src/services/research_prefetch.py` warms those seven caches concurrently
before the handler starts, and the handler is left **completely unmodified**.

That is safe because of two properties, both verified rather than assumed:

- `FallbackChain.execute` is **cache-first by `cache_key`** — a warmed key
  never touches a vendor.
- It wraps fetches in **`SingleFlight`** — a handler call that races the
  prefetch *joins* it rather than starting a second one.

Together, prefetching cannot cause a duplicate vendor call. The worst case is
a wasted warm, and the handler behaves exactly as before.

Measured live on `AAPL`:

| | Value |
| --- | --- |
| Prefetch wall clock | 3.97 s |
| Serial-equivalent | 6.06 s |
| Speedup on that segment | **1.53×** |
| Upstreams warmed | 7 / 7 |
| Repeat call (warm) | **0.9 ms** |

1.53× rather than 7× because the calls are heterogeneous and the slowest one
sets the floor — Amdahl, not a defect. Reported as measured.

---

## 5. What this is not for

- **Writes**, or anything order-dependent between items. This is for
  independent reads whose only relationship is that one caller wants all of
  them.
- **Nested fan-out.** The dashboard parallelises *within* each of its three
  groups, not across them. Doing both would put up to 24 calls in flight and
  multiply the burst pressure §3 exists to bound — trading answer quality for
  a latency win that the flat part of the worker curve says is not there.
- **Anything with side effects in the research prefetch.** It runs
  speculatively; every call it makes must be a pure read that is harmless if
  the handler later fails.

---

## 6. Backwards compatibility

No API contract changed. Response bodies are byte-identical: `map_concurrent`
returns in input order, and the dashboard sorts sectors after gathering, as
it did before. `values()` reproduces the old "skip failures, skip `None`"
semantics of the loops it replaced, and per-item failure logging is preserved
through `_gather`'s `describe` callback so a half-empty board still names the
series or symbol that failed.

The research prefetch is additive and removable: delete the one
`research_prefetch.warm(ticker)` line and the handler reverts to its previous
behaviour exactly.
