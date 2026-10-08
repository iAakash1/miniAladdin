# OmniSignal — execution checkpoint

Durable state for a long-running, resumable work session. **Read this first
after any pause, limit reset or lost context**, then verify the live values
against the real systems (they may have moved) before continuing. No secrets
belong in this file.

Last updated: 2026-10-08 (the kill-list pass, resumed after a usage limit, then the handoff pass, then the product perfection pass).

## SOURCE-VERIFIED ENGINEERING COMPLETE

Everything the source, the test suites and plain HTTP can show has been verified (below). The items under
"OWNER ACTION REQUIRED" and "BROWSER VERIFICATION REQUIRED" are **not engineering defects**: each needs an
account, a credential, a domain or a browser that only the owner has, and none has been faked. Start at
`OWNER_ACTIONS.md`.

### OWNER ACTION REQUIRED

| Action | Why only the owner | Detail |
|---|---|---|
| Move Clerk from the development instance to a production instance | Needs a domain the owner controls, DNS, and the owner's Clerk dashboard | `CLERK_PRODUCTION.md` |
| Decide how quick the first market-dashboard load should be (a cold build is 8 to 27 s, set by free-tier vendor limits; warm 0.06 s) | Each remedy (paid vendor tier, scheduled warm-up) costs money or vendor budget | `OWNER_ACTIONS.md` item 5 |
| Supply a valid NewsAPI key, or leave the provider disabled on purpose | The stored key is rejected; only the account owner can issue a new one. Production reports it truthfully as `AUTH_FAILURE` meanwhile | `OWNER_ACTIONS.md`, `CLOUD_RUN_DEPLOYMENT.md` |
| Set `SEC_USER_AGENT` to a real contact | Production sends the built-in generic contact; SEC asks for a real one and none has been invented | `OWNER_ACTIONS.md` |

### BROWSER VERIFICATION REQUIRED

The Content-Security-Policy is **enforcing** in production (`CSP_MODE` is not set, and unset enforces). It is not
in report-only mode. It was verified over HTTP only. A real-browser check of sign-in, a company page and the
Razorpay checkout under it is outstanding; the checklist and the one-variable fallback to report-only are in
`OWNER_ACTIONS.md`. Until that check is done, enforcement is unconfirmed. Also unverified without a browser:
rendered layout and spacing, breakpoints, hover and touch behaviour, focus order, rendered contrast, and a
genuinely Clerk-signed token reaching the backend.

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
| Rollback | Backend: `gcloud run services update-traffic omnisignal-api-poc --region asia-south1 --project omnisignal-api-aakash-2026 --to-revisions=<rev>=100`, targets: the revision that served before the latest release (kept tagged and warm) or any earlier `omnisignal-api-poc-release-<sha>` by name (cold start; see `CLOUD_RUN_DEPLOYMENT.md`). Frontend: Vercel instant rollback. CSP: set `CSP_MODE=report-only`, redeploy |
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
| `d3eb831`, `c1d5051` | Patched PyJWT and aiohttp with token verification failing closed; the CSP made usable under `next dev` |
| `9417b34` | A transient outage no longer pins the quality / earnings-surprise inputs or a partly failed official record for six hours |
| `ddf3380` | The browser's request caches drop only their own failed entry |
| `f92af0e` | The agent validation and analysis-run routes report a run in which no provider answered as unavailable, not `ok` / `AVAILABLE` |
| `51fe68c` | The code release (backend 5,388 passed twice, frontend 814); the optional backend settings documented |
| later | The handoff documents: owner actions, the CSP mode stated as it is, `SOURCE-VERIFIED ENGINEERING COMPLETE`. Documentation only; the code is byte-identical to `51fe68c` |
| `86ff882` | Product perfection pass: state colors from their own tokens, sign-in and checkout in the product accent, real focus handling in the shortcut sheet and claim inspector, each with a guard |
| `910271a` | One American spelling (guarded), one name for saved research, plain words in place of "payload" and "endpoint", failure advice that is true of production (guarded) |
| `4eddf25` | An empty regime sample no longer prints "0.0% of 1 observations" |
| `0826774` | Every page names itself; the sitemap lists the public Learn topics and no invented modification time; pages open under their entry's name (all guarded) |
| `c4de40e` | Search: one result per security, one security per share class (`BRK.B`, `BRK-B`, `BRK B`, `BRKB`), nothing for a nonsense query |
| `00260c5` | Search: when a query mixes its own terms with a frame word ("tesla stocks"), a vendor's row must name one of those terms; "qzxwqzxw stocks" no longer returns the largest stock funds |
| docs | This pass's documents: changelog, owner decision 5, release procedure (superseded revisions' tags), testing guide. Documentation only |

## What was verified, and how

**Backend.** The full suite (`tests/`, excluding `test_live_smoke.py`, which needs the real internet) ran twice in a row
on the final tree, from a snapshot that `diff -r` showed equal to the tree on disk (`src/`, `tests/`, `api/`):
**5,412 passed, 10 skipped, 0 failed**, both times (6 m 43 s and 6 m 47 s). Run from a bare `git archive`, six quant tests
fail for want of git-ignored research data; `TESTING.md` says how to build a snapshot that has it.

**Frontend.** `tsc --noEmit` clean, ESLint clean, **839 tests passed, 0 failed** (run twice), production build succeeds.
Every commit in the series was also checked on its own in a throwaway worktree (typecheck and the frontend suite for the
three frontend commits; the commit's own tests for the backend ones).

**Production, for the code release (`51fab09`).** Cloud Run smoke suite 36/36 on the zero-traffic tagged revision and again on
the service URL; anonymous request to the service 403; real-vendor comparison against the previous revision (same prices, chart
points, verdict and provenance counts, plus the new `status` and `coverage` fields); no 5xx and no instrumented handler firing in
the revision's logs; the real JSON replayed through the frontend normalisers with no `NaN`, `Infinity` or `undefined`.

**Google Cloud.** Measured from Cloud Monitoring: ten revisions each held an always-on instance (nine idle behind a
`release-<sha>` tag) on a service whose whole capacity is one instance. A tag keeps its revision's minimum instance at 0%
traffic. The superseded revisions' tags were removed; their instances were released within a minute; traffic was never
touched and the revisions remain. Project IAM is minimal (owner, Cloud Build roles, log writer for the build account), the
service invoker is the Vercel service account alone, and an anonymous request is refused.

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

## Other known limits (none is an owner action)

- The three owner actions and the browser check above. (`CLERK_AUTHORIZED_PARTIES` is available but unset until a live token's `azp` is known.)
- The free-tier usage meter is client-side by design (`dashboard/src/lib/usage.ts`); paper trading, admin and history are enforced on the server.
- Browser-local data (watchlists, memos, research history) is stored per browser profile, not per account.
- `entities`, `registry`, `reasoning` and `related` under `dashboard/src/lib/intelligence/` have tests but no production consumer. Left for the owner to rewire or remove.
- Dev-only: `npm audit` lists five high findings in the lint toolchain (`braces`); never shipped.
- No automated workflow runs the test suites; only the secret scan runs on push.
- Yahoo RSS answers 429 from Cloud Run egress; Finnhub and FMP report plan limits on some endpoints; Massive and Polygon hit the local rate limiter under burst.
- A share class is one security in search (`BRK.B`, `BRK-B`, `BRK B` and `BRKB` all find `BRK.B`), but the quote layer still asks each vendor for the symbol as given. Measured 2026-10-08 on the live service: the two spellings return the same price, date and 1-day and 1-week changes, and their close series can differ by a session or two at the start of the window because different vendors answer. Canonicalizing symbols throughout the quote layer is a larger change that was not made.
- The first market-dashboard load after a quiet period waits 8 to 27 s on free-tier vendor limits (owner decision 5).
- Concurrency 1 on one instance: a long research run (~20–35 s) queues the next request. The first request after a release meets a fresh container; warm it.
- Legacy `compute_decision` is over-confident on sparse data (scoring change, owner's call).

## Resume checklist

1. `git status --short --branch`, `git rev-parse HEAD`, `git ls-remote origin refs/heads/main`.
2. `curl https://omnisignalterminal.vercel.app/api/build` and compare to the Vercel deployment record.
3. `gcloud run services describe omnisignal-api-poc` (traffic, revision) and `python3 scripts/smoke_cloud_run.py <service-url> <commit-prefix> <revision>`.
4. Re-hash the three EXP-007 files and compare to the prefixes above.
5. From `dashboard/`: `node --import tsx --test tests/*.test.ts`, `npx tsc --noEmit`, `npm run lint`, `npm run build`.
6. Backend: run the suite from a snapshot of the tree (see `docs/TESTING.md`), never while editing files.
