"""
Factor Lab — the service behind cross-sectional factor research.

Assembles three things the repository already had but never connected: the
point-in-time panel (what each factor was worth, and when it was knowable),
realised forward returns (what happened next), and the cross-sectional
estimators in `src/research/`.

## Why this is the panel's first real consumer

`docs/PANEL.md` justifies the wide layout by saying cross-sectional ranking
reads one factor column across every symbol on a date. Until this service,
nothing did that — every view in the product examined one ticker at a time,
which cannot distinguish a factor that works from a market that rose.

## Cost, and why it is cached hard

A cold build is dominated by fetching prices for the whole universe, not by
computation: ~30 provider calls through the bounded fan-out, then a
vectorized panel build at ~13,600 cells/s. Measured end to end at roughly
35-40 s cold for 30 names over 2.5 years, and milliseconds warm.

That asymmetry is why the TTL is long. Factor evidence over a multi-year
window does not change between two page loads; recomputing it per request
would spend a minute of vendor budget to produce an identical answer.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from collections.abc import Iterator, MutableMapping
from datetime import date as Date
from datetime import timedelta
from typing import Any, Optional

import pandas as pd

from src import providers
from src.observability import timer
from src.panel import PanelBuilder, Universe
from src.panel.factors import PRICE_FACTOR_COLUMNS
from src.panel.schema import FACTOR_COLUMNS
from src.providers.parallel import map_concurrent
from src.research import (
    analyse, analyse_redundancy, attribute, dispersion, evaluate_factor,
    forward_returns, rank_cross_section, screen, simulate,
)
from src.research.cross_section import MIN_NAMES_PER_DATE
from src.services import job_store
from src.services.job_store import JobStoreUnavailable

logger = logging.getLogger("omnisignal.services.factor_lab")

#: Long on purpose — see the module docstring. Evidence over years does not
#: move between page loads.
CACHE_TTL_SECONDS = 3600.0

#: Weekly observation cadence. Daily would multiply vendor cost and panel
#: size ~5x while adding almost no independent information: a 21-day forward
#: return sampled daily overlaps 20/21, so the extra rows are nearly the same
#: observation repeated.
STEP_DAYS = 5

#: One trading month. Long enough for a factor to express itself, short
#: enough that ~2 years of vendor history yields a usable number of
#: non-overlapping windows.
DEFAULT_HORIZON = 21

#: The public API accepts presets, not arbitrary floats. Every distinct tuple
#: is a separate multi-vendor panel build, cache entry and background job; an
#: unconstrained query therefore turns URL cardinality directly into threads
#: and upstream spend. These are the useful research windows the UI may offer.
SUPPORTED_WINDOWS_YEARS: tuple[float, ...] = (1.0, 2.5, 5.0)
SUPPORTED_HORIZONS: tuple[int, ...] = (5, 21, 63)

#: Hard process-level cap on live factor workers, including a worker abandoned
#: after its deadline. Python cannot cancel a thread blocked in vendor I/O, so
#: not counting abandoned workers would let repeated retries grow without bound.
MAX_CONCURRENT_BUILDS = 2

_lock = threading.Lock()

# ── build jobs ───────────────────────────────────────────────────────────────
#
# A cold build takes 30-60 s. Blocking an HTTP request for that long is not a
# slow endpoint, it is a broken one: the Next.js dev proxy gives up first, and
# a serverless deployment has a hard function timeout well below it. Observed
# directly — the backend logged `200 in 44413ms` while the browser showed a
# network failure.
#
# So the endpoint never blocks. It starts a background build, answers
# immediately with the stage the build has actually reached, and the client
# polls. That also makes the loader honest for the first time: the stages it
# shows are reported by the process doing the work rather than estimated from
# a timer.

#: In the order the build actually performs them, which is not the order this
#: tuple used to claim. It read ("prices", "panel", "filings", ...), but
#: `PanelBuilder.build` loads every symbol's SEC facts *before* it touches
#: prices — so a real build reported "filings" and then "prices", and the
#: client's stage index visibly ran backwards from 2 to 0 while the loader
#: insisted filings came third. "panel" is gone because it was never
#: separately observable: the builder emits panel rows inside the same
#: per-symbol loop it reports "prices" from.
STAGES: tuple[str, ...] = (
    "filings", "prices", "returns", "estimators",
)

#: Wall-clock ceiling on a single build, after which the job is declared
#: stalled and the caller is told so.
#:
#: This exists because of a real incident: /terminal/factors sat on "Running
#: the estimators" for ~2920 seconds. Nothing was wrong with the loader — it
#: was faithfully reporting that the job had not finished. The bug was that
#: `run()` had no upper bound: a build thread that blocks (or dies in a way
#: `except Exception` cannot observe) leaves `done=False` in the registry
#: forever, and every subsequent poll answers `building` with the last stage
#: it managed to set. There was no exit from that state.
#:
#: The value is set against measurement, not guessed. A cold mega30 build is
#: 53.6 s end to end, of which 52.1 s is vendor I/O for the panel and 1.3 s
#: is every estimator combined. 240 s is ~4.5x the observed cold build, so a
#: merely slow vendor day still completes; anything past it is not slow, it
#: is stuck.
#:
#: Note what this deliberately does *not* claim: Python cannot cancel a
#: thread doing blocking work, so the stalled worker is abandoned rather than
#: killed. It is a daemon, so it cannot hold the process open, and the job
#: registry drops its entry so a retry starts clean. What is guaranteed here
#: is that *the request terminates* — not that the orphan stops running.
BUILD_DEADLINE_SECONDS = 240.0

#: How long a failed build is remembered before a new request rebuilds.
#:
#: Without this the retry rule was "restart whenever the last attempt
#: failed", which the polling client evaluates every 1.5 s. A build that
#: fails deterministically — one vendor down, a universe whose data never
#: arrives — therefore never reported its failure to anyone: each poll saw
#: the failed job, started a *new* one, and answered `building`. The page
#: loaded forever while the backend span up a fresh build thread twice a
#: second. That is the same symptom as a stall and a far more likely cause
#: of one.
#:
#: So a failure is now an answer with a short memory: every caller inside
#: the window gets the real error, and a retry after it builds again.
FAILED_RETRY_COOLDOWN_SECONDS = 30.0

#: Heartbeats are independent of stage changes. A vendor call can legitimately
#: spend a long time inside one stage; stage-only liveness would reclaim live
#: work simply because it had nothing new to report.
HEARTBEAT_INTERVAL_SECONDS = 5.0
STALE_OWNER_SECONDS = 20.0

JOB_PREFIX = "factor-job:"
RESULT_PREFIX = "factor-result:"
_worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"


def _job_key(key: str) -> str:
    return f"{JOB_PREFIX}{key}"


def _result_key(key: str, token: str) -> str:
    return f"{RESULT_PREFIX}{key}:{token}"


class _JobRegistryView(MutableMapping[str, dict[str, Any]]):
    """Compatibility/debug view over the real JobStore-backed registry.

    Production code uses the store directly. Keeping this mapping-shaped view
    means existing diagnostics and termination tests can inspect a job without
    reintroducing a second, process-local source of truth.
    """

    def __getitem__(self, key: str) -> dict[str, Any]:
        value = job_store.get_store().get(_job_key(key))
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        job_store.get_store().put(_job_key(key), value)

    def __delitem__(self, key: str) -> None:
        if job_store.get_store().get(_job_key(key)) is None:
            raise KeyError(key)
        job_store.get_store().delete(_job_key(key))

    def __iter__(self) -> Iterator[str]:
        for key in job_store.get_store().keys():
            if key.startswith(JOB_PREFIX):
                yield key[len(JOB_PREFIX):]

    def __len__(self) -> int:
        return sum(1 for _ in self)


_jobs: MutableMapping[str, dict[str, Any]] = _JobRegistryView()

#: Build workers that have been started, so `reset_for_tests` can wait for
#: them. Production deliberately abandons a stalled worker — Python cannot
#: cancel a thread doing blocking I/O — and that is unchanged. A test suite is
#: a different situation: an abandoned worker keeps calling providers, and it
#: lands inside whatever `patch` a later test has installed. That is how a
#: backtest test asserting one vendor call saw three, the extra two being this
#: builder loading its benchmark and its first symbol.
_workers: list[threading.Thread] = []
_jobs_lock = threading.RLock()


def _set_stage(
    handle: Optional[tuple[str, str | int]], stage: str, done: int = 0, total: int = 0
) -> None:
    """Record progress for the build identified by `handle`.

    The handle carries the generation token, not just the key. Without it an
    abandoned worker — one whose build blew the deadline and was replaced —
    keeps calling this and rewrites the *replacement* job's stage, driving
    the client's progress backwards through stages the new build has not
    reached. The token check makes a stale writer a no-op.
    """
    if not handle:
        return
    key, token = handle
    now = time.time()

    def advance(job: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if (
            job is None
            or job.get("token") != token
            or job.get("owner_worker_id") not in (None, _worker_id)
            or job.get("status", "running") != "running"
        ):
            return job
        previous = job.get("stage")
        if previous and previous != stage:
            timings = dict(job.get("timings") or {})
            timings[previous] = round(now - job.get("stage_started", now), 2)
            job["timings"] = timings
            job["stage_started"] = now
        index = STAGES.index(stage) if stage in STAGES else 0
        if index >= job.get("stage_index", 0):
            job["stage"] = stage
            job["stage_index"] = index
        job["done"] = False
        job["progress_done"] = done
        job["progress_total"] = total
        job["heartbeat_at"] = now
        return job

    try:
        job_store.get_store().mutate(_job_key(key), advance)
    except JobStoreUnavailable:
        logger.exception("factor lab could not record progress for %s", key)


def available_universes() -> list[dict[str, Any]]:
    from src.panel.universe import available

    return [
        {"name": name, "symbols": len(Universe.named(name))}
        for name in available()
    ]


def request_supported(years: float, horizon: int) -> bool:
    """Whether a request maps to one of the finite, documented build keys."""
    return years in SUPPORTED_WINDOWS_YEARS and horizon in SUPPORTED_HORIZONS


def run(
    universe_name: str = "mega30",
    years: float = 2.5,
    horizon: int = DEFAULT_HORIZON,
) -> dict[str, Any]:
    """Return the evaluation, or the progress of the build producing it.

    Never blocks. A cached result comes back immediately; otherwise a
    background build is started (or joined) and the current stage is
    reported so the caller can poll.
    """
    if not request_supported(years, horizon):
        return {
            "status": "error",
            "error": (
                f"unsupported factor window: years={years}, horizon={horizon}. "
                f"Supported years are {list(SUPPORTED_WINDOWS_YEARS)} and "
                f"supported horizons are {list(SUPPORTED_HORIZONS)} trading days."
            ),
            "retryable": False,
            "supported": {
                "years": list(SUPPORTED_WINDOWS_YEARS),
                "horizons": list(SUPPORTED_HORIZONS),
            },
        }

    # Validate before anything else. An unknown universe is knowable
    # instantly, so backgrounding it would make the caller poll a job that was
    # always going to fail — and would answer "building" to a question that
    # already has an answer.
    try:
        Universe.named(universe_name)
    except KeyError as exc:
        return {
            "status": "error",
            "error": f"unknown universe: {exc}",
            "universes": available_universes(),
        }

    key = f"{universe_name}:{years}:{horizon}"
    now = time.time()
    store = job_store.get_store()

    try:
        before = store.get(_job_key(key))
    except JobStoreUnavailable as exc:
        return {
            "status": "error",
            "error": f"background job state is unavailable: {exc}",
            "retryable": True,
            "universe": {"name": universe_name},
        }

    # Capacity is process-local because the work itself is a thread in this
    # process. The shared ownership claim below prevents every other process
    # from starting the same key; this guard prevents distinct keys from
    # creating unbounded threads in the process that won their claims.
    with _jobs_lock:
        _workers[:] = [worker for worker in _workers if worker.is_alive()]
        active_builds = len(_workers)
    if before is None and active_builds >= MAX_CONCURRENT_BUILDS:
        return {
            "status": "busy",
            "error": "factor build capacity is in use; no additional worker was started",
            "retryable": True,
            "retry_after_seconds": 2,
            "active_builds": active_builds,
            "max_concurrent_builds": MAX_CONCURRENT_BUILDS,
            "universe": {"name": universe_name},
        }

    token = uuid.uuid4().hex

    def claim(current: Optional[dict[str, Any]]) -> dict[str, Any]:
        status = "missing"
        if current is not None:
            status = str(current.get("status") or (
                "failed" if current.get("failed")
                else "success" if current.get("done")
                else "running"
            ))

        if current is not None and status == "running":
            started = float(current.get("started", now))
            if now - started > BUILD_DEADLINE_SECONDS:
                abandoned = dict(current)
                abandoned.update(
                    status="abandoned", done=True, failed=True,
                    finished=now,
                    error=(
                        f"the build stalled in the {current.get('stage', STAGES[0])!r} "
                        f"stage and was stopped after {now - started:.0f}s"
                    ),
                )
                return abandoned

            heartbeat = float(current.get("heartbeat_at", started))
            if now - heartbeat <= STALE_OWNER_SECONDS:
                return current
            # The owning process stopped proving it was alive. Reclaim now,
            # not after the full build deadline. A unique token means a late
            # old worker cannot write progress or a result into this attempt.

        if current is not None and status == "failed":
            finished = float(current.get("finished", current.get("started", now)))
            if now - finished <= FAILED_RETRY_COOLDOWN_SECONDS:
                return current

        if current is not None and status == "success" and current.get("result_key"):
            return current

        generation = int(current.get("generation", 0)) + 1 if current else 1
        attempt = int(current.get("attempt", 0)) + 1 if current else 1
        record: dict[str, Any] = {
            "started": now,
            "stage": STAGES[0],
            "stage_index": 0,
            "stage_started": now,
            "timings": {},
            "done": False,
            "failed": False,
            "status": "running",
            "token": token,
            "generation": generation,
            "attempt": attempt,
            "owner_worker_id": _worker_id,
            "heartbeat_at": now,
            "progress_done": 0,
            "progress_total": 0,
        }
        if current is not None:
            record["reclaimed_from"] = {
                "token": current.get("token"),
                "owner_worker_id": current.get("owner_worker_id"),
                "status": status,
            }
        return record

    try:
        snapshot = store.mutate(_job_key(key), claim)
    except JobStoreUnavailable as exc:
        return {
            "status": "error",
            "error": f"background job state is unavailable: {exc}",
            "retryable": True,
            "universe": {"name": universe_name},
        }

    if snapshot is None:
        return {"status": "error", "error": "the job claim disappeared", "retryable": True}

    status = str(snapshot.get("status", "running"))
    if status == "abandoned":
        logger.error(
            "factor lab build for %s stalled in stage %r after %.0fs; abandoning it",
            universe_name, snapshot.get("stage"), now - float(snapshot.get("started", now)),
        )
        return _stalled_payload(snapshot, universe_name, now)

    if status == "failed":
        return {
            "status": "error",
            "error": snapshot.get("error") or "factor evaluation failed",
            "retryable": True,
            "universe": {"name": universe_name},
        }

    if status == "success":
        result_key = snapshot.get("result_key")
        try:
            result = store.get(str(result_key)) if result_key else None
        except JobStoreUnavailable as exc:
            return {"status": "error", "error": str(exc), "retryable": True}
        payload = result.get("payload") if isinstance(result, dict) else None
        if isinstance(payload, dict):
            return {**payload, "status": "ready", "cached": True}
        return {
            "status": "error",
            "error": "the completed build's shared result is no longer available",
            "retryable": True,
            "universe": {"name": universe_name},
        }

    # Only the request whose token won the atomic claim may start compute.
    if snapshot.get("token") == token and snapshot.get("owner_worker_id") == _worker_id:
        with _jobs_lock:
            _workers[:] = [worker for worker in _workers if worker.is_alive()]
            if len(_workers) >= MAX_CONCURRENT_BUILDS:
                def release_claim(current: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
                    if current and current.get("token") == token:
                        current.update(
                            status="cancelled", done=True, failed=True,
                            finished=time.time(), error="local build capacity changed before start",
                        )
                    return current
                store.mutate(_job_key(key), release_claim)
                return {
                    "status": "busy", "error": "factor build capacity is in use",
                    "retryable": True, "retry_after_seconds": 2,
                    "active_builds": len(_workers),
                    "max_concurrent_builds": MAX_CONCURRENT_BUILDS,
                    "universe": {"name": universe_name},
                }
            worker = threading.Thread(
                target=_run_job, args=(key, universe_name, years, horizon, token),
                name=f"factor-lab-{universe_name}", daemon=True,
            )
            worker.start()
            _workers.append(worker)

    return {
        "status": "building",
        "stage": snapshot.get("stage", STAGES[0]),
        "stage_index": snapshot.get("stage_index", 0),
        "stages": list(STAGES),
        "progress_done": snapshot.get("progress_done", 0),
        "progress_total": snapshot.get("progress_total", 0),
        "elapsed_seconds": round(time.time() - float(snapshot.get("started", now)), 1),
        "attempt": snapshot.get("attempt", 1),
        "universe": {"name": universe_name},
    }


def _optional(name: str, compute, degraded: list[dict[str, str]]):
    """Run one estimator; on failure record it and carry on.

    Returns `None` both when the estimator legitimately has nothing to
    report and when it raised — the caller renders both as absent, but only
    the raise appends to `degraded`, which is what lets the UI say
    "attribution unavailable" instead of silently dropping a section.
    """
    try:
        return compute()
    except Exception as exc:  # noqa: BLE001 — isolation is the whole point
        logger.exception("factor lab estimator %r failed", name)
        degraded.append({"estimator": name, "reason": f"{type(exc).__name__}: {exc}"})
        return None


def _stalled_payload(
    job: dict[str, Any], universe_name: str, now: float
) -> dict[str, Any]:
    """What the caller gets when a build blew its deadline.

    Says which stage it died in and how long the stages before it took, so
    the answer distinguishes "a vendor is hanging" from "a computation is
    wedged" without anyone having to read the server logs.
    """
    stage = job.get("stage") or STAGES[0]
    elapsed = now - job["started"]
    timings = dict(job.get("timings") or {})
    timings[stage] = round(now - job.get("stage_started", job["started"]), 2)

    done = job.get("progress_done") or 0
    total = job.get("progress_total") or 0
    detail = f" ({done}/{total} complete)" if total else ""

    return {
        "status": "error",
        "error": (
            f"the build stalled in the {stage!r} stage{detail} and was stopped "
            f"after {elapsed:.0f}s. Stage timings so far: "
            + ", ".join(f"{name} {seconds}s" for name, seconds in timings.items())
            + ". This is usually a vendor that stopped responding; trying again "
            "starts a fresh build."
        ),
        "stalled_stage": stage,
        "stage_timings": timings,
        "elapsed_seconds": round(elapsed, 1),
        # The distinction the UI needs: an unknown universe is permanent, a
        # stall is not, and the recovery action differs.
        "retryable": True,
        "universe": {"name": universe_name},
    }


def _heartbeat(key: str, token: str, stop: threading.Event) -> None:
    """Prove the owning process still exists even while one stage is quiet."""
    store = job_store.get_store()
    while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        now = time.time()

        def beat(current: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
            if (
                current
                and current.get("token") == token
                and current.get("owner_worker_id") == _worker_id
                and current.get("status") == "running"
            ):
                current["heartbeat_at"] = now
            return current

        try:
            current = store.mutate(_job_key(key), beat)
        except JobStoreUnavailable:
            logger.exception("factor lab heartbeat store unavailable for %s", key)
            return
        if not current or current.get("token") != token or current.get("status") != "running":
            return


def _finish_job(key: str, token: str, *, error: Optional[str] = None,
                result_key: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Finish only the attempt this worker owns; stale workers are no-ops."""
    now = time.time()

    def finish(current: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if (
            current is None
            or current.get("token") != token
            or current.get("owner_worker_id") != _worker_id
            or current.get("status") != "running"
        ):
            return current
        current.update(
            status="failed" if error else "success",
            done=True,
            failed=bool(error),
            error=error,
            finished=now,
            heartbeat_at=now,
        )
        if result_key:
            current["result_key"] = result_key
        return current

    return job_store.get_store().mutate(_job_key(key), finish)


def _run_job(
    key: str, universe_name: str, years: float, horizon: int, token: str
) -> None:
    """Background build with shared ownership, heartbeat and terminal state."""
    stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(key, token, stop),
        name=f"factor-lab-heartbeat-{universe_name}",
        daemon=True,
    )
    heartbeat.start()
    try:
        payload = _build(universe_name, years, horizon, progress=(key, token))
        if "error" in payload:
            _finish_job(key, token, error=str(payload.get("error")))
        else:
            result_key = _result_key(key, token)
            # Result is token-specific. If a deadline already abandoned this
            # worker, its orphan can expire without ever being referenced by
            # the current job record.
            job_store.get_store().put(
                result_key,
                {"token": token, "payload": payload, "finished": time.time()},
                ttl=CACHE_TTL_SECONDS,
            )
            _finish_job(key, token, result_key=result_key)
    except KeyError as exc:
        _finish_job(key, token, error=f"unknown universe: {exc}")
    # BaseException, not Exception. `except Exception` cannot see SystemExit
    # or KeyboardInterrupt, and a worker killed by one of those left
    # `done=False` in the registry with no writer ever coming back to fix it
    # — an unpollable job that answers "building" forever. The deadline in
    # `run()` now catches that case too, but taking 240 s to report something
    # already known is not a good answer.
    except BaseException as exc:  # noqa: BLE001 — a research view must not 500 the app
        logger.exception("factor lab failed for %s", universe_name)
        try:
            _finish_job(
                key, token,
                error=f"factor evaluation failed: {type(exc).__name__}: {exc}",
            )
        except JobStoreUnavailable:
            logger.exception("factor lab could not record failure for %s", key)
        # Not re-raised. This is a daemon worker; re-raising SystemExit here
        # would only kill this thread — which is already ending — while
        # producing an unhandled-thread-exception trace that looks like a
        # crash. The outcome is recorded, which is the part that matters.
    finally:
        stop.set()


def _build(
    universe_name: str, years: float, horizon: int,
    progress: Optional[tuple[str, str | int]] = None,
) -> dict[str, Any]:
    started = time.perf_counter()

    def stage(name: str) -> None:
        if progress:
            _set_stage(progress, name)

    stage("filings")
    universe = Universe.named(universe_name)
    end = Date.today()
    start = end - timedelta(days=int(years * 365))


    def relay(sub_stage: str, done: int, total: int) -> None:
        # The builder knows which symbol it is on; map that onto the stage
        # names the client renders so the count lands on the right row.
        if progress:
            _set_stage(progress, sub_stage if sub_stage in STAGES else "prices", done, total)

    with timer("factor_lab.panel_build", universe=universe_name):
        panel, manifest = PanelBuilder(on_progress=relay).build(
            universe, start, end, step=STEP_DAYS
        )
    if panel.empty:
        return {"error": "no panel data could be built for this universe"}

    stage("returns")
    with timer("factor_lab.prices", universe=universe_name):
        prices = _load_prices(list(universe.symbols))

    dates = sorted(panel["date"].unique())
    outcomes = forward_returns(prices, dates, horizon)
    if outcomes.empty:
        return {"error": "no realised forward returns available yet"}

    # Two joins, deliberately different.
    #
    # `evaluable` is an INNER join: measuring a factor requires knowing what
    # happened next, so dates whose forward window has not closed cannot
    # contribute to an IC.
    #
    # `rankable` is a LEFT join: the engine's ranking *today* is knowable
    # today, and it is the most useful row on the page. Showing only dates
    # with realised outcomes would hide the current cross-section — which is
    # exactly what an inner join did in the first version of this service.
    evaluable = panel.merge(outcomes, on=["symbol", "date"], how="inner")
    rankable = panel.merge(outcomes, on=["symbol", "date"], how="left")

    # Portfolio simulation uses the *holding-period* return, not the
    # evaluation horizon. Holding for exactly one rebalance interval makes
    # consecutive periods non-overlapping, so the Sharpe ratio needs no
    # autocorrelation correction — the overlap is designed out rather than
    # corrected for.
    periods = forward_returns(prices, dates, STEP_DAYS).rename(
        columns={"forward_return": "period_return"}
    )
    tradeable = panel.merge(periods, on=["symbol", "date"], how="inner")

    # Evaluate whatever the panel actually populated, not a hardcoded sleeve.
    # SEC-derived fundamentals appear here automatically once the builder
    # fills them, which is what lets a new factor be judged by the same bar
    # as every existing one rather than being introduced by assertion.
    populated = tuple(
        name for name in FACTOR_COLUMNS
        if name in evaluable.columns and evaluable[name].notna().any()
    )

    stage("estimators")

    # Every estimator past the IC is optional. They are independent of one
    # another, so a failure in redundancy says nothing about whether the
    # portfolio simulation is trustworthy — and letting one exception abort
    # the build discards ~50 s of vendor work to report nothing. Each is
    # isolated and its failure recorded, so the response can show what was
    # computed and name what was not.
    #
    # The IC itself is deliberately *not* isolated: it is the page's subject,
    # and a Factor Lab with no factor evaluation has nothing to degrade to.
    degraded: list[dict[str, str]] = []

    with timer("factor_lab.evaluate", universe=universe_name):
        factors = [
            _serialise(evaluation)
            for name in populated
            if (evaluation := evaluate_factor(
                evaluable, name, horizon, STEP_DAYS
            )) is not None
        ]
    with timer("factor_lab.portfolios", universe=universe_name):
        portfolios = {}
        for name in populated:
            result = _optional(f"portfolio:{name}", lambda n=name: simulate(tradeable, n), degraded)
            if result is not None:
                portfolios[name] = _serialise_portfolio(result)
    for row in factors:
        row["portfolio"] = portfolios.get(row["factor"])
        stability = _optional(
            f"stability:{row['factor']}",
            lambda r=row: analyse(r["factor"], [(d, v) for d, v in r["ic_series"]]),
            degraded,
        )
        row["stability"] = _serialise_stability(stability) if stability is not None else None

    factors.sort(key=lambda row: -abs(row["t_stat"]))

    if not factors:
        return {
            "error": (
                f"{universe_name} has {len(universe)} symbols; cross-sectional "
                f"evaluation needs at least {MIN_NAMES_PER_DATE} names on a date. "
                "A rank correlation over five names is noise, not a ranking — so "
                "this reports nothing rather than a number that would look real."
            ),
            "universes": available_universes(),
        }

    latest = max(dates)
    return {
        "universe": {
            "name": universe_name,
            "symbols": list(universe.symbols),
            "point_in_time_membership": universe.point_in_time,
        },
        "window": {
            "start": str(start), "end": str(end),
            "observation_dates": len(dates),
            "evaluable_cells": len(evaluable),
            "step_days": STEP_DAYS,
            "horizon_days": horizon,
        },
        "factors": factors,
        "latest_cross_section": {
            "date": str(latest),
            "factors": {
                name: rank_cross_section(rankable, name, latest)
                for name in populated
            },
        },
        "screen": _optional(
            "screen", lambda: _screen_payload(rankable, latest, populated), degraded
        ),
        "redundancy": _optional(
            "redundancy", lambda: _redundancy_payload(panel, populated), degraded
        ),
        "attribution": _optional(
            "attribution", lambda: _attribution_payload(evaluable, populated), degraded
        ),
        # Present and empty on a clean build. The UI distinguishes "this
        # estimator returned nothing because there was nothing to say" from
        # "this estimator failed", and only the second belongs here.
        "degraded": degraded,
        "caveats": _caveats(len(factors), universe),
        "engine_version": manifest.engine_version,
        "build_seconds": round(time.perf_counter() - started, 2),
        "cached": False,
    }


def _serialise(evaluation) -> dict[str, Any]:
    return {
        "factor": evaluation.factor,
        "mean_ic": round(evaluation.mean_ic, 5),
        "std_ic": round(evaluation.std_ic, 4),
        "t_stat": round(evaluation.t_stat, 3),
        "naive_t_stat": round(evaluation.naive_t_stat, 3),
        "overlap_inflation": round(evaluation.inflation, 2),
        "newey_west_lags": evaluation.newey_west_lags,
        "hit_rate": round(evaluation.hit_rate, 3),
        "dates": evaluation.dates,
        "names_median": evaluation.names_median,
        "top_minus_bottom": (
            round(evaluation.top_minus_bottom, 5)
            if evaluation.top_minus_bottom is not None else None
        ),
        "quantiles": evaluation.quantiles,
        "saturation": round(evaluation.saturation, 4),
        "significant": evaluation.significant,
        "assessment": evaluation.assessment,
        "ic_series": evaluation.ic_series,
    }


def _serialise_stability(stability) -> dict[str, Any]:
    return {
        "window": stability.window,
        "rolling": stability.rolling,
        "first_half_ic": (
            round(stability.first_half_ic, 5)
            if stability.first_half_ic is not None else None
        ),
        "second_half_ic": (
            round(stability.second_half_ic, 5)
            if stability.second_half_ic is not None else None
        ),
        "best_window": stability.best_window,
        "worst_window": stability.worst_window,
        "concentration": round(stability.concentration, 3),
        "sign_flips": stability.sign_flips,
        "decayed": stability.decayed,
        "assessment": stability.assessment,
    }


def _attribution_payload(
    evaluable: pd.DataFrame, factors: tuple[str, ...]
) -> Optional[dict[str, Any]]:
    """How much of the cross-section the factors actually explain."""
    result = attribute(evaluable, factors)
    if result is None:
        return None
    return {
        "factors": result.factors,
        "factor_returns": {k: round(v, 6) for k, v in result.factor_returns.items()},
        "t_stats": {k: round(v, 3) for k, v in result.t_stats.items()},
        "mean_r_squared": round(result.mean_r_squared, 4),
        "mean_adjusted_r_squared": round(result.mean_adjusted_r_squared, 4),
        "overfit_gap": round(result.overfit_gap, 4),
        "names_median": result.names_median,
        "unexplained_share": round(result.unexplained_share, 4),
        "dates": result.dates,
        "assessment": result.assessment,
    }


def _redundancy_payload(
    panel: pd.DataFrame, factors: tuple[str, ...]
) -> Optional[dict[str, Any]]:
    """How many independent signals the seven factors actually represent."""
    result = analyse_redundancy(panel, factors)
    if result is None:
        return None
    return {
        "factors": result.factors,
        "matrix": result.matrix,
        "effective_factors": result.effective_factors,
        # Every unobserved pair entered the eigenvalue calculation as zero
        # correlation, which pushes effective_factors up. Published so the
        # number can be discounted rather than read at face value.
        "measured_pairs": result.measured_pairs,
        "total_pairs": result.total_pairs,
        "pair_coverage": (
            round(result.pair_coverage, 4) if result.pair_coverage is not None else None
        ),
        "redundant_pairs": [
            {"a": a, "b": b, "correlation": c} for a, b, c in result.redundant_pairs
        ],
        "dates": result.dates,
        "assessment": result.assessment,
    }


def _screen_payload(
    rankable: pd.DataFrame, latest: Date, factors: tuple[str, ...]
) -> dict[str, Any]:
    """The composite cross-section: every name ranked, with factor agreement."""
    rows = screen(rankable, factors, latest)
    return {
        "date": str(latest),
        "dispersion": dispersion(rows),
        "rows": [
            {
                "rank": row.rank,
                "symbol": row.symbol,
                "composite": round(row.composite, 1),
                "agreement": round(row.agreement, 3),
                "conviction": row.conviction,
                "factors_used": row.factors_used,
                "percentiles": row.percentiles,
                "strongest": row.strongest,
                "weakest": row.weakest,
            }
            for row in rows
        ],
    }


def _serialise_portfolio(result) -> dict[str, Any]:
    return {
        "buckets": result.buckets,
        "rebalances": result.rebalances,
        "total_return": round(result.total_return, 5),
        "annualised_return": round(result.annualised_return, 5),
        "annualised_volatility": round(result.annualised_volatility, 5),
        "sharpe": round(result.sharpe, 3),
        "max_drawdown": round(result.max_drawdown, 5),
        "hit_rate": round(result.hit_rate, 3),
        "turnover": round(result.turnover, 4),
        "long_leg_return": round(result.long_leg_return, 5),
        "short_leg_return": round(result.short_leg_return, 5),
        "benchmark_return": round(result.benchmark_return, 5),
        "beat_benchmark": result.beat_benchmark,
        "assessment": result.assessment,
        "equity_curve": result.equity_curve,
    }


def _caveats(factor_count: int, universe: Universe) -> list[str]:
    """Stated with the results, not buried in a footnote.

    A research tool that reports statistics without their limitations is
    presenting decoration. Each of these materially changes how the numbers
    above should be read.
    """
    family_wise = 1 - 0.95 ** max(factor_count, 1)
    return [
        f"Multiple comparisons: {factor_count} factors were tested. Even if none "
        f"had predictive power, the chance at least one appears significant at "
        f"the 5% level is about {family_wise:.0%}. Judge the set, not the best member.",
        "Overlapping windows: forward returns overlap between observation dates, "
        "so t-statistics are Newey-West corrected. The uncorrected values are shown "
        "alongside — the gap between them is how much the naive statistic overstates.",
        "Survivorship bias: universe membership is current, not historical, so every "
        "name in it survived to today. This inflates results in an unknown direction "
        "and is not correctable without point-in-time index membership."
        if not universe.point_in_time else
        "Universe membership is point-in-time.",
        "Factor coverage: every factor the panel populated is evaluated here. "
        "Price factors come from OHLCV; fundamentals come from SEC XBRL with each "
        "figure dated by its filing, so a restatement becomes visible exactly when "
        "it was published. Sleeves with no point-in-time source are absent rather "
        "than approximated.",
        "Trading costs are not modelled. Turnover is reported per factor so a "
        "cost assumption can be applied by the reader rather than inherited from "
        "one invented here — at 40% weekly turnover, realistic costs can exceed "
        "the entire simulated edge.",
        "Factor redundancy: the screen weights every factor equally, but the "
        "correlation matrix shows how many independent signals those factors "
        "actually represent. Where that number is well below the factor count, "
        "equal weighting silently over-votes whichever family is duplicated.",
        "The screen weights every factor equally. Weighting by measured IC would "
        "fit weights to noise, since none of these factors is statistically "
        "significant on this sample — so the composite makes a deliberately weak "
        "claim, and the agreement column carries more information than the rank.",
        "Sample size: roughly two years of free-tier vendor history. Factor evidence "
        "at this length is suggestive at best; treat a single significant result as a "
        "hypothesis, not a finding.",
    ]


def _load_prices(symbols: list[str]) -> dict[str, pd.Series]:
    """Close series per symbol, fanned out through the bounded pool."""
    def load(symbol: str) -> tuple[str, Optional[pd.Series]]:
        result = providers.market_data.get_series(symbol, "5y")
        if not result.ok or not result.data.bars:
            return symbol, None
        series = pd.Series(
            {pd.Timestamp(bar.date): bar.close for bar in result.data.bars}
        ).sort_index()
        return symbol, series

    outcomes = map_concurrent(load, symbols, label="factor-lab-prices")
    return {
        symbol: series
        for symbol, series in (outcome.value for outcome in outcomes if outcome.ok)
        if series is not None and not series.empty
    }


def reset_for_tests(timeout: float = 10.0) -> int:
    """Clear caches and jobs, and wait for any in-flight build worker.

    The wait is the part that matters. Clearing `_jobs` drops the registry
    entry but leaves the thread running, and a running builder keeps calling
    providers — inside whatever `patch` the next test has installed. Joining
    here makes the reset mean what its name says.

    Bounded, and it never raises: a worker that outlives the timeout is
    reported through the returned count rather than hanging the suite. That
    count used to be promised here and never computed — the function always
    returned `None`, so a worker that failed to join within the timeout was
    silently invisible to whatever called this. A non-zero return is worth a
    log line of its own: it means a daemon thread is still doing vendor I/O
    after the suite believes this fixture is done, which is exactly how one
    test's abandoned worker used to land inside a *later* test's `patch`.
    """
    with _jobs_lock:
        workers = list(_workers)
        _workers.clear()

    # Joined outside the lock: a worker still finishing needs `_jobs_lock` to
    # record its result, and holding it here would deadlock against that.
    for worker in workers:
        worker.join(timeout=timeout)
    still_alive = sum(1 for worker in workers if worker.is_alive())
    if still_alive:
        logger.warning(
            "factor lab reset_for_tests: %d worker(s) did not join within %.1fs",
            still_alive, timeout,
        )

    try:
        store = job_store.get_store()
        for key in store.keys():
            if key.startswith(JOB_PREFIX) or key.startswith(RESULT_PREFIX):
                store.delete(key)
    except JobStoreUnavailable:
        pass
    job_store.reset_store_for_tests()
    return still_alive
