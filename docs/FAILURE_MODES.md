# Failure modes

What breaks, what the reader sees, and — for the ones that have actually
happened here — what made them hard to catch.

The organising principle: **a failure that looks like a success is worse than
an outage.** An outage is visible and someone fixes it. A plausible wrong
number is acted on.

## Data

| Failure | Response |
|---|---|
| Vendor down | Typed `VendorError`, cooldown after 3 consecutive failures, next vendor tried |
| Vendor returns 200 with an error body | Parsed as a failure, not as data |
| Vendor returns a stale figure | Recorded `stale`, `observed_at` preserved, shown as old rather than current |
| A field is absent | `None` — never 0, never a median, never last-known |
| A number is non-finite | Refused at the boundary; no claim is made |
| Security has too little history | `INSUFFICIENT_DATA` with the reason, not an empty chart |

### The one that reads as fine

A security missing one ranking input is **not ranked at all**, rather than
ranked on three of four terms. Substituting a default would let an absence of
evidence behave like evidence — and the resulting rank is a number that looks
exactly like every other rank.

`percentile_rank` returns `None`, not 50, for the same reason. An invented
median is precisely how an unmeasured security climbs past a measured one.

## Presentation

| Failure | Response |
|---|---|
| Nothing qualifies for High Conviction | The expected case. Says so, and shows the near misses with what each is missing |
| A scenario cannot move anything | Says why — "the macro gate only ever subtracts", "no scored headlines" |
| A narrative fails validation | Withheld, deterministic summary served instead |
| An endpoint has nothing to return | A typed availability state at HTTP 200 |

An empty tier is not an error. A tier that always has entries is a ranking
wearing a threshold's name.

## Failures this codebase actually had

### The rail that kept saying SEALED

Twelve workspaces each stated the same three global facts as static text. With
the backend down, every one still announced HOLDOUT SEALED and REGISTRY 103
ENTRIES while the panels above them correctly reported that nothing could be
read.

A rail that keeps saying "sealed" when the app cannot reach the thing that
would tell it is the most dangerous kind of stale: it is the reassuring half of
the screen, it is always in view, and it is the last thing a reader would think
to doubt.

**Now:** read live, and it reports `cannot be read` rather than a remembered
value dressed as a current one.

### Nine cells against eight headers

The Evidence registry rendered nine cells per row against eight header cells —
the row-actions column had a cell and no header — so every value lined up under
the header to its left. A reader saw mean IC under IC T-STAT.

Every figure was plausible, every one was labelled as a different statistic,
and typecheck, lint, 1,715 tests and a clean production build all passed with
it in place.

**Now:** `DataTable` derives headers and cells from one array, and the census in
`table-contract.test.ts` holds the count of hand-built tables still.

### The build that never reported its failure

The retry rule was "restart whenever the last attempt failed", evaluated by a
client polling every 1.5 s. A deterministically failing build therefore never
reported its failure to anyone: each poll saw the failed job, started a new
one, and answered `building`. The page loaded forever while the backend span up
a fresh build thread twice a second — the same symptom as a stall, and a more
likely cause of one.

**Now:** a failure is an answer with a 30-second memory.

### The simulator that had momentum backwards

The What-If momentum lever scaled each daily return by `(1 + change)`. That
scales magnitude, not direction, so for a security that had *fallen* over the
window, "momentum weakens by 20%" made the decline shallower and the score went
**up**.

Every number it produced was finite, ordered and plausible. No test caught it;
it was caught by reading the output.

**Now:** the lever states a signed target return, and monotonicity is asserted
over rising, falling and flat paths.

### The flake with two independent causes

A test suite failure that appeared only sometimes. Instrumenting the patch
window showed two separate leaks: a `factor-lab-mega30` daemon thread started
by an API test, and `research_prefetch.warm`'s abandoned `map_concurrent`
workers. Both landed inside a *later* test's patch window, so a backtest test
asserting one vendor call saw three.

Python cannot cancel a thread doing blocking I/O, so production deliberately
abandons a stalled worker. A test suite is a different situation.

**Now:** two autouse fixtures scope the leaks to tests; production abandonment
semantics are unchanged.

## Failure modes that are live and unmitigated

Stated because an undocumented known risk is worse than a documented one.

**Multiple workers on an in-process job registry.** Each worker keeps its own,
so the same background build can start more than once and a client polling
across workers sees progress move backwards. Admin diagnostics now warns when
the deployment's shape makes this live. See
[BACKGROUND_JOBS.md](BACKGROUND_JOBS.md).

**The Redis job store is unverified against a real server.** Tested against a
fake with correct `WATCH`/`MULTI` semantics; the wire format and connection
handling are unexercised.

**No browser sweep in this session.** Several hand-built tables were checked at
source rather than in a rendered DOM, and the table census names each one and
why. Those DOM checks are owed.

## The shape of the rules

```
missing ≠ zero            unknown ≠ safe           stale ≠ fresh
trending ≠ recommended    rank ≠ verdict           empty ≠ broken
confidence ≠ probability of profit                 risk ≠ probability of loss
```

Each exists because collapsing it produces a number that looks right.
