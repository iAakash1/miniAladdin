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

1. **Company-page information architecture + routing.** Restructure the
   analyze experience around the research narrative (overview → thesis →
   financial health → growth → valuation → technical → street → news →
   macro → risk → history) with domain routing (`/company/{ticker}` and
   per-section deep links). The company page becomes the heart of the
   product; existing panels become sections of one flowing report.
2. **Command palette + keyboard navigation.** ⌘K over companies, terminal
   sections, watchlist entries, vault history, and Learn More topics —
   search as the primary navigation mechanism. Recently viewed + pinned
   companies (persisted via the existing preferences/Supabase layer).
3. **Search Intelligence Engine.** Question-shaped queries composed over
   the existing deterministic engines ("why did the recommendation
   change", "compare A and B" → vault compare; "what changed since
   earnings" → history diff + news clusters). Deterministic retrieval
   first; LLM narrates only.
4. **Learn More index.** One browsable, searchable education surface over
   the four glossaries (validation, factor, technical, street) — the
   platform's finance curriculum, discoverable from the palette.
5. **Table system.** Sorting/filtering/sticky headers/density as shared
   primitives for portfolio, vault, and validation tables.
6. **Finnhub metric=all mapping** (P1 from the provider audit) feeding a
   financial-health section of the company page.

Charter constraints binding all of it: professional calm over novelty, the
existing token system, color as meaning only, density with progressive
disclosure, accessibility as a requirement, deterministic engines produce
every number, and nothing ships half-done.
