"""
Bounded concurrent fan-out for provider calls.

## Why this exists

`get_dashboard()` made 32 provider calls in sequence. Measured cold, that was
**43.6 seconds, 100% of it inside those calls** — the handler itself did
essentially no work, it just waited 32 times in a row. Warm it was 0.000 s,
because every call was a cache hit. So the dashboard was never slow; it was
*serialised*, and the cost landed entirely on users who arrived with a cold
cache — which on Render means after every deploy and every spin-down.

The calls are independent. Nothing about macro series 7 depends on macro
series 6. Sequencing them was incidental, not required.

## Why bounded, and not just `ThreadPoolExecutor(len(items))`

Because `RateLimiter.try_acquire` is **non-blocking**. When a vendor's token
bucket is empty it raises `VendorError` immediately rather than waiting, and
the fallback chain then moves to the next vendor. An unbounded burst would
therefore not merely be rude to the vendor — it would convert slow successes
into instant *failures* and silently degrade answer quality, while looking
faster on a stopwatch. Bounded concurrency paces the burst so a wave of
calls never exceeds a vendor's capacity.

The provider layer is safe to call this way: `InMemoryCache`, `RateLimiter`,
`VendorStats` and the circuit state are each lock-guarded, and `SingleFlight`
coalesces concurrent duplicate keys so a fan-out containing the same symbol
twice performs one fetch. This module adds concurrency; it does not add
sharing that was not already thread-safe.

## What it deliberately does not do

No async, no event loop. FastAPI runs these handlers in a threadpool over
blocking I/O by design (CLAUDE.md), and the provider layer is synchronous
`requests`. Threads match the existing model; an async rewrite would mean a
second HTTP client and a second set of vendor adapters.

Not for writes, and not for anything order-dependent between items. This is
for independent reads whose only relationship is that a caller wants all of
them.
"""

from __future__ import annotations

import concurrent.futures
import contextvars
import logging
import time
from dataclasses import dataclass
from typing import Callable, Generic, Optional, Sequence, TypeVar

logger = logging.getLogger("omnisignal.providers.parallel")

T = TypeVar("T")
R = TypeVar("R")

#: Chosen against the vendor default of 30 requests/minute (`DEFAULT_RPM`).
#: Eight in flight is a burst a single vendor absorbs comfortably while still
#: collapsing a 32-call dashboard from 32 waits into 4. Raising it trades
#: latency for a higher chance of tripping a bucket, which costs answer
#: quality rather than time — the wrong direction.
DEFAULT_WORKERS = 8

#: Per-item ceiling. A vendor adapter already applies `TIMEOUT_SECONDS = 6.0`
#: with up to two retries, so a pathological item can legitimately take ~20 s.
#: This is the backstop for a call that hangs beyond even that, so one dead
#: socket cannot pin a user request open indefinitely.
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Outcome(Generic[R]):
    """One item's result: a value or a failure, never a silent absence.

    Failures are returned rather than raised because a fan-out that aborts on
    the first bad vendor would make the dashboard less reliable than the
    sequential loop it replaced — that loop tolerated a `None` per card and
    rendered the rest.
    """

    value: Optional[R]
    error: Optional[BaseException]
    seconds: float

    @property
    def ok(self) -> bool:
        return self.error is None


def map_concurrent(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    workers: int = DEFAULT_WORKERS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    label: str = "fanout",
) -> list[Outcome[R]]:
    """Apply `fn` to every item concurrently. Results follow **input order**.

    Input order is a guarantee, not an implementation detail: the dashboard
    renders ordered lists, and ordering by completion would make the response
    body vary between identical requests — breaking response caching and
    making diffs between two runs unreadable.

    Never raises for a failing item; inspect `Outcome.ok`. Raises only if
    `fn` is missing or `workers` is nonsensical, both caller bugs.
    """
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if not items:
        return []

    # One item does not justify a thread and its handoff. This is the common
    # case for single-symbol services, so it is worth not paying for.
    if len(items) == 1:
        return [_run_one(fn, items[0])]  # caller's context, already current

    started = time.perf_counter()
    results: list[Optional[Outcome[R]]] = [None] * len(items)

    # Deliberately not `with ThreadPoolExecutor(...)`: its `__exit__` calls
    # `shutdown(wait=True)`, which blocks until every worker finishes —
    # including the hung one the timeout exists to escape. Using the context
    # manager would make `timeout` decorative, and a test proves it does not
    # (`test_a_hung_item_cannot_pin_the_request_open`).
    pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=min(workers, len(items)),
        thread_name_prefix=f"omni-{label}",
    )
    try:
        # Copy the caller's context into every worker. `contextvars` do not
        # cross a ThreadPoolExecutor boundary on their own, so without this a
        # provider call made inside a fan-out would record into the global
        # registry but attribute to no request — losing exactly the requests
        # where the most time is spent.
        #
        # A *fresh copy per item*, not one shared copy: a `Context` can only
        # be entered by one thread at a time, and reusing a single object
        # across workers raises "context is already entered". The values
        # inside are shared by reference, which is what makes attribution
        # work and why `RequestProfile` is lock-guarded.
        futures = {
            pool.submit(contextvars.copy_context().run, _run_one, fn, item): index
            for index, item in enumerate(items)
        }
        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                # Already resolved, so this never blocks.
                results[futures[future]] = future.result()
        except concurrent.futures.TimeoutError:
            # Whatever finished is kept; the rest are marked below. Partial
            # results beat an exception — the sequential loop this replaced
            # rendered every card it managed to fetch.
            logger.warning(
                "%s: batch deadline of %.1fs passed with %d/%d items done",
                label, timeout,
                sum(1 for outcome in results if outcome is not None), len(items),
            )
    finally:
        # `wait=False` abandons any still-running worker rather than joining
        # it. Bounded in practice: vendor adapters carry their own 6 s socket
        # timeout, so an abandoned thread exits on its own shortly after.
        pool.shutdown(wait=False, cancel_futures=True)

    filled = [
        outcome if outcome is not None
        else Outcome(None, TimeoutError(f"exceeded {timeout}s batch deadline"), timeout)
        for outcome in results
    ]

    elapsed = time.perf_counter() - started
    failures = sum(1 for outcome in filled if not outcome.ok)
    serial = sum(outcome.seconds for outcome in filled)
    logger.info(
        "%s: %d items in %.2fs (serial would be %.2fs, %.1fx), %d failed",
        label, len(items), elapsed, serial,
        serial / elapsed if elapsed > 0 else 1.0, failures,
    )
    return filled


def values(outcomes: Sequence[Outcome[R]]) -> list[R]:
    """Successful, non-None values in input order.

    The common caller shape: services that already treated a failed fetch as
    "omit this card" get their old semantics in one call.
    """
    return [
        outcome.value for outcome in outcomes
        if outcome.ok and outcome.value is not None
    ]


def _run_one(fn: Callable[[T], R], item: T) -> Outcome[R]:
    started = time.perf_counter()
    try:
        return Outcome(fn(item), None, time.perf_counter() - started)
    except BaseException as exc:  # noqa: BLE001 — isolated, never propagated
        logger.warning("fanout item failed: %s", exc)
        return Outcome(None, exc, time.perf_counter() - started)
