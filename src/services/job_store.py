"""Where background-job state lives, and why that is a deployment question.

A job registry in a module-level dict is correct for exactly one deployment
shape: a single process. The moment a deployment runs two workers, the dict
stops being a registry and becomes two registries that disagree. Worker A
starts a build and records it; worker B takes the next poll, finds nothing,
and starts a second build of the same thing. Both run, both write, and the
client watches a progress bar move backwards as the two take turns answering.

Nothing about that failure looks like a bug from inside a worker. Each one is
behaving correctly on the state it can see, every log line is reasonable, and
the only symptom is work done twice and a page that will not settle. It is
also invisible in development, because a laptop runs one process.

So the store is chosen by the deployment, not assumed by the code:

    REDIS_URL set      ->  RedisJobStore, shared across every worker
    otherwise          ->  InProcessJobStore, correct for one process

and `describe()` reports which is in use, so the diagnostics surface can say
"in-process registry with 4 workers configured" rather than leaving an
operator to discover it from a progress bar.

**A failure to reach Redis is not a reason to fall back.** Falling back would
silently reintroduce the split-registry bug in the one environment where it
does damage, and it would do so at the moment the system is already degraded.
The store reports itself unavailable instead, and a caller turns that into an
honest "this cannot be started right now".

The atomic primitive is `mutate`. Read-modify-write is what a job registry
actually does — advance a stage, claim a generation, record a failure — and
doing it non-atomically across workers is how two builds end up sharing one
token. In-process it is a lock; on Redis it is a WATCH/MULTI retry loop.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger("omnisignal.jobs")

#: How long a job record survives without being touched. Long enough that a
#: slow build is never evicted mid-flight, short enough that an abandoned one
#: does not hold a key for the life of the deployment.
DEFAULT_TTL_SECONDS = 3600.0

#: Bounded so a WATCH loop under contention cannot spin forever. Exceeding it
#: is reported rather than retried silently: persistent contention on one key
#: means two workers are fighting over one job, which is worth knowing.
MAX_MUTATE_ATTEMPTS = 8


class JobStoreUnavailable(RuntimeError):
    """The configured store could not be reached.

    Raised rather than returning None so a caller cannot mistake "the backend
    is down" for "no such job" — the second would start duplicate work.
    """


class JobStore(Protocol):
    def get(self, key: str) -> Optional[dict[str, Any]]: ...
    def put(self, key: str, value: dict[str, Any], ttl: Optional[float] = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> list[str]: ...
    def mutate(
        self,
        key: str,
        fn: Callable[[Optional[dict[str, Any]]], Optional[dict[str, Any]]],
        ttl: Optional[float] = None,
    ) -> Optional[dict[str, Any]]: ...
    def describe(self) -> dict[str, Any]: ...


class InProcessJobStore:
    """A dict behind a lock. Correct for one process, and only one.

    Expiry is checked on read rather than swept on a timer: a sweeper is
    another thread to get wrong, and a registry this size is cheap to filter.
    """

    kind = "in_process"

    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS) -> None:
        self._data: dict[str, tuple[dict[str, Any], float]] = {}
        self._lock = threading.RLock()
        self._ttl = ttl

    def _live(self, key: str, now: float) -> Optional[dict[str, Any]]:
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expires = entry
        if expires <= now:
            del self._data[key]
            return None
        return value

    def get(self, key: str) -> Optional[dict[str, Any]]:
        with self._lock:
            value = self._live(key, time.time())
            # A copy, so a caller mutating what it read cannot edit the
            # registry from outside the lock — the one way an in-process store
            # can be less safe than the networked one it stands in for.
            return dict(value) if value is not None else None

    def put(self, key: str, value: dict[str, Any], ttl: Optional[float] = None) -> None:
        with self._lock:
            self._data[key] = (dict(value), time.time() + (ttl if ttl is not None else self._ttl))

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def keys(self) -> list[str]:
        now = time.time()
        with self._lock:
            return sorted(k for k in list(self._data) if self._live(k, now) is not None)

    def mutate(
        self,
        key: str,
        fn: Callable[[Optional[dict[str, Any]]], Optional[dict[str, Any]]],
        ttl: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        with self._lock:
            current = self._live(key, time.time())
            updated = fn(dict(current) if current is not None else None)
            if updated is None:
                self._data.pop(key, None)
                return None
            self._data[key] = (
                dict(updated), time.time() + (ttl if ttl is not None else self._ttl)
            )
            return dict(updated)

    def describe(self) -> dict[str, Any]:
        with self._lock:
            count = len(self._data)
        return {
            "kind": self.kind,
            "shared_across_workers": False,
            "available": True,
            "jobs": count,
            "note": (
                "Job state lives in this process only. Correct for a single-worker "
                "deployment; with more than one worker each holds its own registry "
                "and the same job can be started more than once."
            ),
        }

    def reset(self) -> None:
        """Drop everything. For tests and for `reset_for_tests` callers."""
        with self._lock:
            self._data.clear()


class RedisJobStore:
    """One registry, shared by every worker.

    `redis` is imported lazily so a deployment that does not use it does not
    need the package installed. The client is created once and reused; a
    per-call client would open a connection per poll.
    """

    kind = "redis"

    def __init__(self, url: str, ttl: float = DEFAULT_TTL_SECONDS, prefix: str = "omnisignal:job:") -> None:
        self._url = url
        self._ttl = ttl
        self._prefix = prefix
        self._client: Any = None

    def _redis(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import redis  # noqa: PLC0415 — lazy by design
        except ImportError as exc:  # pragma: no cover - depends on the deployment
            raise JobStoreUnavailable(
                "REDIS_URL is set but the redis package is not installed"
            ) from exc
        try:
            client = redis.Redis.from_url(
                self._url, decode_responses=True,
                socket_connect_timeout=2.0, socket_timeout=2.0,
            )
            client.ping()
        except Exception as exc:  # noqa: BLE001 — any connection fault is the same answer
            raise JobStoreUnavailable(f"the job store could not be reached: {exc}") from exc
        self._client = client
        return client

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Optional[dict[str, Any]]:
        raw = self._redis().get(self._key(key))
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            # A value written by an older schema or a different service. Not
            # a job, so not returned as one.
            logger.warning("discarding unreadable job record at %s", key)
            return None
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any], ttl: Optional[float] = None) -> None:
        self._redis().set(
            self._key(key), json.dumps(value, default=str),
            ex=int(ttl if ttl is not None else self._ttl),
        )

    def delete(self, key: str) -> None:
        self._redis().delete(self._key(key))

    def keys(self) -> list[str]:
        # SCAN rather than KEYS: KEYS blocks the server for the whole scan,
        # which on a shared instance is everyone else's latency.
        client = self._redis()
        found: list[str] = []
        cursor = 0
        while True:
            cursor, batch = client.scan(cursor=cursor, match=f"{self._prefix}*", count=100)
            found.extend(str(k)[len(self._prefix):] for k in batch)
            if cursor == 0:
                break
        return sorted(found)

    def mutate(
        self,
        key: str,
        fn: Callable[[Optional[dict[str, Any]]], Optional[dict[str, Any]]],
        ttl: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Read-modify-write, atomic against other workers.

        WATCH the key, compute outside the transaction, then MULTI/EXEC. If
        another worker wrote in between, EXEC fails and the whole thing runs
        again on the new value — which is the point: the second worker's
        function sees the first worker's result rather than overwriting it.
        """
        client = self._redis()
        full = self._key(key)
        expiry = int(ttl if ttl is not None else self._ttl)

        for attempt in range(MAX_MUTATE_ATTEMPTS):
            try:
                with client.pipeline() as pipe:
                    pipe.watch(full)
                    raw = pipe.get(full)
                    current: Optional[dict[str, Any]] = None
                    if raw is not None:
                        try:
                            parsed = json.loads(raw)
                            current = parsed if isinstance(parsed, dict) else None
                        except ValueError:
                            current = None

                    updated = fn(dict(current) if current is not None else None)

                    pipe.multi()
                    if updated is None:
                        pipe.delete(full)
                    else:
                        pipe.set(full, json.dumps(updated, default=str), ex=expiry)
                    pipe.execute()
                    return updated
            except JobStoreUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001
                # redis.WatchError is the expected one and means "try again".
                # Anything else on the last attempt is a real failure.
                if type(exc).__name__ != "WatchError":
                    raise JobStoreUnavailable(f"job store write failed: {exc}") from exc
                logger.debug("job %s changed under a write, retrying (%d)", key, attempt + 1)

        raise JobStoreUnavailable(
            f"job {key} was rewritten by another worker {MAX_MUTATE_ATTEMPTS} times; "
            "two workers are contending for one job"
        )

    def describe(self) -> dict[str, Any]:
        try:
            count = len(self.keys())
        except JobStoreUnavailable as exc:
            return {
                "kind": self.kind,
                "shared_across_workers": True,
                "available": False,
                "jobs": None,
                "note": str(exc),
            }
        return {
            "kind": self.kind,
            "shared_across_workers": True,
            "available": True,
            "jobs": count,
            "note": "Job state is shared, so every worker sees the same registry.",
        }


_store: Optional[JobStore] = None
_store_lock = threading.Lock()


def get_store() -> JobStore:
    """The store this deployment is configured for, created once."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            url = os.getenv("REDIS_URL", "").strip()
            _store = RedisJobStore(url) if url else InProcessJobStore()
    return _store


def reset_store_for_tests() -> None:
    """Drop the cached store so the next call re-reads the environment."""
    global _store
    with _store_lock:
        if isinstance(_store, InProcessJobStore):
            _store.reset()
        _store = None


def describe() -> dict[str, Any]:
    """What the diagnostics surface reports, including the hazard.

    The warning is the reason this function exists. A production deployment
    running several workers on an in-process registry is the split-registry
    bug, live, and nothing else in the system will say so.
    """
    from src.services import deployment

    store = get_store()
    try:
        detail = store.describe()
    except JobStoreUnavailable as exc:
        detail = {
            "kind": getattr(store, "kind", "unknown"),
            "available": False, "shared_across_workers": None, "jobs": None,
            "note": str(exc),
        }

    workers = _configured_workers()
    detail["configured_workers"] = workers
    detail["environment"] = deployment.environment_name()

    warning: Optional[str] = None
    if not detail.get("shared_across_workers"):
        if workers is not None and workers > 1:
            warning = (
                f"This deployment runs {workers} workers on an in-process job registry. "
                "Each worker holds its own, so the same background job can be started "
                "more than once and a client polling across workers sees progress move "
                "backwards. Set REDIS_URL to share the registry."
            )
        elif deployment.is_production() and workers is None:
            warning = (
                "Production is using an in-process job registry and the worker count "
                "could not be determined. If more than one worker is running, background "
                "jobs are duplicated across them. Set REDIS_URL to share the registry."
            )
    detail["warning"] = warning
    return detail


def _configured_workers() -> Optional[int]:
    """How many workers this deployment says it runs, or None if it does not.

    None is not 1. A deployment that does not state a worker count has not
    told us it is single-process, and reporting it as safe would be the
    guess this module exists to avoid.
    """
    for name in ("WEB_CONCURRENCY", "GUNICORN_WORKERS", "UVICORN_WORKERS"):
        raw = os.getenv(name, "").strip()
        if raw:
            try:
                value = int(raw)
            except ValueError:
                continue
            if value > 0:
                return value
    return None
