# Background jobs

> A job registry in a module-level dict is correct for exactly one deployment
> shape: a single process.

## The failure it guards against

The factor-lab panel build takes minutes, so it runs on a worker thread and the
client polls. The registry that connects the two is a dict in
`src/services/factor_lab_service.py`.

With one process that is right. With two workers it is not a registry any more,
it is two registries that disagree:

1. Worker A receives the first request, starts a build, records it.
2. Worker B receives the next poll, finds nothing, starts a **second** build of
   the same universe.
3. Both run. Both write. The client's progress bar moves backwards as the two
   take turns answering.

Nothing about this looks like a bug from inside a worker. Each behaves
correctly on the state it can see, every log line is reasonable, and the only
symptoms are work done twice and a page that will not settle. It is also
invisible in development, because a laptop runs one process.

## The store

`src/services/job_store.py` makes the choice a deployment's rather than the
code's:

| Environment | Store | Shared across workers |
|---|---|---|
| `REDIS_URL` set | `RedisJobStore` | yes |
| otherwise | `InProcessJobStore` | no |

Both satisfy one protocol: `get`, `put`, `delete`, `keys`, `mutate`,
`describe`.

`mutate` is the primitive that matters. Read-modify-write is what a job
registry actually does — advance a stage, claim a generation, record a
failure — and doing it non-atomically across workers is how two builds end up
sharing one token. In-process it is a lock; on Redis it is a `WATCH`/`MULTI`
retry loop, so a worker whose write loses the race **re-runs its function on
the winner's value** rather than overwriting it. The loop is bounded: persistent
contention on one key means two workers are fighting over one job, which is
worth reporting rather than retrying forever.

### An unreachable Redis does not fall back

Falling back to the in-process store would silently reintroduce the
split-registry bug in the one environment where it does damage, at the moment
the system is already degraded. The store reports itself unavailable instead,
and a caller turns that into an honest refusal.

### None is not one

`_configured_workers()` returns `None` when no worker count is declared. A
deployment that has not said how many workers it runs has not told us it is
single-process, so production with an unknown count is warned about rather than
assumed safe.

## What an operator sees

`/api/admin/diagnostics` reports `background_jobs`, including a `warning` when
the deployment's shape is the hazard above:

```
This deployment runs 4 workers on an in-process job registry. Each worker holds
its own, so the same background job can be started more than once and a client
polling across workers sees progress move backwards. Set REDIS_URL to share the
registry.
```

That warning is the point. There is no other way to discover this condition:
the symptom does not point at its cause.

## What is wired, and what is not

**Wired.** The abstraction, both adapters, and the diagnostics warning.

**Not wired: `factor_lab_service` still uses its own dict.** This is deliberate,
and the reason is specific rather than a shortage of time.

Sharing the *registry* without also distributing the *compute* produces a new
failure mode that is worse than the one it fixes. The build runs on a thread in
whichever process started it. If that worker restarts mid-build, its job record
survives in Redis marked not-done, and another worker polling it waits on a
build that no longer exists — up to `BUILD_DEADLINE_SECONDS` before the stall
logic evicts it. Today, that second worker would simply start its own build and
answer in minutes. So the half-refactor trades "work done twice" for "several
minutes waiting on a dead job", which is a worse trade for a reader.

The complete fix needs the owning worker to prove it is still alive: a
heartbeat written as each stage advances, and a record whose heartbeat has gone
stale reclaimed promptly rather than after the full build deadline. `mutate` is
the primitive that makes that safe to implement, which is why it exists in this
shape. That work is outstanding and is not claimed here.

## What is verified

The in-process store is tested directly, including under eight threads
contending on one key — the non-atomic version loses increments, which in
production is a stage counter going backwards.

The Redis store is tested against a fake implementing `GET`/`SET`/`DELETE`/
`SCAN` and `WATCH`/`MULTI`/`EXEC` with real optimistic-locking semantics,
including the case where another worker writes inside the window and the retry
must see the new value.

**Not verified: the Redis store against a real server.** This environment has
no Redis and the package is not installed, so the wire format, the connection
handling and the client's own `WatchError` type are unexercised. The fake
reproduces the semantics the code depends on, which is better than asserting
nothing and weaker than the real thing. That check is owed the first time a
deployment sets `REDIS_URL`.
