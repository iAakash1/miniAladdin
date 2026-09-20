# OmniSignal v2 upgrade report

Date: 2026-09-20

## Delivered

- Rich PIT v2 published as an immutable 94-feature dataset with zero drift in
  the 76-feature frozen block and 18 admitted foreign-fundamental features.
- EXP-011 revenue mapping audited behind an outcome firewall. The audit requires
  a formal replication decision, so EXP-012 was not preregistered or fitted.
- Evidence contracts expanded with explicit source type, security identity,
  temporal availability, freshness, confidence, PIT, citation, licence and
  validation fields.
- Reconciliation is now typed and dimension-level. It groups only comparable
  field/unit/currency/period observations, preserves all values, distinguishes
  upstream independence and exposes conflicts instead of voting them away.
- LangGraph is the only analysis-run orchestrator. Missing LangGraph produces
  `LANGGRAPH_UNAVAILABLE`; no sequential fallback silently changes semantics.
- `/api/system/health` and `/terminal/system` provide a canonical component
  state model. `/api/health` remains a liveness probe for deployment tooling.
- `/terminal/research` makes the architecture visible as Evidence OS, Quant
  Engine and Research Lab, with the real graph trace and governance state in
  one workspace.

## Preserved boundaries

- No model was promoted.
- No final holdout observation was read.
- EXP-008 was not altered.
- No EXP-012 artifact was created.
- The agent layer still cannot write signal, risk, confidence, portfolio or
  promotion fields.

## Verification at this checkpoint

- Backend focused suites: agent graph, validation, health, API exposure and
  route integrity pass.
- Dashboard: TypeScript and ESLint clean; 569 unit tests pass.
- Full-suite and production-build results are recorded in the final checkpoint
  once they complete; this line is intentionally not pre-claimed.
