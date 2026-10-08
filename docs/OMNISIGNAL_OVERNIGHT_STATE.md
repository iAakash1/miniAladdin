# OmniSignal — execution checkpoint

Durable state for a long-running, resumable work session. **Read this first
after any pause, limit reset or lost context**, then verify the live values
against the real systems (they may have moved) before continuing. No secrets
belong in this file.

Last updated: 2026-10-08 (the kill-list pass, resumed after a usage limit).

## Where things are

| | |
|---|---|
| Repository | `github.com/iAakash1/miniAladdin` (product name: OmniSignal) |
| Branches | `main` (production) and `redesign/research-terminal` (working branch), kept equal; every push is a fast-forward |
| Live identifiers | Read them, do not trust this file: `GET https://omnisignalterminal.vercel.app/api/build` (Vercel commit and deployment id), `GET /api/health` on the private service with an identity token (Cloud Run commit and revision), `gcloud builds list` (Cloud Build) |
| Chain at the commit that contains this file | GitHub `main` = Vercel production = Cloud Build source = Cloud Run revision `omnisignal-api-poc-release-<7-char SHA of this commit>`. The backend image is built from the commit that carries this document so that it names itself; the verified values are in the report that closed the pass |
| Production URL | `https://omnisignalterminal.vercel.app` (`mini-aladding.vercel.app` redirects to it). Vercel functions in `bom1` |
| Cloud Run | project `omnisignal-api-aakash-2026`, `asia-south1`, service `omnisignal-api-poc`, private (anonymous request → 403), min=max=1 instance, concurrency 1, runtime SA `omnisignal-api-runtime`, build SA `omnisignal-build` |
| Release procedure | `docs/CLOUD_RUN_DEPLOYMENT.md` (backend first, then push; warm the revision afterwards) |
| Rollback | Backend: `gcloud run services update-traffic omnisignal-api-poc --region asia-south1 --project omnisignal-api-aakash-2026 --to-revisions=<rev>=100`, targets `release-51fab09`, `release-dea3555`, `release-7671e5a`. Frontend: Vercel instant rollback. CSP: set `CSP_MODE=report-only`, redeploy |
| Render | Rollback target only, documented, not in the serving path. The keep-alive workflow was removed |

### Commits of this pass (all authored and committed by `iAakash1`, no trailer)

| Commit | What |
|---|---|
| `532f71c` | A vendor failure is a failure: shape, error envelope, non-finite numbers, unreadable rows (all 31 adapters) |
| `b587aef` | Outage, absence and stale reading kept apart in the API; every caller gets its own copy of a cached result |
| `fd65f58` | `CLERK_AUTHORIZED_PARTIES` (opt-in) |
| `097068e` | Per-request Content-Security-Policy; anonymous `/api/*` answers 401 at the edge |
| `45c7ea0` | A failed read is shown as failed; dates; undated news |
| `fbf574b` | Status key in text, hover gating, breakpoints, spacing, accessible names, dead code removed |
| `51fab09` | CSP and Clerk documents, keep-alive removed, README and docs made true |
| `8a8aeee` | Next 16.3.8 for the published security fixes |
| later | Patched PyJWT and aiohttp, token verification fails closed; CSP usable under `next dev`; this checkpoint |

## What was verified, and how

**Backend.** The full suite (`tests/`, excluding `test_live_smoke.py`, which needs the real internet) ran twice in a row
on the final tree, from a snapshot whose file hash equalled the tree on disk: **5,342 passed, 0 failed**, both times.

**Frontend.** `tsc --noEmit` clean, ESLint clean, **811 tests passed, 0 failed**, production build succeeds.
Every commit in the series was also checked on its own in a throwaway worktree (typecheck and the frontend suite for the
three frontend commits; the commit's own tests for the backend ones).

**Production, for the code release (`51fab09`).** Cloud Run smoke suite 36/36 on the zero-traffic tagged revision and again on
the service URL; anonymous request to the service 403; real-vendor comparison against the previous revision (same prices, chart
points, verdict and provenance counts, plus the new `status` and `coverage` fields); no 5xx and no instrumented handler firing in
the revision's logs; the real JSON replayed through the frontend normalisers with no `NaN`, `Infinity` or `undefined`.

**Content-Security-Policy, live.** Header present on every HTML page; a 128-bit nonce, different per request, on every
external script; the one inline script (theme bootstrap) allowed by a hash that equals the SHA-256 of the served text; no
`unsafe-eval`, no wildcard script host; `/api/csp-report` answers 204 / 415 / 413 / 400 / 405 as designed. Anonymous `/api/*`
→ 401 JSON; `/api/news`, `/api/macro`, `/api/build` stay public. Signed-out `/terminal/*` still answers Clerk's not-found.

**Latency (warm, 8 samples each, from the build machine):** `/api/build` 69 ms median, `/api/macro` (through the proxy to Cloud
Run) 112 ms, `/` 140 ms, `/news` 104 ms, `/sign-in` 90 ms, `/learn` 119 ms.

**Dependencies.** `npm audit --omit=dev`: 0. Python: `PyJWT` 2.15.0 and `aiohttp` 3.14.3 pinned. Two advisories (`cryptography`
PKCS#7 decryption, `pyarrow` Arrow IPC files) cover features the service never calls and are left unchanged. Full record in
`docs/DEPENDENCY_AUDIT.md`.

## Research firewall

EXP-007 verdict `NO PRODUCTION CANDIDATE`; holdout untouched; registry production 0, candidates 0, validated 0. EXP-008 was not run.
Fingerprint prefixes (sha256), re-hashed before and after this pass and after every group of work, unchanged:
`artifacts/experiments/EXP-007/final_selection.json` `a69f54e5a309ec3f`, `experiments/EXP-007/checkpoints/configs.jsonl`
`d0251b4cc4e21d03`, `experiments/EXP-007/search.json` `9ada5cda42234782`. `git diff` over `experiments/`, `artifacts/`, `data/`,
`datasets/`, `research_papers/` and `src/quant/` between the start and the end of the pass is empty.

## Known issues and external limits

- **NewsAPI key is rejected** (HTTP 401). Reported as `AUTH_FAILURE`, credential `rejected`, cooling down; four other news vendors are
  healthy and the research run returns headlines. A real key is the account owner's to supply.
- **Clerk runs a development instance** (`*.clerk.accounts.dev`). Moving to production needs a domain the owner controls, DNS records and the
  owner's Clerk dashboard (`docs/CLERK_PRODUCTION.md`). `CLERK_AUTHORIZED_PARTIES` is available but unset until a live token's `azp` is known.
- **No browser has been opened** (the owner's rule). Everything below is therefore *unverified*, not failing: rendered layout and
  spacing, hydration and the Clerk sign-in flow under the enforced CSP, the Razorpay checkout under the CSP, focus behaviour, hover and
  touch behaviour, the responsive breakpoints, rendered contrast. If the CSP misbehaves in a real browser: `CSP_MODE=report-only`.
- The free-tier usage meter is client-side by design (`dashboard/src/lib/usage.ts`); paper trading, admin and history are enforced on the server.
- Browser-local data (watchlists, memos, research history) is stored per browser profile, not per account.
- `entities`, `registry`, `reasoning` and `related` under `dashboard/src/lib/intelligence/` have tests but no production consumer. Left for the owner to rewire or remove.
- Dev-only: `npm audit` lists five high findings in the lint toolchain (`braces`); never shipped.
- No automated workflow runs the test suites; only the secret scan runs on push.
- Yahoo RSS answers 429 from Cloud Run egress; Finnhub and FMP report plan limits on some endpoints; Massive and Polygon hit the local rate limiter under burst.
- Concurrency 1 on one instance: a long research run (~20–35 s) queues the next request. The first request after a release meets a fresh container; warm it.
- Legacy `compute_decision` is over-confident on sparse data (scoring change, owner's call).

## Resume checklist

1. `git status --short --branch`, `git rev-parse HEAD`, `git ls-remote origin refs/heads/main`.
2. `curl https://omnisignalterminal.vercel.app/api/build` and compare to the Vercel deployment record.
3. `gcloud run services describe omnisignal-api-poc` (traffic, revision) and `python3 scripts/smoke_cloud_run.py <service-url> <commit-prefix> <revision>`.
4. Re-hash the three EXP-007 files and compare to the prefixes above.
5. From `dashboard/`: `node --import tsx --test tests/*.test.ts`, `npx tsc --noEmit`, `npm run lint`, `npm run build`.
6. Backend: run the suite from a snapshot of the tree (see `docs/TESTING.md`), never while editing files.
