# miniAladdin — product architecture

What the product would be if it were built today, given what the audits and the
capability harvest established. This is the control plane for the migration: it
records the information architecture, and the mapping from every backend
capability to where it now lives.

---

## The finding that decided the architecture

Of 43 endpoints, **eleven were never called by any component**. They are not
stubs. Among them:

| Endpoint | What it publishes |
|---|---|
| `/api/ml/features` | 27 features with lookback, availability lag, PIT safety, formula, direction |
| `/api/ml/datasets` | 19 datasets with point-in-time class, survivorship, ingestion, columns |
| `/api/ml/registry` | 103 entries with validation methodology, walk-forward, multiple testing, leakage evidence, unmet gates |
| `/api/ml/provenance/{label}/{model}` | the chain from dataset to prediction |
| `/api/quant/latest` | dataset sources with `retrieved_at` and PIT status per partition |
| `/api/providers/capabilities` | introspected vendor capability matrix |

The product's claim is that it tells you how far a number can be trusted. The
evidence for that claim was being computed, tested, and thrown away, while the
UI spent its space on a model leaderboard.

**So the architecture is not a new idea bolted onto the backend. It is the
backend's own object model, finally surfaced.**

---

## Information architecture

Organised by the research loop, not by backend module. Five groups, each a
question a researcher moves between rather than a subsystem name.

```
OBSERVE     Command        what matters right now
            Securities     what is happening with this asset

EXPLAIN     Factors        what explains returns
            Signals        does this feature predict anything

VALIDATE    Models         what has been trained
            Evidence       should I trust this one
            Experiments    what evidence do we actually have

ALLOCATE    Portfolio      what should I own
            Risk           what can hurt me

VERIFY      Data           where did this number come from
            Methodology    how is it computed
```

The old architecture — Market, Research, Factors, Quant, Models, Portfolio,
Workspace, Learn — named subsystems. `Quant` in particular meant "the part of
the backend written later", which is not a question anyone asks.

Two changes carry most of the weight:

**Evidence is separated from Models.** "What has been trained" and "should I
trust this" are different questions with different answers, and merging them is
what produced a leaderboard.

**Data is promoted to a top-level workspace.** Provenance was the differentiator
and had no surface at all.

---

## The shell

```
┌──────────────────────────────────────────────────────────────────┐
│ TITLE                                              actions       │
├────────────┬─────────────────────────────────┬───────────────────┤
│ OBSERVE    │                                 │  CONTEXT          │
│  Command   │                                 │                   │
│  Securities│      WORKSPACE                  │  what this answers│
│ EXPLAIN    │                                 │  method           │
│  Factors   │      panels, tables, strips     │  assumptions      │
│  Signals   │                                 │  provenance chain │
│ VALIDATE   │                                 │                   │
│  Models    │                                 │                   │
│  Evidence  │                                 │                   │
│ ...        │                                 │                   │
├────────────┴─────────────────────────────────┴───────────────────┤
│ CATALOGUE recorded · HOLDOUT blocked · PRODUCTION unavailable    │
└──────────────────────────────────────────────────────────────────┘
```

Three regions scrolling independently, because a terminal is navigated rather
than read top to bottom, and what is selected must stay on screen while its
context changes.

**The bottom rail is the piece that matters.** Research state appears on every
screen, reading the same way whether the news is good or not. A state that shows
up only when something is wrong teaches people that its absence means everything
is fine — which is exactly the inference this product must not encourage.

Responsive states are designed, not stacked: at 1180px the context column
becomes a drawer; at 860px navigation does too, and the workspace keeps the
screen. Wide tables scroll inside their own region so the page never scrolls
sideways.

---

## Visual language

**Cards are gone.** A card is a container for one thing when you have no
hierarchy. Panels are ruled regions of one page — no radius, no shadow, no
float — and the default for a row of figures is a metric strip on a shared
baseline rather than six boxes.

**Type is a scale of seven**, each size with a job: micro (units), meta
(provenance), label (headers), body (cells), value (the numbers being read),
lead (panel titles), title (one per screen). A page needing an eighth has a
hierarchy problem.

**Numbers are monospaced, tabular, slashed-zero.** A column that does not align
cannot be scanned, and scanning is the point.

**Two colour vocabularies, kept strictly apart.**

| Research state | says where a number came from |
|---|---|
| live · recorded · stale · waking · unavailable · blocked · experimental · candidate · production |

| Evidence tone | says whether it is good news |
|---|---|
| positive · negative · warning · null |

Conflating them is how a stale number reads as a bad one. There is no
decorative accent: colour is applied when sign or status *is* the information.
Desaturated on purpose — a terminal that shouts at every negative number
teaches people to stop reading it.

**Motion is used once.** A waking service pulses, because it is the one state
actually changing while you look at it. Everything else is still.

---

## The primitives

| Primitive | Enforces |
|---|---|
| `Value` | Refuses to render a bare number. Null, NaN or infinity return an em dash, never a zero. Unit and method travel with it. |
| `Status` | The nine research states, with the definition on hover. |
| `Panel` | A ruled region with a title, optional state, and no card styling. |
| `Strip` | The replacement for a card grid. |
| `Table` | Sticky headers, three densities, right-aligned numerics, unit qualifiers under column headers, own horizontal scroll. |
| `StateBlock` | Empty, error and data-gated states. A gated capability lists what it needs and says no synthetic values stand in. |
| `Provenance` | The chain from source to number. |

`Value` returning an em dash for a non-finite input is a direct consequence of
the audits: three separate places rendered invalid mathematics as `0.0`, and it
read as a measurement.

---

## Capability map

| Capability | Backend | Endpoint | Was | Now |
|---|---|---|---|---|
| Dataset contracts | `ml_service.dataset_catalog` | `/api/ml/datasets` | **nothing** | Data |
| Feature registry | `ml_service.feature_catalog` | `/api/ml/features` | **nothing** | Data |
| Model registry + gates | `ml_service.registry` | `/api/ml/registry` | **nothing** | Evidence |
| Risk measures (23) | `risk.analyse` | `/api/quant/portfolio` | inside Portfolio | Risk |
| Risk decomposition | `risk.risk_contributions` | `/api/quant/portfolio` | inside Portfolio | Risk |
| Preflight gates | `quant_preflight_service` | `/api/quant/preflight` | Quant | Quant → Evidence |
| Selection verdict | `quant_service.selection` | `/api/quant/selection` | Quant | Quant → Evidence |
| Staged search | `quant_service.search` | `/api/quant/search` | Quant | Signals |
| Factor lab | `factor_lab_service` | `/api/factors` | Factors | Factors |
| Inference | `inference` | `/api/quant/inference` | Quant | Models |
| Provenance chain | `ml_service.provenance` | `/api/ml/provenance` | **nothing** | Data *(pending)* |
| Provider capability matrix | `fabric.capability_matrix` | `/api/providers/capabilities` | **nothing** | Data *(pending)* |
| Analyst memo | `report_generator` | `/api/memo` | **nothing** | Securities *(pending)* |
| Covariance estimators | `portfolio.covariance` | *(none yet)* | — | Risk *(needs endpoint)* |
| Diversification ratio | `portfolio.diversification` | *(none yet)* | — | Risk *(needs endpoint)* |

Nothing has been removed. New workspaces sit beside the surfaces they will
replace so the two can be compared before anything is deleted.

---

## Built

- Design system: tokens, type scale, density scale, status vocabulary, table
  and panel primitives, responsive states, focus states.
- Workbench shell with research-state rail.
- **Data** — dataset and feature contracts, on two previously unused endpoints.
- **Evidence** — the registry as an evidence chain, unmet gates as the headline.
- **Risk** — 23 measures grouped by the question each answers.

## Not yet migrated

Command, Securities, Factors, Signals, Models, Portfolio, Experiments and
Methodology still run on the old shell. They work; they have not been rebuilt.

Also pending: endpoints for the covariance estimators and diversification ratio
added in this session's harvest, the provenance-chain and provider-matrix
surfaces, and the analyst memo.

## Refused

**Effective number of bets.** The standard principal-axis construction is not a
function of its inputs — ten independent names return 10.000 under one
eigenbasis and 3.770 under another with the covariance unchanged. Recorded in
`SEMANTIC_AUDIT.md` with the measurement.

**Options, fixed income, valuation.** No data contract exists for option chains,
yield curves or financial statements at point-in-time. The mathematics is
implementable; presenting it against absent data is not. When these appear they
will appear as `StateBlock` entries naming exactly what they require.
