"""A Factor Lab request must always terminate.

The incident this file exists for: /terminal/factors sat on "Running the
estimators" for ~2920 seconds. The loader was telling the truth — the job
really had not finished — because `run()` had no upper bound at all. A build
thread that blocks, or dies in a way `except Exception` cannot see, leaves
`done=False` in the job record forever, and every poll after that answers
`status: building` with the last stage it managed to set. There is no path
out of that state: not a timeout, not an error, not a retry.

Measured while diagnosing it, so the shape of the fix is not guesswork:

    panel build (vendor I/O)   52.08 s
    IC / Newey-West             1.00 s
    portfolios                  0.26 s
    stability                   0.00 s
    rank_cross_section          0.01 s
    screen                      0.00 s
    redundancy                  0.03 s
    attribution                 0.03 s
    ---------------------------------
    all estimators              1.33 s

So the estimators are not slow, and no timeout tuned to computation would
have helped. The bug is the missing deadline, and these tests hold the line
on termination rather than on any particular duration.
"""

from __future__ import annotations

import threading
import time

import pytest

from src.services import factor_lab_service as service


@pytest.fixture(autouse=True)
def _clean():
    service.reset_for_tests()
    yield
    service.reset_for_tests()


def _drain(name: str = "mega30", limit: float = 10.0) -> dict:
    """Poll `run` the way the browser does, until it stops saying 'building'."""
    deadline = time.time() + limit
    payload = service.run(name)
    while payload.get("status") == "building" and time.time() < deadline:
        time.sleep(0.02)
        payload = service.run(name)
    return payload


def test_a_build_that_never_finishes_still_terminates(monkeypatch):
    """The exact incident: a build thread that blocks forever.

    Before the fix this polled `status: building` until the test timed out,
    which is precisely what the browser did for 48 minutes.
    """
    release = threading.Event()
    entered = threading.Event()

    def hang(*args, **kwargs):
        entered.set()
        release.wait()  # never set during the test
        return {}

    monkeypatch.setattr(service, "_build", hang)
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 0.4)

    try:
        payload = _drain(limit=8.0)
        assert entered.wait(2.0), "the build thread never started"
        assert payload["status"] == "error", (
            f"a permanently blocked build must resolve to an error, got {payload['status']!r}"
        )
        # The message has to be useful enough to act on.
        assert "estimators" in payload["error"] or "stalled" in payload["error"].lower()
    finally:
        release.set()


def test_the_stalled_error_names_the_stage_it_died_in(monkeypatch):
    reached = threading.Event()
    release = threading.Event()

    def hang_in_filings(universe_name, years, horizon, progress=None):
        service._set_stage(progress, "filings", 7, 30)  # progress is (key, token)
        reached.set()
        release.wait()
        return {}

    monkeypatch.setattr(service, "_build", hang_in_filings)
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 0.4)

    try:
        payload = _drain(limit=8.0)
        assert reached.wait(2.0)
        assert payload["status"] == "error"
        assert "filings" in payload["error"], payload["error"]
        # Someone reading this needs to know it is retryable, not permanent.
        assert payload.get("retryable") is True
    finally:
        release.set()


def test_a_stalled_job_does_not_poison_later_requests(monkeypatch):
    """After a stall is reported, asking again starts a fresh build.

    The failure mode being guarded: marking the job failed but leaving it in
    the registry, so every future request returns the same stale error and
    the universe becomes permanently unusable until the process restarts.
    """
    release = threading.Event()
    calls: list[str] = []

    def hang_once(universe_name, years, horizon, progress=None):
        calls.append(universe_name)
        if len(calls) == 1:
            release.wait()
            return {}
        return {"factors": [], "universe": {"name": universe_name}, "ok": True}

    monkeypatch.setattr(service, "_build", hang_once)
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 0.4)

    try:
        first = _drain(limit=8.0)
        assert first["status"] == "error"

        second = _drain(limit=8.0)
        assert second["status"] != "error", f"a retry stayed poisoned: {second}"
        assert len(calls) >= 2, "the retry never started a new build"
    finally:
        release.set()


def test_build_failure_surfaces_as_an_error_not_an_endless_build(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("vendor exploded")

    monkeypatch.setattr(service, "_build", explode)

    payload = _drain(limit=8.0)
    assert payload["status"] == "error"
    assert "vendor exploded" in payload["error"]


def test_a_thread_killed_by_a_base_exception_still_terminates(monkeypatch):
    """`except Exception` cannot see SystemExit, so the job would never be
    marked done and every poll would answer 'building' forever."""
    started = threading.Event()

    def die_hard(*args, **kwargs):
        started.set()
        raise SystemExit("interpreter going down")

    monkeypatch.setattr(service, "_build", die_hard)
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 0.4)

    payload = _drain(limit=8.0)
    assert started.wait(2.0)
    assert payload["status"] == "error", payload


def test_progress_is_monotonic_while_building(monkeypatch):
    """A stage may never go backwards — the UI ticks stages off as they pass."""
    release = threading.Event()
    seen: list[int] = []

    def walk(universe_name, years, horizon, progress=None):
        for stage in service.STAGES:
            service._set_stage(progress, stage)
            time.sleep(0.02)
        release.wait()
        return {}

    monkeypatch.setattr(service, "_build", walk)
    # Far beyond anything this test needs. With a short deadline the stall
    # path fires mid-poll, evicts the job and starts a *fresh* build at
    # stage 0 — correct behaviour, but a different property than the one
    # under test, and it made this fail only when the suite ran slowly
    # enough to cross the deadline.
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 60.0)

    try:
        payload = service.run("mega30")
        last = len(service.STAGES) - 1
        for _ in range(400):
            if payload.get("status") != "building":
                break
            seen.append(payload["stage_index"])
            if payload["stage_index"] == last:
                break  # one build's worth of progress is the whole question
            time.sleep(0.01)
            payload = service.run("mega30")
        assert seen, "never observed a building state"
        assert seen == sorted(seen), f"stage index went backwards: {seen}"
        assert seen[-1] == last, f"never reached the final stage: {seen}"
    finally:
        release.set()


def test_an_unknown_universe_answers_immediately_without_a_job():
    payload = service.run("does-not-exist")
    assert payload["status"] == "error"
    assert "unknown universe" in payload["error"]
    # It must not have spawned a build to discover something knowable up front.
    with service._jobs_lock:
        assert not service._jobs


def test_no_build_thread_survives_the_deadline_report(monkeypatch):
    """The abandoned worker must be a daemon, so it can never hold the
    process open after the request has been answered."""
    release = threading.Event()
    names: list[str] = []

    def hang(*args, **kwargs):
        names.extend(t.name for t in threading.enumerate() if "factor-lab" in t.name)
        release.wait()
        return {}

    monkeypatch.setattr(service, "_build", hang)
    monkeypatch.setattr(service, "BUILD_DEADLINE_SECONDS", 0.4)

    try:
        _drain(limit=8.0)
        workers = [t for t in threading.enumerate() if "factor-lab" in t.name]
        assert all(t.daemon for t in workers), "a non-daemon worker can outlive the process"
    finally:
        release.set()


# ── partial results ──────────────────────────────────────────────────────────
#
# A cold build spends ~52 s of vendor budget before any estimator runs.
# Throwing that away because redundancy raised is the wrong trade: the
# factors, portfolios and screen computed from the same panel are still
# correct and still worth showing.


def test_one_failing_estimator_does_not_destroy_the_lab(monkeypatch):
    import pandas as pd

    def boom(*args, **kwargs):
        raise ValueError("redundancy blew up")

    monkeypatch.setattr(service, "_redundancy_payload", boom)

    degraded: list[dict[str, str]] = []
    assert service._optional("redundancy", boom, degraded) is None
    assert degraded == [{"estimator": "redundancy", "reason": "ValueError: redundancy blew up"}]
    assert isinstance(pd.DataFrame(), pd.DataFrame)  # module import sanity


def test_a_successful_estimator_is_returned_untouched():
    degraded: list[dict[str, str]] = []
    assert service._optional("screen", lambda: {"rows": 3}, degraded) == {"rows": 3}
    assert degraded == []


def test_a_failed_estimator_is_never_reported_as_a_result():
    """The failure must be distinguishable from 'nothing to report'."""
    degraded: list[dict[str, str]] = []
    result = service._optional("attribution", lambda: (_ for _ in ()).throw(RuntimeError("nope")), degraded)
    assert result is None
    assert len(degraded) == 1
    assert degraded[0]["estimator"] == "attribution"
    assert "RuntimeError" in degraded[0]["reason"]


def test_an_abandoned_worker_cannot_rewrite_a_newer_builds_progress():
    """A stale writer must be a no-op, not a time machine.

    An abandoned build keeps calling `_set_stage` with the key it was
    started for. Before the token check that mutated whatever job now held
    that key, so a replacement build's stage was dragged back to whatever
    the dead one was doing — the client's progress visibly ran backwards.
    """
    service.reset_for_tests()
    key = "mega30:2.5:21"
    with service._jobs_lock:
        service._jobs[key] = {
            "started": time.time(), "stage": "returns",
            "stage_index": service.STAGES.index("returns"),
            "stage_started": time.time(), "timings": {},
            "done": False, "failed": False, "token": 99,
        }

    # The current build advances normally.
    service._set_stage((key, 99), "estimators")
    with service._jobs_lock:
        assert service._jobs[key]["stage"] == "estimators"

    # A worker from generation 98 — long since abandoned — tries to report.
    service._set_stage((key, 98), "prices", 2, 30)
    with service._jobs_lock:
        assert service._jobs[key]["stage"] == "estimators", "a stale worker moved the stage backwards"
        assert service._jobs[key]["stage_index"] == service.STAGES.index("estimators")
        assert service._jobs[key].get("progress_done", 0) != 2
