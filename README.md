# OmniSignal — Multi-Factor Risk & Prediction Engine

OmniSignal scores equities across five weighted signals — momentum, risk-adjusted
return, trend, street expectations and news sentiment — then dampens the result
by a Systemic Risk Multiplier computed from Federal Reserve macro data. The
result is a single, explainable verdict with every number behind it, plus an
optional LLM-written explanation grounded strictly in those numbers.

**Live:** [mini-aladding.vercel.app](https://mini-aladding.vercel.app) ·
Engineering docs: [`docs/AUDIT.md`](docs/AUDIT.md) ·
[`docs/REDESIGN.md`](docs/REDESIGN.md) · [`docs/DESIGN-SYSTEM.md`](docs/DESIGN-SYSTEM.md) ·
[`docs/QA.md`](docs/QA.md)

---

## Architecture (what actually runs where)

```
Browser
  │
  ▼
Vercel — Next.js frontend (dashboard/)
  │  static marketing + /news (own RSS aggregation in a route handler)
  │  /terminal behind Clerk auth · Razorpay Pro tier
  │
  │  next.config.ts rewrites /api/* ──────────┐
  ▼                                           ▼
Railway — FastAPI backend (api/index.py + src/)
  ├─ FRED (macro → Systemic Risk Multiplier)
  ├─ yfinance (prices, technicals)
  ├─ Alpha Vantage (fundamentals, MACD)
  ├─ NewsAPI / Yahoo RSS (headline sentiment)
  └─ Groq LLM (explanation layer — optional, never fatal)
```

- **Vercel serves the frontend only.** There is no serverless Python on Vercel.
- **Railway serves the API.** Deployment config lives in the hosting dashboards
  (Railway start command: `uvicorn api.index:app --host 0.0.0.0 --port $PORT`);
  there is intentionally no Procfile/vercel.json in the repo.
- `dashboard/src/app/api/news` is the one API implemented inside Next.js
  (public market news aggregation); app routes take precedence over the
  `/api/*` rewrite.

### Decision pipeline

All math is Python; the LLM only explains numbers it is given.

```
prices/technicals ─┐
macro (FRED→SRM) ──┼─► RiskAwarePredictionAgent (5 scoring layers ±10)
sentiment ─────────┘        │ raw signal
                            ▼
              SRM dampening (src/prediction_agent.py)
                            ▼
     compute_decision (src/decision.py — shared, single source of truth)
        verdict · confidence · rationale · risk level
                            ▼
        Groq gpt-oss-120b explanation (src/services/llm_service.py)
        validated JSON · cached 5 min · falls back, never fails the request
```

| SRM condition | Adjustment |
|---|---|
| Yield curve inverted (10Y − 2Y < 0) | +0.3 |
| Inflation > 4% YoY | +0.2 |
| Fed funds > 5% | +0.1 |
| SRM ≥ 1.3 | verdict pulled two steps toward Sell |
| SRM ≥ 1.2 | one step |

## Environment variables

**Railway (backend)**

| Var | Required | Purpose |
|---|---|---|
| `FRED_API_KEY` | yes | Macro series (free: fred.stlouisfed.org) |
| `ALPHA_VANTAGE_KEY` | optional | Fundamentals + MACD (free tier: 25 req/day) |
| `NEWSAPI_KEY` | optional | Premium headlines (falls back to Yahoo RSS) |
| `GROQ_API_KEY` | optional | LLM explanations (free tier: console.groq.com) |
| `LLM_MODEL` | optional | Default `openai/gpt-oss-120b` |
| `ALLOWED_ORIGINS` | optional | CORS allowlist, comma-separated |
| `LOG_LEVEL` | optional | Default `INFO` |

**Vercel (frontend)**

| Var | Required | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` | yes | Auth |
| `NEXT_PUBLIC_RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | yes | Pro checkout |
| `API_URL` | optional | Backend base (defaults to the Railway deployment) |
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
npm install && npm run dev      # http://localhost:3000, proxies /api → :8000
npm test && npm run lint && npm run build
```

Opt-in live smoke tests: `OMNISIGNAL_LIVE_TESTS=1 python -m pytest tests/test_live_smoke.py`.

## Project structure

```
├── api/index.py          FastAPI app (thin HTTP layer; sync handlers on purpose)
├── src/
│   ├── models.py         Pydantic domain models
│   ├── decision.py       Shared verdict/confidence/risk synthesis
│   ├── risk_analysis.py  FRED → Systemic Risk Multiplier
│   ├── prediction_agent.py  5-layer scoring + SRM dampening
│   ├── sentiment_edge.py Multi-source headline sentiment
│   ├── news_api.py · alpha_vantage.py   Upstream clients
│   ├── data_pipeline.py  Async CLI pipeline (report generation)
│   ├── report_generator.py  Markdown/PDF reports → research_vault/
│   └── services/llm_service.py  Groq explanation layer
├── dashboard/            Next.js 16 app (see dashboard/README.md)
├── tests/                Pytest suite + opt-in live smoke tests
├── docs/                 Audit, redesign, design system, QA
└── research_vault/       Generated reports (gitignored; one example kept)
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Service + data-source status |
| `GET /api/macro` | SRM + FRED indicators (demo fallback if FRED is down) |
| `GET /api/research/{ticker}` | Full pipeline; `?fast=true` skips sentiment + LLM |
| `GET /api/chart/{ticker}?period=` | Daily close/volume series |

Contract note: `verdict`, `macro`, `technicals`, `sentiment` are stable;
`confidence`, `confidence_breakdown`, `risk_level`, `rationale`, `ai`,
`disclaimer` were added additively in v1.1.

### LLM explanation layer

`src/services/llm_service.py` calls Groq `openai/gpt-oss-120b` with
deterministic parameters (`temperature=0.2, top_p=1, reasoning_effort=medium,
max 4096 tokens, JSON-object mode`). The model receives the engine's finished
decision — recommendation, confidence with itemized breakdown, risk level,
rationale, indicators, macro, sentiment — and returns narrative only:

```
executive_summary · technical_reasoning · macro_reasoning · news_reasoning
risk_reasoning · confidence_reason · key_catalysts[] · key_risks[]
investment_horizon · market_outlook
```

Output is `json.loads`-parsed and Pydantic-validated (one corrective retry,
then a deterministic fallback assembled from the engine's own rationale —
never a failed request). The schema has no decision fields, so the model
*cannot* alter recommendation/confidence/risk; engine values are attached
verbatim. Responses cache 5 minutes per (ticker, day, verdict, model, prompt
version). Latency, retries, cache hits, model and prompt version are recorded
in-process (`src/services/metrics.py`) and logged, not exposed.

## License

MIT — see LICENSE. Research and education only; not investment advice.
