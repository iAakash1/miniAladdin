# Cloud Run deployment

Cloud Run is the validated candidate backend for OmniSignal. Render remains
the active rollback target until the Vercel-to-Cloud-Run authentication path
is proven end to end.

## Provisioned candidate (2026-09-22)

| Resource | Value |
|---|---|
| Project | `omnisignal-api-aakash-2026` (`797507035809`) |
| Region | `asia-south1` |
| Existing service | `omnisignal-api-poc` |
| Runtime identity | `omnisignal-api-runtime@omnisignal-api-aakash-2026.iam.gserviceaccount.com` |
| Vercel bridge identity | `omnisignal-vercel@omnisignal-api-aakash-2026.iam.gserviceaccount.com` |
| Workload identity pool/provider | `vercel` / `vercel` |
| Trusted issuer | `https://oidc.vercel.com/aakash-jawales-projects` |
| Trusted Vercel subjects | project `mini-aladding`, environments `preview` and `production` only |

The bridge identity has service-level `run.invoker`; it has no project-wide
application role and no downloaded key. The runtime identity receives
`secretAccessor` on individual secret resources, not at project scope.

Secret containers currently exist for `deepseek-api-key`, `groq-api-key`,
`alpha-vantage-key`, `fred-api-key`, `newsapi-key`, and
`supabase-service-role-key`. Their values are deliberately not copied from
Render by automation. A container with no enabled version must not be attached
to Cloud Run; add each value through Secret Manager, verify an enabled version,
and only then add its environment mapping to the candidate revision.

As of the 2026-09-22 audit, all six containers have zero enabled versions. The
credential-parity gate is therefore **closed**. The intended mappings are:

| Secret resource | Runtime variable | Cutover role |
|---|---|---|
| `deepseek-api-key` | `DEEPSEEK_API_KEY` | Grounded final writer |
| `groq-api-key` | `GROQ_API_KEY` | Analyst stage and bounded fallback |
| `alpha-vantage-key` | `ALPHA_VANTAGE_KEY` | Fundamentals and provider fallback |
| `fred-api-key` | `FRED_API_KEY` | Macro regime inputs |
| `newsapi-key` | `NEWSAPI_KEY` | Primary news provider |
| `supabase-service-role-key` | `SUPABASE_SERVICE_ROLE_KEY` | Server-only persistence |

`SUPABASE_URL`, `CLERK_JWKS_URL`, and `CLERK_ISSUER` are configuration rather
than credentials, but their production values must also be present before
parity can pass. Optional provider keys are added only when the active Render
configuration and a tested runtime path require them; inventorying a provider
in source is not sufficient reason to grant a new secret.

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

gcloud run deploy omnisignal-api-poc \
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
  --service-account omnisignal-api-runtime@PROJECT.iam.gserviceaccount.com \
  --set-env-vars MEMORY_LIMIT_MB=2048,DEPLOYMENT_ENV=cloud_run,WEB_CONCURRENCY=1,PROVIDER_CONCURRENCY_LIMIT=8 \
  --set-secrets ALPHA_VANTAGE_KEY=alpha-vantage-key:latest
```

Add DeepSeek, Groq, provider, Supabase, Clerk, and Logo.dev variables through
Secret Manager references or non-secret environment variables according to
their sensitivity. Do not copy values from Render into repository files.

Before adding a reference, prove that its version exists without reading it:

```bash
gcloud secrets versions list SECRET_NAME \
  --project omnisignal-api-aakash-2026 \
  --filter='state=ENABLED' \
  --format='value(name)'
```

The minimum mappings for the new narrative path are
`DEEPSEEK_API_KEY=deepseek-api-key:latest` and
`GROQ_API_KEY=groq-api-key:latest`. Provider and persistence parity with Render
is a separate cutover gate, not something the deploy command may silently omit.
Set `DEEPSEEK_FAST_MODEL=deepseek-flash` and
`DEEPSEEK_PRO_MODEL=deepseek-v4-pro`; remove the stale
`DEEPSEEK_MODEL=deepseek-chat` setting rather than allowing the compatibility
fallback to select a retired model.

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
6. Configure Vercel OIDC → Google Workload Identity Federation for a dedicated
   least-privilege bridge service account. The App Router proxy exchanges the
   short-lived Vercel token and sends the Google ID token in
   `X-Serverless-Authorization`, preserving Clerk's browser `Authorization`
   header for application auth. No service-account key is stored.
7. Only then update Vercel's backend origin and retain Render for rollback.

The configured provider uses Vercel's team issuer and allowed audience
`https://vercel.com/aakash-jawales-projects`. Its principal bindings are exact
subjects, not an `attribute.project` wildcard:

```text
owner:aakash-jawales-projects:project:mini-aladding:environment:preview
owner:aakash-jawales-projects:project:mini-aladding:environment:production
```

The bridge implementation is in `dashboard/src/app/api/[...path]/route.ts` and
`dashboard/src/lib/backend-proxy.ts`. Infrastructure configuration and a
successful preview smoke test remain mandatory before changing production.

## Rollback

Set Vercel `BACKEND_ORIGIN` to the existing Render service,
`BACKEND_AUTH_MODE=none`, and redeploy the
frontend. Cloud Run revisions are immutable; route traffic back to the last
known-good revision if the failure is isolated to a new backend revision.
