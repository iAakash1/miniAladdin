# OmniSignal — Engineering Audit

July 3, 2026. Scope: entire repository (backend `api/` + `src/`, frontend `dashboard/`,
tests, scripts, docs, git history, live deployments). Every finding cites file and
line numbers from the audited revision (`11b95c4`).

---

## 0. Fact-check of the externally supplied audit

Several claims in the review this audit responds to were tested against reality
before acting. Results:

| Claim | Verdict | Evidence |
|---|---|---|
| "Live site returns 404 / no deployment" | **False** | `https://mini-aladding.vercel.app/api/news` served live JSON (168 articles) at 2026-07-02 18:44 UTC, after the `vercel --prod` deploy logged `✓ Ready`. |
| "Seven overlapping deployment docs at root (DEMO_MODE.md, QUICK_DEPLOY.md, …)" | **False** | None of the seven files exist anywhere in the repo (`find` across all folders). Root has one `README.md`. |
| "README references a vercel.json that doesn't exist" | **True** | `README.md` ("Vercel auto-detects the `vercel.json` configuration") — no such file in the repo. Deployment is actually configured in the Vercel/Railway dashboards. |
| "A live FRED key is reachable in git history" | **No live key found** | 16 commits across all refs; `git log --all -p` and a full blob scan (`git cat-file --batch`) matched zero key-shaped strings (`fred… [0-9a-f]{20,}`, `sk-…`, `sk_live_…`, `rzp_live_…`, `AIza…`, `ghp_…`). History was squashed to an orphan root (`6d068c4`) during a prior cleanup and the FRED key was rotated then. GitHub's cache may retain pre-squash blobs, but the key they contain is the rotated, dead one. Defense-in-depth still added (see fixes). |
| "47 commits on GitHub vs 16 local = suspicious rewrite" | **Expected** | The rewrite was deliberate (documented security cleanup + key rotation). Not new information; no action required beyond the scanner below. |
| CORS `*` + credentials, bare excepts, `>=` pins, vault artifacts, root `test_api.py` | **All true** | Detailed below. |

---

## 1. Findings

### Critical

**C1 — Invalid CORS configuration** — `api/index.py:36-42`
`allow_origins=["*"]` combined with `allow_credentials=True` violates the Fetch
spec (browsers refuse to honor `Access-Control-Allow-Origin: *` on credentialed
requests). Today no browser calls Railway directly (the Next.js proxy is
same-origin), which is why nothing visibly breaks — but the config is wrong,
signals carelessness, and becomes a real hole the moment credentials are added.
**Fix:** explicit allowlist from an `ALLOWED_ORIGINS` env var; `allow_credentials=False`
(nothing cookie-based crosses this boundary).

**C2 — No secret-scanning guardrail** — repo-wide
A real key reached a committed README once before (since scrubbed + rotated).
Nothing prevents a recurrence. **Fix:** gitleaks in CI
(`.github/workflows/gitleaks.yml`) + local `pre-commit` hook config.

### High

**H1 — Error details leak to clients & failures are silent** —
`api/index.py:178, 205, 249`; `src/risk_analysis.py:169`
`except Exception as e: … str(e)` returns library internals (paths, upstream
messages) to API consumers, and `print()` is the only server-side trace. A
failing FRED call silently degrades to demo numbers with no operational signal.
**Fix:** module loggers with `logging.exception(...)`; generic client messages;
demo-mode fallbacks kept but logged loudly. Response *shapes* unchanged (the
dashboard normalizers depend on them).

**H2 — Two diverging implementations of the decision logic** —
`api/index.py:210-211` vs `src/data_pipeline.py:60-137`
The API's verdict is `technicals.risk_adjusted_signal` only. The CLI/report
pipeline's `_compute_verdict()` additionally applies sentiment adjustment and
computes confidence + rationale. Same product, two brains — they have already
drifted (the API returns no confidence at all). **Fix:** extract
`_compute_verdict` into a shared pure function (`src/decision.py`), used by both;
API response gains additive `confidence` / `risk_level` / `rationale` fields.
The existing top-level `verdict` value is left byte-compatible.

**H3 — Blocking I/O inside `async def` endpoints** — `api/index.py:69, 87, 113, 225`
Every endpoint is declared `async` but calls synchronous `fredapi` / `yfinance` /
`requests` code directly, blocking the event loop: one slow FRED call stalls
*every* concurrent request. FastAPI's threadpool exists precisely for this.
**Fix:** declare the handlers as plain `def` (FastAPI runs them in the
threadpool), and run macro + technicals concurrently inside `/api/research`
(they are independent; sentiment stays after technicals because it reuses the
resolved company name). `src/data_pipeline.py` already proves the parallel
pattern — the API just never adopted it.

**H4 — Unpinned dependencies** — `requirements.txt:1-14`
All `>=` ranges plus a completely unpinned `fredapi`. A future `pip install`
on Railway can pull a breaking major (pandas 3, pydantic 3…) and take prod down
on redeploy. **Fix:** exact pins.

### Medium

**M1 — 19 broad `except Exception` blocks** — across `api/index.py` (5),
`src/sentiment_edge.py` (3), `src/risk_analysis.py` (3), `src/alpha_vantage.py` (2),
`src/news_api.py` (2), `src/data_pipeline.py` (3), `src/prediction_agent.py` (2, print-only)
Individually defensible (external APIs fail in creative ways), but combined
with `print()` logging they hide real bugs. Addressed together with H1.

**M2 — `print()` as the only logging** — 19 call sites (same files as M1, plus
`src/report_generator.py:190, 195, 210`)
No timestamps, no levels, no way to filter in Railway logs. Replaced with
`logging` (H1 fix).

**M3 — No timeouts on FRED/yfinance calls** — `src/risk_analysis.py:69-86`,
`src/prediction_agent.py:57-63`
`requests`-based clients set timeouts (`alpha_vantage.py:79`, `news_api.py:87`,
`sentiment_edge.py:128, 158` — good), but `fredapi` and `yfinance` calls have
none; a hung upstream holds a threadpool slot indefinitely. Mitigated by
endpoint-level concurrency fix; full fix (wrapping fredapi in a session with
timeout) noted as follow-up.

**M4 — Railway origin is publicly callable, unauthenticated** — deployment
The Next.js proxy adds Clerk gating, but `minialaddin-production.up.railway.app`
answers anyone, so free-tier FRED/AV/NewsAPI quotas can be drained directly.
Acceptable for a portfolio project; documented with a recommended shared-secret
proxy header as follow-up (not implemented — would break direct local dev).

**M5 — Generated reports committed to git** — `research_vault/NVDA_omnisignal_20260314_*.{md,pdf}`
Pipeline output, not source. **Fix:** untrack, gitignore the vault, keep the
`.md` as a clearly-named example.

**M6 — `test_api.py` at repo root** — manual script with prints, outside pytest
discovery, duplicating `tests/` intent. **Fix:** fold into `tests/` as a proper
integration smoke test (opt-in via env var so CI doesn't hit live APIs).

### Low

**L1 — Platform detection checks the wrong env var** — `api/index.py:82`
`"production" if os.getenv("VERCEL")` — the backend runs on Railway;
`/api/health` reports `"development"` in production (verified live).
**Fix:** check `RAILWAY_ENVIRONMENT`, fall back to `ENV`.

**L2 — Presentation leaks into data** — `src/sentiment_edge.py:190`
`source = f"🔴 BREAKING | {source}"` mixes UI decoration into an API field the
frontend then renders verbatim. Kept for now (changing it alters displayed
data); flagged for the next contract revision.

**L3 — `datetime.utcnow()` deprecated (3.12+)** — `src/news_api.py:76`
**Fix:** `datetime.now(timezone.utc)`.

**L4 — Stale README** — architecture section says "Deployment: Vercel
(serverless)", references a non-existent `vercel.json` and a
`MASFIN_System_Template.ipynb` that isn't in the tree; the real topology
(Vercel = frontend, Railway = backend, keys per host) is undocumented.
**Fix:** rewrite deployment/architecture sections; document that deployment
config lives in the hosting dashboards (no Procfile/vercel.json in-repo).

**L5 — `OmniSignalReport.confidence` defaults silently** — `src/models.py:123`,
`src/report_generator.py:396`
`generate_from_components()` never computes confidence, so reports render a
meaningless "50%". Resolved by H2 (shared decision function).

### Frontend

Audited in the July 2 redesign (see `docs/QA.md`): no `any` at boundaries, no
console noise, route-split bundles, a11y pass, tested news pipeline. New
findings this round: **none blocking.** The LLM feature below follows the
existing panel/token system.

---

## 2. Roadmap

| Priority | Item | Status |
|---|---|---|
| Critical | C1 CORS allowlist · C2 gitleaks CI + pre-commit | this change-set |
| High | H1/M1/M2 logging + non-leaky errors · H2 shared decision logic · H3 sync handlers + parallel research · H4 pinned deps | this change-set |
| Medium | M5 vault untracked · M6 test_api relocation · L1/L3/L4 fixes | this change-set |
| Medium | **LLM explanation layer (Groq `openai/gpt-oss-120b`)** — service, validation, cache, fallback, API fields, terminal panel, tests | this change-set |
| Follow-up | M3 fredapi/yfinance hard timeouts · M4 proxy shared-secret header · L2 source-field cleanup · streamed research progress | documented only |

## 3. LLM layer — design constraints applied

Python remains the single source of truth: verdict (`prediction_agent.py`
layers + dampening), confidence/rationale (shared `compute_decision`, extracted
from `data_pipeline._compute_verdict`), and a deterministic LOW/MEDIUM/HIGH
risk level are all computed *before* the model is called and passed in as
facts. The model (Groq `openai/gpt-oss-120b`, `temperature=0.2`, `top_p=1`,
`reasoning_effort="medium"`, `max_completion_tokens=4096`, `stream=False`,
JSON-object response mode) may only explain those numbers. Its output is parsed
with `json.loads`, validated against a Pydantic schema, retried once on
validation failure, and the deterministic fields are overwritten with the
Python values regardless of what the model said. On any failure (missing key,
timeout ≈8s, 429, malformed JSON twice) the endpoint returns a canned,
clearly-flagged fallback — `/api/research/{ticker}` can never be taken down by
the LLM. Responses are cached 5 minutes per (ticker, day, verdict, model).
`fast=true` skips the LLM entirely, as it already skips sentiment.
