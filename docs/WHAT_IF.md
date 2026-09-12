# What-If Lab

> A sensitivity tool whose only defensible implementation is the boring one:
> move an input, call the real engine, report what it said.

## The rule

**Every scenario perturbs an argument `score_ticker` already accepts, and then
calls `score_ticker`.** There is no second aggregation, no estimate of what the
verdict "would" become, and no scenario-specific arithmetic.

That is not fastidiousness. The alternative — adjusting family scores directly
and re-deriving a verdict — is a second scoring path, and a second scoring path
drifts. When it drifts, the simulator teaches a reader a sensitivity the model
does not have, and the reader has no way to tell. A simulator that disagrees
with production is worse than no simulator.

The same reasoning produced one shared input builder. `scoring_inputs()` in
`src/agents/orchestrator.py` is the single place the engine's arguments are
derived from an evidence context, and both production scoring and the simulator
call it. Two hand-written copies of that argument list would drift quietly, and
the symptom would be the worst kind: the simulator's **Current** column no
longer matching the scorecard printed beside it on the same page, with nothing
to tell a reader which of the two to believe.

## Isolation

Nothing here is written anywhere.

| Not touched | Why it is safe |
|---|---|
| Stored production signal | The route builds its own context and discards it |
| Live scorecard | The perturbed scorecard is a return value, never assigned to the context |
| Portfolio / watchlist | Never referenced |
| Historical analysis runs | No run is recorded; no `run_id` is issued |
| Explore ranking snapshot | Never referenced; asserted by test |

The price frame is **copied** before perturbation (`frame.copy()`), because
mutating the shared frame in place would corrupt every agent that reads it
afterwards — silently, and only for the request that happened to run a
simulation.

Tests pin both of the properties above by name:
`test_simulation_does_not_mutate_the_production_analysis` and
`test_simulation_does_not_modify_the_explore_snapshot`, at service and route
level.

Every response carries `simulation: true`, and the panel is labelled
**SIMULATION** in its badge and again beneath the numbers.

## The levers

| Lever | Engine argument | What moves |
|---|---|---|
| `momentum` | the price frame | Total window return, signed |
| `macro_regime` | `srm` | Systemic risk multiplier, clamped to the engine's own 0.5–1.6 |
| `valuation` | `pe_ratio`, `forward_pe` | Both multiples, proportionally |
| `sentiment` | `sentiment_avg` | Mean headline tone, clamped to −1…1 |

### The momentum bug worth recording

The first implementation scaled each daily return by `(1 + change)`. Every
number it produced was finite, ordered and plausible, and it was **wrong**: it
scaled magnitude rather than direction. For a security that had *fallen* over
the window, "momentum weakens by 20%" made the decline 20% shallower and the
score went **up**.

No test caught it. It was caught by reading the output — `Momentum weakens by
20%` next to `+0.0949 → +0.1111` — and the lesson is that a monotonicity
property has to be asserted, not assumed, because the broken version looks
exactly as healthy as the correct one.

The fix states the target as a return rather than a scale factor: if the window
return is +8% and the change is −20%, the simulated window return is −12%. A
constant daily drift reaches it. That makes each daily return an increasing
affine function of the original, so the ordering of the days is preserved
exactly and the correlation with the original series is 1. It is **not** a claim
that every day keeps its sign — on a measured 260-bar path a 20% shift flips
4–8% of days, the ones whose own move was smaller than the drift.

Because the shift moves the frame's final close, the caller passes the
*original* `price` and the *original* multiples to the engine. Otherwise one
lever would move two sleeves and the attribution would be meaningless.

## Honest no-ops

Three scenarios can legitimately change nothing, and each says so in words.
This is the part most likely to be mistaken for a bug, and it is why the `note`
field exists.

**The macro gate is doubly one-sided.** In `src/scoring/engine.py`:

```python
# Gate applies to the momentum sleeve only, bullish side only (§9)
gated_family = raw_family
if family == "momentum" and raw_family > 0:
    gated_family = raw_family * gate
```

and the gate itself is `max(0.0, tanh(...))`, flat at 1.00 for every
`srm ≤ 1.10`. So:

1. **Easing stress below the threshold cannot raise the score.** The gate only
   ever subtracts; a calmer regime removes a haircut that was not being
   applied. Risk still falls, because risk reads the regime directly.
2. **Rising stress cannot lower the score of a bearish security.** There is no
   bullish momentum credit to withdraw. Stress taking credit away from an
   already-negative reading would make stress a *bullish* input.

Both are deliberate, and both produce two identical numbers on screen. A reader
who sees that without the sentence concludes the tool is broken instead of
learning how the model works — so the note distinguishes the two cases and
names the reason.

**An absent input has nothing to move.** No valuation multiple, or no headline
carrying a tone score, is reported as exactly that. The alternative — treating
absent as zero and reporting a confident sensitivity — is the missing-is-not-zero
rule this codebase is built on, applied to a surface where breaking it would be
especially persuasive.

## What it is not

- **Not a forecast.** It reports what the engine returns under a hypothetical
  input, not what is likely to happen.
- **Not advice.** It changes no position and recommends no action.
- **Not open-ended.** The API takes a preset key, not a free `lever` + `change`
  pair, so a caller cannot ask for a P/E of −400 or a regime the model has no
  meaning for. The presets are the scenarios this system can honestly simulate.

## API

```
GET  /api/what-if/scenarios   -> { simulation: true, scenarios: [...] }
POST /api/what-if             { ticker, scenario } -> availability payload
```

Failure states are the shared availability vocabulary, always HTTP 200:
`UNSUPPORTED` for an unknown scenario (with the offered list attached),
`INSUFFICIENT_DATA` when the security has no baseline to simulate against,
`DEPENDENCY_UNAVAILABLE` when the data could not be loaded. A malformed ticker
is a 422, because that is a caller error rather than a data state.
