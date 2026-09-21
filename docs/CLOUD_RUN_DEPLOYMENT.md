# Cloud Run deployment

Cloud Run is the validated candidate backend for OmniSignal. Render remains
the active rollback target until the Vercel-to-Cloud-Run authentication path
is proven end to end.

## Runtime contract

- Image: Linux `amd64`, Python 3.12, one non-root Uvicorn process.
- Initial allocation: 1 vCPU, 2 GiB memory.
- Request concurrency: 1.
- Autoscaling: minimum 0, maximum 1 during the validation phase.
- Request timeout: 600 seconds.
- Access: authenticated only. An anonymous request must receive `403`.
- Startup: `uvicorn api.index:app`, one worker, listening on `$PORT`.

The single worker and concurrency of one are deliberate. Python imports are a
material part of the process footprint, and multiplying workers multiplies
that baseline. Provider calls still overlap inside the process-wide bounded
executor and are additionally constrained by capability fan-out budgets.

The image copies only product read models: `experiments/`, `artifacts/`, data
manifests, the model registry, reports, and universe metadata. Raw SEC archives,
training panels, curated research tables, and per-trial prediction files are
offline inputs and must not be baked into the API image.

### Local validation (2026-09-21)

| Measure | Broad data copy | Runtime allowlist |
|---|---:|---:|
| Docker build context | 6.12 GB | 83.17 MB |
| Image size | 6.22 GB | 328.12 MB |

The allowlist reduced the image by 94.7%. The `linux/amd64` image started as
the non-root `omnisignal` user and answered `/api/health`,
`/api/system/health`, `/api/quant/status`, and `/api/quant/model-lab`. Startup
RSS was 195.95 MB; after those reads RSS was 202.21 MB with a 203.18 MB peak.
The bundled registry reported 103 entries and Model Lab returned 79 completed
outer-evaluation records.

## Build and deploy a candidate

Use a dedicated project and region selected by the operator. Commands below
contain identifiers only; secret values must never be placed on the command
line or in shell history.

```bash
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/REPOSITORY/omnisignal-api:COMMIT

gcloud run deploy omnisignal-api \
  --image REGION-docker.pkg.dev/PROJECT/REPOSITORY/omnisignal-api:COMMIT \
  --region REGION \
  --platform managed \
  --cpu 1 \
  --memory 2Gi \
  --concurrency 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 600 \
  --no-allow-unauthenticated \
  --set-env-vars MEMORY_LIMIT_MB=2048,DEPLOYMENT_ENV=cloud_run \
  --set-secrets ALPHA_VANTAGE_KEY=alpha-vantage-key:latest
```

Add other provider, Supabase, Clerk, Gemini, and Logo.dev variables through
Secret Manager references or non-secret environment variables according to
their sensitivity. Do not copy values from Render into repository files.

## Validation gate

Before changing `BACKEND_ORIGIN` in Vercel:

1. Verify anonymous access returns `403`.
2. Obtain an identity token for the intended service account and verify
   `/api/health`, `/api/system/health`, `/api/quant/status`, and
   `/api/quant/model-lab` return `200`.
3. Confirm `/api/system/health` reports the expected memory limit, one worker,
   and bounded provider concurrency.
4. Run a cold research request and record before/peak/after RSS.
5. Run a bounded soak and confirm RSS returns to a stable band.
6. Prove the Vercel proxy can mint or obtain a Google-signed identity token
   without embedding a long-lived service-account key in the client bundle.
7. Only then update Vercel's backend origin and retain Render for rollback.

A private Cloud Run URL cannot replace the current public Render origin by a
configuration-only change: Vercel must authenticate each server-side proxy
request. Until that identity bridge exists, switching the origin would turn
working application requests into `403` responses.

## Rollback

Revert Vercel's backend origin to the existing Render service and redeploy the
frontend. Cloud Run revisions are immutable; route traffic back to the last
known-good revision if the failure is isolated to a new backend revision.
