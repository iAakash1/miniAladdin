# Data flow

## A research request, end to end

```mermaid
sequenceDiagram
    autonumber
    participant UI as Terminal UI
    participant API as FastAPI
    participant F as Evidence fabric
    participant P as Vendor adapters
    participant L as Provenance ledger

    UI->>API: GET /api/research/AAPL
    API->>API: warm caches (research_prefetch)

    par macro + technicals concurrently
        API->>P: FRED snapshot
    and
        API->>P: 1y price series (chain)
    end

    API->>F: collect("quote", AAPL)
    F->>P: 7 vendors, bounded concurrency
    P-->>F: 4 answered · fmp not_entitled · marketstack rate_limited
    F->>F: reconcile_price → median, dispersion, agreement
    F-->>L: record_fabric(Consensus quote)

    API->>F: collect("company") · collect("fundamentals")
    F-->>API: union + conflicts

    API->>F: collect("filings") · collect("xbrl_timeline")
    F-->>API: filings, restatements

    API->>F: collect("news") over 5 vendors
    F->>F: merge by URL then canonical title
    F-->>API: unique stories + corroboration

    API->>API: scoring engine (deterministic)
    API->>API: LLM narration (optional, never fatal)
    API->>L: build()
    API-->>UI: typed payload + provenance
```

Steps 8–9 are the shape that matters: **two vendors failed and the request
succeeded.** Their failures travel into the ledger as evidence rather than
vanishing.

## Failure, in detail

```mermaid
sequenceDiagram
    participant F as fabric.collect
    participant A as polygon
    participant B as fmp
    participant C as marketstack

    par
        F->>A: get_price
        A-->>F: 309.35 (1039ms)
    and
        F->>B: get_price
        B-->>F: HTTP 403
    and
        F->>C: get_price
        C-->>F: 429
    end

    F->>F: _classify(403) → not_entitled
    F->>F: _classify(429) → rate_limited
    Note over F: three Evidence objects,<br/>one ok, two not
    F-->>F: reconcile over the one that answered
```

`fmp` answering 403 is an entitlement boundary, not an outage. Classifying it
as such keeps the circuit breaker from cooling the whole vendor down and taking
its working endpoints with it.

## SEC / XBRL and restatement detection

```mermaid
flowchart TB
    EDGAR([SEC EDGAR — keyless])
    SUB["/submissions — filings"]
    CF["/api/xbrl/companyfacts"]
    FACTS["get_xbrl_facts<br/>latest value per fiscal year"]
    TL["get_xbrl_timeline<br/>every filed observation<br/>restatements preserved"]
    G{"Comparability guards"}
    TREND["Year-over-year trend"]
    RESTATE["Restatement detection"]
    UI["SecFilings panel"]

    EDGAR --> SUB --> UI
    EDGAR --> CF --> FACTS --> TREND --> UI
    CF --> TL --> G --> RESTATE --> UI

    G -.->|"same concept"| G
    G -.->|"same period START and END"| G
    G -.->|"same unit"| G
    G -.->|"same form family"| G
    G -.->|"distinct values only"| G
    G -.->|"±0.5% noise floor"| G
```

The **period start** guard is not theoretical. Grouping on period *end* alone
produced 106 "restatements" for Apple, the largest a fictitious −77% — both
values filed on the same day, because a 10-K carries the fiscal-year figure and
the Q4 that shares its end date. Adding `start` took it to 9 real ones: Apple's
2009 retrospective adoption of ASU 2009-13, refiled a year later.

## Portfolio

```mermaid
flowchart LR
    POS[("positions<br/>ticker · shares · avg price")]
    PAR["parallel series fetch<br/>holdings + benchmark in one fan-out"]
    VAL["value_positions<br/>invested vs market"]
    CURVE["value_curve<br/>Σ shares × real close"]
    RISK["volatility · max drawdown<br/>correlation on returns"]
    BENCH["benchmark_comparison<br/>rebased to 100 at shared start"]
    UI["PortfolioIntelligence"]

    POS --> PAR --> VAL --> UI
    PAR --> CURVE --> RISK --> UI
    CURVE --> BENCH --> UI
```

The benchmark rides the same fan-out as the holdings rather than being a
separate call after them. The output is labelled **return difference**, never
alpha: no beta is estimated and no risk-free rate is subtracted.

## Visual intelligence

```mermaid
flowchart TB
    ID["Company identity<br/>name · domain · sector · industry"]
    DOM{"domain known?"}
    SEARCH["Logo.dev brand search<br/>secret key, backend only"]
    LOGO["img.logo.dev/ticker<br/>publishable key, browser-safe"]

    QUERY["Deterministic query<br/>from name + industry + sector"]
    PX["Pexels"]
    US["Unsplash"]
    RANK["Rank · dedupe · stable pick"]
    CACHE[("Cache — identity 7d, context 24h")]
    UI["Media strip, attributed"]

    ID --> DOM
    DOM -->|no| SEARCH --> LOGO
    DOM -->|yes| LOGO
    ID --> QUERY
    QUERY --> PX & US
    PX & US --> RANK --> CACHE --> UI
```

Logo.dev is **identity**; Pexels and Unsplash are **context**. They are not
interchangeable, and a stock photograph is never presented as a company's own
image. The two image providers run concurrently — neither is the other's
fallback.

---

## Quant: a dataset build, end to end

The distinguishing feature of this path is where it *stops*. Each stage can
refuse, and the refusal names the source and the reason rather than degrading to
a partial answer — a silently incomplete panel is the one failure that makes
results look better.

```mermaid
sequenceDiagram
    autonumber
    participant R as ExperimentRunner
    participant C as Catalog
    participant S as RawStore
    participant U as UniverseHistory
    participant F as FeatureEngine
    participant G as Guards
    participant W as WalkForward
    participant FW as HoldoutFirewall

    R->>C: admit(source, role="feature")
    alt not point-in-time (catalog OR manifest)
        C-->>R: ValueError — named source, named reason
    end
    C->>S: read partitions
    S-->>F: frame + manifest
    R->>U: membership per date (survivorship-free)
    F->>F: per-symbol features (chronology enforced)
    F->>F: as-of joins — options, earnings, estimates, fundamentals
    Note over F: statement tables joined FORWARD to<br/>earnings_calendar; no announcement -> dropped
    F->>F: cross-sectional ranks, fitted per date
    F-->>G: panel
    G->>G: truncation invariance at 3 cutoffs
    alt integrity fails
        G-->>R: abort — no result is admissible
    end
    G->>G: negative controls
    alt a blocking control finds signal
        G-->>R: abort BEFORE any model is fitted
    end
    G->>W: plan folds
    W->>FW: arm_window(holdout_start, holdout_end)
    loop every fold
        W->>FW: assert_clear(train), assert_clear(validation)
        alt holdout rows present
            FW-->>W: HoldoutBreach — nothing is computed
        end
        W->>W: fit, predict, score
    end
```

### Timestamp semantics, per source

| Source | `date` means | Usable as-dated? |
|---|---|---|
| `ohlcv` | the session it describes | yes |
| `split` / `dividend` | ex-date | yes |
| `us_treasury` | observation | yes |
| `volatility_history` / `option_chain` | observation | yes |
| **`eps_estimate` / `sales_estimate`** | **estimate vintage** | **yes** |
| `earnings_calendar` | announcement | yes |
| `eps_history` | fiscal period end | **no — gate required** |
| `income_statement`, `balance_sheet_*`, `cash_flow_statement` | fiscal period end | **no — gate required** |

The last two rows are the whole reason `features/fundamentals.py` exists. AAPL's
quarter ending 2026-06-30 was announced 2026-07-30; reading the period-end date
as an availability date grants a month of hindsight on every quarterly figure.
