# OmniSignal system health (2026-09-20)

Engineering health only. GREEN / YELLOW / RED describe whether the engineering is sound and honestly reported. **They are not statements about
model quality, profitability or readiness to trade.** No model is promoted; the sealed holdout (2025-08-26 → 2026-08-28) has not been read.

| Area | Status | Why | What would change it |
|---|---|---|---|
| **DATA** | YELLOW | 58 SEC archives verified (continuity, sizes against sec.gov, SHA-256, CRC); 14.57M as-reported rows rebuilt with the v2 defects fixed; local inventory measured. But the Dolt-sourced price/earnings/options sets carry an "open data" note, **not a reviewed licence**, so redistribution and product use are unassessed; delisting bounds before 2017-10-26 are inferred. | Licence review of the Dolt sources; a delisting source that covers pre-2017. |
| **PIT** | YELLOW | `sec-core-facts-v3`, availability rule (US Eastern, after-close next session), FIRST_REPORTED / AS_OF views, real-data restatement invariance all pass. `security_master_pit` is **false**: trusted identity 91.8–95.0% by fold against a preregistered 95%. ALFRED is `BLOCKED_EXTERNAL_FRED_KEY`. | 20-F/IFRS mapping for foreign issuers; recovering delisted names; a FRED key. |
| **RESEARCH** | GREEN | Preregistration gate (pushed before run) enforced in code; immutable experiment records with hashes; EXP-010A noise floor; EXP-010B reproduced its parent exactly (gap 0.0); negative results kept and shown. One disclosed exposure (EXP-010B seed-0 prototype) travels with that result. | — |
| **MODEL** | YELLOW | Registry: 69 experimental, 34 retired, **0 validated/promoted**. The 21-session portfolio improved validation net Sharpe in 10/10 seeds (validation evidence, fold heterogeneity). EXP-011 is complete: the 50 PIT features improved Ridge ordering only (`IMPROVES_ONLY_LINEAR`); the frozen boosting model showed no detectable ordering gain and lower validation economics. Nothing is promoted; the completion of EXP-011 does not change this status. Ridge runs emitted numerical RuntimeWarnings (environment caveat; all stored predictions finite). | A decision on data completion vs a final-candidate freeze (`docs/NEXT_RESEARCH_DECISION_2026.md`); a frozen candidate plus explicit holdout authorisation. |
| **PORTFOLIO** | YELLOW | Engine reproduces frozen economics bit-for-bit; Book returns typed failures (ARTIFACT_NOT_DEPLOYED … ALLOCATOR_INFEASIBLE) with no fake-portfolio fallback (tests present). No portfolio is promoted. | Promotion evidence. |
| **AGENTS** | YELLOW | Decision authority, agent graph and conviction tests exist and pass; the LLM has no BUY/SELL authority. Not re-audited behaviourally in this pass. | A dedicated agent audit. |
| **BACKEND** | GREEN | Full backend suite run twice on the final tree: **2,999 passed, 3 skipped** both times (8:01 and 7:28); 5 further Kaggle-pipeline tests added afterwards and passing. Research read layer, PIT validation and typed failures covered by tests. | — |
| **FRONTEND** | YELLOW | `tsc` clean, ESLint clean, 569 unit tests pass, production build succeeds. **Playwright E2E was not run**: it needs an authenticated Clerk session and no auth bypass was attempted. | Run E2E with a legitimate test session. |
| **SECURITY** | YELLOW | Secret-pattern scan of tracked files: 0 real secrets (one placeholder in `.env.vercel.example`); no `.env` ever tracked; no PDFs, raw SEC or licensed data tracked. `npm audit` production findings (1 critical, 8 high) fixed to **0** by a `next` 16.1.6→16.3.5 patch upgrade plus non-breaking fixes; build, lint, types and tests re-verified. **Python dependency audit was not run** (`pip-audit` not installed). Paper trading is paper-only with fail-closed owner authorisation (tests present). | Run `pip-audit`; rotate nothing was found to rotate. |
| **DEPLOYMENT** | YELLOW | Render/Vercel state was not inspected from this session. `PAPER_TRADING_OWNERS` on Render remains `BLOCKED_EXTERNAL` (no access). | Owner verifies the deployed environment. |

## Remaining blockers (all external or scoped-out, none hidden)

1. `FRED_API_KEY` absent → ALFRED macro vintages `BLOCKED_EXTERNAL_FRED_KEY`.
2. Dolt-source data licences unreviewed → Kaggle export refuses without `--acknowledge-data-license`.
3. Security master gate not met → industry/size controls withheld from the rich panel.
4. Next-step decision pending with the owner (data-completion study vs final-candidate freeze); no experiment is queued.
5. Ridge `RuntimeWarning`s (divide by zero / overflow / invalid value in matmul) remain an environment caveat of EXP-011; not resolved, not suppressed.
6. Playwright E2E and Python `pip-audit` not run.
