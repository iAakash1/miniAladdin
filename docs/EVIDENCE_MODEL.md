# The evidence model

> Every sentence this product shows about a security should reduce to rows a
> reader can check. That is only true if the checking is possible.

## Three record types

**`EvidenceRecord`** — one measured value, with everything needed to check it
later: `provider`, `capability`, `field`, `value`, `unit`, `currency`,
`period`, `observed_at`, `fetched_at`, `stale`.

**`Claim`** — one statement, and the `evidence_ids` it rests on. Carries
`numeric_value` and `unit` when it asserts a number, so the validator can check
the sentence against the measurement rather than trusting it.

**`ValidationReport`** — what survived checking, per claim and in aggregate.

## Observed is not fetched

Two timestamps, always, and conflating them is how a figure cached three days
ago gets presented as current.

- `observed_at` — when the world was in this state.
- `fetched_at` — when we asked.

`observed_at` may legitimately be absent: a provider that does not state it is
different from one that states today's date, and recording today's date because
the provider was silent is the fabrication this field exists to prevent. The
interface says which case it is.

The Evidence Inspector shows both on their own rows and names the gap in days
when it is a day or more. A large gap means the figure is **real and old**,
which is different from wrong and different from current.

## Cited-and-missing is not uncited

Two different failures that a careless interface renders identically:

| Case | What it means |
|---|---|
| `evidence_ids == []` | The claim asserts something with no measurement behind it. The validator marks it UNSUPPORTED (`evidence_required`). |
| A cited id that does not resolve | The claim believes it has support that never arrived. A **pipeline fault** (`evidence_exists`). |

Silently dropping the second produces a drawer that looks exactly like the
first and hides a real defect, so unresolved handles are listed as unresolved.

That UNRESOLVED state is only worth showing if it is an alarm rather than
routine, so the invariant behind it is asserted across the whole fan-out:
`tests/test_agents.py` checks that every cited handle resolves, that handles do
not collide between agents, and that every record separates observed from
fetched. A drawer that regularly reported missing evidence would train a reader
to ignore it and cost them the one case where the pipeline really did lose
something.

## What the validator refuses

It is a real gate, not a formality. It refuses:

- a claim with no evidence (`evidence_required`)
- a claim citing a handle that does not exist (`evidence_exists`)
- a number that disagrees with the evidence it cites
- a comparison across incompatible periods — a TTM margin against a five-year
  average describes two different windows, and differencing them produces a
  plausible number that means nothing
- a stale reading presented as current
- a narrative that argues against the signal it is supposed to explain

A narrative that fails validation is **withheld**, and the deterministic
summary is served instead. It is not shown with a footnote: a caveat under a
confident paragraph is read as a formality, and the paragraph is what the
reader carries away.

## Provider is not source

`reconcile` distinguishes the two. Three vendors reselling one exchange feed
are one source, not three, and treating them as three independent
confirmations is how a single upstream error becomes a consensus.

## Absent is not zero

A record whose value did not arrive renders as "not reported". A non-finite
number renders as what it is rather than as a figure. Neither is a zero, and
neither is an average — substituting either is how an absence of evidence comes
to behave like evidence.

## Where to see it

- `/api/agents/{ticker}/validation` — claims, evidence and the verdict on each.
- Evidence audit (terminal → admin) — the same, rendered, with each claim
  opening a drawer that resolves its handles.
- `/api/ask` — answers cite evidence ids, and citations to evidence that does
  not exist are dropped before the answer is returned.
