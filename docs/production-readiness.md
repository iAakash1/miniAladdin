# Production readiness

What is verified, what is not, and what is blocked on something outside this
repository. Written to be falsifiable: every "verified" line names how.

**Last reviewed:** 2026-09-01

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
