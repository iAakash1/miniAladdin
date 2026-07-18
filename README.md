# OmniSignal — Explainable Equity Research Terminal

OmniSignal scores US-listed equities with a deterministic multi-factor engine —
15 factors across five signal families, weighted by regime, gated by macro
stress — and turns the result into a single verdict where **every number is
auditable**: each factor's contribution, every confidence deduction, and all
nine risk components are shown, not summarized away. A language model narrates
the finished scorecard; it never computes or alters a number. Signed-in work
persists to the account — watchlists, portfolio positions, and every analysis
ever run land in a Supabase-backed Research Vault that syncs across devices.

**Live:** [mini-aladding.vercel.app](https://mini-aladding.vercel.app)

Engineering docs: [`docs/SCORING.md`](docs/SCORING.md) (quantitative framework) ·
[`docs/QUANT-REVIEW.md`](docs/QUANT-REVIEW.md) · [`docs/FACTOR-AUDIT.md`](docs/FACTOR-AUDIT.md) ·
[`docs/AUDIT.md`](docs/AUDIT.md) · [`docs/DESIGN-SYSTEM.md`](docs/DESIGN-SYSTEM.md) ·
[`docs/REDESIGN.md`](docs/REDESIGN.md) · [`docs/QA.md`](docs/QA.md)

---

## Architecture (what actually runs where)

```
Browser
  │
  ▼
Clerk authentication (session JWT travels with every terminal request)
  │
  ▼
Vercel — Next.js 16 frontend (dashboard/)
  │  static marketing site + /news (own RSS aggregation route handler)
  │  /terminal behind Clerk auth · Razorpay Pro tier
  │
  │  next.config.ts rewrites /api/* ──────────┐
  ▼                                           ▼
Render — FastAPI backend (api/index.py + src/)
  ├─ Provider layer: 5 vendor-agnostic facades over 13 upstream vendors
  ├─ Scoring engine v2.1 (src/scoring/engine.py — all math lives here)
  ├─ Walk-forward validation (src/services/backtest_service.py)
  ├─ Groq LLM narration (src/services/llm_service.py — optional, never fatal)
  │
  ▼
Supabase PostgreSQL — persistence layer (src/services/database/)
  watchlists · portfolio positions · analysis history · saved reports
  profiles · preferences — the backend is the ONLY database client;
  the browser never talks to Supabase directly
```

- **Vercel serves the frontend only.** There is no serverless Python on Vercel.
- **Render serves the API** (start command in the Render dashboard:
  `uvicorn api.index:app --host 0.0.0.0 --port $PORT`); there is intentionally
  no Procfile/vercel.json in the repo. A GitHub Actions workflow
  (`.github/workflows/keep-alive.yml`) pings `/api/health` every 10 minutes to
  beat free-tier spin-down.
- The frontend proxy target is `BACKEND_ORIGIN` (defaults to the Render
  deployment). `dashboard/src/app/api/news` is the one API implemented inside
  Next.js; app routes take precedence over the `/api/*` rewrite.

### Provider layer (`src/providers/`)

All external market data flows through five vendor-agnostic providers —
components and the scoring engine never call a vendor API directly:

| Provider | Interface | Fallback chain (healthy vendors, in order) |
|---|---|---|
| MarketDataProvider | `get_price` / `get_prices` / `get_series` | Polygon → Finnhub → TwelveData → FMP → MarketStack → yfinance |
| FundamentalsProvider | `get_company` / `get_fundamentals` / `get_analyst_targets` | Alpha Vantage → Finnhub → FMP |
| NewsProvider | `get_news` | NewsAPI → GNews → Yahoo RSS → Tavily |
| MacroProvider | `get_macro` | FRED |
| SearchProvider | `search` | Tavily → Exa |

Every call returns one normalized schema inside a `ProviderResult` envelope
carrying `source`, `sources_consulted`, `confidence` (cross-source agreement
scoring: two vendors within 0.5% → 1.0; >2% apart → 0.5 + disagreement flag;
stale cache → 0.3), and `cached`/`stale` flags. Infrastructure per vendor:
token-bucket rate limiting (`PROVIDER_<NAME>_RPM` override), 6s timeouts,
bounded retries with exponential backoff, cooldown circuit after repeated
failures, health/latency/success statistics (`GET /api/providers/health`).
Requests deduplicate in flight (single-flight); responses cache in a TTL+LRU
store that retains stale entries as the last resort, behind a `CacheBackend`
protocol so Redis can slot in without touching providers. Vendors without keys
self-disable; the keyless yfinance/Yahoo RSS anchors guarantee every chain
resolves.

### Scoring engine (v2.1 — `src/scoring/engine.py`)

All math is Python; the LLM only explains numbers it is given. The full
framework, with the academic literature behind each factor, is in
[`docs/SCORING.md`](docs/SCORING.md); the terminal's Methodology tab documents
the same mechanism for users.

```
prices · fundamentals · news · macro (via providers)
                    ▼
 15 factors in 5 families — momentum, reversal, fundamental, quality, news
   · return-type factors normalized as t-statistics (move ÷ own noise)
   · level-type factors as robust median/MAD z-scores, winsorized
   · a factor missing its inputs is omitted, never estimated
                    ▼
 regime-adaptive sleeve weights (high-vol: momentum halved, reversal funded;
 earnings window: news up-weighted, analyst targets muted)
                    ▼
 probabilistic macro-stress gate — scales down momentum only; value, quality
 and news are never macro-suppressed; the ungated verdict stays visible
                    ▼
 composite score → verdict (Strong Buy … Strong Sell, fixed thresholds)
   · confidence: starts at 100, reduced by named, itemized deductions
   · risk: separate 0–100 score from nine percentile components,
     each shown as weight × percentile = contribution
                    ▼
 Groq gpt-oss-120b narration (validated JSON, cached 5 min, falls back to the
 engine's own rationale — never fails the request, cannot alter a number)
```

The macro readout shown across the product is the Systemic Risk Multiplier
(`src/risk_analysis.py`), computed from FRED data:

| SRM condition | Adjustment |
|---|---|
| Yield curve inverted (10Y − 2Y < 0) | +0.3 |
| Inflation > 4% YoY | +0.2 |
| Fed funds > 5% | +0.1 |
| Clamp | [0.5, 1.6] |

### Validation

`GET /api/backtest/{ticker}` replays the same engine walk-forward on an
expanding window (weekly cadence, no look-ahead) and grades it against a naive
12-1 momentum baseline and buy & hold: IC and rolling IC, hit rate, confusion
matrix, confidence calibration, Sharpe/Sortino/Calmar, drawdown, monthly
returns, per-factor IC and sign stability, factor correlations, and prediction
drift (PSI). The Validation tab renders all of it live for any ticker, with
each metric's definition and interpretation attached.

### Persistence layer (v3.5)

Supabase PostgreSQL, accessed **only** by the FastAPI backend through the
repository layer in `src/services/database/repositories/`. Identity stays
with Clerk: the frontend attaches the Clerk session JWT to terminal API
calls, `src/services/clerk_auth.py` verifies it against Clerk's public JWKS
(no per-request network round-trip), and every table row is scoped by the
verified `clerk_user_id`. Supabase Auth is not used anywhere.

| Table | Purpose |
|---|---|
| `profiles` | One row per Clerk user, auto-created on first login |
| `watchlists` + `watchlist_items` | Cloud-synced watchlists (unique per list+ticker) |
| `analysis_history` | **Every completed `/api/research` run, recorded automatically** — verdict, confidence, risk, composite, and the complete deterministic payload as JSONB |
| `saved_reports` | Bookmarks over history rows, with custom title + notes |
| `portfolio_positions` | Ticker, shares, average cost (unique per user+ticker) |
| `user_preferences` | Theme, default watchlist, analysis horizon |

Security: RLS is enabled on every table with zero policies for the
anon/authenticated PostgREST roles (and their grants revoked), so the public
Supabase surface is inert — only the backend's service-role connection can
touch data, and per-user scoping is enforced in the repositories against the
Clerk-verified user id. Service keys exist server-side only.

Degradation: the database is never load-bearing for analysis. Without
`SUPABASE_*`/`CLERK_*` env vars (or during an outage) persistence endpoints
answer 503, `/api/research` skips history recording with one log line, and
scoring/validation/news are untouched.

The Vault tab (`/terminal/vault`) is the product face of this layer: search,
filter and reopen any past run exactly as generated, bookmark runs with
notes, and compare two runs — verdict, confidence, and per-factor
contribution deltas are computed deterministically by the backend from the
two stored scorecards (`AnalysisRepository.compare`); the LLM is never asked
to calculate a difference.

### Migration workflow

Schema lives in `supabase/migrations/` (SQL, CLI-managed — no dashboard
edits). New migration: `supabase migration new <name>`, write SQL, then
`supabase db push --linked` against the linked hosted project.
`supabase migration list --linked` shows local↔remote state;
`tests/test_persistence.py::TestMigration` statically validates that the
schema keeps its tables, indexes, constraints and RLS statements.

## Environment variables

**Render (backend)**

| Var | Required | Purpose |
|---|---|---|
| `FRED_API_KEY` | yes | Macro series (free: fred.stlouisfed.org) |
| `ALPHA_VANTAGE_KEY` | optional | Fundamentals (free tier: 25 req/day) |
| `NEWSAPI_KEY` | optional | Premium headlines (falls back to Yahoo RSS) |
| `GROQ_API_KEY` | optional | LLM narration (free tier: console.groq.com) |
| `LLM_MODEL` | optional | Default `openai/gpt-oss-120b` |
| `POLYGON_API_KEY` · `FINNHUB_API_KEY` · `TWELVEDATA_API_KEY` · `FMP_API_KEY` · `MARKETSTACK_API_KEY` · `GNEWS_API_KEY` · `TAVILY_API_KEY` · `EXA_API_KEY` | optional | Extra vendors in the provider chains — each self-disables when absent |
| `SUPABASE_URL` | optional | Persistence: hosted Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | optional | Persistence: server-only key (bypasses RLS by design — never ships to a browser) |
| `CLERK_JWKS_URL` | optional | Verify Clerk session JWTs (`https://<instance>.clerk.accounts.dev/.well-known/jwks.json`) |
| `CLERK_ISSUER` | optional | Expected `iss` claim (`https://<instance>.clerk.accounts.dev`) |
| `ALLOWED_ORIGINS` | optional | CORS allowlist, comma-separated |
| `LOG_LEVEL` | optional | Default `INFO` |

All four persistence vars are optional as a group: without them the API runs
with persistence disabled and analysis fully functional.

**Vercel (frontend)**

| Var | Required | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` | yes | Auth |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` | yes | Razorpay Checkout in the browser (key IDs are public by design — this one is *intentionally* exposed) |
| `RAZORPAY_KEY_ID` | yes | Server-only copy of the key ID for order creation — API routes never read `NEXT_PUBLIC_*` values |
| `RAZORPAY_KEY_SECRET` | yes | Order creation + HMAC verification — must **never** be exposed to the browser |
| `BACKEND_ORIGIN` | optional | Backend base for the `/api/*` proxy (defaults to the Render deployment) |
| `NEXT_PUBLIC_SITE_URL` | optional | Canonical URL for metadata |

Keys live **only** in hosting dashboards and local `.env` files (gitignored).
CI runs gitleaks on full history; `pre-commit install` adds the same scan locally.

## Development

```bash
# Backend
pip install -r requirements-dev.txt
cp .env.example .env            # add your FRED key
uvicorn api.index:app --reload --port 8000
python -m pytest tests/ -v      # hermetic by default

# Frontend
cd dashboard
npm install
echo 'BACKEND_ORIGIN=http://127.0.0.1:8000' >> .env.local   # else it uses the live Render API
npm run dev                     # http://localhost:3000
npm test && npm run lint && npx tsc --noEmit && npm run build
```

Opt-in live smoke tests: `OMNISIGNAL_LIVE_TESTS=1 python -m pytest tests/test_live_smoke.py`.

## Project structure

```
├── api/index.py          FastAPI app (thin HTTP layer; sync handlers on purpose)
├── src/
│   ├── scoring/engine.py Scoring engine v2.1 — factors, sleeves, gate, verdict
│   ├── models.py         Pydantic domain models
│   ├── decision.py       Shared verdict/confidence/risk synthesis
│   ├── risk_analysis.py  FRED → Systemic Risk Multiplier
│   ├── sentiment_edge.py Multi-source headline sentiment
│   ├── providers/        Vendor-agnostic data facades + fallback chains
│   └── services/         Backtest, dashboard, screen, memo, news scoring,
│       │                 LLM narration, in-process metrics
│       ├── clerk_auth.py Clerk session-JWT verification (JWKS, cached)
│       └── database/     Supabase client factory + repositories
│           └── repositories/  profiles · watchlists · analysis (+saved
│                              reports + comparison) · portfolio · preferences
├── api/persistence.py    Persistence REST router (Clerk-scoped CRUD)
├── dashboard/            Next.js 16 app (see dashboard/README.md)
├── supabase/migrations/  CLI-managed schema (see Migration workflow)
├── tests/                Pytest suite (215 tests) + opt-in live smoke tests
├── docs/                 Scoring framework, audits, design system, QA log
└── research_vault/       Generated reports (gitignored; one example kept)
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Service + data-source status |
| `GET /api/macro` | SRM + FRED indicators |
| `GET /api/research/{ticker}` | Full pipeline; `?fast=true` skips sentiment + LLM |
| `GET /api/chart/{ticker}?period=` | Daily close/volume series |
| `GET /api/dashboard` | Market intelligence: FRED macro board, breadth, 11 sectors, event calendar (15-min cache) |
| `GET /api/quotes?symbols=` | Batch watchlist quotes (≤25; per-symbol failure isolation) |
| `GET /api/screen?q=` | Ticker/company/theme search — thematic queries are web-grounded and symbol-validated |
| `GET /api/memo/{ticker}` | Evidence-cited investment memo on top of research |
| `GET /api/backtest/{ticker}` | Walk-forward validation (see Validation above) |
| `GET /api/providers/health` | Vendor success %, latency, cooldowns, cache + dedupe stats |
| `GET/POST/PATCH/DELETE /api/watchlists…` | Cloud watchlists + items (Clerk-authenticated) |
| `GET/POST/PATCH/DELETE /api/portfolio…` | Portfolio positions |
| `GET/DELETE /api/history…` | Paginated analysis history with ticker/verdict/date/search filters |
| `GET /api/history/compare?a=&b=` | Deterministic factor-level comparison of two stored runs |
| `GET/POST/PATCH/DELETE /api/saved-reports…` | Bookmarked reports with notes |
| `GET/PATCH /api/preferences` · `POST /api/profile/sync` | Preferences + profile |

Terminal pages: `/terminal` (market dashboard), `/terminal/analyze`,
`/terminal/portfolio` (cloud watchlists + positions), `/terminal/vault`
(research history, saved reports, run comparison), `/terminal/validation`,
`/terminal/methodology`.

Contract note: `verdict`, `macro`, `technicals`, `sentiment` are stable;
`confidence`, `confidence_breakdown`, `risk_level`, `rationale`, `ai`,
`disclaimer` were added additively in v1.1.

### LLM narration layer

`src/services/llm_service.py` calls Groq `openai/gpt-oss-120b` with
deterministic parameters (`temperature=0.2, top_p=1, reasoning_effort=medium,
max 4096 tokens, JSON-object mode`). The model receives the engine's finished
scorecard — recommendation, itemized confidence, risk decomposition, factor
contributions, macro, sentiment — and returns narrative fields only. Output is
`json.loads`-parsed and Pydantic-validated (one corrective retry, then a
deterministic fallback assembled from the engine's own rationale — never a
failed request). The schema has no decision fields, so the model *cannot*
alter recommendation/confidence/risk; engine values are attached verbatim.
Responses cache 5 minutes per (ticker, day, verdict, model, prompt version).

## License

MIT — see LICENSE. Research and education only; not investment advice.
