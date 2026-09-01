# Production readiness

What is verified, what is not, and what is blocked on something outside this
repository. Written to be falsifiable: every "verified" line names how.

**Last reviewed:** 2026-09-01 (incident review)

---

## 0. Incident 2026-09-01 — "Render is unreachable"

Reported as an outage. It was not one. Both services returned **HTTP 200** on
every request throughout. The measurements:

| endpoint | first request | warm |
|---|---|---|
| `minialaddin-d8oe.onrender.com/api/health` | **43.0s** | — |
| `minialaddin-d8oe.onrender.com/api/quant/status` | — | 1.07s |
| `minialaddin-quant-inference.onrender.com/health` | **42.7s** | — |
| `mini-aladding.vercel.app/` | 1.14s | — |

### Root cause chain

1. **The keep-alive workflow was throttled ~29×.** Its cron is `*/10`
   (10 minutes). GitHub Actions actually ran it at a **median gap of 286
   minutes** over the last twelve runs — 136, 160, 173, 197, 223, 286, 294,
   316, 350, 383, 410 minutes. Every single gap exceeded Render's 15-minute
   spin-down. High-frequency schedules on free runners are best-effort and are
   dropped under load.
2. **The workflow reported success the whole time.** Each run took 39–52
   seconds — the curl waiting out a cold start — and exited 0. A green check
   was masking a mechanism that had not worked in days.
3. **It only ever pinged the backend.** The inference service was never in the
   workflow at all, so it slept unconditionally.
4. **A sleeping inference service always reads as unavailable.** The backend
   calls it with an 8s budget (`QUANT_INFERENCE_TIMEOUT`) against a ~43s wake,
   so the first request after any quiet period fails by construction.
5. **Every transport failure collapsed into `unavailable`** carrying a raw
   exception string, making a routine cold start indistinguishable from a dead
   service.

### A second, unrelated defect found during the same investigation

The deployed backend was serving `total_entries: 0` where local serves 103.

`data/research/models/registry.json` — the model register, and the only place a
promotion can be recorded — was excluded from git by `/data/research/`, a rule
written to keep 216 MB of derived partitions out of the repository. The register
is a 1.5 MB evidence ledger caught by where it happens to live.

`ModelRegistry._load()` returns silently when the file is absent, so a **missing**
register was indistinguishable from an **empty** one. The API then asserted
"No production-grade predictive model currently validated" — a claim about
research — from a file that was not in the image. It happened to match the truth
and was not derived from it, and it would have kept saying NO_MODEL after a real
promotion.

### Fixes

| # | fix |
|---|---|
| 1 | Keep-alive pings **both** services, as independent matrix jobs so one failure cannot mask the other. |
| 2 | The workflow documents the measured throttling, so a green check is not read as a warm service. |
| 3 | Timeouts and connection errors classify as **`waking`** with a specific message, not `unavailable`. |
| 4 | `ModelRegistry.source_present` records whether the file was actually read. |
| 5 | `production_status` returns **`UNKNOWN` with null counts** when the register is absent or corrupt — never `NO_MODEL` with zeros — and refuses to serve. |
| 6 | The register ships: `.gitignore` re-admits that one file and nothing else. |
| 7 | The frontend renders null counts as an em dash instead of `?? 0`. |
| 8 | Fixed `symbol_view` passing an experiments root into what is now `registry_root`. |

### What is NOT fixed, and cannot be from this repository

**GitHub Actions cron cannot reliably keep a Render free-tier service warm.**
The run history is the evidence: a 10-minute schedule delivered at a 286-minute
median. Pinging both services helps when a run does fire, and it does not change
the cadence.

Real options, all requiring a decision outside this repository:

- **Render paid tier** — services do not spin down. The direct fix.
- **An external uptime pinger** (UptimeRobot, Cron-job.org, a small always-on
  host) hitting both `/health` endpoints every 10 minutes. Free tiers exist and
  are not subject to Actions throttling.
- **Accept cold starts.** The application now handles them honestly: the first
  request after a quiet period reports `waking` with an explanation, and all
  research evidence renders from committed artifacts regardless.

---

## 1. The headline

| | |
|---|---|
| Application (build, typecheck, lint, tests) | **Verified locally** |
| Payment verification | **Verified locally** — 188 tests |
| Inference fail-closed behaviour | **Verified locally** — 7 tamper cases |
| Holdout firewall | **Verified locally** — engaged, contract not armed |
| Research model | **NOT production.** 0 production, 0 candidates |
| Live deployment (Vercel / Render) | **NOT VERIFIED — no credentials in this environment** |

The last two lines are the ones that matter. The application is engineered to
ship; the *model* is not promoted, and the *deployment* has not been confirmed
from here.

## 2. Research state — frozen

| | |
|---|---|
| EXP-007 | COMPLETE · **NO PRODUCTION CANDIDATE** |
| Gates failed | `survives_search_size`, `deflated_sharpe`, `selection_carries_information` |
| Deployed inference | EXP-006 · **EXPERIMENTAL · PROMOTION BLOCKED** |
| Holdout | **SEALED**, never read, `touched: false` in both artifacts |
| Contract | **NOT ARMED** |
| Production models | **0** |
| 10 bp half-spread | unchanged |
| Execution lag | 1 period, unchanged |

Nothing in the engineering passes touched a fold, a label, a cost, a threshold,
a seed, or a recorded metric.

## 3. What "verified locally" means, per area

### Build and static analysis
`next build` completes; `tsc --noEmit` clean; `eslint src` clean;
`git diff --check` clean.

### Payment verification
188 tests under `dashboard/tests/`. The security-relevant ones cover: an order
bound to a different Clerk user is refused; amount, product, order linkage and
capture state each fail closed; malformed callbacks are refused before any
cryptographic work; the signature check uses the exact order/payment pair; a
missing or non-numeric `amount_paid` fails closed; array-shaped or absent
provider notes fail closed; a numeric note cannot satisfy the user binding.

### Inference
7 tamper cases in `tests/quant/test_inference_failclosed.py`. The service refuses
to serve on sha256 mismatch, on an artifact with no declared hash, on a feature
count mismatch, and on a feature *order* mismatch. A row supplying under 60% of
its features is refused rather than filled with training medians. Every response
carries `promotion_status: BLOCKED`.

### Holdout firewall
4 tests in `tests/quant/test_firewall_reporting.py`. A readable unarmed contract
reports `NOT_ARMED`; an unreadable one reports `UNKNOWN` rather than a confirmed
negative; **an unreadable contract still engages the firewall**; an armed
contract is the one lift condition.

### Quant read layer
426 tests under `tests/quant/`. None of them fit a model, rebuild a panel, or
read a holdout row.

### Responsive
Document width equals viewport width at 375px on `/quant`, `/terminal`,
`/terminal/models` and `/terminal/portfolio`. Desktop at 1440px unchanged: the
terminal header fits without a scrollbar and all nav items are present.

## 4. What is NOT verified

**Live deployment.** No Vercel or Render credentials are available in this
environment, so nothing here confirms that the deployed instances are healthy,
that environment variables are set correctly on the hosts, or that the browser →
Vercel → Render → inference path works end to end in production. It has not been
checked and is not claimed.

To verify it, from a machine with access:

```bash
curl -fsS "$RENDER_BACKEND/api/quant/status" | jq '.deployment_status, .firewall.contract_state'
curl -fsS "$RENDER_INFERENCE/health"
curl -fsS "$RENDER_INFERENCE/model" | jq '.promotion_status, .artifact_integrity'
```

Expect `NO_MODEL`, `NOT_ARMED`, a ready health response, `BLOCKED`, and
`sha256 verified against metadata at load`. Anything else is a real finding.

## 4b. The backend's deployment is not in this repository

`render.yaml` declares **one** service: `minialaddin-quant-inference`. The
backend that serves `/api/*` runs at `minialaddin-d8oe.onrender.com` and is not
declared anywhere in the repository.

That service was created by hand in the Render dashboard, so its build command,
start command, environment variables, branch and **auto-deploy setting** exist
only there. Three consequences, all real:

1. **The deployment is not reproducible from the repository.** If the service
   were deleted, nothing here says how to recreate it.
2. **Auto-deploy is on, and that was established by observation rather than by
   configuration.** The deployed `/api/quant/status` carries `contract_state`,
   a field introduced in commit `f672669`, so pushes to `main` do reach this
   service. The following commit `41a48f9` had not appeared within the ~10
   minutes it was watched — a build, not a failure — so the register fix was
   confirmed in code and in the local backend, but **not observed live**.
3. **Its environment variables cannot be audited.** `QUANT_INFERENCE_URL` in
   particular is required for the model panel to work at all, and whether it is
   set correctly is invisible from the repository.

**This was deliberately not "fixed" by adding a service block to
`render.yaml`.** Render blueprints match services by name, the existing service's
name is not known from here (the URL slug is `minialaddin-d8oe`), and declaring
a guess would create a **second, duplicate service** rather than adopting the
existing one. That is a worse outcome than the documentation gap.

### What you need to check in the Render dashboard

| | |
|---|---|
| Service | the one serving `minialaddin-d8oe.onrender.com` |
| Auto-Deploy | should be **On** for branch `main` |
| Latest deploy | should be at or after commit `41a48f9` |
| Build command | `pip install -r requirements.txt` |
| Start command | must bind `$PORT`, e.g. `uvicorn api.index:app --host 0.0.0.0 --port $PORT` |
| `QUANT_INFERENCE_URL` | `https://minialaddin-quant-inference.onrender.com` |

Auto-deploy appears to be on (see point 2), so this should land without
intervention. If `registry_available` is still absent an hour after
`41a48f9`, the deploy failed and the Render build log is the place to look.

Once it deploys, this is the check:

```bash
curl -fsS https://minialaddin-d8oe.onrender.com/api/quant/status \
  | jq '{deployment_status, registry_available, total_entries}'
```

Expect `NO_MODEL`, `true`, `103`. If `registry_available` is absent, the deploy
has not picked up the change.

---

## 5. Deployment configuration

Confirmed consistent between code and `render.yaml`:

| variable | read by | default when unset |
|---|---|---|
| `MODEL_ARTIFACT_DIR` | `services/inference/app.py` | `artifacts` |
| `MODEL_ARTIFACT` | `services/inference/app.py` | `gradient_boosting@EXP-006` |
| `ALLOWED_ORIGINS` | `services/inference/app.py` | empty — CORS stays closed |
| `QUANT_INFERENCE_URL` | `src/services/inference_client.py` | unset ⇒ reported unavailable, **never guessed** |
| `QUANT_INFERENCE_TIMEOUT` | `src/services/inference_client.py` | 8s |

**Known operational characteristic.** The inference timeout is 8 seconds and
Render's free tier cold-starts more slowly than that, so the first request after
an idle period can fail. The UI reports this as a service-unavailable state with
a cold-start explanation rather than as an error, and research evidence on the
page is read from committed artifacts and stays visible. This is a hosting-tier
property, not a bug, and it is recorded here so nobody re-diagnoses it.

**Browser routing** is same-origin through the Next rewrite.
`NEXT_PUBLIC_API_URL` is deliberately ignored in the browser — a stale value
once pointed at a dead host and produced `TypeError: Failed to fetch`, so it is
honoured only server-side and for local development.

## 6. Authentication

Clerk protects everything except the marketing site, news, learn, auth pages and
SEO files. `/quant`, `/terminal/*` and `/api/*` all require a session;
unauthenticated requests receive a 404 rewrite rather than a 401, which does not
disclose that a route exists.

Local visual verification of protected routes is done by temporarily widening
the public matcher, and the restoration is verified by hashing `proxy.ts` against
the committed object and re-checking that `/quant` returns 404. No bypass is
committed.

## 7. Honest limitations

- **No production verification** (§4). This is the significant one.
- **Terminal primitives are adopted by two surfaces** — Models and Quant.
  Portfolio, Risk and Factors still carry their own metric shapes. They are
  correct, not yet consolidated.
- **Sections with no data are absent, not stubbed.** Options, futures, FX,
  crypto and an agent workspace appear in reference terminals and have no data
  behind them here. A navigation entry leading to invented data is worse than
  its absence.
