# OmniSignal: owner actions and handoff

**Status: SOURCE-VERIFIED ENGINEERING COMPLETE.** Everything the source, the tests and plain HTTP can
show has been checked (see `OMNISIGNAL_OVERNIGHT_STATE.md`). What follows is not an engineering
backlog: each item needs something only the owner has (an account, a credential, a domain, a browser).
No credential or contact detail has been invented to make any of them look finished.

## What this is, and how it is served

- **OmniSignal** is an evidence-driven equity research workbench. `README.md` describes the product; its
  guarantee is that a failure is never presented as an answer.
- **Frontend:** Next.js on Vercel (project `mini-aladding`, root `dashboard`, production branch `main`,
  functions in `bom1`), served at `https://omnisignalterminal.vercel.app`.
- **Backend:** FastAPI on a **private** Google Cloud Run service, `omnisignal-api-poc` (project
  `omnisignal-api-aakash-2026`, `asia-south1`). The browser never reaches it: the frontend's server-side
  `/api/*` proxy signs each request with a Google identity token obtained from the Vercel OIDC token
  through Workload Identity Federation. A direct anonymous request is refused with `403`.
- **Render** is a documented rollback target only; nothing in production depends on it.

### The deployment chain, and how to prove it

1. A push to `main` is built by Vercel automatically.
2. The backend is released by hand (`CLOUD_RUN_DEPLOYMENT.md`): build the image from `git archive` of the
   commit, deploy it as a zero-traffic tagged revision, run `scripts/smoke_cloud_run.py` against it, then
   move traffic.
3. Each names its commit, and the website names the backend it actually calls. The chain is proven when
   these agree (the last line matters most: until 2026-10-08 the website called an old pinned candidate
   while every release moved the service's traffic to a different revision):

```bash
git ls-remote origin refs/heads/main                                  # GitHub
curl -s https://omnisignalterminal.vercel.app/api/build               # Vercel: "commit"
curl -s -D - -o /dev/null https://omnisignalterminal.vercel.app/api/macro \
  | grep -i '^x-backend'                                              # what the website really calls
TOKEN=$(gcloud auth print-identity-token)                             # Cloud Run (private):
curl -s -H "X-Serverless-Authorization: Bearer $TOKEN" \
  https://omnisignal-api-poc-saigcozo6q-el.a.run.app/api/health       #   "commit", "revision"
gcloud run services describe omnisignal-api-poc --region asia-south1 \
  --project omnisignal-api-aakash-2026 --format='value(spec.traffic[0].revisionName,spec.traffic[0].percent)'
```

### Rollback

| Layer | How |
|---|---|
| Backend | `gcloud run services update-traffic omnisignal-api-poc --region asia-south1 --project omnisignal-api-aakash-2026 --to-revisions=<revision>=100`. Earlier revisions are kept, for example `omnisignal-api-poc-release-3123224` and `omnisignal-api-poc-release-dea3555` |
| Frontend | Vercel dashboard, Deployments, "Instant Rollback" on an earlier production deployment |
| Content-Security-Policy | Set `CSP_MODE=report-only` (or `off`) on the Vercel project and redeploy; no code change |

### Changing backend configuration safely

This service pins traffic to a named revision, so a configuration change creates a revision that
receives **no traffic** until you give it some. That is the safe order for every backend change below:

```bash
# 1. a new revision carrying the change, with no traffic and a tag to reach it
gcloud run services update omnisignal-api-poc --project omnisignal-api-aakash-2026 --region asia-south1 \
  <the change, for example --update-env-vars 'NAME=value'> \
  --no-traffic --tag envchange --revision-suffix env-<yyyymmdd-hhmm>
# 2. prove it before anyone uses it
python3 scripts/smoke_cloud_run.py <the tagged URL it prints> <commit-prefix> omnisignal-api-poc-env-<yyyymmdd-hhmm>
# 3. move traffic (and keep the previous revision name for rollback)
gcloud run services update-traffic omnisignal-api-poc --project omnisignal-api-aakash-2026 \
  --region asia-south1 --to-revisions=omnisignal-api-poc-env-<yyyymmdd-hhmm>=100
```

---

## OWNER ACTION REQUIRED

### 1. Clerk: move from the development instance to a production instance

**Why only the owner:** a Clerk production instance needs a custom domain you control (Clerk does not issue
one for `*.vercel.app`), DNS records at your registrar, and your Clerk dashboard. The site currently runs on
a **development** instance (`caring-snipe-24.clerk.accounts.dev`): sign-in works, but Clerk shows its
development banner and applies development rate limits.

**What to do:** follow `CLERK_PRODUCTION.md`, which lists every step, the Vercel and Cloud Run values, the
allowed origins and redirects, and a post-switch verification procedure. Do not commit any key.

**The source is already ready for it** (checked): the Content-Security-Policy reads the Clerk host from the
publishable key, so a `pk_live_` key on your own domain is allowed automatically; no code names the
development instance; the backend needs only `CLERK_JWKS_URL` and `CLERK_ISSUER`.

### 2. NewsAPI: supply a valid key, or leave the provider disabled

**State today:** NewsAPI answers the stored credential with `apiKeyInvalid`. OmniSignal reports exactly that
(`AUTH_FAILURE`, credential `rejected`), retries it only every 15 minutes, and serves news from the other
healthy vendors (GNews, Marketaux, Tavily, Alpha Vantage). Nothing is hidden or faked.

**Choose one:**

- **Provide a valid key** from newsapi.org (an account only you can open):

```bash
printf '%s' '<the key>' | gcloud secrets versions add newsapi-key --project omnisignal-api-aakash-2026 --data-file=-
```

  It prints `Created version [N]`. A secret is read when an instance starts, so release a new revision with
  "Changing backend configuration safely" above, using `--update-secrets=NEWSAPI_KEY=newsapi-key:N` as the
  change (pinning the version number makes the change visible in the revision's history). NewsAPI should then
  show `HEALTHY` in `/api/providers/health`.
- **Leave it disabled on purpose:** remove the binding, with `--remove-secrets=NEWSAPI_KEY` as the change. The
  vendor then reports `NOT_CONFIGURED`, which is the accurate state of a provider that has no key.

Either is correct. Leaving it as it is today is also truthful, only noisier.

### 3. `SEC_USER_AGENT`: give SEC EDGAR a real contact

**State today:** the variable is unset, so requests to SEC EDGAR carry the built-in generic contact
(`OmniSignal Research (contact: research@omnisignal.app)`). SEC's fair-access policy asks for a User-Agent
that names a real contact, which only you can supply; none has been invented.

**What to do:** use "Changing backend configuration safely" with

```bash
--update-env-vars 'SEC_USER_AGENT=OmniSignal (contact: <a mailbox you read>)'
```

### 4. Content-Security-Policy: do the browser check (next section)

### 5. Decision: how quick the first market-dashboard load should be

**State today:** the dashboard is assembled from many calls to free-tier data vendors, each under its own
rate budget, which OmniSignal respects on purpose. A request that finds nothing cached takes between
8 and 27 seconds (the last measurement against production, 2026-10-08: 26.9 s); the same request served
from the cache takes about 0.06 second. A result built while a source was down is kept for minutes, not
for the quarter hour a complete one keeps, so an outage is never frozen in.
The time is spent waiting out vendor limits, not computing. No code change makes it shorter without
either spending more of a budget or paying for one.

**Choose one (each needs your approval, because each costs money or vendor budget):**

- **Accept it.** The first reader after a quiet period waits; everyone after is quick.
- **Pay for the tier that rate-limits** (the vendors reporting `RATE_LIMITED` in `/api/providers/health`).
- **Warm it on a schedule.** A Cloud Scheduler job that requests the dashboard with an identity token every
  few minutes keeps the cache full, at the price of spending vendor budget continuously.

Nothing is broken whichever you pick; this is a trade between money and a few seconds for the first reader.

### 6. Decision: where Vercel preview deployments should send their backend calls

**State today:** production calls the service (`BACKEND_ORIGIN` is the service URL). The default for
**preview** deployments is still the pinned candidate tag `candidate-fast-601fb7f`, a backend built
from commit `601fb7f` (2026-09-22). The `redesign/research-terminal` branch has its own origin. A
preview of any other branch therefore calls that old build, and the tag keeps one idle instance
running (a tag holds its revision's instance; see `CLOUD_RUN_DEPLOYMENT.md`).

**Choose one:** point the default preview origin at the service (previews then share production's
backend and its data), deploy a fresh private candidate per branch as `CLOUD_RUN_DEPLOYMENT.md`
describes, or stop using previews and remove the tag. Only you know whether previews are used.

---

## BROWSER VERIFICATION REQUIRED

The Content-Security-Policy is **enforcing** in production today. `CSP_MODE` is not set on the Vercel
project, and an unset value enforces. It was verified over HTTP (valid grammar, per-request 128-bit nonce on
every external script, the one inline script allowed by a matching hash, no `unsafe-eval`, no wildcard
script source, the report endpoint behaving as designed). It has **not** been run in a real browser, which
is the only way to confirm that hydration, Clerk's sign-in and the Razorpay checkout work under it.

**The check (about two minutes), in a normal browser with developer tools open on the Console:**

1. Open `https://omnisignalterminal.vercel.app/`. Expect no `Refused to ...` messages.
2. Sign in. The Clerk form must appear and complete, and `/terminal` must load.
3. Open a company page (for example `/company/AAPL`) and let the research run finish.
4. Open the upgrade dialog; the Razorpay checkout frame must load.
5. In the Vercel runtime logs, search for `csp-violation`. A real violation names the blocked address and
   the directive; anything legitimate that is blocked is a hole in the allow-list, not a reason to remove the
   policy.

**If anything is blocked and you cannot wait for a fix:** set `CSP_MODE=report-only` on the Vercel project and
redeploy. The browser then reports violations without blocking anything, and the same log search shows what
needs allowing. Return to enforcement by deleting the variable. Do not remove the policy outright (`off`)
unless report-only also fails. Until this check has been done, treat enforcement as unconfirmed.

`CONTENT_SECURITY_POLICY.md` has the policy, the allow-list and how it is built.

## Also unverified without a browser

Rendered layout and spacing, the responsive breakpoints, hover and touch behaviour, focus order, rendered
contrast, and a genuinely Clerk-signed token reaching the backend (PyJWT 2.15.0 reads Clerk's real keys and
refuses forged tokens, but I could not sign in). Step 2 above covers the last one.
