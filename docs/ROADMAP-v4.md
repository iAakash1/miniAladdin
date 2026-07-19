# OmniSignal v4.5 roadmap — Maximum Intelligence Release

Principle: extract more intelligence from data we already have before adding
anything new. Full findings in [PROVIDERS-AUDIT.md](PROVIDERS-AUDIT.md).

## Shipping in v4.5 (this release)

**P0-A — Technical Intelligence Engine** (zero API cost)
Deterministic computation of the full classic indicator suite from the 1-year
OHLCV frame every analysis already fetches: SMA 20/50/200 + golden/death
cross, EMA 12/26, MACD, RSI, ADX/DI, ATR + volatility regime, Bollinger %B +
bandwidth, Stochastic, OBV trend, MFI, CCI, ROC, Aroon, rolling VWAP, and
swing support/resistance. Classified into trend / momentum / volatility /
volume-confirmation regimes with plain-language findings. Additive
`technical_intelligence` block on `/api/research`; presentation-layer
intelligence only — the v2.1 scoring engine and its verdicts are unchanged.

**P0-B — Street & Insider Intelligence** (Finnhub free tier)
Recommendation trends, EPS-surprise history and insider sentiment (MSPR)
through the existing provider abstraction (cached, rate-limited, deduped,
vendor-invisible to the frontend). Additive `street_intelligence` block with
deterministic interpretation.

**Learn More coverage** for every new indicator/metric via the existing
MetricEntry + MetricExplainer system — definition, formula, interpretation,
healthy/unhealthy ranges, limitations, and exactly how OmniSignal uses it.

## Deferred (documented, prioritized)

- **P1** Map unused Finnhub `metric=all` fields (margins, ROE, liquidity)
  into `FundamentalsData` → financial-health panel.
- **P2** News-cluster timeline UI over the existing v2.1 news methodology.
- **P2** Peer context via Finnhub `/stock/peers`.
- **P2** FRED dashboard polish (M2, dollar index, Michigan sentiment).
- **P2** Portfolio analytics (sector allocation, correlation, risk
  contribution) over persisted positions.
- **✗** FMP wishlist endpoints (DCF, ownership, segments, buybacks…) —
  premium-only on the current plan; revisit only if the plan changes.
- **✗** Alpha Vantage technical endpoints — 25 req/day makes them strictly
  worse than local computation from OHLCV we already hold.

## Non-negotiables carried through every increment

Deterministic engines produce every number; the LLM narrates only. Additive
API changes only (v1.x contract preserved). Provider abstraction unbroken —
no component knows which vendor answered. Every increment lands with tests,
lint/typecheck, production build, and a production-stability check before the
next begins.

## v5 charter — product ownership (adopted 2026-07-18)

Standing priorities from the product charter, in execution order. Each item
lands with the full QA matrix and a production-stability check, per the
established discipline.

1. ~~**Company-page IA + routing.**~~ **Shipped** (`0323f29`):
   `/company/{ticker}` permanent URLs, CompanyReport with self-filtering
   section map, launcher + legacy redirects. This established the
   **Research Section framework** (report-section anchors + SectionNav) —
   every future section extends it rather than inventing placement.
2. **The Intelligence OS — infrastructure, not UI.** A universal entity
   layer that every surface consumes; ⌘K is merely its first client.
   - **Entity contract** (define before any client): `{ id, type, title,
     description, route, keywords, relationships, actions, metadata }`.
     Entity types span the whole domain: company, indicator, metric,
     glossary topic, vault entry, watchlist, portfolio holding, macro
     series, news cluster, validation item, methodology section.
   - **Registry architecture:** a frontend entity registry composed of
     providers — static (routes, glossary entries, methodology sections),
     local (recently viewed), and async (vault history, watchlists,
     company lookup via /api/screen). Backend counterpart: engines
     already return entity-shaped rows; the screen service becomes the
     company-entity resolver. No client couples to a source.
   - **Search is reasoning:** question-shaped queries compose engines
     ("what changed since earnings" = history diff + news clusters;
     "compare A and B" = vault compare). Deterministic engines answer;
     the LLM only explains. Grows inside the same entity layer.
   - **Clients, in order:** ⌘K palette → header search upgrade → related-
     content cross-links on company pages → future surfaces (context
     panels, API consumers) — all reading the same registry.
3. **Search Intelligence Engine.** Question-shaped queries composed over
   the deterministic engines ("why did the recommendation change",
   "compare A and B" → vault compare; "what changed since earnings" →
   history diff + news clusters). Deterministic retrieval; LLM narrates.
   Lands inside the ⌘K surface, not beside it.
4. **The universal OmniSignal data table.** One component: sorting,
   filtering, sticky headers, density, keyboard navigation, CSV export,
   inline explanations — then portfolio, vault, and validation tables
   become configurations of it, not implementations.
5. **The Learn More index.** One browsable, searchable education surface
   over the four glossaries — the platform's finance curriculum,
   discoverable from ⌘K, deep-linkable per entry.
6. **Financial-health section** (Finnhub metric=all mapping, P1 from the
   provider audit) — the first new consumer of the Research Section
   framework and the universal table.

Charter constraints binding all of it: professional calm over novelty, the
existing token system, color as meaning only, density with progressive
disclosure, accessibility as a requirement, deterministic engines produce
every number, and nothing ships half-done.
