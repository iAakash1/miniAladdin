# Final completion audit

Audit date: 2026-09-18. Repository: `iAakash1/miniAladdin`.

## 2026-09-19 continuation result

This continuation preserved the preregistered EXP-008 exactly. The literature
and local-data audit is a separate EXP-009 design package; neither experiment
was trained or run, EXP-007 was not rerun, and the sealed holdout was not read.

### Product disposition

| Area | Status | Evidence / remaining boundary |
|---|---|---|
| Decision Quality | COMPLETE | Deterministic API field plus Beginner, Intermediate and Advanced rendering; invariance/API/service tests pass |
| Book / portfolio artifact | COMPLETE | Committed EXP-006 runtime artifact builds the default book; expected deployment failures return typed 200 states including `SCHEMA_MISMATCH`, `TARGET_MISSING`, `MODEL_MISSING`, and `COVARIANCE_UNAVAILABLE` |
| Paper code path | COMPLETE | Anonymous is 401, authenticated non-owner is 403, configured owner is 200; broker host remains restricted to Alpaca paper |
| Current signed-in Paper access | BLOCKED_EXTERNAL | The deployed `PAPER_TRADING_OWNERS` must contain the current Clerk subject from the same issuer; no authorization was weakened or id hard-coded |
| Route/build coverage | COMPLETE locally | Next production build compiled and enumerated all application routes; the public Playwright build check passed |
| Authenticated browser journey | BLOCKED_EXTERNAL | No real Clerk storage state was supplied; five signed-in Playwright journeys were deliberately skipped |
| Deployment smoke | COMPLETE for unauthenticated probes | Quant status/methods/book, Paper status, recommendations, Explore, frontend build and inference health returned 200; backend health succeeded on one read-only retry after a cold-start timeout |

### Research disposition

- EXP-006 has weak positive rank signal (Rank IC 0.02895; Newey-West
  t-statistic 2.66), but 20.15x annual turnover makes the 10 bp result
  uneconomic (net Sharpe -0.102). This is not a zero-signal result.
- The selected EXP-006 model uses 27 price/volume/volatility/macro features,
  while the frozen store has analyst, earnings, fundamental, and options
  families. However, EXP-005 already found that its first additive versions of
  those families underperformed the same base. The conclusion is therefore
  underutilization plus weak first ablations, not “untested rich data.”
- Existing analyst, earnings, fundamental, and options feature builders and
  PIT tests were retained. No duplicate ingestion or feature module was added.
  Consensus analyst revisions are usable; fundamentals remain exposed to
  restatement-vintage risk; options history/coverage is limited; analyst-level
  stickiness, target revisions, put/call volume and open interest are absent.
- The survey reviews 33 primary-source works, including 24 dated 2024--2026,
  and records a required-field replication register, official/author code,
  data-family matrix, Qlib comparison, five replication candidates, and seven
  EXP-009 candidate designs.
- Recommended EXP-009 order: one fixed turnover-aware buffer, date-grouped
  learning-to-rank on identical folds/data, then one isolated consensus-
  revision arm. Neutralization waits for a PIT security master. Options,
  graph, and text are deferred.

### 2026-09-19 verification record

- Python: **2,629 passed, 5 skipped**, twice consecutively; **141 warnings**
  each run from covered numerical edge cases/deprecations.
- Dashboard: **568 passed, 0 failed**.
- TypeScript, ESLint, and production build: clean; build generated 60 static
  pages and compiled every dynamic route.
- Playwright: **1 passed, 5 skipped** without a signed-in storage state.
- Deployment smoke: eight endpoints passed directly; backend health passed on
  a read-only retry after its initial 60-second timeout. Authenticated Paper
  reads/preview were skipped because `CLERK_SMOKE_TOKEN` was unset.

## Product result

OmniSignal now has three presentation-only experiences over the same research
and scoring APIs:

| Experience | Entry | Density | Decision source |
|---|---|---|---|
| Beginner | `/beginner` | Plain-language signal, confidence, risk, reasons, ideas and evidence health | Shared `/api/research/{ticker}` response |
| Intermediate | `/intermediate` | Signal plus factors, valuation, performance, evidence and real agent checks | Same shared response and agent graph |
| Advanced | `/terminal/command` | Complete research terminal, experiments, provenance and operations | Same shared services and artifacts |

The stored preference accepts `beginner`, `intermediate`, or `advanced`. It is
not an entitlement or role. The scoring modules do not receive the preference,
and the decision-invariance tests reject experience vocabulary inside scoring.

## Route audit

Public and onboarding routes:

| Routes | Result |
|---|---|
| `/`, `/news`, `/learn`, auth, SEO routes | Public by explicit middleware matcher |
| `/start` | Protected chooser with all three modes |
| `/explore` | Protected, renders the shell and company links for the stored mode; `?category=` selects the requested ranking |
| `/evidence/[ticker]` | Protected, experience-aware claim/evidence inspector |

Beginner routes:

| Route | Result |
|---|---|
| `/beginner` | Search, market context, Top Ranked Ideas, performance, trending and thematic Explore links |
| `/beginner/company/[ticker]` | Plain-language analysis, Ask, clickable evidence ids, Evidence Health, What-if, watch, compare and paper preview |
| `/beginner/watchlist` | Real browser-persisted named watchlists and live quotes |
| `/beginner/portfolio` | Authenticated positions and server-computed portfolio intelligence |
| `/beginner/compare` | Two-company vendor/fundamental comparison |

Intermediate routes:

| Route | Result |
|---|---|
| `/intermediate` | Market, ideas, performance and trending at medium density |
| `/intermediate/company/[ticker]` | Scorecard, factor contributions, valuation, Evidence Health, real agent run, Ask, What-if and actions |
| `/intermediate/watchlist` | Real watchlist surface |
| `/intermediate/portfolio` | Positions, concentration, risk coverage and performance |
| `/intermediate/compare` | Two-company comparison |

Advanced terminal destinations are declared once in `dashboard/src/lib/destinations.ts`:

- Terminal: command, security, market, watchlists, paper.
- Portfolio: book, risk, covariance, performance.
- Research: factors, signals, models, relationships, compare, difference.
- Evidence: evidence, **agent runs**, gates, experiments, calibration.
- Data: data, providers, provenance, handbook.
- Record: memos and timeline.

Legacy aliases intentionally redirect: `/terminal` to command,
`/terminal/models` to Models, `/terminal/factors` to Factor Lab,
`/terminal/validation` to Evidence/validation, and `/quant` to Evidence.
The dead Beginner `/terminal/watchlists` and leaked `/terminal/portfolio` links
were removed.

## Action audit

| Action | Beginner | Intermediate | Advanced | Control |
|---|---:|---:|---:|---|
| Analyze a ranked security | yes | yes | yes | Experience-aware company link |
| Compare | yes | yes | yes | Same comparison arithmetic and comparability rules |
| Watchlist | yes | yes | yes | Shared local symbol store |
| Paper trade | preview + confirm | preview + confirm | preview + confirm | Action appears only when paper is configured; broker module refuses every host except Alpaca paper |
| Ask | yes | yes | report surface | Response cites evidence ids; ids open claim/evidence detail |
| Agent checks | evidence summary | embedded real run | navigable Agent Runs workspace | No simulated pipeline state |

Paper E2E stops at the broker preview. Placement always requires the second,
explicit `place paper order` action.

The 2026-09-18 Paper-auth and Book-runtime incidents, their exact root causes,
cache isolation contract, deployable EXP-006 artifact and regression coverage
are recorded in `PRODUCTION_INCIDENTS_2026-09-18.md`.

## Models root-cause fix

The experiment artifact was populated. The apparent all-dash repetition came
from the regime selector defaulting to the first model alphabetically,
`baseline_historical_mean`, while the selected label named
`gradient_boosting` as its best model. The selector now defaults to that best
model. The redundant specification caveat is rendered once, and the label
table is explicitly named Model / target selection. No experimental artifact
was rewritten.

## Evidence and agent visibility

- `EvidenceHealth` is a reusable component showing completeness, source count,
  freshness and critical conflicts from the analysis provenance payload.
- Ask citations are links, not decorative identifiers.
- `/terminal/agents` and `/terminal/agents/[ticker]` run the actual specialist
  graph and show measured latency, statuses, claims, evidence, reconciliation,
  validation, critic output and degraded inputs.
- Advanced company reports link directly to the run and include Evidence
  Health. Intermediate company pages embed the same real run.

## Command center

The command center now combines market and sector movement, watchlist and
recent names, high-conviction policy results, Top Ranked Ideas, performance
leaders, portfolio intelligence, provider health, inference state, registry
state, agent-run access, research status and the paper account. Missing or
unavailable data remains explicit; it is never converted to zero or a healthy
state.

## Factor Lab shared jobs

Factor Lab uses `JobStore` for work records and completed results. The
lifecycle includes atomic claim/reclaim, owner worker id, unique token,
generation and attempt, an independent heartbeat, stale-owner recovery,
monotonic progress, bounded workers, success/failure/abandoned/cancelled
terminal states, deadline handling, failure cooldown and token-specific shared
results. A stale worker cannot advance or finish a reclaimed attempt.

The in-process adapter and optimistic-locking fake Redis adapter are covered by
tests. The pinned Redis client is installed.

A real Redis verification was run and completed: Docker Desktop was not
available, so `redis` was installed via Homebrew and run as an ephemeral local
server instead (`redis 8.10.2`, no persistence, stopped and removed after the
check). `REDIS_URL` correctly selected `RedisJobStore`, `put`/`get`/`delete`
round-tripped, and eight real threads hammering one key through `mutate()`
with no delay never produced a torn or partial record — every successful
write was complete and self-consistent. Under that same artificial contention,
most callers exhausted the 8-attempt retry bound and received a safe retryable
error rather than a lost update, which is the bound behaving as designed
against real load rather than the simplified fake. Full detail in
`BACKGROUND_JOBS.md`.

Not run: a genuine two-process claim against one shared real Redis (two
separate OS processes or Render workers, not two threads in one process).
Production must complete that verification per `RENDER_SETUP.md`'s own
checklist step 5 the first time `REDIS_URL` is supplied there.

## Deployment diagnostics and domains

The operator diagnostics display frontend, backend and inference deployment
SHAs and show `VERSION MISMATCH` when known values differ. The inference
`/health` SHA is its service deployment revision, not the model artifact's
training revision.

Canonical public URL: `https://mini-aladding.vercel.app`.

The canonical URL currently redirects to
`https://omnisignalterminal.vercel.app`. That proves the two domains are
attached to the same public deployment path but also exposes Vercel
project/alias drift. Keep the canonical URL in metadata and documentation;
consolidate the domains in the existing Vercel project rather than creating a
third project. The non-canonical alias remains in CORS until consolidation is
complete.

## Security and research invariants

- Protected pages and APIs continue to use Clerk middleware and backend token
  verification. No production auth bypass was introduced.
- Admin diagnostics remain backend-permission gated and ordinary signed-in
  accounts receive 403.
- Secrets are never returned by diagnostics; only configured/reachable state.
- EXP-007 was not rerun, the holdout was not touched, no experimental model
  was promoted, and frozen research artifacts were not modified.

## Verification record

Run on 2026-09-18, on top of baseline `0337db9` (already deployed to the
primary Render backend before this pass began):

- Python suite: **2586 passed, 3 skipped**, run twice consecutively, identical
  both times. No flake.
- Dashboard unit tests: **552 passed**.
- `npx tsc --noEmit`: clean. (No `npm run typecheck` script exists in
  `package.json`; this is the equivalent direct invocation.)
- `npm run lint`: clean, zero output.
- `npm run build`: clean production build, zero errors or warnings.
- Playwright (`npx playwright test`, real Desktop Chrome channel, no storage
  state, no external base URL supplied): **1 passed** (the unauthenticated
  `/api/build` revision check), **5 skipped** — honestly, per the spec's own
  `test.skip()` guards, not a silent no-op. No authenticated browser journey
  was run or claimed as run in this environment.
- Real Redis: verified against an ephemeral local server, not only the fake
  adapter. See the Factor Lab section above and `BACKGROUND_JOBS.md`.

Not run in this environment: an authenticated live-browser walkthrough of the
three-experience-mode demo flow (no Clerk session available here), and a
two-process real-Redis claim test. Both are genuine open items, not concealed
gaps — see "Remaining limitations" below and `RENDER_SETUP.md`.

## Remaining limitations

Genuine operational gaps, stated rather than closed by declaration:

- **No authenticated browser session was available in this environment.**
  The demo flow described for mentors — sign in, choose a mode, open a stock,
  ask a question, preview a paper order, switch modes, open Models — has been
  verified by reading and testing every component it touches, and by the
  Playwright spec's own signed-in journeys, but not by an actual authenticated
  walkthrough here. Run `PLAYWRIGHT_STORAGE_STATE=<path> npx playwright test`
  with a real signed-in browser state (or point `E2E_BASE_URL` at the
  deployed frontend with a session) before the first mentor demo.
- **Real Redis was verified in-process, not across two OS processes.** See
  above and `BACKGROUND_JOBS.md`. `RENDER_SETUP.md` step 5 covers the
  production check.
- **No live Vercel/Render deployment check is claimed by this document.**
  Whether the pushed commit has actually deployed is a separate, later
  verification — a git push landing on `origin/main` does not mean Render or
  Vercel has finished redeploying from it.
