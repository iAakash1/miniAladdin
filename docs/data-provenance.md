# Data provenance

Every served number carries what is needed to question it. This describes the
contract and the rule that makes it hold.

## The envelope

`src/services/envelope.py`

```python
DataEnvelope(
    value,          # the number, or None
    source,         # artifact path, endpoint, or provider
    as_of,          # when the data describes the world
    retrieved_at,   # when we fetched it — deliberately separate
    policy,         # which freshness policy governs it
    method,         # how it was produced
    unit,
    detail,         # why it is absent, when it is
)
```

`as_of` and `retrieved_at` are separate because a fresh fetch of a stale series
happens constantly, and conflating them is how a dead feed looks healthy.

## Status is derived, never asserted

There is no way to pass `status` in. It is computed from `as_of` and the
declared policy:

| status | meaning | trustworthy |
|---|---|---|
| `live` | measured inside the policy's window | yes |
| `recorded` | a committed artifact; age is provenance, not decay | yes |
| `stale` | real, and older than the policy allows | no |
| `waking` | the source exists and is starting; retrying works | no |
| `unavailable` | asked, and the source could not answer | no |
| `unknown` | not asked, or the answer cannot be interpreted | no |

This is the whole design. The recurring failure in this product has been a
caller labelling data it did not measure — unknown rendered as sealed,
unavailable rendered as zero, a missing register rendered as "nothing is
validated". A caller cannot mislabel what it does not get to label.

Two distinctions earn their place:

- **`recorded` is not `stale`.** EXP-006 does not become less true in September.
  A ttl-less policy returns `recorded` regardless of age, because "may I trust
  this as current?" is not a question that applies to an artifact.
- **`waking` is not `unavailable`.** Render's free tier takes ~43s to wake
  against an 8s budget, so a timeout is the *expected* first response after a
  quiet period. One means retry; the other means stop waiting.

A `None` value is never `live`, whatever its timestamp.

## Declared policies

| policy | TTL | reason |
|---|---|---|
| `quote` | 15 min | Intraday prices move continuously. |
| `macro` | 2 days | Cadences run daily to monthly; tolerates a weekend. |
| `news` | 1 hour | A feed that has not moved in an hour is likelier broken than quiet. |
| `inference` | 5 min | Metadata is immutable per deploy; the service is not. |
| `experiment` | none | A recorded artifact. Age is provenance. |
| `registry` | none | Append-only promotion ledger, authoritative regardless of age. |

An unknown policy name raises rather than silently defaulting — a typo must not
pick a freshness window.

## On the wire

`/api/quant/selection/:id` returns an `envelopes` block for the six
decision-bearing numbers: net Sharpe, gross Sharpe, IC t-stat, alpha t-stat,
deflated-Sharpe probability, PBO. Each carries its own source, status and
methodology. Additive — existing consumers are untouched.

## In the UI

`EnvelopeMetric` renders straight from an envelope, so methodology text lives on
the server and cannot drift between components. It previously had: two
components showing net Sharpe described it differently.

A value that is not trustworthy renders **its status instead of its number**.
There is no path that prints a figure the server declined to vouch for.

The pass/fail colour stays in the component, because that is a judgement against
a gate rather than a property of the measurement — and most numbers are not
verdicts.

## Where this came from

The freshness policy is Fincept's per-topic `TopicPolicy`; the value-with-
provenance object is OpenBB's standard-model pattern; provenance living in the
panel container is their widget contract. Both projects are AGPL-3.0 and no code
from either is used. See `reference-fincept-study.md` and
`reference-openbb-study.md`.

## Not yet covered

The envelope is applied to the quant selection surface. Market quotes, macro and
news still return bare values. The contract exists and the policies for those
domains are declared; wiring them is mechanical and not yet done. They are not
described as provenance-carrying anywhere in the UI.
