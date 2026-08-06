# OmniSignal — Project Constitution

Read this first. It governs every change, by anyone, in any session.

## What this is

An explainable equity research terminal: a deterministic multi-factor
scoring engine (15 factors, 5 sleeves, macro-stress gate) whose every number
is auditable, wrapped in a calm, professional, education-first product.
Split app: Next.js 16 frontend (`dashboard/`, Vercel), FastAPI backend
(`api/` + `src/`, Render), Supabase Postgres persistence (backend-only
client), Clerk auth (JWT verified backend-side against JWKS).

Beneath the product sits the research layer: a point-in-time factor panel
(`src/panel/`, Parquet snapshots) recording what each factor was worth on
each date **and when that was knowable** — the substrate that makes the
engine evaluable rather than merely explainable.

## Non-negotiable principles

1. **Deterministic engines own every number.** Scores, verdicts, confidence,
   risk, deltas, valuations — all computed in Python engines
   (`src/scoring/`, `src/services/`). The LLM (Groq gpt-oss-120b) narrates
   finished scorecards; it never computes, never decides, and its schema has
   no decision fields.
1a. **One definition per number; optimizations prove equality.** A second
   implementation of shared semantics (a vectorized path, a cache, a port)
   is permitted only with an **oracle test** asserting it equals the
   original to floating-point round-off, and only inside a domain where that
   equality is provable. Outside that domain it must refuse loudly, never
   approximate — a fast path that silently disagrees with production is
   worse than no fast path. `src/panel/factors.py` is the reference pattern.
2. **Evidence before conclusions.** Every conclusion shown to a user traces
   to a number they can verify; every metric carries context (what/why/
   healthy/dangerous/how-we-use-it) via the Learn More glossary system.
3. **Engines over pages.** Business logic lives in backend engines exposing
   structured output; React components render and explain, never calculate.
4. **Compute locally before calling APIs.** Anything derivable from data in
   hand (indicators, statistics, deltas) is computed in-process. See
   docs/PROVIDERS-AUDIT.md before touching any vendor.
5. **Provider abstraction is sacred.** No component or engine calls a vendor
   directly; everything flows through `src/providers/` facades (fallback
   chains, caching, rate limits, single-flight). No component knows which
   vendor answered.
5a. **Independent upstream calls are fanned out, never queued.** Sequential
   provider loops are a latency bug: the dashboard's 32 of them cost 43.6 s
   cold and 0.000 s warm, so the entire cost fell on cold-cache users. Use
   `providers.parallel.map_concurrent` — **bounded** (`try_acquire` is
   non-blocking, so an oversized burst converts slow successes into instant
   failures and silently demotes answers to a worse vendor), input-ordered,
   failure-isolating. Never nest fan-outs. docs/CONCURRENCY.md.
6. **The backend is the only database client.** The browser never talks to
   Supabase. Every row is scoped by verified `clerk_user_id`. Supabase Auth
   is not used.
7. **Additive API evolution.** The v1.x research contract is stable; new
   blocks are additive, optional, and never fatal to the request.
7a. **Research data is point-in-time or it is fiction.** Any stored factor,
   score or signal carries both the date it *describes* (`date`) and the
   date it became *knowable* (`as_of`); every historical read filters on
   `as_of <= T`. Factor computation for a date receives a window truncated
   at that date, so look-ahead is impossible by construction rather than by
   discipline. Research snapshots are immutable, content-addressed and
   verifiable — never edited in place. Missing inputs produce `NULL`, never
   `0.0`: absent is not neutral. See docs/PANEL.md.
8. **Calm, professional UI.** The token system in
   `dashboard/src/app/globals.css` is the design language (documented in
   docs/DESIGN-SYSTEM.md). Color states facts about data; density over
   decoration; progressive disclosure; no gradients/glow/motion-for-motion.
   Design test for every decision: does this help someone think more clearly?
9. **Routing mirrors the domain.** Research has permanent, deep-linkable
   URLs. Back must always mean "back".
1b. **Factors earn their place; they are not asserted into it.** The panel is
   where a factor is *tested*, the engine is where survivors go. A new factor
   is added to `src/panel/`, run through the Factor Lab, and enters
   `src/scoring/engine.py` only if the evidence supports it. Plausibility, a
   citation, and an existing implementation are not evidence. A failed factor
   stays visible in the lab — deleting it would hide the result. `asset_growth`
   is the worked example (docs/FACTOR-LAB.md §11).
9a. **Evidence is shown, including when it is unflattering.** Any view that
    reports a statistic reports its limitations beside it, in the payload
    rather than in documentation — overlap corrections with the uncorrected
    value for comparison, multiple-comparison exposure, survivorship bias,
    sample size. A negative or insignificant result renders as neutrally as a
    positive one. A research tool whose UI only looks good when the answer is
    favourable is a marketing tool. docs/FACTOR-LAB.md.
10. **Education appears where curiosity occurs.** Every metric, indicator,
    and series gets a MetricEntry in the appropriate glossary
    (`dashboard/src/lib/*Glossary.ts`) rendered through MetricExplainer.

## Process discipline

- **Audit before building; notes before code.** Never redesign for its own
  sake; preserve what already feels correct.
- **Think in systems, not tickets.** Don't improve a table — extend the
  table system. Don't improve a section — extend the Research Section
  framework (`CompanyReport` sections + section map). Every solution should
  be the reusable version of itself; one-off implementations are debt.
- **The bar test, before every commit:** if this were Bloomberg's,
  Palantir's, or Stripe's codebase, would this change raise or lower the
  overall quality bar? If it lowers it even slightly, refine before
  committing.
- **Product review after every major implementation.** Stop and review the
  product, not the code: would an analyst enjoy this daily? Would a
  Bloomberg user understand it instantly? Would a principal engineer
  respect the architecture? If not clearly yes, keep refining.
- **Complete increments only.** Each change lands with: backend tests
  (`.venv/bin/python -m pytest tests/ --ignore=tests/test_live_smoke.py`),
  frontend QA (`npx tsc --noEmit && npm run lint && npm test &&
  npm run build` from `dashboard/`), and a production-stability check after
  deploy. Nothing ships half-done.
- **Deploys are automatic on push** (Render + Vercel via GitHub). Verify the
  backend via the `/api/health` version marker; bump the app version on
  releases so deploys are remotely detectable.
- **Workspace hazard:** the parent folder contains stray copies of
  `dashboard/`, `src/`, `api/`. The repo root is `miniAladdin/` — always use
  absolute paths.
- **State limitations, never paper over them.** Survivorship bias, vendor
  history depth, unpopulated factors, disappointing benchmark numbers — all
  documented in the open, next to the thing they limit. A known, named
  limitation is engineering; a hidden one is a liability. Do not report a
  measurement you have not taken, and do not claim a speedup you have not
  measured (docs/PANEL.md §5 and §7 are the pattern).
- **Measure from the system, not from a script.** Every seam worth an
  optimisation decision is instrumented through `src.observability`
  (percentiles, never means — the mean of a bimodal latency distribution
  describes nothing that happened). If answering "where did the time go?"
  needs a throwaway script, instrument it instead. Labels are closed sets;
  never label by ticker. docs/OBSERVABILITY.md.
- **Profile before optimizing; mutate before trusting a test.** Every
  performance claim carries a benchmark, every correctness claim a test that
  has been shown capable of failing. Mutation testing is the check on the
  check: if a deliberate bug survives the suite, the suite is decoration.
  Surviving mutants are either fixed with new tests or documented as
  provably unreachable — never ignored.
- **Delete inert code.** Arithmetic or guards that cannot change any result
  are removed, not kept as decoration; they mislead the next reader into
  believing a case is handled. If something must stay for symmetry with
  another module, label it as unreachable and say why.
- **Where to look:** roadmap and priorities in docs/ROADMAP-v4.md (v5
  charter section); provider ground truth in docs/PROVIDERS-AUDIT.md; quant
  framework in docs/SCORING.md; research/panel layer in docs/PANEL.md;
  concurrency model in docs/CONCURRENCY.md; instrumentation in
  docs/OBSERVABILITY.md; cross-sectional research in docs/FACTOR-LAB.md. Engineering history and known debt: CHANGELOG.md.
