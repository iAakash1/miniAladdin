# Finance agents

## What an agent is here

A specialised component with an objective, declared inputs, a typed output and
defined failure semantics. **Most contain no language model.** Computing a
21-day return is arithmetic, and routing arithmetic through a model turns a
checkable number into an unverifiable one.

**No agent produces a verdict.** The BUY/HOLD/SELL decision is the scoring
engine's and is copied onto the pipeline result after validation. An agent
that returned its own recommendation would be a second decision authority,
which this codebase already spent a release removing.

## The agents

| Agent | Produces | Uses a model |
|---|---|:--:|
| `market` | price, returns, relative volume, freshness, source disagreement | no |
| `fundamental` | valuation, margins, returns on capital, analyst target, quality inputs | no |
| `technical` | volatility, drawdown, 52-week proximity, benchmark-relative return | no |
| `news` | coverage volume, source diversity, event classes, tone | optional |
| `macro` | regime, rates, term spread, inflation, risk components | no |

## Orchestration

The run is a **LangGraph** `StateGraph`: one fixed topology, one conditional
edge, and no node that asks a model what to do next. The five specialists fan
out in parallel over one evidence snapshot and rejoin at `reconcile`.

LangGraph is the orchestration layer and not an autonomous agent framework
here — the full topology, the state reducers and the reason a graph rather than
a loop are in [LANGGRAPH_WORKFLOW.md](LANGGRAPH_WORKFLOW.md).

Without the package installed, `run()` falls back to the sequential
orchestrator and records `langgraph_unavailable`, so a deployment that cannot
carry the dependency still produces an analysis by a route it declares.

## Shared evidence context

The orchestrator fetches once and every agent reads the same context. If each
agent fetched its own inputs, the same data would be paid for repeatedly and —
worse — two agents could reason about different snapshots of one security. A
contradiction produced that way is indistinguishable from a real one, which
would make the validator untrustworthy in exactly the cases it exists for.

## Contracts

`EvidenceRecord` — one measured value with provenance, unit, currency and
period. Period is not decoration: TTM revenue and fiscal-year revenue are
different measurements, and comparing them produces a confident, wrong claim.

`Claim` — one statement with the evidence ids supporting it. A claim with no
evidence ids fails validation by construction, which is the mechanism that
stops a generated sentence introducing a number nobody measured.

`AgentResult` — what one agent produced, **including what it could not**. An
agent that could not reach its data reports that rather than returning an
empty success: "no negative news" and "the news provider was down" look
identical once the list is empty, and only one is a finding.

Every result carries `agent_schema_version`, so a stored run can be read back
under the contract it was produced with. A graph run carries five versions —
graph, agent schema, validation, scoring and prompt — because those five things
change independently and a trace carrying one number could not say which moved.

The evidence a claim rests on is followable rather than decorative: see
[EVIDENCE_MODEL.md](EVIDENCE_MODEL.md) for what the Evidence Inspector resolves
and the three distinctions it refuses to collapse.

## Failure semantics

An agent never raises. `BaseAgent.run` catches, records the exception type as
a warning and returns an `ERROR` status, so one unavailable vendor costs the
reader one section rather than the whole analysis.

## API

`GET /api/agents/{ticker}/validation` returns every claim, its evidence
handles and the validator's verdict on each. This is the traceability surface:
every sentence the product shows about a security should reduce to rows in
here. The operations workspace renders it with failures first — a passing
claim is unremarkable, a refused one is why the page exists.
