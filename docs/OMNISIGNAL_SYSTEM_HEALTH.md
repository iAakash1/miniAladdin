# OmniSignal system health (2026-09-20)

> **Current runtime source:** `GET /api/system/health` now reports each layer as
> `READY`, `DEGRADED`, `BLOCKED`, `UNAVAILABLE`, or `NOT_CONFIGURED`; the System
> workspace renders that payload. The API liveness probe remains separate and
> cannot be mistaken for research readiness.

Engineering health only. GREEN / YELLOW / RED describe whether the engineering is sound and honestly reported. **They are not statements about
model quality, profitability or readiness to trade.** No model is promoted; the sealed holdout (2025-08-26 → 2026-08-28) has not been read.

| Area | Status | Why | What would change it |
|---|---|---|---|
| **DATA** | YELLOW | 58 SEC archives verified (continuity, sizes against sec.gov, SHA-256, CRC); 14.57M as-reported rows rebuilt with the v2 defects fixed; local inventory measured. But the Dolt-sourced price/earnings/options sets carry an "open data" note, **not a reviewed licence**, so redistribution and product use are unassessed; delisting bounds before 2017-10-26 are inferred. | Licence review of the Dolt sources; a delisting source that covers pre-2017. |
| **PIT** | YELLOW | Rich PIT v2 `ds-richpit2-6368cccdb94c62d0` has 139,292 name-dates, 839 securities and 94 features; the 76-column frozen block changed in 0 of 10,586,192 cells and 18 foreign-fundamental columns passed admission. `security_master_pit=true`; size/industry controls remain withheld because their every-fold coverage gate failed. ALFRED is `BLOCKED_EXTERNAL_FRED_KEY`; identity stability remains PARTIAL. | Recover the remaining identity-history gaps; satisfy the controls' own gate; a FRED key if vintage yields are needed. |
| **RESEARCH** | GREEN | Preregistration gate (pushed before run) enforced in code; immutable experiment records with hashes; EXP-010A noise floor; EXP-010B reproduced its parent exactly (gap 0.0); negative results kept and shown. One disclosed exposure (EXP-010B seed-0 prototype) travels with that result. | — |
| **MODEL** | YELLOW | Registry: 69 experimental, 34 retired, **0 validated/promoted**. EXP-011 remains `IMPROVES_ONLY_LINEAR`, but the outcome-firewalled revenue audit found 171 unambiguous filing corrections affecting 4,256 attached name-dates directly and classified the impact `UNRESOLVED_MAPPING_IMPACT`. Nothing is promoted and no EXP-012 run exists. | A formal EXP-011 replication decision before any final-candidate freeze; then a new preregistration if research continues. |
| **PORTFOLIO** | YELLOW | Engine reproduces frozen economics bit-for-bit; Book returns typed failures (ARTIFACT_NOT_DEPLOYED … ALLOCATOR_INFEASIBLE) with no fake-portfolio fallback (tests present). No portfolio is promoted. | Promotion evidence. |
| **AGENTS** | GREEN | Typed evidence now includes source, identity, temporal, freshness, confidence, PIT, citation, licence and validation fields. Deterministic reconciliation preserves `AGREED`, `SINGLE_SOURCE`, `CONFLICTED`, `STALE`, and `UNAVAILABLE` dimensions. LangGraph is mandatory; absence refuses the run rather than invoking a sequential fallback. The LLM has no BUY/SELL authority. | — |
| **BACKEND** | GREEN | Full backend suite run twice on the final tree: **2,999 passed, 3 skipped** both times (8:01 and 7:28); 5 further Kaggle-pipeline tests added afterwards and passing. Research read layer, PIT validation and typed failures covered by tests. | — |
| **FRONTEND** | YELLOW | `tsc` clean, ESLint clean, 569 unit tests pass, production build succeeds. **Playwright E2E was not run**: it needs an authenticated Clerk session and no auth bypass was attempted. | Run E2E with a legitimate test session. |
| **SECURITY** | YELLOW | Secret-pattern scan of tracked files: 0 real secrets (one placeholder in `.env.vercel.example`); no `.env` ever tracked; no PDFs, raw SEC or licensed data tracked. `npm audit` production findings (1 critical, 8 high) fixed to **0** by a `next` 16.1.6→16.3.5 patch upgrade plus non-breaking fixes; build, lint, types and tests re-verified. **Python dependency audit was not run** (`pip-audit` not installed). Paper trading is paper-only with fail-closed owner authorisation (tests present). | Run `pip-audit`; rotate nothing was found to rotate. |
| **DEPLOYMENT** | YELLOW | Render/Vercel state was not inspected from this session. `PAPER_TRADING_OWNERS` on Render remains `BLOCKED_EXTERNAL` (no access). | Owner verifies the deployed environment. |

## Remaining blockers (all external or scoped-out, none hidden)

1. `FRED_API_KEY` absent → ALFRED macro vintages `BLOCKED_EXTERNAL_FRED_KEY`.
2. Dolt-source data licences unreviewed → Kaggle export refuses without `--acknowledge-data-license`.
3. Size/industry control admission not met in every fold → controls remain withheld even though the security-master PIT flag now passes.
4. EXP-011 revenue-mapping replication decision pending; final holdout remains sealed and not ready; no EXP-012 study is queued.
5. Ridge `RuntimeWarning`s (divide by zero / overflow / invalid value in matmul) remain an environment caveat of EXP-011; not resolved, not suppressed.
6. Playwright E2E and Python `pip-audit` not run.
