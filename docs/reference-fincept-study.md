# Fincept Terminal — architecture study

Source: <https://github.com/Fincept-Corporation/FinceptTerminal>, primarily its
`docs/ARCHITECTURE.md`.

**Licence: AGPL-3.0-or-later, dual-licensed**, with the open repository carrying
explicit restrictions on commercial, internal and hosted use. AGPL's copyleft
reaches network use. **No Fincept code, markup, assets or branding appears in
this repository.** What follows is a study of architecture, implemented
independently.

Fincept is a Qt6 desktop application: ~1,626 C++ files, ~342k lines, 54
lazy-instantiated screens. Most of its surface area does not transfer to a
Next.js research product. Its *layering* does.

---

## What Fincept does that is worth taking

### 1. A stated, one-directional layer order

> Presentation → Application → Data Plane → Adapters → Infrastructure →
> Platform. Never reverse.

**Why it works.** The prohibition is what carries the value, not the list. A
screen physically cannot reach a broker, so "where does this number come from"
always has an answer.

**Adopted.** Our equivalent, now written down in `terminal-architecture.md`:

```
Route → View → Service (src/services) → Domain (src/quant) → Provider
```

Already true in the strong places — `portfolio/optimizer.py` cannot see a model,
`risk/engine.py` cannot see an allocator. The gap was the *data plane*, which is
what this session added.

### 2. `DataHub` topics with a per-topic `TopicPolicy`

Topics named `domain:subdomain:id[:modifier]`, a SQLite-backed `CacheManager`,
and a **TTL and minimum refresh interval declared per topic**. One fetch, many
subscribers.

**Why it works.** Freshness becomes a property of the *data* rather than a
convention in each screen. Two panels showing the same series cannot disagree
about whether it is current, because neither of them decides.

**Adopted, adapted.** `src/services/envelope.py::FreshnessPolicy` declares a TTL
per data kind — quote 15 min, macro 2 days, news 1 hour, inference 5 min,
experiment and registry `None` — with a written reason for each. `status` is
**derived** from the timestamp and the policy and cannot be passed in.

**Rejected: the pub/sub hub itself.** Fincept needs one because 54 always-live
screens share a process. We have request-scoped page loads behind a CDN; a
subscription bus would be machinery without a subscriber. The *policy* was the
transferable half.

### 3. Producers declare which topics they refresh

A data source implements `Producer`, declares its topic patterns, and publishes.
Screens subscribe; they never call HTTP or the database directly.

**Adopted in principle.** Components already fetch through `quantFetch` rather
than reaching for `process.env`. The envelope extends it: a service now returns
value *and* provenance, so a component cannot render a number whose origin it
never saw.

### 4. `Instrument` as the canonical symbol vocabulary

`InstrumentSource` + `SymbolResolver` dispatch provider-specific resolution;
code never manipulates raw broker strings.

**Noted, not implemented.** We have one symbol namespace today, so a resolver
would be indirection with nothing to resolve. Recorded because the moment a
second provider disagrees about a ticker, this is the shape of the fix.

### 5. Environment whitelisting for subprocesses

Python subprocesses receive 22 known API keys; every other credential-shaped
variable is stripped.

**Worth adopting; not done this session.** Our training CLI inherits the parent
environment wholesale. Nothing leaks today because nothing in the research path
prints its environment, which is a property of the current code rather than a
guarantee. Logged as a real follow-up.

### 6. `IStatefulScreen` — screens declare whether state survives restart

**Adopted conceptually.** Our terminal keeps context in the URL rather than a
session store, which is the web-native equivalent and is more shareable. The
useful discipline is the *explicitness*: state that persists says so.

---

## Deliberately rejected

| Fincept feature | Why not |
|---|---|
| **Node/workflow editor** | Visual recombination of research steps is a UI for generating uncounted trials. Our binding constraint is that 1,029 trials have already been spent on ~96 independent blocks of data. |
| **37 agents** | Breadth of persona is not breadth of evidence. |
| **100+ connectors** | EXP-005 and EXP-007's context sweep both measured that adding data sources to this panel *reduces* information — `G_all`, the arm with everything, is the worst base-containing arm at IC +0.0096. Connector count would be a vanity metric against our own evidence. |
| **16 broker adapters, paper trading, order matching** | We have no execution venue and no promoted model. Building an order path for a system with zero production models is building the wrong thing. |
| **Docking / draggable panels** | On a research page the ordering *is* the argument: blocked and sealed states lead, supporting statistics follow. A layout that lets a reader move net Sharpe below the fold lets them build a page that misrepresents the research. |
| **SQLite cache layer** | Our expensive computation is offline and already artifact-cached. A second cache would be a second thing to invalidate. |

---

## Summary

The single most valuable idea in Fincept's architecture is **declared freshness
per data kind**, and it is now implemented. The second is the **one-directional
layer rule**, which we mostly had and have now written down. Almost everything
else is correct for a 54-screen desktop trading terminal and wrong for a
research product with one dataset and no execution.
