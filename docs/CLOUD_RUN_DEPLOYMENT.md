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
The measured first real calls also require `LLM_TIMEOUT=20` and use the bounded
`LLM_MAX_OUTPUT_TOKENS=6000`; the compact v2 prompt contracts keep typical
responses below that ceiling. The DeepSeek final writer streams its response
in one non-retried attempt: a 20 s limit on silence between chunks, a 25 s
limit on the first content token (an overloaded API answers 200 and then sends
only keep-alives), and a whole-write deadline of `LLM_FAST_TIMEOUT` (default
60 s) for Flash or `LLM_DEEP_TIMEOUT` (default 70 s) for Pro, capped at 80 s. Cloud Run writes best-effort analyst snapshots
and third-party caches only under ephemeral `/tmp`, never under `/app`.

## Preview candidates

Every backend change reaches the redesign preview as an immutable, private,
zero-traffic revision built from one commit:

```bash
SHA=$(git rev-parse HEAD); SHORT=${SHA:0:7}
git archive "$SHA" | tar -x -C "$BUILD_DIR" && cp "$BUILD_DIR/.dockerignore" "$BUILD_DIR/.gcloudignore"
(cd "$BUILD_DIR" && gcloud builds submit --region asia-south1 \
  --tag asia-south1-docker.pkg.dev/omnisignal-api-aakash-2026/cloud-run-source-deploy/omnisignal-api:$SHORT)
gcloud run deploy omnisignal-api-poc --region asia-south1 \
  --image asia-south1-docker.pkg.dev/omnisignal-api-aakash-2026/cloud-run-source-deploy/omnisignal-api@DIGEST \
  --no-traffic --tag redesign-$SHORT --revision-suffix redesign-$SHORT \
  --update-env-vars GIT_COMMIT=$SHA
cd dashboard && vercel env update BACKEND_ORIGIN preview redesign/research-terminal \
  --value https://redesign-$SHORT---omnisignal-api-poc-saigcozo6q-el.a.run.app --yes
```

- Building from `git archive` means the image contains the commit and nothing
  else from the working tree; deploying by digest means the revision cannot
  drift if the tag is reused. `/api/health` reports the commit it was built
  from.
- `--no-traffic` keeps production on its current revision. The tag gives the
  candidate its own URL; the branch-scoped `BACKEND_ORIGIN` points only the
  redesign preview at it.
- `CLOUD_RUN_AUDIENCE` stays the canonical service URL even when the origin
  is a tag URL. Cloud Run validates the identity token against the service,
  not the tag; minting it for the tag URL is refused.
- Secrets are added per revision with `--update-secrets NAME=secret:latest`
  after confirming an enabled version exists and the runtime service account
  holds `secretAccessor` on that secret alone.
- Verify before use: an unauthenticated request to the tag URL returns `403`,
  the IAM policy has no `allUsers`/`allAuthenticatedUsers`, and the traffic
  split still shows 100% on the production revision.

A Vercel environment change applies to the next deployment, so the branch is
pushed after the origin is updated.

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

## Release procedure and provenance (2026-10-07)

> The "Provisioned candidate" section above is a point-in-time record from
> 2026-09-22 and is superseded by this one: the runtime identity now holds
> per-secret `secretAccessor` bindings, and candidate revisions carry the
> Clerk, Supabase, provider and LLM configuration.

A push to GitHub does not by itself change what users see. Two independent
systems decide that, and only one of them watches Git:

| Tier | Source of truth | Triggered by | Identifies itself at |
|---|---|---|---|
| Frontend (Vercel project `mini-aladding`, root `dashboard`, production branch `main`) | the GitHub commit | a push to `main`; a CLI deploy carries **no** git metadata | `GET /api/build` (public) |
| Backend (Cloud Run service `omnisignal-api-poc`, `asia-south1`) | the container image **and the traffic split** | a manual build and deploy; there are no Cloud Build triggers | `GET /api/health` (private; needs an identity token) |

Pushing code to `main` updates the first and does nothing to the second. A new
Cloud Run revision also serves no traffic until it is given some, so "deployed"
and "live" are different states. That gap is how a production service ran a
credential-free proof-of-concept revision for weeks while the repository moved
on.

### Deploy the backend

```bash
SHA=$(git rev-parse HEAD)               # the commit that is on origin/main
SHA7=${SHA:0:7}
mkdir -p /tmp/src-$SHA7 && git archive $SHA | tar -x -C /tmp/src-$SHA7   # tracked files only: no .env

# Builds run as omnisignal-build, not the default compute account (see
# "Least privilege" below). A custom account needs the config file.
gcloud builds submit /tmp/src-$SHA7 --project omnisignal-api-aakash-2026 \
  --config cloudbuild.yaml --substitutions _TAG=$SHA7 \
  --service-account projects/omnisignal-api-aakash-2026/serviceAccounts/omnisignal-build@omnisignal-api-aakash-2026.iam.gserviceaccount.com

# a revision that takes no traffic yet, tagged so it can be tested
gcloud run deploy omnisignal-api-poc --project omnisignal-api-aakash-2026 --region asia-south1 \
  --image asia-south1-docker.pkg.dev/omnisignal-api-aakash-2026/cloud-run-source-deploy/omnisignal-api@<digest> \
  --no-traffic --tag release-$SHA7 --revision-suffix release-$SHA7 \
  --min-instances 1 --update-env-vars GIT_COMMIT=$SHA
```

`GIT_COMMIT` is not optional: it is the only thing that lets the running
service name its commit. Without it `/api/health` reports `"unknown"`.

### Prove what is running

The service is private. Call it with an identity token; never make it public.

```bash
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" https://<tagged-or-service-url>/api/health
#   "commit":   the Git SHA the image was built from
#   "revision": Cloud Run's own revision name (K_REVISION)
curl -s https://omnisignalterminal.vercel.app/api/build
#   commit, ref, environment, deployment (Vercel id), built_at
```

Both checks are scripted. `scripts/smoke_cloud_run.py <url> <commit-prefix>
<revision>` runs ~40 probes against a private URL with your own identity token
(identity, research truth, search, chart and quote semantics, FRED, and every
paper-trading mutation refused); run it on the tagged zero-traffic revision
before moving traffic and on the service URL after.
`scripts/smoke_credential_free.py` starts the API with an empty environment and
no `.env`, from a clean `git archive`, and proves nothing needs a credential
to start or to refuse.

The chain is only proven when all of these agree:

1. `git rev-parse HEAD` equals `git ls-remote origin refs/heads/main`.
2. `/api/build` `commit` on the production alias equals that SHA.
3. `/api/health` `commit` on the service URL equals that SHA, and `revision`
   names the revision holding 100% of traffic
   (`gcloud run services describe omnisignal-api-poc --format='value(status.traffic)'`).

### Move traffic, and undo it

Backend first: an older frontend tolerates a newer backend, but a newer
frontend calling an older backend meets routes that do not exist.

```bash
gcloud run services update-traffic omnisignal-api-poc --region asia-south1 \
  --project omnisignal-api-aakash-2026 --to-revisions=omnisignal-api-poc-release-$SHA7=100
# rollback is the same command naming the previous revision
```

An anonymous request to the service must still receive `403`.

**Then warm it.** A revision's minimum instance is *not* kept while the revision
sits at 0% traffic: the log reads `Starting new instance. Reason:
DEPLOYMENT_ROLLOUT` at the moment traffic moves. So the first request after a
release meets a fresh container (about 6 s), a cold macro cache on it (about
3 s) and, if the frontend was deployed too, a new Vercel function. Measured
once, that was 13 s through Vercel. Make the first request yourself, before
anyone else does:

```bash
curl -s https://omnisignalterminal.vercel.app/api/macro >/dev/null   # container, FRED cache, function
python3 scripts/smoke_cloud_run.py <service-url> <commit-prefix> <revision>
```


## Hardening pass (2026-10-07)

### Least privilege

The runtime identity was never the problem: the live service runs as
`omnisignal-api-runtime`, which holds **no project role** and reads secrets
through per-secret `secretAccessor` bindings. The broad grant was on the
**default compute service account**, which held `roles/editor` on the whole
project — and could not simply be removed, because *Cloud Build ran as that
account*. The one thing that depended on it was the build.

| | Before | After |
|---|---|---|
| Image builds run as | default compute SA (`roles/editor`) | `omnisignal-build` |
| `omnisignal-build` can | — | push to the `cloud-run-source-deploy` repository only; read the `…_cloudbuild` source bucket only; write build logs |
| Default compute SA project roles | `roles/editor` | none |
| Service accounts holding `roles/editor` | 1 | 0 |
| User-managed service-account keys | 0 | 0 |

Order matters if this is ever repeated: create the account and grants, prove a
build succeeds under it (`--service-account`), and only then remove the old
grant. Reverting is `gcloud projects add-iam-policy-binding … --role=roles/editor`.
`797507035809@cloudbuild.gserviceaccount.com` still holds the legacy
`roles/cloudbuild.builds.builder`; nothing uses it (no triggers exist) and it
was left alone rather than widen the change. The original proof-of-concept
revision `omnisignal-api-poc-00001-wql` (0% traffic) still names the default
compute account; it calls no Google API, so it needs no role.

### Cold start

Measured, not assumed. On a revision scaled to zero, the first `/api/health`
(which does no work) took **9.9 s**; the same call warm takes ~40 ms. Cloud Run's
own `container/startup_latencies` reported 6.0–7.9 s per new instance, and the
log shows 9.6 s from "Starting new instance" to uvicorn's first line. The
application is not the cost: importing it takes ~0.5–0.7 s locally and the first
request is answered in 56 ms. A first FRED fetch then adds ~3.5 s, and the
Vercel proxy's token exchange a little more — together the ~16 s seen on the
landing page's macro strip.

What was done, in order of how much it matters:

1. **`--min-instances 1`.** The only thing that removes the cold start from the
   first user request, because it is instance provisioning and image fetch, not
   code. Cost: one always-allocated instance (1 vCPU, 2 GiB) at Cloud Run's idle
   rate — an estimated US$10–25 a month in `asia-south1`; check the billing
   report rather than trusting that range. Revert with
   `gcloud run services update omnisignal-api-poc --min-instances 0`. Chosen
   over a scheduled ping because a ping needs a new service (Cloud Scheduler)
   and an extra invoker identity, and still gives no guarantee that the
   instance survives between pings.
2. **Bytecode precompiled in the image** (`Dockerfile`). Small and free: 0.68 s
   → 0.56 s import.

Not done, on purpose: pruning dependencies. `pyarrow` (≈108 MB) and `scipy`
(≈98 MB) dominate the image, but removing either needs proof that no runtime
path imports it, and a wrong guess is a production outage to save seconds that
`min-instances` already removes.

Measured after the change, from a machine in India:

| Request | Before | After |
|---|---|---|
| Cloud Run direct, first request after ≥10 min idle | 9.9 s | 0.06 s |
| Public path (Vercel → OIDC → Cloud Run → FRED), first request after ≥10 min idle | ~14–16 s | 2.3 s |
| Same, warm | 0.9–2.1 s | 0.6 s |
| First request in the minutes after a release | — | up to ~13 s (see "Then warm it") |

The 2.3 s is Vercel's own function start and the three-call Google token
exchange, which the proxy then caches for ~55 minutes.

### Where the proxy runs

The Vercel project defaulted to `iad1` (US East). Requests entered at Mumbai
(`x-vercel-id: bom1::iad1::…`), ran in Virginia, then called Cloud Run back in
Mumbai: two crossings of the planet for a call whose backend time is a few
milliseconds. `dashboard/vercel.json` pins the functions to `bom1`, beside the
backend. A user anywhere still pays one long hop, so this is never worse than
the default and is much better for the people the product is for; a test
(`dashboard/tests/function-region.test.ts`) pins it. It is a configuration
file rather than a project setting so the decision is reviewable and
reproducible.

Concurrency stays at 1 with a single instance, so a long research request
(tens of seconds) still queues the next one. That is the memory-bounding
decision recorded above, unchanged.

### News providers

`NEWSAPI_KEY` is bound to Secret Manager secret `newsapi-key`, which holds one
enabled version. That value is 36 characters in UUID form, not the 32-hex
characters of a NewsAPI key, and NewsAPI answers it with `apiKeyInvalid`; it is
not a copy of any other secret. The integration itself is correct (documented
endpoint, `X-Api-Key` header), so the fix is a valid key, which only the
account owner can obtain from newsapi.org:

```bash
printf '%s' "<new-key>" | gcloud secrets versions add newsapi-key --data-file=-
```

then deploy a new revision, since secrets are read when an instance starts.

Until then the product reports it truthfully: the vendor chain falls through to
the other news sources and names the one that answered; a rejected credential is
its own state (`AUTH_FAILURE`, credential `rejected`) rather than "paused"; it
is re-probed once every 15 minutes, not every minute; and `/api/health`, the
provider inventory and the providers page no longer call it available. A
configured key nothing has used yet is reported as `unverified`, so a fresh
instance says "configured" until the first news request settles it.
