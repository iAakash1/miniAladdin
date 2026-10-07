# OmniSignal — execution checkpoint

Durable state for a long-running, resumable work session. **Read this first
after any pause, limit reset or lost context**, then verify the live values
against the real systems (they may have moved) before continuing. No secrets
belong in this file.

Last updated: 2026-10-08

## Where things are

Values below were verified at code commit `dea3555`. This document's own commit
is documentation only and follows it.

| | |
|---|---|
| Repository | `github.com/iAakash1/miniAladdin` (product name: OmniSignal) |
| Branch | `main` (also mirrored on `redesign/research-terminal`, kept equal) |
| Code commit at last release | `dea3555d71e52b9cf51088ef022441fdd53d28c5` |
| Vercel production | built from that commit, functions in `bom1`; `GET /api/build` names the commit and deployment |
| Production URL | `https://omnisignalterminal.vercel.app` (`mini-aladding.vercel.app` redirects to it) |
| Cloud Run | project `omnisignal-api-aakash-2026`, `asia-south1`, service `omnisignal-api-poc`; revision `omnisignal-api-poc-release-dea3555` at 100%, image digest `sha256:8d681d9dedfd9e7171c160e8a1be270b67f3f7e6b9a189193e891c6b5f89f071` (Cloud Build `bdb0ee14-ffc9-4f91-a591-1f43a3433473`, run as `omnisignal-build`); min=max=1, concurrency 1; anonymous request → 403 |
| Backend source | unchanged since `7671e5a`; `dea3555` is a provenance rebuild so the running image names the commit it was built from |
| Runtime service account | `omnisignal-api-runtime` (no project roles; per-secret `secretAccessor`) |
| Build service account | `omnisignal-build` (Artifact Registry writer on one repo, bucket objectViewer, logWriter) |
| `roles/editor` held by | nobody |
| Rollback | `gcloud run services update-traffic omnisignal-api-poc --region asia-south1 --project omnisignal-api-aakash-2026 --to-revisions=<rev>=100`; targets `release-7671e5a`, `release-d9cbb08`, `release-3d19402`, `release-0e93c4f`. Frontend: Vercel instant rollback |

Release procedure and provenance checks: `docs/CLOUD_RUN_DEPLOYMENT.md`.
Test rules: `docs/TESTING.md`.

## Last verification (production)

- `/api/build` → commit `dea3555…`, ref `main`, environment `production`.
- Backend `/api/health` → commit `dea3555d71e5`, revision `omnisignal-api-poc-release-dea3555`; the traffic split names that revision at 100%.
- `scripts/smoke_cloud_run.py`: 36 passed, 0 failed on the tagged zero-traffic revision, and again on the canonical service URL after the traffic move.
- Public routes `/`, `/learn`, `/news`, `/sign-in`, `/sitemap.xml`, `/robots.txt` → 200. `/terminal/*` → 404 for a signed-out request by design (Clerk `protect-rewrite`).
- First request after the traffic move took 14.3 s (fresh container, as documented), then 0.86 s and 0.36 s.
- Registry: production 0, production_candidate 0, validated 0, experimental 69, retired 34. EXP-007: `NO PRODUCTION CANDIDATE`, passed false, holdout touched false, selected config `9d1651c56782` (`hist_gradient_boosting`).

## Tests (last full runs)

- Frontend on `dea3555`: 714 passed, 0 failed; typecheck, lint and production build clean.
- Backend: 3,328 passed, 0 failed, 0 skipped (three consecutive runs at `7671e5a`). **Not re-run for `dea3555`: no backend file has changed since** (`git diff --name-only 7671e5a HEAD` lists only `dashboard/` and this document).
- Credential-free smoke: 40 passed, 0 failed (at `7671e5a`).

## Research firewall

EXP-007 verdict `NO PRODUCTION CANDIDATE`; holdout untouched; registry production 0, candidates 0, validated 0.
Fingerprint prefixes (sha256): `final_selection.json` `a69f54e5a309ec3f`, `checkpoints/configs.jsonl` `d0251b4cc4e21d03`, `search.json` `9ada5cda42234782`. Re-hashed after every commit in this pass; unchanged. No commit since `7671e5a` touches a path outside `dashboard/` other than this document.

## UI pass (source-level; no browser has been opened)

Done and deployed, each with a guard test in `dashboard/tests`:

- **Design scales**: type, weight, tracking, radius, motion, easing, z-index layers (`--z-*`), spacing rhythm (`--gap`, previously undefined for a month), colour tokens (18 legacy alias names retired; 692 uses migrated).
- **Contrast**: computed from the token file for every text token on every surface in both themes (≥4.5:1), text on accent (`--on-accent`), field and checkbox outlines (`--rule-control`, ≥3:1), browser-chrome colour per theme.
- **Buttons, focus, accessibility floor**: one button family, one focus ring, reduced-motion catch-all, 24px targets (36px on touch), forced-colors states, 16px text fields on touch, every `main` a skip-link target, form controls named, graph nodes and selectable rows keyboard-operable.
- **Status and badge grammar**: `Status` has 15 states (adds retired, paper, error, warning, info); `Badge` is the one verdict chip; the legacy `.badge` and the style-less `.pal-badge` are gone; a research model is no longer titled "Deployed model".
- **Search palette**: focus returns to the opener, Tab stays inside, results announced, a failed search is not reported as empty, ticker-first rows with an active accent bar. **Inspectors** take focus and give it back; Escape yields to a modal above.
- **Charts**: laid out at measured width (one unit per CSS pixel) with 10px axis text; hover maps to the right observation at any panel width; a vertical swipe scrolls the page.
- **Numbers**: every number and date names its locale; one `fmtSigned` replaces 45 hand-built sign rules; flags read yes/no; times in UTC.
- **Legacy families retired**: `.input`, `.label`, `.data-table`, panel padding and heading sizes come from classes; 386 unreachable CSS classes (63KB) and 6 keyframes deleted; one fade, one pulse, one skeleton.
- **Structure and copy**: no panel inside a panel; no invalid HTML nesting; per-symbol page titles; one name ("Research log") for the saved-research page; shortcuts printed for the reader's platform; form errors named and announced.
- **Defects found on the way and fixed**: `--gap` undefined; `@keyframes fade-in` defined twice; a selector-list accident that unstyled the shell drawer header for one deploy (fixed within the hour, guarded by a test); 9px/8.5px graph labels; white-on-blue selection at 2.9:1; near-black text on the light accent at 3.4:1; disclaimer in the disabled ink.

Not verified (needs a browser or a signed-in session): rendered layout, the client-side resize path of the charts, the signed-in `/terminal/*` screens, focus behaviour in a real browser.

## Known defects and external limits

- **NewsAPI key is invalid** (a UUID-shaped value, not a 32-hex key; NewsAPI answers `apiKeyInvalid`). Reported honestly as `AUTH_FAILURE`; needs a real key from the account owner.
- **Clerk runs a development instance** (`*.clerk.accounts.dev`; responses carry `dev-browser-missing`). A production Clerk instance and domain is the owner's call.
- **`keep-alive.yml` pings the Render rollback target and its inference service every 10 minutes.** Both still answer (cold start 33–43 s). Production on Cloud Run configures no inference URL and does not use either. Keep for rollback readiness, or retire the workflow and the Render docs: the owner's call.
- Search results show no exchange: the screen API returns symbol, name and provider only; adding it is a backend change.
- Responsive breakpoints are tuned per component (15 distinct `max-width` values) and about 190 inline spacing literals are off the 4px grid; not normalised, because that cannot be checked without rendering.
- Eight hover rules move an element (`translateY`) and are not gated on `(hover: hover)`, so a tap on a touch screen can leave the lift in place.
- Yahoo RSS 429 from Cloud Run egress; Tiingo / Finnhub partial 403 (plan limits).
- Concurrency 1 on one instance: a long research run (~20–35 s) queues the next request.
- First request after any release meets a fresh container; warm it (see the deployment doc).
- Legacy `compute_decision` is over-confident on sparse data (scoring change, owner's call).

## Not done in this session

- Provider failure-injection matrix across every vendor (timeout, 401/403/404/429, malformed JSON, NaN/Infinity): backend work, not started.
- Cache and concurrency stress; exhaustive search tests beyond the existing share-class cases.
- Idle-latency re-measurement through the `bom1` proxy after a 10-minute idle gap.

## Resume checklist

1. `git status`, `git rev-parse HEAD`, `git ls-remote origin refs/heads/main`.
2. `curl https://omnisignalterminal.vercel.app/api/build` and compare to the Vercel deployment record.
3. `gcloud run services describe omnisignal-api-poc` (traffic, revision) and `scripts/smoke_cloud_run.py <service-url> <commit-prefix> <revision>`.
4. Re-hash the three EXP-007 files and compare to the prefixes above.
5. From `dashboard/`: `node --import tsx --test tests/*.test.ts`, `npx tsc --noEmit`, `npm run lint`, `npm run build`.
