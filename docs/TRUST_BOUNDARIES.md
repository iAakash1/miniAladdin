# Trust boundaries

Where data changes hands, and what stops being assumed at each crossing.

```
   vendor API                    ← untrusted: unavailable, wrong, stale, hostile
       │  redact(), isfinite(), typed VendorError
       ▼
   provider layer                ← per-vendor health, cooldowns, reconciliation
       │  EvidenceRecord: value + unit + observed_at + fetched_at + stale
       ▼
   evidence context              ← one snapshot, shared by every agent
       │  Claim: statement + evidence_ids + numeric_value
       ▼
   scoring engine                ← the ONLY producer of a verdict
       │  ScoreCard: raw_score [-1,1], confidence/risk 0-100, completeness 0-1
       ▼
   validation                    ← refuses; cannot change a number
       │
       ▼
   language model                ← prose only, and never trusted with a number
       │  signal/confidence/risk attached AFTER generation
       ▼
   HTTP boundary                 ← allow_nan=False, typed availability, RBAC
       │
       ▼
   browser                       ← ?? not ||, Number.isFinite, null-last sorting
```

## Vendor → provider

**Assume nothing.** A vendor can be down, slow, wrong, stale, or return a 200
containing an error. Every failure becomes a typed `VendorError` with the
message redacted, and a cooldown after consecutive failures so a dead vendor
stops costing every request its timeout.

Three vendors reselling one exchange feed are **one source**. Reconciliation
distinguishes provider from source, because treating resellers as independent
confirmations turns a single upstream error into a consensus.

## Provider → evidence

The crossing where a number acquires its meaning. A bare float is not evidence;
an `EvidenceRecord` carries the unit, the period, when the world was in that
state, when we asked, and whether it is stale.

`observed_at` is left absent when the provider does not state it. Recording
today's date because the provider was silent is fabrication.

## Evidence → scoring

**One snapshot.** Every agent reads the same context. If each fetched its own,
two agents could reason about different snapshots of one security, and a
contradiction produced that way is indistinguishable from a real one — which
would make the validator's findings untrustworthy in exactly the cases it
exists for.

## Scoring → everything downstream

**`src/scoring/engine.py` is the only producer of BUY/HOLD/SELL.** Everything
after it reads and cannot write. In the graph this is one node, `node_score`,
and it is asserted by test rather than convention.

Scales are fixed and are not interchangeable: `raw_score` is bounded [−1, 1],
`confidence` and `risk_score` are 0–100, `data_completeness` is a 0–1
**fraction**. The fraction-versus-percentage boundary is a real defect source,
so the conversion happens in one place per consumer.

## Validation → narrative

The validator refuses; it does not correct. A narrative that fails validation
is **withheld** and the deterministic summary served instead — not shown with a
footnote, because a caveat under a confident paragraph is read as a formality
and the paragraph is what the reader carries away.

## Model → reader

The tightest boundary in the system, because it is the one a reader cannot
inspect.

A model writes prose. It never writes a signal, a confidence, a risk score, a
rank or a threshold. Those are attached after generation from the scorecard.
The What-If simulator calls the real engine rather than estimating what the
engine would say. The rank comparison restates the ranking's own arithmetic
rather than narrating it.

Every one of those is the same decision: **a second producer of a number
drifts, and a reader has no way to tell which one they are looking at.**

## Backend → browser

- `allow_nan=False`: a non-finite number fails to serialise rather than
  arriving as something a JSON parser will turn into a surprise.
- Availability states, not bare 404s: `EMPTY`, `NOT_CONFIGURED`,
  `INSUFFICIENT_DATA`, `UNSUPPORTED`, `DEPENDENCY_UNAVAILABLE`, `STALE`,
  `PERMISSION_DENIED`, `ERROR` — all HTTP 200, because a 404 would claim the
  route was wrong and a 500 would claim we failed.
- RBAC on the route, not on the link.

## Inside the browser

The boundary does not end at the fetch.

- `?? null`, never `|| 0` — `0` is a measurement and `||` swallows it.
- `Number.isFinite` before rendering anything as a figure.
- **Null-last sorting.** An unmeasured security must never sort as the safest
  or the best. This is why product tables route through `DataTable`, which has
  the rule built in; a hand-built table is counted and checked.
- Colour is never the only carrier of meaning — a mark and a word accompany it,
  so a verdict survives a reader who cannot distinguish the colours.

## The rules that run through all of it

```
missing ≠ zero            unknown ≠ safe           stale ≠ fresh
trending ≠ recommended    rank ≠ verdict           completeness ≠ accuracy
confidence ≠ probability of profit                 risk ≠ probability of loss
provider ≠ source         simulated ≠ real         empty ≠ broken
```
