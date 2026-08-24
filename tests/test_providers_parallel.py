"""
Concurrent fan-out tests.

Concurrency bugs do not fail loudly; they fail on someone else's machine, on
a Tuesday. So these tests assert the properties that make the primitive safe
to put in front of every provider call — ordering, isolation, bounded
parallelism, and timeout containment — rather than only that it returns
answers.
"""

from __future__ import annotations

import threading
import time

import pytest

from src.providers.parallel import (
    DEFAULT_WORKERS,
    Outcome,
    map_concurrent,
    values,
)


def _slow(seconds: float):
    def inner(item):
        time.sleep(seconds)
        return item * 2
    return inner


# ── ordering ─────────────────────────────────────────────────────────────────

def test_results_follow_input_order_not_completion_order():
    """The contract the dashboard depends on.

    Items finish in reverse order here, so anything driven by completion
    would return them backwards.
    """
    def variable(item):
        time.sleep((10 - item) * 0.01)
        return item

    outcomes = map_concurrent(variable, list(range(10)), workers=10)
    assert [outcome.value for outcome in outcomes] == list(range(10))


def test_order_holds_when_some_items_fail():
    def sometimes(item):
        if item % 2:
            raise ValueError(f"item {item}")
        return item

    outcomes = map_concurrent(sometimes, list(range(6)), workers=4)
    assert [o.value for o in outcomes] == [0, None, 2, None, 4, None]
    assert [o.ok for o in outcomes] == [True, False, True, False, True, False]


# ── isolation ────────────────────────────────────────────────────────────────

def test_one_failure_does_not_abort_the_batch():
    """A sequential loop tolerated a bad vendor; the replacement must too."""
    def explode(item):
        if item == 3:
            raise RuntimeError("vendor down")
        return item

    outcomes = map_concurrent(explode, list(range(6)))
    assert sum(1 for o in outcomes if o.ok) == 5
    assert isinstance(outcomes[3].error, RuntimeError)


def test_every_item_failing_still_returns_a_full_list():
    outcomes = map_concurrent(lambda item: 1 / 0, list(range(4)))
    assert len(outcomes) == 4
    assert all(not o.ok for o in outcomes)
    assert values(outcomes) == []


def test_base_exception_is_captured_not_propagated():
    """Vendor adapters can raise anything, including outside `Exception`.

    `_run_one` catches `BaseException` on purpose: something that escapes a
    worker resurfaces at `future.result()` on the request thread and takes
    down the whole response, which is precisely what per-item isolation is
    supposed to prevent.
    """
    def nasty(item):
        if item == 1:
            raise KeyboardInterrupt("simulated")
        return item

    outcomes = map_concurrent(nasty, [0, 1, 2])
    assert [o.value for o in outcomes] == [0, None, 2]
    assert isinstance(outcomes[1].error, KeyboardInterrupt)


def test_values_drops_failures_and_nones():
    outcomes = [
        Outcome(1, None, 0.0),
        Outcome(None, ValueError("x"), 0.0),
        Outcome(None, None, 0.0),
        Outcome(4, None, 0.0),
    ]
    assert values(outcomes) == [1, 4]


# ── bounded parallelism ──────────────────────────────────────────────────────

def test_concurrency_never_exceeds_the_worker_limit():
    """The property that protects the vendors' token buckets.

    `try_acquire` is non-blocking, so exceeding a vendor's burst capacity
    converts slow successes into instant failures. This is the assertion
    that keeps that from happening.
    """
    live = 0
    peak = 0
    lock = threading.Lock()

    def watched(item):
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.02)
        with lock:
            live -= 1
        return item

    map_concurrent(watched, list(range(40)), workers=5)
    assert peak <= 5, f"peak concurrency {peak} exceeded the limit of 5"


def test_work_actually_runs_in_parallel():
    """Guards against the primitive silently degrading to a sequential loop."""
    items = list(range(8))
    started = time.perf_counter()
    map_concurrent(_slow(0.05), items, workers=8)
    elapsed = time.perf_counter() - started

    sequential = len(items) * 0.05
    assert elapsed < sequential / 2, (
        f"{elapsed:.3f}s is not meaningfully faster than {sequential:.3f}s serial"
    )


def test_single_item_skips_the_pool_entirely():
    """One item does not justify a thread and its handoff.

    Asserted by where the work runs, not just by the answer: checking the
    return value alone passes whether or not the shortcut exists.
    """
    caller = threading.current_thread().name
    outcomes = map_concurrent(lambda item: threading.current_thread().name, [41])
    assert outcomes[0].value == caller


def test_empty_input_returns_empty():
    assert map_concurrent(lambda item: item, []) == []


@pytest.mark.parametrize("workers", [0, -1])
def test_nonsensical_worker_count_is_rejected(workers):
    # Matched precisely: ThreadPoolExecutor's own "max_workers must be
    # greater than 0" contains "workers must be" as a substring, so a loose
    # pattern passes even when our own guard has been removed.
    with pytest.raises(ValueError, match=r"^workers must be >= 1"):
        map_concurrent(lambda item: item, [1, 2], workers=workers)


def test_worker_count_is_capped_by_item_count():
    """40 threads for 2 items would be waste, not speed."""
    names = set()

    def record(item):
        names.add(threading.current_thread().name)
        time.sleep(0.02)
        return item

    map_concurrent(record, [1, 2], workers=DEFAULT_WORKERS)
    assert len(names) <= 2


# ── timeout containment ──────────────────────────────────────────────────────

def test_a_hung_item_cannot_pin_the_request_open():
    """One dead socket must not hold a user request forever."""
    def hang(item):
        time.sleep(5 if item == 0 else 0.01)
        return item

    started = time.perf_counter()
    outcomes = map_concurrent(hang, [0, 1, 2], workers=3, timeout=0.3)
    elapsed = time.perf_counter() - started

    assert elapsed < 2.0, f"timeout did not contain the hang ({elapsed:.2f}s)"
    assert not outcomes[0].ok
    assert [o.value for o in outcomes[1:]] == [1, 2], "fast items must survive"


def test_outcome_records_per_item_duration():
    outcomes = map_concurrent(_slow(0.05), [1, 2], workers=2)
    assert all(o.seconds >= 0.04 for o in outcomes)


# ── interaction with the provider layer ──────────────────────────────────────

def test_single_flight_coalesces_duplicates_across_threads():
    """A fan-out containing the same key twice must fetch once.

    This is why concurrency is safe to add here rather than needing a new
    dedupe layer: `SingleFlight` already handles it, and this pins that it
    keeps working when the callers are threads rather than requests.
    """
    from src.providers.dedupe import SingleFlight

    flight = SingleFlight()
    fetches = 0
    lock = threading.Lock()
    # The first fetch is held open until every caller has arrived, rather
    # than for a fixed 50ms. Coalescing only applies to callers that are
    # genuinely concurrent — a thread arriving after the first fetch has
    # completed gets a fresh fetch, and that is correct. Timing the window
    # with a sleep made the test a race against the scheduler, and it lost
    # roughly whenever the machine was busy enough to run the other 761
    # tests alongside it. Gating on arrivals pins the real property exactly.
    ARRIVALS = 8
    all_arrived = threading.Event()
    arrived = 0

    def fetch(_item):
        nonlocal fetches

        def work():
            nonlocal fetches
            # Held until the last caller is inside `do`, so every one of them
            # is unambiguously concurrent with this fetch.
            assert all_arrived.wait(5.0), "callers never converged"
            with lock:
                fetches += 1
            return "payload"

        nonlocal arrived
        with lock:
            arrived += 1
            if arrived == ARRIVALS:
                all_arrived.set()
        return flight.do("same-key", work)

    outcomes = map_concurrent(fetch, list(range(ARRIVALS)), workers=ARRIVALS)
    assert all(o.ok and o.value == "payload" for o in outcomes)
    assert fetches == 1, f"expected coalescing to a single fetch, got {fetches}"


def test_cache_stays_consistent_under_concurrent_writes():
    """The fan-out must not corrupt the shared TTL cache."""
    from src.providers.cache import InMemoryCache

    cache = InMemoryCache(max_entries=64)

    def churn(item):
        cache.set(f"key-{item % 16}", item, ttl_seconds=30)
        return cache.get(f"key-{item % 16}")

    outcomes = map_concurrent(churn, list(range(200)), workers=8)
    assert all(o.ok for o in outcomes)
    assert len(cache._data) <= 64  # noqa: SLF001 — asserting the LRU bound holds
