# OmniSignal — execution checkpoint

Durable state for a long-running, resumable work session. **Read this first
after any pause, limit reset or lost context**, then verify the live values
against the real systems (they may have moved) before continuing. No secrets
belong in this file.

Last updated: 2026-10-08

## Where things are

| | |
|---|---|
| Repository | `github.com/iAakash1/miniAladdin` (product name: OmniSignal) |
| Branch | `main` (also mirrored on `redesign/research-terminal`, kept equal) |
| HEAD / origin/main | `2c03b826ba749f654656188debbaa5a60ccaf2ce` |
| Vercel production | `dpl_6mq6yTJhCnc7BcVarVu4omDwucxH`, built from the SHA above, functions in `bom1` |
| Production URL | `https://omnisignalterminal.vercel.app` (`mini-aladding.vercel.app` redirects to it) |
| Cloud Run | project `omnisignal-api-aakash-2026`, `asia-south1`, service `omnisignal-api-poc`, revision `omnisignal-api-poc-release-7671e5a` at 100%, min=max=1, concurrency 1 |
| Backend source | `7671e5a`. Every commit since is frontend-only (`dashboard/`), so the running backend is functionally current; rebuild it for the final SHA before declaring the work done, so Cloud Build source equals main |
| Runtime service account | `omnisignal-api-runtime` (no project roles; per-secret `secretAccessor`) |
| Build service account | `omnisignal-build` (Artifact Registry writer on one repo, bucket objectViewer, logWriter) |
| `roles/editor` held by | nobody |
| Rollback | `gcloud run services update-traffic omnisignal-api-poc --region asia-south1 --project omnisignal-api-aakash-2026 --to-revisions=<rev>=100`; targets `release-d9cbb08`, `release-3d19402`, `release-0e93c4f`. Frontend: Vercel instant rollback |

Release procedure and provenance checks: `docs/CLOUD_RUN_DEPLOYMENT.md`.
Test rules: `docs/TESTING.md`.

## Last verification (production)

- `/api/build` → commit `2c03b826…`, ref `main`, environment `production`.
- Public routes `/`, `/learn`, `/news`, `/sign-in`, `/sitemap.xml`, `/robots.txt` → 200. `/terminal/*` → 404 for a signed-out request by design (Clerk `protect-rewrite`).
- Deployed stylesheets carry the new status states, the `--gap` and `--z-*` tokens, and none of the retired quant terminal's rules.
- Backend (checked at `7671e5a`): `scripts/smoke_cloud_run.py` 36 passed, 0 failed; anonymous request → 403.

## Tests (last full runs)

- Frontend on HEAD: 682 passed, 0 failed; typecheck, lint and production build clean.
- Backend: 3,328 passed, 0 failed, 0 skipped (three consecutive runs at `7671e5a`). No backend file has changed since.
- Credential-free smoke: 40 passed, 0 failed.

## Research firewall

EXP-007 verdict `NO PRODUCTION CANDIDATE`; holdout untouched; registry production 0, candidates 0, validated 0.
Fingerprint prefixes (sha256): `final_selection.json` `a69f54e5a309ec3f`, `checkpoints/configs.jsonl` `d0251b4cc4e21d03`, `search.json` `9ada5cda42234782`. Re-hashed after every commit in this pass; unchanged. No commit touches a path outside `dashboard/` since `7671e5a`.

## UI pass (source-level; no browser has been opened)

Done and deployed, each with a guard test:

- **Design scales**: type, weight, tracking, radius, motion and easing tokens; undefined-token test now requires a real declaration.
- **Buttons, focus, accessibility floor**: one button family, one focus ring, reduced-motion catch-all, 24px targets (36px on touch), forced-colors states, 16px text fields on touch pointers.
- **Status and badge grammar**: `Status` covers live, recorded, stale, waking, unavailable, blocked, experimental, candidate, production, unknown, retired, paper, error, warning, info. `Badge` is the one verdict chip. The legacy `.badge` and the style-less `.pal-badge` are gone.
- **Search palette**: focus returns to the opener, Tab stays inside, results announced, retired shown as retired.
- **Inspectors**: focus moves in on open and returns on close; Escape no longer closes an inspector beneath the palette.
- **Charts**: plots are laid out at their measured width (one unit per CSS pixel) with 10px axis text; hover maps to the right observation in panels wider or narrower than 640.
- **Numbers**: every number and date names its locale; one `fmtSigned` replaces 45 hand-built sign rules.
- **Legacy families retired**: `.input`, `.label`, `.data-table`, panel padding and heading sizes now come from classes. 386 unreachable classes (63KB) deleted.
- **Defects found on the way**: `--gap` was never defined (28 rules had no padding or margin since 2026-09-11); `@keyframes fade-in` defined twice with different bodies; graph labels at 9px and 8.5px; `⌘K` printed on every platform; "Deployed model" heading on a research-only model.
- **Layers**: `--z-*` tokens, ordered and tested.

Not verified (needs a browser or a signed-in session): rendered layout, the client-side resize path of the charts, the signed-in `/terminal/*` screens, focus behaviour in a real browser.

## Known defects and external limits

- **NewsAPI key is invalid** (a UUID-shaped value, not a 32-hex key; NewsAPI answers `apiKeyInvalid`). Reported honestly as `AUTH_FAILURE`; needs a real key from the account owner.
- **Clerk runs a development instance** (`*.clerk.accounts.dev`; responses carry `dev-browser-missing`). A production Clerk instance and domain is the owner's call.
- Yahoo RSS 429 from Cloud Run egress; Tiingo / Finnhub partial 403 (plan limits).
- Concurrency 1 on one instance: a long research run (~20–35 s) queues the next request.
- First request after any release meets a fresh container; warm it (see the deployment doc).
- Legacy `compute_decision` is over-confident on sparse data (scoring change, owner's call).

## Current task

UI/UX source-level pass, second sweep: look for what the first sweep's tooling could not see (class names matched as substrings, `\b` matching across hyphens, inline overrides that fight classes).

## Next tasks

1. Remaining surfaces: home screen composition, empty-state wording, `u-*` / `mono` / `num` legacy utilities, inline `style` hex-free but token-free values.
2. Provider failure-injection matrix across every vendor (timeout, 401/403/404/429, malformed JSON, NaN/Infinity).
3. Re-measure idle latency now that the proxy runs in `bom1`.
4. Rebuild and deploy the backend at the final SHA (release procedure), warm it, smoke it.
5. GitHub Actions `keep-alive.yml` still pings retired Render URLs; stale Render docs.
6. Final report in the required format; verdict only after a full pass finds nothing meaningful.

## Resume checklist

1. `git status`, `git rev-parse HEAD`, `git ls-remote origin refs/heads/main`.
2. `curl https://omnisignalterminal.vercel.app/api/build` and compare to the Vercel deployment record.
3. `gcloud run services describe omnisignal-api-poc` (traffic, revision) and `scripts/smoke_cloud_run.py`.
4. Re-hash the three EXP-007 files and compare to the prefixes above.
5. Continue from "Current task".
