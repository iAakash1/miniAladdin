# The analysis graph

> LangGraph is the orchestration layer. It is **not** an autonomous agent
> framework here, and the distinction is the whole design.

## What this is not

No node decides what to do next by asking a model. There is no planner, no tool
selection loop, and no agent that can choose to re-run itself. The graph is a
fixed topology with one conditional edge, and every path through it is
enumerable by reading this page.

That is deliberate. The product's central claim is that a verdict is
reproducible from evidence, and an orchestration layer that lets a model choose
the route makes two runs over the same data structurally different. A reader
comparing them would have no way to tell whether the difference came from the
market or from the planner.

## The topology

```
                              START
                                │
                        build_evidence
                                │
        ┌───────────┬───────────┼───────────┬───────────┐
      market   fundamental  technical     news     macro_risk     (parallel)
        └───────────┴───────────┼───────────┴───────────┘
                            reconcile
                                │
                              score          ← the only writer of the verdict
                                │
                             validate
                                │
                             explain
                                │
                    should_run_critic?  ──skip──┐
                                │               │
                             critic ────────────┤
                                                │
                                            finalise
                                                │
                                               END
```

One conditional edge, `should_run_critic`, and its condition is a fact about
state rather than a model's judgement: run the critic when there is a narrative
to review and a critic configured, otherwise skip.

## Why a graph rather than a loop

The five specialists have no data dependency on each other — they read one
shared evidence context and write one result each — so they fan out. Expressed
as a `for` loop that is five sequential provider-bound stages; expressed as a
graph it is one.

The fan-out is also what forces the state contract to be honest. LangGraph
rejects concurrent writes to a channel without a reducer, correctly: a
last-writer-wins merge across a fan-out is a race dressed as a result. So
`agent_results` carries `Annotated[dict, _merge]` and each specialist writes
under its own key, which makes the union order-independent by construction
rather than by luck. `warnings`, `errors`, `fallbacks` extend; `timings` merges.

## The invariant the graph exists to protect

**`node_score` is the only node that writes `model_signal`, `confidence`,
`risk_score` or `data_completeness`.** They are copied from the scorecard the
scoring engine produced.

Everything downstream — validation, explanation, the critic — reads them and
cannot change them. A model that ignores its instructions changes the prose and
nothing else. This is enforced by test, not by convention: see
`tests/test_agent_graph.py`.

`score` runs **after** `reconcile` and **before** `validate`, which is the
order that makes the claim checkable. Scoring after validation would let the
validator's findings influence the number; scoring before reconciliation would
score a snapshot the specialists had not finished agreeing on.

## Error isolation is per node

`_timed` wraps every node. A node that raises records the failure in `errors`,
adds a warning, and the graph carries on:

```python
update = {
    "errors": [f"{name}: {type(exc).__name__}"],
    "warnings": [f"the {name} stage did not complete"],
}
```

An unavailable news provider costs a reader the news section, not the analysis.
The exception type is recorded and the message is not — a vendor's error text
can carry a URL with a key in it, and this state is logged and served.

`_timed` also records each node's wall time into `timings`, which is what the
Agent Observatory renders. Per-node timing is the only way to answer "why did
this take nine seconds" with something other than a guess.

## Degradation

`run()` checks `available()` first. Without the LangGraph package installed it
falls back to the sequential orchestrator and records `langgraph_unavailable`
in `fallbacks`, so a deployment that cannot carry the dependency still produces
an analysis — and says that it did so by a different route.

The fallback produces the same authoritative fields from the same engine. It
loses the parallel fan-out and the per-node timings, not the verdict.

## Versioning

`GRAPH_VERSION` is bumped when the node set or their contract changes, so a
stored trace can be read under the shape that produced it. It travels in the
final state beside `agent_schema_version`, `validation_version`,
`scoring_version` and `prompt_version` — five versions because five things can
change independently, and a trace that carried one number could not say which.

## State carries no secrets

`AnalysisState` is traceable, serialisable and logged. Nothing in it is a
credential, and provider errors enter as type names rather than messages for
the reason above.
