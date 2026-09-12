"""The background-job registry, and the deployment question underneath it.

The in-process store is exercised directly, including under real thread
contention. The Redis store is exercised against a fake that implements the
commands it uses — GET/SET/DELETE/SCAN and, importantly, WATCH/MULTI/EXEC with
real optimistic-locking semantics, because the retry loop is the only part of
that class where a mistake costs correctness rather than an error message.

**What is not checked here:** the Redis store against a real server. This
environment has no Redis and the package is not installed, so the wire format,
the connection handling and the client's own WatchError type are unverified.
The fake reproduces the semantics the code depends on, which is strictly better
than asserting nothing, and weaker than the real thing. That check is owed the
first time a deployment sets REDIS_URL.
"""

from __future__ import annotations

import json
import threading

import pytest

from src.services import job_store
from src.services.job_store import (
    InProcessJobStore, JobStoreUnavailable, RedisJobStore,
)


@pytest.fixture(autouse=True)
def _clean_store(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("GUNICORN_WORKERS", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    job_store.reset_store_for_tests()
    yield
    job_store.reset_store_for_tests()


# ── the in-process store ─────────────────────────────────────────────────────

def test_a_stored_job_comes_back():
    store = InProcessJobStore()
    store.put("a", {"stage": "loading", "done": 1})
    assert store.get("a") == {"stage": "loading", "done": 1}


def test_reading_a_job_cannot_edit_the_registry():
    """The one way an in-process store can be less safe than the networked one
    it stands in for: a caller mutating what it read, outside the lock."""
    store = InProcessJobStore()
    store.put("a", {"stage": "loading"})
    borrowed = store.get("a")
    borrowed["stage"] = "tampered"
    assert store.get("a") == {"stage": "loading"}


def test_writing_a_job_copies_it_too():
    store = InProcessJobStore()
    payload = {"stage": "loading"}
    store.put("a", payload)
    payload["stage"] = "tampered"
    assert store.get("a") == {"stage": "loading"}


def test_a_missing_job_is_none_not_an_error():
    assert InProcessJobStore().get("nothing") is None


def test_an_expired_job_is_gone():
    store = InProcessJobStore(ttl=0.0)
    store.put("a", {"stage": "loading"})
    assert store.get("a") is None
    assert store.keys() == []


def test_a_per_call_ttl_overrides_the_default():
    store = InProcessJobStore(ttl=0.0)
    store.put("lives", {"stage": "x"}, ttl=60.0)
    assert store.get("lives") is not None


def test_mutate_returning_none_deletes():
    store = InProcessJobStore()
    store.put("a", {"stage": "loading"})
    assert store.mutate("a", lambda _: None) is None
    assert store.get("a") is None


def test_mutate_sees_the_current_value():
    store = InProcessJobStore()
    store.put("a", {"count": 1})

    def bump(current):
        assert current == {"count": 1}
        return {"count": current["count"] + 1}

    assert store.mutate("a", bump) == {"count": 2}


def test_mutate_on_a_missing_key_is_handed_none():
    store = InProcessJobStore()
    seen: list = []

    def create(current):
        seen.append(current)
        return {"created": True}

    assert store.mutate("new", create) == {"created": True}
    assert seen == [None]


def test_concurrent_mutations_do_not_lose_writes():
    """Read-modify-write is what a job registry does. Under threads, a
    non-atomic version loses increments — the symptom in production being a
    stage counter that goes backwards."""
    store = InProcessJobStore()
    store.put("counter", {"n": 0})

    def bump() -> None:
        for _ in range(200):
            store.mutate("counter", lambda c: {"n": (c or {"n": 0})["n"] + 1})

    threads = [threading.Thread(target=bump) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert store.get("counter") == {"n": 1600}


def test_keys_lists_live_jobs_only():
    store = InProcessJobStore()
    store.put("live", {"x": 1}, ttl=60.0)
    store.put("dead", {"x": 1}, ttl=0.0)
    assert store.keys() == ["live"]


# ── selection ────────────────────────────────────────────────────────────────

def test_without_a_url_the_store_is_in_process():
    assert isinstance(job_store.get_store(), InProcessJobStore)


def test_with_a_url_the_store_is_redis(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    job_store.reset_store_for_tests()
    assert isinstance(job_store.get_store(), RedisJobStore)


def test_the_store_is_created_once():
    assert job_store.get_store() is job_store.get_store()


# ── the hazard this module exists to report ─────────────────────────────────

def test_several_workers_on_an_in_process_registry_is_reported():
    """The split-registry bug, stated before an operator finds it in a
    progress bar."""
    import os

    os.environ["WEB_CONCURRENCY"] = "4"
    try:
        job_store.reset_store_for_tests()
        detail = job_store.describe()
    finally:
        os.environ.pop("WEB_CONCURRENCY", None)

    assert detail["shared_across_workers"] is False
    assert detail["configured_workers"] == 4
    assert detail["warning"]
    assert "started" in detail["warning"] and "REDIS_URL" in detail["warning"]


def test_a_single_worker_deployment_is_not_warned_about():
    import os

    os.environ["WEB_CONCURRENCY"] = "1"
    try:
        job_store.reset_store_for_tests()
        detail = job_store.describe()
    finally:
        os.environ.pop("WEB_CONCURRENCY", None)
    assert detail["warning"] is None


def test_production_with_an_unknown_worker_count_is_warned_about():
    """None is not one. A deployment that has not said how many workers it runs
    has not told us it is safe, and reporting it as safe would be a guess."""
    import os

    os.environ["APP_ENV"] = "production"
    try:
        job_store.reset_store_for_tests()
        detail = job_store.describe()
    finally:
        os.environ.pop("APP_ENV", None)

    assert detail["configured_workers"] is None
    assert detail["warning"] is not None
    assert "could not be determined" in detail["warning"]


def test_development_with_an_unknown_worker_count_is_not_warned_about():
    detail = job_store.describe()
    assert detail["environment"] == "development"
    assert detail["warning"] is None


def test_a_zero_or_unparseable_worker_count_is_not_treated_as_a_number():
    import os

    for bad in ("0", "", "lots", "-2"):
        os.environ["WEB_CONCURRENCY"] = bad
        try:
            assert job_store._configured_workers() is None, bad
        finally:
            os.environ.pop("WEB_CONCURRENCY", None)


# ── the Redis store, against a fake with real WATCH semantics ───────────────

class FakeRedis:
    """Enough Redis to exercise the store, with honest optimistic locking.

    WATCH records the watched key's current version; EXEC fails if it changed.
    That is the behaviour the retry loop depends on, and the only part of the
    class where being wrong costs correctness rather than an error message.
    """

    class WatchError(Exception):
        pass

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        #: Called once before each EXEC, so a test can simulate another worker
        #: writing inside the window.
        self.interleave = None
        self.pings = 0

    def ping(self) -> bool:
        self.pings += 1
        return True

    def _bump(self, key: str) -> None:
        self.versions[key] = self.versions.get(key, 0) + 1

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex=None) -> None:
        self.data[key] = value
        self._bump(key)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.data.pop(key, None)
            self._bump(key)

    def scan(self, cursor=0, match="", count=100):
        prefix = match.rstrip("*")
        return 0, [k for k in sorted(self.data) if k.startswith(prefix)]

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._r = redis
        self._watched: dict[str, int] = {}
        self._queued: list = []
        self._buffering = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def watch(self, key: str) -> None:
        self._watched[key] = self._r.versions.get(key, 0)

    def get(self, key: str):
        return self._r.get(key)

    def multi(self) -> None:
        self._buffering = True

    def set(self, key: str, value: str, ex=None) -> None:
        self._queued.append(("set", key, value))

    def delete(self, key: str) -> None:
        self._queued.append(("delete", key))

    def execute(self):
        if self._r.interleave is not None:
            hook, self._r.interleave = self._r.interleave, None
            hook()
        for key, version in self._watched.items():
            if self._r.versions.get(key, 0) != version:
                raise FakeRedis.WatchError("the watched key changed")
        for op in self._queued:
            if op[0] == "set":
                self._r.set(op[1], op[2])
            else:
                self._r.delete(op[1])
        self._queued.clear()
        return []


def _redis_store(fake: FakeRedis) -> RedisJobStore:
    store = RedisJobStore("redis://fake/0")
    store._client = fake
    return store


def test_redis_round_trips_a_job():
    fake = FakeRedis()
    store = _redis_store(fake)
    store.put("a", {"stage": "loading"})
    assert store.get("a") == {"stage": "loading"}
    assert "omnisignal:job:a" in fake.data, "the key was stored without its prefix"


def test_redis_returns_none_for_a_missing_job():
    assert _redis_store(FakeRedis()).get("nothing") is None


def test_redis_discards_an_unreadable_record():
    """A value written by another service or an older schema is not a job and
    must not be returned as one."""
    fake = FakeRedis()
    fake.data["omnisignal:job:a"] = "not json at all"
    assert _redis_store(fake).get("a") is None


def test_redis_discards_a_record_that_is_not_an_object():
    fake = FakeRedis()
    fake.data["omnisignal:job:a"] = json.dumps([1, 2, 3])
    assert _redis_store(fake).get("a") is None


def test_redis_mutate_retries_when_another_worker_writes_first():
    """The property the whole class is for: worker B's function must run again
    on worker A's result rather than overwriting it."""
    fake = FakeRedis()
    store = _redis_store(fake)
    store.put("counter", {"n": 0})

    def other_worker() -> None:
        fake.set("omnisignal:job:counter", json.dumps({"n": 100}))

    fake.interleave = other_worker
    seen: list = []

    def bump(current):
        seen.append(dict(current or {}))
        return {"n": (current or {"n": 0})["n"] + 1}

    result = store.mutate("counter", bump)

    assert seen == [{"n": 0}, {"n": 100}], "the retry did not see the other write"
    assert result == {"n": 101}, "the other worker's write was overwritten"


def test_redis_mutate_gives_up_rather_than_spinning():
    """Persistent contention means two workers are fighting over one job, which
    is worth reporting rather than retrying forever."""
    fake = FakeRedis()
    store = _redis_store(fake)
    store.put("hot", {"n": 0})

    bumps = {"n": 0}

    def always_interfere() -> None:
        bumps["n"] += 1
        fake.set("omnisignal:job:hot", json.dumps({"n": bumps["n"]}))
        fake.interleave = always_interfere

    fake.interleave = always_interfere

    with pytest.raises(JobStoreUnavailable, match="contending"):
        store.mutate("hot", lambda c: {"n": (c or {"n": 0})["n"] + 1})


def test_redis_mutate_can_delete():
    fake = FakeRedis()
    store = _redis_store(fake)
    store.put("a", {"stage": "x"})
    assert store.mutate("a", lambda _: None) is None
    assert store.get("a") is None


def test_redis_keys_strips_the_prefix():
    fake = FakeRedis()
    store = _redis_store(fake)
    store.put("one", {"x": 1})
    store.put("two", {"x": 2})
    assert store.keys() == ["one", "two"]


def test_an_unreachable_redis_does_not_fall_back_to_a_split_registry():
    """Falling back would reintroduce the duplicate-job bug in the one
    environment where it does damage, at the moment the system is already
    degraded. It reports itself unavailable instead."""
    store = RedisJobStore("redis://nowhere:6379/0")

    def refuse(*a, **k):
        raise OSError("connection refused")

    store._client = None
    import sys
    import types

    module = types.ModuleType("redis")
    module.Redis = types.SimpleNamespace(from_url=refuse)
    sys.modules["redis"] = module
    try:
        with pytest.raises(JobStoreUnavailable, match="could not be reached"):
            store.get("a")
        detail = store.describe()
    finally:
        sys.modules.pop("redis", None)

    assert detail["available"] is False
    assert detail["kind"] == "redis"
