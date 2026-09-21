# Render setup

This repository is connected to existing Render services. Do not create a
second backend or inference service to apply these settings.

## Existing services

| Service | Purpose | Source | Start command |
|---|---|---|---|
| `miniAladdin` (`minialaddin-d8oe` URL slug) | Primary FastAPI backend | repository root | `uvicorn api.index:app --host 0.0.0.0 --port $PORT` |
| `minialaddin-quant-inference` | Read-only EXP-006 research inference | `render.yaml` | `uvicorn services.inference.app:app --host 0.0.0.0 --port $PORT` |

`render.yaml` declares only the existing inference service. The primary
backend remains configured in the Render dashboard; adding it to the blueprint
without first importing the existing service would create a duplicate.

## Primary backend environment names

Set values in the existing backend service. Names are exact; values are never
committed.

Required platform and identity:

| Name | Purpose |
|---|---|
| `APP_ENV` | Set to `production` so fail-closed production checks engage. |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins. Include `https://mini-aladding.vercel.app` and the active Vercel alias while the alias redirect exists. |
| `CLERK_ISSUER` | Clerk token issuer. |
| `CLERK_JWKS_URL` | Clerk signing-key endpoint. |
| `SUPABASE_URL` | Persistence project URL. |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only persistence credential. |

Core data and explanation providers:

| Name | Purpose |
|---|---|
| `FRED_API_KEY` | Macro regime inputs. |
| `ALPHA_VANTAGE_KEY` | Fundamentals and market-data fallback. |
| `NEWSAPI_KEY` | News provider. |
| `GROQ_API_KEY` | Optional generated explanation layer. |
| `LLM_MODEL` | Optional model override used by the configured explanation adapter. |

Additional provider credentials are optional and individually detected:
`POLYGON_API_KEY`, `FINNHUB_API_KEY`, `TWELVEDATA_API_KEY`, `FMP_API_KEY`,
`MARKETSTACK_API_KEY`, `MASSIVE_API_KEY`, `TIINGO_API_KEY`, `GNEWS_API_KEY`,
`TAVILY_API_KEY`, `EXA_API_KEY`, `BRAVE_API_KEY`, `APIFY_API_TOKEN`,
`GEMINI_API_KEY`, `LOGO_DEV_PUBLISHABLE_KEY`, `LOGO_DEV_SECRET_KEY`,
`PEXELS_API_KEY`, and `UNSPLASH_ACCESS_KEY`.

Research and background work:

| Name | Purpose |
|---|---|
| `QUANT_INFERENCE_URL` | Base URL of the existing inference service. |
| `QUANT_INFERENCE_TIMEOUT` | Optional bounded call timeout. |
| `QUANT_REGISTRY_ROOT` | Optional model-registry location override. |
| `QUANT_ARTIFACT_ROOT` | Optional experiment-artifact location override. |
| `QUANT_DATA_ROOT` | Optional research dataset location override. |
| `FACTOR_LAB_ARTIFACT_ROOT` | Optional location of offline-built, immutable Factor Lab artifacts. The web process never builds them. |
| `PROVIDER_CONCURRENCY_LIMIT` | Fixed process-wide provider worker budget. Defaults to `8`; keep bounded on the 512 MB service. |
| `MEMORY_LIMIT_MB` | Optional explicit diagnostics override. Normally cgroups report the Render limit automatically. |
| `WEB_CONCURRENCY` | Worker count reported by diagnostics. The current Uvicorn command has no `--workers` flag and therefore launches one process; setting this name alone does not create workers. |

Paper trading is intentionally paper-only:

| Name | Purpose |
|---|---|
| `APCA_API_KEY_ID` | Alpaca paper key id. `ALPACA_API_KEY_ID` is the accepted alias. |
| `APCA_API_SECRET_KEY` | Alpaca paper secret. `ALPACA_API_SECRET_KEY` is the accepted alias. |
| `APCA_API_BASE_URL` | Must be exactly `https://paper-api.alpaca.markets`. `ALPACA_API_BASE_URL` is the accepted alias. Any live-trading host is refused. |
| `PAPER_TRADING_OWNERS` | Comma-separated Clerk user ids permitted to use the shared paper account. |

Operator-only lists:

| Name | Purpose |
|---|---|
| `ADMIN_CLERK_USER_IDS` | Backend admin role bootstrap list. |
| `METRICS_RESET_OWNERS` | Ids allowed to reset the metrics window. |

## Inference service environment names

The blueprint already supplies `PYTHON_VERSION`, `MODEL_ARTIFACT_DIR`, and
`MODEL_ARTIFACT`. `ALLOWED_ORIGINS` may stay empty because browsers reach
inference through the backend. Render injects `RENDER_GIT_COMMIT`; `/health`
reports it as the deployment commit, separately from the artifact training
commit in `/model`.

## Frontend hand-off

Vercel should set `BACKEND_ORIGIN` to the primary Render backend and
`NEXT_PUBLIC_SITE_URL` to the canonical `https://mini-aladding.vercel.app`.
`VERCEL_GIT_COMMIT_SHA` is copied at build time into the non-secret frontend
build diagnostic. The Operations page compares that SHA with the backend and
inference SHAs and displays `VERSION MISMATCH` when known revisions differ.

## Verification

After an existing service deploys:

1. Check backend `/api/health` and record its `commit`.
2. Check inference `/health`; require `model_loaded: true` and record `commit`.
3. Open `/terminal/admin` with an operator account and confirm the three SHAs.
4. Check `/api/quant/status`, `/api/quant/inference/status`, and
   `/api/paper/status` without printing any credential values.
5. Check `/api/factors?universe=mega30`. It must return a published artifact
   state (`READY` or `STALE`) or an explicit `BUILD_REQUIRED`; it must never
   start a background panel build.
6. Check `/api/system/health` for current/peak RSS, the detected memory limit,
   and the process-wide provider concurrency budget.

The current backend is capped at 512 MB. The 2026-09-20 incident and measured
remediation are recorded in
[`incidents/PROD_INCIDENT_001_RENDER_MEMORY.md`](incidents/PROD_INCIDENT_001_RENDER_MEMORY.md).
