# OmniSignal — Project Constitution

Read this first. It governs every change, by anyone, in any session.

## What this is

An explainable equity research terminal: a deterministic multi-factor
scoring engine (15 factors, 5 sleeves, macro-stress gate) whose every number
is auditable, wrapped in a calm, professional, education-first product.
Split app: Next.js 16 frontend (`dashboard/`, Vercel), FastAPI backend
(`api/` + `src/`, Render), Supabase Postgres persistence (backend-only
client), Clerk auth (JWT verified backend-side against JWKS).

## Non-negotiable principles

1. **Deterministic engines own every number.** Scores, verdicts, confidence,
   risk, deltas, valuations — all computed in Python engines
   (`src/scoring/`, `src/services/`). The LLM (Groq gpt-oss-120b) narrates
   finished scorecards; it never computes, never decides, and its schema has
   no decision fields.
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
6. **The backend is the only database client.** The browser never talks to
   Supabase. Every row is scoped by verified `clerk_user_id`. Supabase Auth
   is not used.
7. **Additive API evolution.** The v1.x research contract is stable; new
   blocks are additive, optional, and never fatal to the request.
8. **Calm, professional UI.** The token system in
   `dashboard/src/app/globals.css` is the design language (documented in
   docs/DESIGN-SYSTEM.md). Color states facts about data; density over
   decoration; progressive disclosure; no gradients/glow/motion-for-motion.
   Design test for every decision: does this help someone think more clearly?
9. **Routing mirrors the domain.** Research has permanent, deep-linkable
   URLs. Back must always mean "back".
10. **Education appears where curiosity occurs.** Every metric, indicator,
    and series gets a MetricEntry in the appropriate glossary
    (`dashboard/src/lib/*Glossary.ts`) rendered through MetricExplainer.

## Process discipline

- **Audit before building; notes before code.** Never redesign for its own
  sake; preserve what already feels correct.
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
- Roadmap and priorities: docs/ROADMAP-v4.md (v5 charter section). Provider
  ground truth: docs/PROVIDERS-AUDIT.md. Quant framework: docs/SCORING.md.
