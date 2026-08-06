"""
Concurrent cache warming for a research request.

## The trick, and why it is safe

`research_ticker` issues nine provider calls in sequence. Seven of them are
independent — only the news fetch depends on an earlier one, because it needs
the company name that `get_company` resolves.

Rewriting a 469-line handler to thread those seven results through would be a
large, risky diff for a latency fix. This module does something smaller and
strictly safer: it **warms the cache** for those seven, concurrently, before
the handler starts. The handler is then left completely untouched, and its
sequential calls resolve instantly.

That works because of two properties the provider layer already has, both
verified rather than assumed:

- `FallbackChain.execute` is **cache-first by `cache_key`**, so a warmed key
  returns without touching a vendor.
- It wraps the fetch in **`SingleFlight`**, so a handler call that arrives
  while the prefetch is still in flight *joins* that fetch instead of
  starting a second one.

Together those mean prefetching cannot cause a duplicate vendor call. The
worst case is a wasted warm — the handler behaves exactly as before.

## Why this is not just a cache with extra steps

The cache already existed; what was missing was *parallelism*. The handler's
cost was never computation, it was nine round trips taken one after another.
Warming them concurrently converts nine sequential waits into one.

## What it deliberately does not prefetch

**News.** Its cache key includes the company name, which is only known after
`get_company` resolves. Guessing the name would warm a key nobody reads and
spend vendor budget to do it.

**Anything with side effects.** This runs speculatively; every call here must
be a pure read that is safe to make even if the handler later fails.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from src import providers
from src.providers.parallel import map_concurrent
from src.services import fundamentals_data

logger = logging.getLogger("omnisignal.research.prefetch")

#: Seven independent reads. Kept as (label, thunk-factory) so the list reads
#: as documentation of what a research request actually needs.
_WARMERS: tuple[tuple[str, Callable[[str], Callable[[], object]]], ...] = (
    ("series",      lambda t: lambda: providers.market_data.get_series(t, "1y")),
    ("benchmark",   lambda _: lambda: providers.market_data.get_series("SPY", "1y")),
    ("company",     lambda t: lambda: providers.fundamentals.get_company(t)),
    ("fundamentals", lambda t: lambda: providers.fundamentals.get_fundamentals(t)),
    ("street",      lambda t: lambda: providers.fundamentals.get_street(t)),
    ("quality",     lambda t: lambda: fundamentals_data.get_quality_inputs(t)),
    ("pead",        lambda t: lambda: fundamentals_data.get_pead_inputs(t)),
)


def warm(ticker: str) -> dict[str, bool]:
    """Warm the caches a research request will read. Never raises.

    Returns `{label: succeeded}` for observability. Callers should ignore the
    result for control flow: a cold cache is slower, never wrong, so a failed
    warm must not change what the handler does.
    """
    ticker = ticker.upper()
    started = time.perf_counter()

    outcomes = map_concurrent(
        lambda entry: entry[1](ticker)(),
        _WARMERS,
        label="research-prefetch",
    )

    status = {
        label: outcome.ok
        for (label, _), outcome in zip(_WARMERS, outcomes)
    }
    failed = [label for label, ok in status.items() if not ok]

    logger.info(
        "prefetch %s: %d/%d warm in %.2fs%s",
        ticker, len(status) - len(failed), len(status),
        time.perf_counter() - started,
        f" (cold: {', '.join(failed)})" if failed else "",
    )
    return status
