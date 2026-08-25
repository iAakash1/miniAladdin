# CRC — responsibilities and collaborators

Class-Responsibility-Collaborator cards for the components that carry the
system's behaviour.

**A note on honesty of representation.** Much of this system is modules and
functions rather than classes, and this table says so. `fabric` is a module of
free functions, not an object; `capabilities` is a registry of frozen
dataclasses; the reconcilers are functions inside `fabric`, not a class
hierarchy. Drawing them as classes would make a neater diagram and a false
one. The **Kind** column records what each thing actually is.

## Provider layer

| Component | Kind | Responsibilities | Collaborators |
|---|---|---|---|
| `capabilities` | module + `Capability` frozen dataclass | Declare every question the system can ask a vendor, exactly once. Own the method name, reconciliation strategy, auth and network requirements, expected failure modes, and the justification for any capability outside the fan-out. Refuse construction of a capability that is unexplained or mis-declared. | `fabric` (derives its method/label views), `api.index` (publishes the registry) |
| `fabric` | module | Discover which vendors can answer a capability (`capable`). Run them concurrently and keep every reply (`collect`). Classify failures. Reconcile answers per strategy. | `capabilities`, `parallel.map_concurrent`, vendor adapters, `Ledger` |
| `Evidence` | dataclass | Carry one vendor's answer to one question — including a failed one — with provider, capability, latency, status and timestamp. | `fabric`, `Ledger` |
| `FallbackChain` | generic class | Serve **one best value** fast: walk vendors in priority order, stop at the first success, cache it, degrade to stale on total failure. Deliberately *not* an evidence producer. | `CacheBackend`, `SingleFlight`, vendor adapters |
| `MarketDataProvider` | class | Own quote and series access. Expose both modes: `get_price`/`get_series` through the chain, `quote_evidence`/`series_evidence` through the fabric. | `FallbackChain`, `fabric`, market vendors |
| `FundamentalsProvider` | class | Own profile, fundamentals, ownership, street and analyst access, in both modes. Share vendor instances with `MarketDataProvider` so one API key means one token bucket. | `FallbackChain`, `fabric`, fundamentals vendors |
| `NewsProvider` | class | Fan out headlines across every news vendor, then merge, dedupe and corroborate. Ask only sentiment-capable vendors for sentiment. | `fabric`, news vendors |
| `FilingsProvider` | class | Reach SEC EDGAR for filings, XBRL facts and the point-in-time timeline. | `fabric`, `sec_vendor` |
| Vendor adapters | classes (one per vendor) | Speak one vendor's HTTP dialect. Normalise units and adjustment conventions **at this boundary**. Track health and rate limits. Never leak a credential into an error. | `fabric`, `schemas` |

## Reconciliation

| Component | Kind | Responsibilities | Collaborators |
|---|---|---|---|
| `reconcile_price` | function | Median-reconcile quotes; report agreement count, dispersion and conflict; keep every vendor's reading attributed. | `Evidence` |
| `reconcile_series` | function | Compare daily closes across vendors on the sessions they share. Separate *systematic* adjustment mismatch (stable ratio — a raw series among adjusted ones) from ordinary venue noise. Count session gaps only inside the shared window. | `Evidence`, `PriceSeries` |
| `merge_profile` | function | Union profile fields across vendors, resolving industry by GICS-over-SIC; record conflicts rather than silently picking. | `Evidence` |
| `merge_fundamentals` | function | Union statement lines across vendors; keep per-field attribution. | `Evidence` |
| `merge_news` | function | Dedupe on URL *and* canonical title; count corroboration; preserve per-article vendor sentiment attribution. | `Evidence` |

## Services

| Component | Kind | Responsibilities | Collaborators |
|---|---|---|---|
| `Ledger` | class | Record every input behind a verdict: label, kind, vendors, statuses, latencies, what it was used for. Build the provenance payload. | `Evidence`, `api.index` |
| `visual_intelligence` | module | Build a deterministic image query from the **reconciled** profile, fan out to image vendors, rank, dedupe, cache, and preserve photographer attribution. | `fabric`, `capabilities`, visual vendors |
| `portfolio_intelligence` | module | Value positions from real quotes, build the value curve, compute drawdown, correlation, concentration and money-weighted contribution. Refuse to compute what it has no model for. | `MarketDataProvider` |
| `scoring.engine` | module | Produce verdict, confidence and factor scorecard from the OHLCV frame and fundamentals. Deduct confidence for measured shortfalls. | `api.index` |

## Boundary

| Component | Kind | Responsibilities | Collaborators |
|---|---|---|---|
| `api.index` | FastAPI app | Orchestrate a research run: fan out capabilities in parallel, assemble additive blocks, record provenance, and never let a presentation block fail a verdict. Publish the capability registry. | every provider and service |
| `dashboard/src/lib/api.ts` | module | Map the API payload into typed frontend models. The single place a backend field becomes a frontend field. | `types.ts` |
| `CompanyReport` | React component | Compose the research surface; register which sections exist for a given payload so navigation never points at an empty anchor. | every panel component |
| Panel components | React components | Render one analytical block each, marking provenance, conflict, staleness and primary-source status *visually distinctly*. | `types.ts` |
