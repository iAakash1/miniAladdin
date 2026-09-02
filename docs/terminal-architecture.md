# Terminal architecture

## The layer rule

```
Route  →  View  →  Service  →  Domain  →  Provider
```

**Dependencies point one way and never back.** A view cannot reach a provider; a
domain module cannot reach a service. Adapted from Fincept's stated ordering,
where the prohibition is what carries the value rather than the list.

| layer | lives in | may see | must not see |
|---|---|---|---|
| Route | `dashboard/src/app/` | views | services, domain |
| View | `dashboard/src/components/terminal/` | primitives, `quantFetch` | `process.env`, providers |
| Service | `src/services/` | domain, envelope | HTTP request objects |
| Domain | `src/quant/` | other domain modules | services, HTTP |
| Provider | `src/providers/`, `src/quant/datasets/` | external I/O | domain logic |

Where this already held, it held strongly: `portfolio/optimizer.py` cannot see a
model, so a covariance bug is distinguishable from an allocation bug;
`risk/engine.py` cannot see an allocator. The gap was the **data plane** — the
contract between service and view — which `envelope.py` now fills.

## Navigation

Ordered as a research workflow, not a feature list:

```
Market → Research → Factors → Quant → Models → Portfolio → Workspace → Learn
```

You look at the market, form a view on a name, test it as a factor, see what the
register already says, inspect what is deployed, check the portfolio.

`/quant` previously had **no entry in this list** and was reachable only by
typing the URL — the deepest surface in the product, holding the experiment
register, search lab, promotion gates and holdout firewall. An unreachable
workspace is an unbuilt one.

Validation and Methodology moved out of Learn, where filing them told the reader
that the evidence behind the research was optional.

## Command palette

⌘K. Beyond entity search, the palette addresses quant surfaces **by section**:
`/quant#verdict`, `#search`, `#provenance`, `#timeline`, `#run`. A researcher
arrives with a specific question — did it clear the gates, what is the holdout
doing, what command runs this — and the palette answers it rather than depositing
them at the top of a long page.

## Primitives

`dashboard/src/components/terminal/primitives/`

| primitive | contract |
|---|---|
| `Panel` | title, subtitle, **source, asOf, retrievedAt, status** in the container |
| `Metric` | label, value, unit, **method**, pass/fail tone |
| `EnvelopeMetric` | renders from a server envelope; methodology comes from the server |
| `StateBlock` | `loading` / `empty` / `error` / `offline` / `locked`, each naming *what* and *why* |
| `ProvenanceChain` | ordered derivation, because the order is the claim |

Theme-neutral: they use the app's tokens and work inside the dark `.qt` research
surface and on ordinary terminal pages without redefinition.

## The research surface

`/quant` is dark regardless of app theme — scoped via `data-theme` on the route
wrapper, so `/terminal` is untouched. It is read for long stretches beside a
terminal and its dense numeric tables depend on that palette for contrast.

Colour discipline, enforced by the component API:

- **green** a gate that passed, or a genuinely healthy system state
- **red** a gate that failed, or a blocking condition
- **amber** a warning, or evidence too thin to quote
- **grey** unknown, unavailable, not computed

Green is never used because a number is positive. The highest IC in the search
leaderboard routinely renders amber, because it is routinely overfit.

## Ordering is an argument

The research page leads with what is blocked and sealed and shows supporting
statistics afterwards. This is why user-arranged dashboards were rejected from
both references: a layout that lets a reader move net Sharpe below the fold lets
them build a page that misrepresents the research.

## What is deliberately absent

Options, futures, FX, crypto, screeners and an agent workspace appear in both
reference terminals and have no data behind them here. **A navigation entry
leading to invented data is worse than its absence.** The envelope contract
exists for them; when a real source is wired, the panel renders with provenance
or renders `unavailable`.
