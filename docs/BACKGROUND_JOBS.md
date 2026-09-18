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

## Factor Lab lifecycle

Factor Lab now uses the configured `JobStore` for both its job record and its
completed payload. A record carries:

- a unique attempt token and monotonically increasing generation;
- the owning worker id;
- `running`, `success`, `failed`, `abandoned`, or `cancelled` state;
- stage, progress, timings, start/finish times, and a heartbeat;
- the token-specific shared-result key after success.

Claim and reclaim are atomic `mutate` operations. Only the request whose token
wins the claim starts compute. A separate heartbeat thread updates liveness
even while the build is blocked inside one vendor call. If the owner process
disappears, another worker reclaims the job after `STALE_OWNER_SECONDS`; the
old token can no longer advance a stage, record failure, or publish a result.

The full build deadline remains a different guard. A worker can be alive and
still stuck, so a poll beyond the deadline marks that attempt `abandoned` and
returns a retryable error. The next poll claims a fresh attempt. Failed work is
held for a short cooldown so a polling browser cannot start a new deterministic
failure every 1.5 seconds.

Results use a token-specific key. The worker writes the result first and only
then atomically points the successful job record at it. A late worker whose
ownership was revoked can leave only an unreferenced value that expires; it
cannot replace the current result.

## What is verified

The in-process store is tested directly, including under eight threads
contending on one key — the non-atomic version loses increments, which in
production is a stage counter going backwards.

The Redis store is tested against a fake implementing `GET`/`SET`/`DELETE`/
`SCAN` and `WATCH`/`MULTI`/`EXEC` with real optimistic-locking semantics,
including the case where another worker writes inside the window and the retry
must see the new value.

The Factor Lab lifecycle is additionally tested for stale-owner reclaim, fresh
owner joining, token isolation, monotonic progress, bounded threads, deadline
abandonment, failure cooldown and successful result reuse.

The fake Redis tests reproduce optimistic locking and retry semantics. A real
Redis verification result belongs in the final completion audit for the build
that was actually tested; it must not be inferred from the fake.

**Real-server result, run on 2026-09-18** (`redis 8.10.2`, ephemeral local
instance, no persistence): `REDIS_URL` correctly selected `RedisJobStore`;
`put`/`get`/`delete` round-tripped; and — the property that actually matters —
eight real Python threads hammering one key through `mutate()` with no delay
between attempts never produced a torn or partially-written record. Every
successful write was a complete, self-consistent dict, exactly as `WATCH`/
`MULTI`/`EXEC` promises.

Under that same extreme, artificial load (no realistic Factor Lab call
produces 8 threads in a tight loop on one key — the heartbeat is one thread
per job at a 5s cadence, and cross-worker contention on one exact
`(universe, years, horizon)` key at the same instant is the rare case, not the
steady state) most callers exhausted `MAX_MUTATE_ATTEMPTS` and received
`JobStoreUnavailable`, which `run()` turns into `{"status": "error",
"retryable": True}` rather than a lost update or a 500. That is the bound
working as designed — "worth reporting rather than retrying forever" — and it
is now confirmed against a real server rather than assumed from the fake.

Not run: a two-process test (two separate OS processes, or two Render
workers) claiming the same key against one shared real Redis. The in-thread
test above exercises the same `mutate` code path a second process would use,
but a genuinely separate process is the check `RENDER_SETUP.md`'s
verification step 5 still asks for the first time `REDIS_URL` is configured
in production.
