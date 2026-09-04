# Fincept and OpenBB, as product references

## How this was studied, and its limits

This is drawn from official documentation, the projects' own architectural
writing, and public descriptions of their current releases. It is **not** drawn
from operating either product. Fincept Terminal v4 is a native C++20/Qt6
desktop binary; OpenBB Workspace is an enterprise deployment. Neither was run,
so nothing here claims to describe how they *feel* — only what they are built
to do and why.

Where a claim is about their architecture it is sourced. Where it is a
judgement about miniAladdin it is mine, and marked as such.

No code, markup, asset or implementation from either project has been copied.
What follows is a reading of their product decisions.

---

## 1. The provider abstraction (OpenBB)

**Source** — OpenBB Platform developer documentation; "The OpenBB Platform data
pipeline" (openbb.co/blog/the-openbb-platform-data-pipeline).

**Concept** — A *standard model* per endpoint, and a *provider model* per
vendor implementing it. Each provider ships a `Fetcher` following a
transform-extract-transform sequence: `transform_query` produces a typed
`QueryParams`, `aextract_data` returns raw vendor output, `transform_data`
returns typed `Data`. Field naming is reconciled with `__alias_dict__`, which
maps a vendor's field names onto the standard ones.

**What they do** — Make "get me prices for AAPL" a single call whose answer has
one shape regardless of which of a dozen vendors served it.

**Why it matters** — It is the only way a multi-vendor product stays sane. The
alternative is every screen knowing which vendor it is talking to, which is how
a UI ends up with `results[0].c` in one place and `close` in another.

**What miniAladdin already has** — The same shape, arrived at independently.
`VendorClient` is the provider model; `PriceQuote`, `PriceSeries`,
`CompanyProfile` are the standard models; `ChainLink`/`FallbackChain` is the
reconciliation layer. Validation lives in the schema (`PriceSeries` validates on
construction) so no adapter can route around it.

**What is missing** — Nothing structural. Our per-vendor field mapping is
hand-written in each adapter rather than declared as a map, which is fine at
seven vendors and would not be at seventy.

**Adopt** — Nothing new. Confirmed the existing design.

**Reject** — The generated `ProviderInterface` singleton and the dynamic router
assembly. It buys breadth we do not want and costs a layer of indirection that
makes a wrong number harder to trace, which is the opposite of this product's
priority.

**Priority** — None. Already done.

---

## 2. Widgets, dashboards and parameter linking (OpenBB Workspace)

**Source** — OpenBB Workspace documentation (docs.openbb.co/workspace).

**Concept** — A widget is a self-contained data component with its own source,
metadata and presentation. A dashboard is a user-arranged collection of them,
with *parameter linking* so changing a date range in one refreshes the others.
Apps are pre-built dashboard templates.

**What they do** — Let a user compose their own analytical surface without
writing code.

**Why it matters** — It is the right answer for a platform serving many
institutions with incompatible workflows. Each desk builds its own screen.

**What miniAladdin already has** — Deliberately, the opposite. Workspaces are
composed by us, and the security page is an argued sequence: identity, price,
history, company, ratios, filed facts, research.

**What is missing** — Nothing. This is a fork in the road, not a gap.

**Adopt** — The *parameter linking* idea only, in the narrow form we already
have: `ChartCursor` synchronises a hovered date across charts. That is
parameter linking with one parameter and no configuration.

**Reject — explicitly** — User-arranged dashboards. This product's entire thesis
is that an arrangement is an argument about what matters, and that the argument
is our job. A drag-and-drop canvas moves that responsibility to the reader and
guarantees that every screenshot of the product is of a different product. It
would also destroy the one thing we have that neither reference has: a fixed
reading order in which provenance always sits beside its number.

**Priority** — Rejected, not deferred.

---

## 3. AI agents over widget metadata (OpenBB) and 37 agents (Fincept)

**Source** — OpenBB Workspace documentation; Fincept v4 release descriptions.

**Concept** — Agents read the metadata of available data components and answer
questions by querying the right ones. Fincept ships 37 across trading,
investing, economics and geopolitics.

**What they do** — Turn "what happened to Apple's margins" into a query plan.

**Why it matters** — When it works it collapses a research task into a
sentence.

**What miniAladdin already has** — A deterministic command palette that acts on
the open object, and a research programme whose verdict is
`NO PRODUCTION CANDIDATE`.

**Adopt** — Nothing yet.

**Reject — explicitly, and for a specific reason** — Not because agents are
uninteresting, but because this product's differentiator is that every number
says where it came from. An agent's answer is a synthesis whose provenance is,
at best, a list of sources it consulted. Shipping one next to a panel that
tells you which of two vendors reported 166,000 employees would teach the
reader that the two claims are equally inspectable. They are not. If an agent
ever ships here it has to carry the same evidence chain as everything else, and
that is a much larger piece of work than wiring a model to a toolset.

**Priority** — Rejected for now. Revisit only with a grounded evidence chain.

---

## 4. Connector count as a product claim (Fincept)

**Source** — Fincept v4 public descriptions: 100+ data connectors, 16 broker
integrations, an 18-module quant suite.

**What they do** — Compete on breadth.

**Why it matters** — For a Bloomberg replacement it genuinely does. A terminal
that cannot reach an asset class is useless to the desk that trades it.

**What miniAladdin has** — Seven market-data vendors, one broker, one asset
class.

**Adopt** — Nothing.

**Reject — explicitly** — Breadth as a goal. Every connector is a schema, a
rate limit, a failure mode and a set of fields that mean *almost* the same
thing as another vendor's. We already found a case where two vendors disagree
by ten per cent about a headcount and the product silently averaged them.
Twenty more vendors is twenty more of those, and the reason this product is
worth using is that it catches them.

**Priority** — Rejected. Add a vendor only when it answers a question none of
the current seven can.

---

## 5. Bring-your-own-data backends (OpenBB Workspace)

**Source** — OpenBB Workspace documentation: proprietary internal data,
licensed third-party feeds and public datasets behind one interface.

**Concept** — A user points the product at their own service and it becomes a
first-class source.

**Why it matters** — An institution's own data is the data it trusts most.

**What miniAladdin has** — Nothing. Providers are compiled in.

**Adopt — conditionally** — The *idea* is right and the cost is low given our
existing `VendorClient` contract: a vendor is a class with a key, a health
check and typed methods. A user-supplied one would slot in.

**Reject** — Doing it before the internal sources are fully exposed. We are
still not showing everything the current seven return, which makes adding an
eighth path a distraction.

**Priority** — Low. After options and evidence.

---

## 6. Equity research workflow (both)

**Source** — Fincept feature descriptions (fundamental analysis, financial
statements, company metrics); OpenBB Platform equity endpoints.

**Concept** — Company identity, statements, ratios, estimates, ownership,
filings and news, reachable from one symbol.

**Why it matters** — It is the actual job.

**What miniAladdin already has** — Identity, quote, history, profile, a
28-field ratio surface, ownership, filings, coverage, and now six fiscal years
of SEC XBRL facts with per-fact provenance.

**What is missing** — Estimates (no provider returns them), options, and a
comparison that enforces semantic compatibility.

**Adopt** — The completeness of the *sequence*, not its composition.

**Reject** — Tabs. Both reference products lean on tabbed sub-navigation per
security. We use one scrolling sequence with an object index, because a tab
hides the thing a reader should have noticed on the way past.

**Priority** — High. This is the north star's spine.

---

## 7. Where both are weaker than us

Stated as a claim about our design rather than a criticism of theirs, since
neither product was operated.

Neither reference makes **per-field provenance** a primary interaction. OpenBB
attributes data at the *provider* level — you know the endpoint served by
`fmp` — and Fincept surfaces source metadata per connector. Neither, as
documented, answers "which vendor said this *particular* number, and does any
other vendor disagree".

That is the gap miniAladdin already occupies. The employee-count case is the
proof: three vendors contribute to one profile, two disagree by ten per cent,
and the honest rendering is `158,000±` opening onto both observations.

**Priority** — Highest. It is the thing worth being best at.

---

## Implementation order this produces

1. **Provider matrix** — we cannot honestly build options without knowing what
   the stack supports. (Phase B)
2. **Options**, to whatever depth the providers actually permit. (Phase C)
3. **Evidence chain** on the existing `Inspectable` primitive. (Phase D)
4. **Semantic comparison** that refuses incompatible metrics. (Phase E)
5. **Streaming** — only if the matrix shows a provider that supports it and a
   surface that benefits. (Phase G)

Explicitly not on this list: dashboard composition, agents, connector breadth,
node editors.
