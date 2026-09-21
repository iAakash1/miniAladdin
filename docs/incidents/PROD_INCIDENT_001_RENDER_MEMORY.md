# PROD-INCIDENT-001 — Render backend memory exhaustion

Status: remediated in code; production verification pending deployment

Service: `miniAladdin` (URL slug `minialaddin-d8oe`)

Incident time: 2026-09-20 21:46:34 IST / 16:16:34 UTC

Platform limit: 512 MB RAM

## Confirmed facts

Render terminated the instance with:

> Ran out of memory (used over 512MB) while running your code.

The dashboard-managed service starts with:

```text
uvicorn api.index:app --host 0.0.0.0 --port $PORT
```

There is no `--workers` flag and the observed process was a single Python
process. The tracked `render.yaml` declares only
`minialaddin-quant-inference`; it does not configure this primary backend.
Creating another service is not a repair for that drift.

The last completed application work before the old process disappeared was a
cold Factor Lab `mega30` build:

```text
sec-facts: 30 items, 17 successful, 13 failed, 30.38s
panel: SEC facts loaded for 17/30 symbols
```

This puts the failure in the interval where many SEC companyfacts payloads and
the subsequent panel construction could coexist in memory.

## Classification

The confirmed failure is `REQUEST_COMPUTE_MEMORY_PRESSURE`.

The high-confidence immediate trigger is a cold Factor Lab / `mega30`
point-in-time panel build inside the 512 MB web process. The evidence does not
establish a persistent memory leak. Render does not expose historical memory
charts on the current tier, so the exact incident-time baseline, peak curve,
and retained memory after the request are unknown.

Remaining hypotheses after the incident evidence:

| Hypothesis | Finding |
|---|---|
| Baseline footprint too close to 512 MB | Contributor, but not sufficient alone in local measurements. |
| Request-specific spike | Strongly supported by the Factor Lab log boundary. |
| Concurrent provider fan-out | Plausible contributor; now bounded process-wide. |
| Multiple Python workers | Not supported; actual start command launches one worker. |
| Persistent leak | Not demonstrated by bounded local soak tests. |

## Remediation

The production request path no longer builds a historical panel. `/api/factors`
only reads a size-bounded, hash-verified immutable artifact. An operator builds
that artifact explicitly outside the web process:

```bash
python -m scripts.factor_lab build --universe mega30 --years 2.5 --horizon 21
```

Additional controls:

- one fixed, process-wide provider executor (default eight workers), including
  dynamic submission so timed-out calls cannot create successive thread pools;
- bounded in-process caches;
- cold-request single-flight for Explore recommendations;
- lazy `yfinance` import, keeping it out of the baseline worker when another
  market-data provider answers;
- compact Model Lab API projection while the SQLite ledger remains the complete
  provenance source;
- registry-status caching invalidated by registry file metadata;
- `/proc/self/status`, `resource`, and cgroup memory diagnostics in startup,
  request logs, and system health;
- guaranteed observability-context cleanup through a middleware `finally` block.

The cleanup correction closes a lifecycle defect. It is not claimed as the OOM
root cause because profiling did not demonstrate retained request contexts.

## Measured local evidence

Measurements use one macOS Python 3.12 process and are comparative, not a
prediction of Render's Linux allocator. No external provider call was made by
the endpoint and soak fixtures.

| Measurement | Before | Peak/after | Delta |
|---|---:|---:|---:|
| API import/startup after lazy `yfinance` | 14.56 MB fresh | 135.50 MB startup | +120.94 MB |
| Prior API startup | — | about 149–150 MB | about 14 MB higher |
| `/api/health`, 1,000 requests | 148.36 MB warmed | 148.64 / 148.56 MB | +0.20 MB |
| `/api/quant/status`, prior 600-request soak | 154.81 MB warmed | 180.95 / 180.84 MB | +26.03 MB |
| `/api/quant/status`, remediated 600-request soak | 143.28 MB warmed | 143.62 / 143.62 MB | +0.34 MB |
| `/api/quant/status`, final repeat (same bound) | 142.62 MB warmed | 143.41 / 143.41 MB | +0.79 MB |
| `/api/factors`, 600 artifact-only requests | 146.78 MB warmed | 147.66 / 147.58 MB | +0.80 MB |
| fixture research endpoint, 300 requests | 147.97 MB warmed | 148.19 / 148.11 MB | +0.14 MB |
| `/api/quant/model-lab`, prior response | — | 1,420,540 bytes; +24.92 MB | — |
| `/api/quant/model-lab`, compact response | — | 85,451 bytes; +1.40 MB | — |

The new quant-status series plateaued after its first lazy import. Its two
steady-state runs grew 0.057 and 0.132 MB per 100 requests, versus 4.338 MB per
100 before the registry read was cached. These results do not prove the absence
of every long-horizon leak; they do falsify the earlier endpoint-specific
growth at this test bound.

## Dependency findings

Independent clean-interpreter deltas were: pandas +80.58 MB, yfinance +103.94
MB, Supabase +42.92 MB, pyarrow +32.18 MB, NumPy +17.93 MB, SciPy +20.57 MB,
cryptography +0.13 MB, and LangGraph +0.20 MB. These deltas overlap and must not
be added together.

Pandas remains core runtime infrastructure. PyArrow remains required for
committed quant/portfolio artifacts. SciPy remains required by runtime
portfolio optimisation. Supabase and LangGraph are lazy on health paths.
Yfinance was the actionable eager import and is now lazy.

## Related production defects and security actions

`PATCH /api/preferences` also exposed `PROD-DEFECT-002`: Supabase returned
`PGRST204` because `experience_mode` was absent from the schema cache. The API
now returns typed `PERSISTENCE_SCHEMA_DRIFT`, and migration
`20260921000000_repair_experience_mode.sql` repairs the column and constraint.

An Alpha Vantage credential appeared in historical provider logs. Log output is
now sanitized by value and by secret-like query parameter. On 2026-09-21 the
operator installed a different working `ALPHA_VANTAGE_KEY` in Render. The old
exposed key must still be revoked at Alpha Vantage; replacing the Render value
does not revoke the old credential.

## Deployment verification gate

After the remediation commit deploys to the existing service:

1. Apply the Supabase migration and verify `PATCH /api/preferences`.
2. Confirm `/api/health` reports the deployed commit and a memory limit of
   approximately 512 MB.
3. Confirm `/api/system/health` reports process memory and provider concurrency.
4. Exercise health, quant status, Model Lab, Factor Lab, and one normal research
   request while watching the new RSS log fields.
5. Confirm Factor Lab returns an artifact state and never starts a build.
6. Confirm no credential value appears in application logs.
7. Revoke the formerly exposed Alpha Vantage key.

A larger Render instance, if availability requires it before this verification,
is `TEMPORARY_CAPACITY_MITIGATION`, not root-cause resolution.
