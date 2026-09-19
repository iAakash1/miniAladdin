# EXP-009 decision matrix

Qualitative ratings are comparative for this repository. For complexity and
compute, HIGH is worse/more demanding; for other columns, HIGH is better.

| Candidate | Literature evidence | Data availability | PIT quality | Complexity | Compute | Likely incrementality | Reproducibility | Decision |
|---|---|---|---|---|---|---|---|---|
| Learning to rank | MEDIUM | HIGH | HIGH | MEDIUM | MEDIUM | MEDIUM | HIGH | Top-three method; fixed cells only |
| Analyst revisions | HIGH | HIGH | HIGH for weekly consensus | LOW | LOW | MEDIUM | HIGH locally | Top-three data arm; prior negative ablation lowers prior |
| Earnings / PEAD | HIGH | MEDIUM | MEDIUM-HIGH after gate | MEDIUM | LOW | MEDIUM | HIGH locally | Secondary event-conditioned arm |
| Options | MEDIUM/mixed | MEDIUM | MEDIUM | HIGH | MEDIUM | LOW-MEDIUM | MEDIUM | Defer; prior negative and short history |
| Fundamental expansion | HIGH | HIGH | LOW-MEDIUM due restatements | MEDIUM | LOW | MEDIUM | LOW today | Block official use until SEC vintages |
| Insider Form 4 | MEDIUM | LOW locally / HIGH public feasibility | HIGH with filing time | MEDIUM | LOW | MEDIUM | HIGH | Acquire after security master |
| Institutional 13F | MEDIUM | LOW locally / HIGH public | HIGH but delayed | MEDIUM | LOW | LOW-MEDIUM | HIGH | Lower priority; quarterly/45-day lag |
| Neutralization | HIGH | LOW today | LOW without historical master | MEDIUM | LOW | MEDIUM-HIGH robustness | MEDIUM | Prerequisite project; do not fake sectors |
| Turnover-aware construction | HIGH and directly matched | HIGH | HIGH | LOW-MEDIUM | LOW | HIGH economic value | HIGH | Top priority |
| Graph features | LOW-MEDIUM | LOW | LOW | HIGH | HIGH | Unknown | LOW | Defer |
| Text/LLM features | MEDIUM | LOW | MEDIUM if SEC; low for licensed transcripts | HIGH | HIGH | Medium event value | MEDIUM-LOW | Defer until corpus/provenance |

## Top three EXP-009 ingredients

1. **Fixed turnover-aware rank buffer/no-trade rule.** It directly attacks the
   observed 20.15x turnover and can be evaluated on frozen predictions.
2. **Date-grouped learning-to-rank objective.** It tests the mismatch between a
   rank target and point-regression loss with a small fixed comparison.
3. **One isolated analyst-revision arm.** The local consensus history is large,
   vintage dated and already engineered. It is the cleanest richer family, but
   its EXP-005 underperformance means the test must be conditional and small.

PIT sector/size data is a prerequisite/control project, not smuggled into the
same result. Earnings is the next candidate. Options, graph and text are not in
the first EXP-009 because their data limitations and implementation burden
would make attribution poor.

## Recommended staged structure

This is not yet a binding registration:

- Stage A: frozen point-regression control versus at most two fixed rankers.
- Stage B: winner frozen; immediate replacement versus one fixed rank buffer.
- Stage C: winner frozen; base versus base + all eight analyst features.
- Negative stages stop; no later stage is searched to rescue an earlier one.
- Every new cell increments cumulative trial count; holdout remains sealed.

The tempting “richer data + LTR + neutralization + buffer” stack should not be
run as one jump. Its result would not reveal which box helped and would spend
too many degrees of freedom on roughly 96 independent validation blocks.
