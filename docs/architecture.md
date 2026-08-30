# Architecture

Derived from the code, not from intent. Every component named here maps to a
file you can open.

## System context

```mermaid
flowchart TB
    U([Analyst])

    subgraph BROWSER["Browser — dashboard/"]
        NEXT["Next.js 16 App Router<br/>terminal components"]
        CLERK["Clerk session"]
    end

    subgraph RENDER["Render — api/ + src/"]
        API["FastAPI<br/>api/index.py, api/persistence.py"]
        RESEARCH["Research pipeline<br/>api/index.py :: research_ticker"]
        PORT["Portfolio intelligence<br/>src/services/portfolio_intelligence.py"]
        VIS["Visual intelligence<br/>src/services/visual_intelligence.py"]
        PROV["Provenance ledger<br/>src/services/provenance.py"]

        subgraph FABRIC["Evidence fabric — src/providers/fabric.py"]
            CAPS["Capability registry<br/>CAPABILITY_METHODS"]
            FAN["Bounded parallel fan-out<br/>src/providers/parallel.py"]
            RECON["Reconcilers<br/>reconcile_price · merge_profile<br/>merge_fundamentals · merge_news"]
        end

        CHAIN["FallbackChain<br/>src/providers/orchestrator.py"]
        ADAPTERS["Vendor adapters<br/>src/providers/vendors/*.py"]
        CACHE["InMemoryCache + SingleFlight<br/>src/providers/cache.py, dedupe.py"]
    end

    SUPA[("Supabase Postgres<br/>watchlists · positions · history")]
    EXT{{"17 external APIs"}}

    U --> NEXT --> CLERK
    NEXT -->|"/api/* rewrite"| API
    API --> RESEARCH & PORT
    RESEARCH --> FABRIC & CHAIN & VIS & PROV
    PORT --> CHAIN
    FABRIC --> ADAPTERS
    CHAIN --> ADAPTERS
    ADAPTERS <--> CACHE
    ADAPTERS <--> EXT
    FABRIC --> PROV
    API <--> SUPA
```

`next.config.ts` rewrites `/api/*` to `BACKEND_ORIGIN`. There is no serverless
Python on Vercel and no queue, broker or worker anywhere in this system.

## The two retrieval modes, and why both exist

This is the single most important thing to understand about the codebase, and
the distinction is documented in the module docstring of
`src/providers/providers.py`.

```mermaid
flowchart LR
    Q{"What is the<br/>question?"}
    Q -->|"'What is the price?'"| C["FallbackChain"]
    Q -->|"'Who agrees about the price?'"| F["Evidence fabric"]

    C --> C1["walks vendors in order"]
    C1 --> C2["stops at first answer"]
    C2 --> C3["one value, cached,<br/>single-flighted"]

    F --> F1["asks every capable vendor"]
    F1 --> F2["concurrently"]
    F2 --> F3["keeps all answers<br/>and all failures"]
    F3 --> F4["reconciles + attributes"]
```

The chain backs the scoring engine, the batch quotes endpoint and the
portfolio series loader — callers that want *a price, now*. Running a
six-vendor fan-out on a watchlist refresh would multiply its cost by six for a
caller that wants one number.

The fabric backs research surfaces and the provenance ledger, where the
interesting output is the *agreement*, not the value. Both draw on the same
vendor objects, rate limiters and cache, so a fan-out following a chain for the
same symbol is largely free.

Replacing either with the other would be wrong in a specific way: chain-only
throws away the four vendors that also knew the answer; fabric-only makes every
watchlist tick six times more expensive.

## Evidence lifecycle

```mermaid
flowchart TB
    RESP["Vendor HTTP response"]
    ADAPT["Adapter<br/>normalises units, preserves period"]
    EV["Evidence<br/>provider · capability · ok · data<br/>error · status · latency_ms · fetched_at"]
    FAIL["Failure classified<br/>rate_limited · not_entitled<br/>timeout · unavailable"]
    REC["Capability-specific reconciler"]
    PAY["Research payload"]
    LEDGER["Provenance ledger"]
    UI["Typed frontend model → panel"]

    RESP --> ADAPT --> EV
    EV -->|"exception"| FAIL --> EV
    EV --> REC --> PAY --> UI
    EV --> LEDGER --> UI
```

A failure produces an `Evidence` object exactly like a success does. That is
the whole point: "Polygon was asked and timed out" is a fact the reader needs,
and dropping it makes a degraded run indistinguishable from a narrow one.

## Domain model

```mermaid
classDiagram
    class Evidence {
        +str provider
        +str capability
        +str symbol
        +bool ok
        +Any data
        +str~None~ error
        +float latency_ms
        +datetime fetched_at
        +str status
    }
    class ProviderResult~T~ {
        +T data
        +str source
        +list sources_consulted
        +float confidence
        +bool disagreement
        +bool cached
        +bool stale
    }
    class PriceQuote {
        +float price
        +float bid, ask, mid
        +float day_open, day_high, day_low
        +float vwap, change, change_pct
        +float ma_50, ma_200
        +str price_basis
        +spread_bps()
    }
    class FundamentalsData {
        +float pe_ratio, roe_ttm
        +float net_margin_ttm
        +float net_margin_5y
        +dict vendor_metrics
    }
    class OwnershipData {
        +float held_percent_institutions
        +float short_percent_of_float
        +str short_interest_date
    }
    class AnalystConsensus {
        +float target_mean, target_high, target_low
        +str recommendation
        +float recommendation_mean
    }
    class Ledger {
        +record()
        +record_fabric()
        +build()
    }

    Evidence "1" --> "0..1" PriceQuote : data
    Evidence "1" --> "0..1" FundamentalsData : data
    Evidence "1" --> "0..1" OwnershipData : data
    Evidence "1" --> "0..1" AnalystConsensus : data
    Ledger "1" o-- "*" Evidence
    ProviderResult "1" --> "0..1" PriceQuote : data
```

`FundamentalsData` carries `net_margin_ttm` **and** `net_margin_5y` as separate
fields on purpose. A trailing margin and a five-year average are different
measurements; one field named `margin` would invite a reconciler to average
them.

## CRC

| Component | Responsibilities | Collaborators |
|---|---|---|
| `fabric.collect` | discover capable vendors by method introspection; fan out concurrently; classify failures; record latency | `parallel.map_concurrent`, vendor adapters, `Evidence` |
| `fabric.reconcile_price` | median consensus, range, dispersion, agreement count, conflict flag; attribute session fields per vendor | `Evidence`, `PriceQuote` |
| `fabric.merge_profile` | union identity fields; prefer GICS over SIC; flag numeric conflicts | `Evidence`, `CompanyProfile` |
| `fabric.merge_fundamentals` | union statement lines; surface disagreement; never average | `Evidence`, `Fundamentals` |
| `fabric.merge_news` | dedupe by URL then canonical title; record corroboration | `Evidence`, `NewsHeadline` |
| `FallbackChain.execute` | serve one value: cache → healthy vendors in order → stale cache | `VendorClient`, `InMemoryCache`, `SingleFlight` |
| `VendorClient` | key management, token-bucket limiting, timeout, bounded retry, circuit cooldown, health stats | `RateLimiter`, `VendorStats` |
| `Ledger` | assemble the chain of custody; classify input health; carry per-vendor rosters | `Evidence`, `ProviderResult` |
| `portfolio_intelligence` | valuation, concentration, volatility, drawdown, correlation, contribution, benchmark | positions, stored analyses, price series |
| `visual_intelligence` | brand identity, deterministic image query, concurrent search, rank, dedupe, cache | Logo.dev, Pexels, Unsplash |

---

## Quant research subsystem

Full treatment in [`docs/quant.md`](quant.md). The shape, and the one property
that distinguishes it from the evidence fabric: **the quant path refuses by
default.** The evidence fabric's job is to gather everything available and mark
its provenance; the quant path's job is to reject anything whose provenance is
not good enough to train on, because a leak makes results *better* and is
therefore invisible exactly when it matters.

```mermaid
flowchart LR
    subgraph IN["Local Dolt clones (14 GB, never in git)"]
        S["stocks · options · earnings · rates"]
    end
    subgraph ADMIT["Admission"]
        C["DatasetCatalog<br/>PIT class per source"]
        M["Manifest status<br/>stricter of the two wins"]
    end
    subgraph BUILD["Point-in-time build"]
        U["UniverseHistory"] --> A["CorporateActions"] --> F["FeatureEngine (103)"] --> L["LabelEngine"]
    end
    subgraph GATE["Guards"]
        T["Truncation invariance"]
        N["Negative controls"]
        FW["HoldoutFirewall"]
    end
    subgraph EVAL["Evaluation"]
        W["WalkForward"] --> MD["Models"] --> B["Backtest"] --> R["Risk"]
    end
    S --> C --> M -->|admitted| U
    M -->|refused| X["ValueError"]
    L --> T --> N --> W
    FW -.->|guards every fit| MD
    R --> REG["ModelRegistry<br/>gated promotion"] --> API["/api/quant/*"] --> UI["/quant"]
```

### CRC — quant components

| Class | Responsibilities | Collaborators |
|---|---|---|
| `DatasetCatalog` | Classify every source point-in-time and survivorship; refuse the inadmissible | `DatasetBuilder` |
| `DatasetBuilder` | Assemble the PIT panel; enforce admission; record provenance | Catalog, RawStore, features |
| `FeatureRegistry` | Definition, lookback, direction, leakage note per feature; refuse unregistered | builder, audit |
| `HoldoutFirewall` | Refuse holdout rows at every guarded stage; lift only on an armed contract | walk-forward, runner |
| `WalkForwardEngine` | Expanding folds with purge and embargo; reserve the holdout | Calendar, Firewall |
| `ExperimentRunner` | Execute a frozen definition; integrity, controls, models, ablation; one artifact | all of the above |
| `BacktestEngine` | Execution lag, costs, turnover; gross and net kept separate | CostModel, Attribution |
| `ModelRegistry` | Store evidence; refuse promotion on missing evidence or failing numbers | `quant_service` |
| `quant_service` | Shape artifacts for the API; compute verdicts from the registry's own gates | API, `/quant` |
