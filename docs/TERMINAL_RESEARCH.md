# Terminal research: what we took, and what we did not

Source study of two open financial terminals, read against miniAladdin's own
architecture. The purpose is product ideas, not code: nothing here was copied,
and several of the strongest ideas were deliberately declined.

Read at source and documentation level in September 2026:

- **Fincept Terminal** — `github.com/Fincept-Corporation/FinceptTerminal`,
  particularly `docs/ARCHITECTURE.md`. A C++20/Qt6 desktop binary with an
  embedded Python 3.11 runtime for analytics.
- **OpenBB Platform** — `docs.openbb.co`, developer guide and provider
  extension docs. A Python data platform with a provider extension system.

---

## 1. One fetch per topic, subscribers fan out free

**Fincept.** Every external call goes through `DataHub`, an in-process pub/sub
keyed by topic — `market:quote:AAPL`. A screen subscribes; the hub checks the
cache, refreshes if stale, and publishes to every subscriber. Screens never
call HTTP directly and never own caches. `CacheManager` holds TTL per topic
policy in SQLite.

**Why it exists.** A desktop terminal shows one symbol in six places at once. Six
independent fetches is six times the vendor rate limit spent on one fact, and
six arrival times for a number that should be identical everywhere.

**What we had.** Exactly the failure that motivates it. The home screen issued
two overlapping quote requests — the watchlist wanting AAPL, MSFT, NVDA, TSLA
and the recents list wanting MSFT, AAPL, NVDA — on independent timers. The
browser showed both taking thirty seconds against a cold vendor cache and both
timing out into em dashes, and the same symbol could hold two different prices
on one screen.

**Adopted.** `lib/quote-hub.ts`. Panels declare symbols; the hub unions every
subscription into one request on one timer and pushes to all subscribers.
Reference counted, so one panel closing cannot take a symbol another still
shows. `lib/research-cache.ts` applies the same idea to the 23-second research
fan-out that three panels on the security page need parts of.

**Declined.** The SQLite persistence layer beneath it. Fincept is a desktop
binary that survives restarts; this is a web terminal where a persisted quote
would be a stale price wearing a live badge. The cache collapses concurrent
readers and nothing more.

---

## 2. Presentation never touches transport

**Fincept.** "A screen is a `QWidget` subclass that renders state and accepts
user input. It does not call `HttpClient` directly, does not own caches, and
does not contain business logic." Dependency direction is enforced:
Presentation → Application → Data Plane → Adapters → Infrastructure.

**What we have.** Components still call `fetch` directly. The quote hub and the
research cache are the first two seams; most surfaces have not moved behind
them.

**Partially adopted, honestly.** The layering is right and we are two modules
into it, not finished. What has moved is what was demonstrably breaking:
duplicated quote requests and duplicated research fan-outs. Moving the rest is
worth doing and has not been done, and this document should not imply otherwise.

---

## 3. A standard model behind many providers

**OpenBB.** A router command declares a standard model; provider extensions
supply `Fetcher`s implementing it. Each fetcher runs Transform–Extract–Transform:
input dict to `QueryParams`, provider call, provider response to a standardised
`List[Data]`. `__alias_dict__` absorbs naming differences between vendors. The
`ProviderInterface` singleton routes a requested provider to its fetcher.

**Why it exists.** Twelve vendors spell the same field twelve ways. Without a
standard model, every consumer learns every vendor's vocabulary.

**What we have.** The Python provider layer already does this well —
`FundamentalsData` is a standard model with fifteen vendor-agnostic fields, and
critically it writes the *period into the field name*: `net_margin_ttm` beside
`net_margin_5y`, because a schema calling both `margin` would invite a
reconciler to average them. That is a stronger idea than OpenBB's aliasing and
we already had it.

**Adopted.** The frontend now honours it. The ratio surface had been fetched and
discarded for months; it is on the security page with each field's period shown,
and the comparison keeps TTM and five-year figures as separate rows rather than
one.

**Declined.** A provider-selection UI. OpenBB lets a caller pick `provider=`.
Here the orchestrator reconciles across vendors and reports which answered,
which is more useful than making a reader choose one — and a chooser implies a
per-field guarantee the reconciliation does not give.

---

## 4. A canonical instrument, independent of any source

**Fincept.** An `Instrument` model standardises symbols across brokers, with a
`SymbolResolver` seam per broker. Raw broker strings are barred from
cross-broker code.

**What went wrong here.** Every security surface had been wired through the
research panel, so when that dataset went stale the entire security workflow
went with it — a terminal with no way to look up a company.

**Adopted.** `lib/security.ts` holds identity that knows nothing about
experiments, folds or gates, and `lib/symbols.ts` keys watchlists and recents on
the ticker alone. Verified by killing the API: the watchlist keeps its names and
loses only its prices.

---

## 5. Errors as values, not exceptions across boundaries

**Fincept.** `Result<T>` and signals; no exceptions cross a module boundary.

**Adopted in spirit, not in form.** We do not have a `Result` type. What we have
is stricter about the same thing: a failure must produce a distinguishable
*state*, never a zero and never an absence that reads as a measurement. The
observation module separates observed from last-observed from unavailable from
not-recorded, and the sweep in `test_state_is_not_inferred.py` forbids deriving
a verdict from a fetch that may have failed.

---

## 6. What we rejected outright

**Fincept's 54 screens and multi-window docking.** Fincept is a desktop binary
where a user arranges panels across monitors. A 24-destination sidebar was
already too flat here; the fix was fewer, better-grouped destinations, not more
surfaces.

**Fincept's 37 trader/investor AI agents.** No grounded data path exists for
them here, and an ungrounded agent in a research terminal manufactures the one
thing this product exists not to manufacture.

**Fincept's paper-trading engine and broker integrations.** Out of scope; there
is no execution path and pretending otherwise would be the largest possible
version of feature theatre.

**OpenBB's widget/workspace customisation.** A composable widget canvas is a
genuinely good idea for a platform with a hundred data commands. Here it would
mean shipping an empty canvas and calling it flexibility.

---

## 7. Where we are ahead

Worth protecting rather than trading away.

**Semantic typing of displayed values.** Every kind declares its comparability
class, direction, delta semantics and scale, and the comparison engine refuses
arithmetic across them. Neither terminal studied does this; both would happily
subtract a rank correlation from a return correlation.

**A difference carries its own unit.** The gap between two percentages is
percentage points, and between two multiples a ratio. Found and fixed while
building the security comparison.

**Evidence as a first-class layer.** Trace shows lineage *and* where trust
stopped, with a measured failure distinguished from an unmeasured gate. The
research is honestly demoted rather than hidden: NO PRODUCTION CANDIDATE is one
line on the terminal home and the full archive is one click away.

**Failure states that hold.** A provider outage degrades each surface
independently, and the status rail reports what it last saw with a timestamp
rather than continuing to assert it.
