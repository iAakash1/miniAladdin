# GenAI evaluation

## Research question

Can an evidence-grounded multi-agent architecture reduce factual hallucination
and decision inconsistency in generative-AI equity research, while producing
explanations suitable for readers with different levels of financial
expertise?

## Configurations

| | Architecture |
|---|---|
| **M0** | ungrounded generator — claims carry no evidence handles, no validation |
| **M1** | grounded generator — claims cite evidence; no claim-level checking |
| **M2** | grounded and validated — the shipped architecture |

### What M0 is, and is not

M0 is a **structural** baseline, not a live model run. It models an ungrounded
generator by stripping evidence handles from the same claims and skipping
validation — that is the defining property of an ungrounded system: its
sentences carry no traceable support.

It is deliberately **not** presented as a measurement of any vendor's model. A
number labelled with a model's name that the model never produced would be
exactly the dishonesty this project exists to avoid. The metrics measure
*architecture*, not model quality.

## Scenarios

Twelve frozen scenarios in `src/evaluation/scenarios.py`, versioned
`genai-eval-v1`. Frozen because a benchmark whose inputs change between runs
measures the market as much as the system.

`healthy` (the control) · `unsupported_number` · `number_drift` ·
`period_mismatch` · `stale_price` · `unit_confusion` · `currency_mix` ·
`missing_macro` · `narrative_contradicts_signal` · `narrative_misstates_risk` ·
`prompt_injection` · `dangling_citation`

The control matters: without it, a validator that refuses everything scores
perfectly.

## Results

```
config    claims unsupported  defects caught  evidence cov.  narrative leaks  decision inv.
M0                    100.0%            0.0%           0.0%           100.0%         100.0%
M1                      7.1%           10.0%          92.9%           100.0%         100.0%
M2                      0.0%          100.0%          92.9%             0.0%         100.0%
```

Reproduce with:

```bash
.venv/bin/python -c "from src.evaluation import evaluate, summary_table; print(summary_table(evaluate()))"
```

## Reading the result

**Grounding alone is not enough.** M1 gets citations onto 92.9% of claims and
still leaks: it never checks whether the cited evidence *says* what the claim
says, so a number that drifted from its source, a TTM/fiscal-year comparison
and a stale price all pass. Checking is what closes the gap, not citing.

**Decision invariance is 100% across all three.** The verdict is identical
under every configuration, which is what makes the comparison meaningful — the
metrics compare two ways of explaining one decision, not two products.

## Limitations

- M0 and M1 are structural models of those architectures, not live model runs.
- The scenario set is hand-built and small; it measures detection of *known*
  defect classes, not unknown ones.
- No human study of comprehension was run, so the "suitable for different
  expertise levels" half of the research question is supported by design
  argument and language tests, not by reader evidence.
- Latency and token cost are not measured here, because M0 and M1 do not make
  real model calls in this harness.
