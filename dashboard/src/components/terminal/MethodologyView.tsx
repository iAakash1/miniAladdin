'use client'

import Section from '@/components/ui/Section'
import MetricExplainer from './MetricExplainer'
import { FACTOR_GLOSSARY, FACTOR_FAMILY, FAMILY_TITLES, type FactorFamily, type FactorKey } from '@/lib/factorGlossary'

/* ============================================================
   Methodology Center — the "how OmniSignal actually works" page.
   Entirely static, authored reference content: no ticker data, no
   API calls, nothing computed here. Every fact below is grounded in
   the real pipeline (src/scoring/engine.py) and provider layer
   (src/providers/) — see the file-level comments on factorGlossary.ts
   and metricGlossary.ts for the same discipline applied there.

   Deliberately conceptual rather than literal about tunable numbers
   (exact sleeve weights, exact verdict cut points): those live in
   named constants in engine.py and can be retuned without this page
   silently going stale. What's stable and worth documenting here is
   the *mechanism* — how normalization works, that weights adapt to
   regime, that confidence and risk are itemized rather than opaque.
   ============================================================ */

interface PipelineStage {
  title: string
  body: string
}

const PIPELINE: PipelineStage[] = [
  {
    title: 'Market data',
    body: 'Live quotes, OHLCV price history, fundamentals, news and macro series, each pulled through a vendor fallback chain so no single provider outage stops scoring.',
  },
  {
    title: 'Normalization',
    body: 'Every raw figure becomes a robust, outlier-resistant statistic — a median/MAD z-score, or a t-statistic for return-type factors — so factors that started on completely different scales become comparable.',
  },
  {
    title: 'Factor computation',
    body: '15 factors compute across five families: momentum, reversal, fundamental, quality and news. A factor missing its required input is simply omitted, never estimated.',
  },
  {
    title: 'Signal sleeves',
    body: "Factors combine into one score per family, weighted by how much evidence each factor typically carries within that family.",
  },
  {
    title: 'Composite score',
    body: 'Family scores combine into a single composite. Momentum — and only momentum — is scaled down by a probabilistic macro-stress gate during volatile regimes; value, quality and news are never macro-suppressed.',
  },
  {
    title: 'Confidence',
    body: 'Confidence starts at 100 and is reduced by named, itemized deductions: family disagreement, data completeness, event proximity, data staleness, the model’s own recently measured skill, verdict stability, and macro uncertainty.',
  },
  {
    title: 'Risk',
    body: 'A separate 0–100 score aggregates nine percentile-based components — downside deviation, tail risk, drawdown, volatility regime, beta, idiosyncratic share, liquidity, macro and sector — each shown as weight × percentile = contribution.',
  },
  {
    title: 'Verdict',
    body: 'The composite score maps to Strong Buy, Buy, Hold, Sell or Strong Sell once it crosses a fixed threshold in either direction. An “ungated” verdict — what the sleeves said before any macro gate — is computed alongside it so a suppressed bullish read is visible, not hidden.',
  },
  {
    title: 'Explainability',
    body: 'The complete scorecard — every factor, contribution, confidence deduction and risk component — is handed to GPT-OSS-120B as structured data. The model narrates what the engine already computed; it never computes a number itself.',
  },
  {
    title: 'Validation',
    body: 'The same engine is replayed walk-forward over price history on an expanding window, so its live-generated verdicts can be graded against what actually happened next.',
  },
]

interface DataSource {
  name: string
  purpose: string
  vendors: string[]
  updateFrequency: string
  fallback: string
  missingData: string
}

const DATA_SOURCES: DataSource[] = [
  {
    name: 'Market data',
    purpose: 'Live quotes and OHLCV price history — the input to every price-derived factor and to the risk engine.',
    vendors: ['Polygon', 'Finnhub', 'Twelve Data', 'FMP', 'MarketStack', 'Yahoo Finance'],
    updateFrequency: 'Quotes cached 60 seconds; price history cached 5 minutes.',
    fallback: 'Six vendors chained in priority order — if one fails, rate-limits, or returns a suspect quote, the next is tried automatically. The product never surfaces which vendor answered, only the data.',
    missingData: 'A ticker needs at least 60 trading days of history before any factor computes; below that, scoring is skipped rather than run on too little history.',
  },
  {
    name: 'Fundamentals',
    purpose: 'Company profile, valuation ratios and analyst price targets — the input to the fundamental factor family.',
    vendors: ['Alpha Vantage', 'Finnhub', 'FMP'],
    updateFrequency: 'Cached 1 hour — fundamentals move slowly enough that faster refresh only adds vendor load.',
    fallback: 'Three vendors chained in priority order, sharing rate-limit accounting with the market-data vendors where the same vendor serves both.',
    missingData: 'Each fundamental factor computes independently and only when its specific inputs are present — a missing analyst target does not block earnings yield or the P/E gap from scoring.',
  },
  {
    name: 'News',
    purpose: 'Recent headlines — the input to the news sentiment factor and to the research report’s news narrative.',
    vendors: ['NewsAPI', 'GNews', 'Yahoo RSS', 'Tavily'],
    updateFrequency: 'Cached 5 minutes.',
    fallback: 'Four vendors chained in priority order; results are deduplicated by headline title so one story picked up by multiple vendors is only counted once.',
    missingData: 'Sentiment shrinks toward neutral as coverage thins, so a single headline moves the score far less than sustained coverage in one direction.',
  },
  {
    name: 'Macro',
    purpose: 'Yield curve, financial conditions, credit spreads and rates — the input to the macro-stress gate and the risk engine’s macro component.',
    vendors: ['FRED — Federal Reserve Economic Data'],
    updateFrequency: 'Headline snapshot cached 15 minutes; individual series cached 30 minutes.',
    fallback: 'Single source — the Federal Reserve’s own published data has no meaningful commercial alternative at this update frequency.',
    missingData: 'The macro-stress read uses whatever fast inputs are available (term spread, financial conditions, credit spread, volatility percentile) and only goes unmeasured if none are available — it does not require all of them.',
  },
  {
    name: 'Search',
    purpose: 'Supplementary web research context.',
    vendors: ['Tavily', 'Exa'],
    updateFrequency: 'Cached 10 minutes.',
    fallback: 'Two vendors chained in priority order.',
    missingData: 'Not used as a scoring input — research context only.',
  },
]

const FAQ: { q: string; a: string }[] = [
  {
    q: 'Why does confidence change from one day to the next, even with the same verdict?',
    a: 'Confidence is a live function of current data completeness, how much the active factor families agree with each other, proximity to an earnings or Fed event, data staleness, and the model’s own recently measured skill on this name — not a fixed number attached to a verdict. Any of those inputs moving changes confidence, independent of whether the verdict itself flips.',
  },
  {
    q: 'Why did the recommendation change since the last analysis?',
    a: 'Because the underlying factors moved: momentum decayed or turned, an earnings surprise entered or left its drift window, an analyst target changed, or sentiment shifted. The research report’s factor-attribution section shows exactly which families moved and by how much — the verdict is a direct, deterministic consequence of that movement, not a separate judgment.',
  },
  {
    q: 'Why doesn’t the AI decide the verdict?',
    a: 'A narrative language model is not a statistically calibrated estimator — it has no principled way to produce a trustworthy number. The deterministic engine computes every score, confidence figure, risk figure and verdict from named, testable rules. GPT-OSS-120B is only ever given the finished scorecard and asked to explain it in words; it cannot alter a single number.',
  },
  {
    q: 'How often does the model recompute?',
    a: 'Live analyses recompute on demand against current data. The validation backtest recomputes on a weekly cadence across history specifically to test whether the signal holds up over time, not to match the live product’s refresh rate.',
  },
  {
    q: 'Why do fundamentals sometimes disagree with momentum?',
    a: 'Cheap-and-falling and expensive-and-rising are both common, real market states — disagreement between families isn’t a bug. The conflict index on every research report directly measures how much the active families disagree, and higher disagreement is one of the itemized deductions that lowers confidence rather than being averaged away and hidden.',
  },
  {
    q: 'What happens when data providers disagree?',
    a: 'Each provider facade calls vendors in a fixed priority order and uses the first one that answers cleanly; price quotes are additionally cross-validated before use. The product never blends numbers from two different vendors within the same factor — one vendor’s answer is used, or the next vendor in the chain is tried.',
  },
]

const LIMITATIONS: string[] = [
  'A single-name research tool, not a portfolio construction or diversification system — it says nothing about how names interact together.',
  'Validation backtests model no transaction costs, slippage, taxes or borrow fees.',
  'Analyst targets and forward-earnings estimates carry the same industry-wide optimism bias and revision risk everywhere else they’re used — shrinkage on thin coverage reduces their influence but cannot remove that bias.',
  'News sentiment is only as reliable as the underlying headline feed and its automated tone labeling.',
  'Momentum-based factors can only react to a regime change once it shows up in price — they cannot anticipate one.',
  'A model that looks statistically sound on one ticker’s history is not a guarantee of future performance on that ticker, or any other.',
  'This is a research and decision-support tool, not personalized investment advice.',
]

const FAMILY_ORDER: FactorFamily[] = ['momentum', 'reversal', 'fundamental', 'quality', 'news']

function factorsIn(family: FactorFamily): FactorKey[] {
  return (Object.keys(FACTOR_GLOSSARY) as FactorKey[]).filter((key) => FACTOR_FAMILY[key] === family)
}

function PipelineFlow() {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'stretch',
        gap: 0,
      }}
      role="list"
      aria-label="Scoring pipeline stages, in order"
    >
      {PIPELINE.map((stage, index) => (
        <div key={stage.title} style={{ display: 'flex', alignItems: 'stretch' }}>
          <div
            role="listitem"
            className="panel"
            style={{
              width: 168,
              padding: '12px 14px',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <span className="num" style={{ fontSize: '0.625rem', color: 'var(--faint)' }}>
              {String(index + 1).padStart(2, '0')}
            </span>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text)' }}>{stage.title}</span>
            <p style={{ fontSize: '0.6875rem', lineHeight: 1.5, color: 'var(--muted)' }}>{stage.body}</p>
          </div>
          {index < PIPELINE.length - 1 && (
            <span
              aria-hidden="true"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 22,
                flexShrink: 0,
                color: 'var(--faint)',
                fontSize: '0.875rem',
              }}
            >
              →
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

function DataSourceCard({ source }: { source: DataSource }) {
  return (
    <div className="panel" style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <h4 className="h-panel" style={{ fontSize: '0.875rem' }}>{source.name}</h4>
        <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{source.updateFrequency}</span>
      </div>
      <p style={{ fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--text)' }}>{source.purpose}</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {source.vendors.map((vendor) => (
          <span
            key={vendor}
            className="num"
            style={{ fontSize: '0.6875rem', padding: '3px 8px', borderRadius: 'var(--r-sm)', background: 'var(--surface-2)', color: 'var(--muted)' }}
          >
            {vendor}
          </span>
        ))}
      </div>
      <p style={{ fontSize: '0.75rem', lineHeight: 1.55, color: 'var(--muted)' }}>
        <span style={{ color: 'var(--faint)' }}>Fallback: </span>{source.fallback}
      </p>
      <p style={{ fontSize: '0.75rem', lineHeight: 1.55, color: 'var(--muted)' }}>
        <span style={{ color: 'var(--faint)' }}>Missing data: </span>{source.missingData}
      </p>
    </div>
  )
}

export default function MethodologyView() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Methodology</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          What OmniSignal actually computes, where every number comes from, and where it stops —
          in the same amount of detail a research desk would expect before trusting a signal.
        </p>
      </div>

      <Section id="meth-architecture" title="Overall architecture" defaultOpen>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6, marginBottom: 16, maxWidth: '80ch' }}>
          Every analysis moves through the same ten stages, in the same order, whether the result is a
          Strong Buy or a Strong Sell. Nothing in this pipeline is ticker-specific — it’s the same
          code path for every name.
        </p>
        <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
          <PipelineFlow />
        </div>
      </Section>

      <Section id="meth-data-sources" title="Data sources">
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6, marginBottom: 16, maxWidth: '80ch' }}>
          Five kinds of data feed the engine, each behind its own vendor fallback chain. The product
          never shows which vendor answered a given request — only that an answer was cross-checked
          and cached to keep the system fast and within vendor rate limits.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {DATA_SOURCES.map((source) => (
            <DataSourceCard key={source.name} source={source} />
          ))}
        </div>
      </Section>

      <Section id="meth-factor-library" title="Factor library">
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6, marginBottom: 20, maxWidth: '80ch' }}>
          15 factors, grouped into five families. Every factor below is what the engine actually
          computes — nothing here is aspirational or planned. Each one expands into its formula,
          interpretation, and the academic literature it comes from.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          {FAMILY_ORDER.map((family) => (
            <div key={family}>
              <h4 className="label" style={{ fontSize: '0.6875rem', marginBottom: 10, color: 'var(--faint)' }}>
                {FAMILY_TITLES[family]}
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 4vw, 44px)' }}>
                {factorsIn(family).map((key) => (
                  <div key={key} style={{ maxWidth: 320 }}>
                    <MetricExplainer entry={FACTOR_GLOSSARY[key]} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section id="meth-composite-score" title="Composite score, confidence & risk">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, maxWidth: '80ch' }}>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Normalization</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              Return-based factors are converted into a t-statistic — how many multiples of the
              stock’s own noise a move represents — which preserves trend direction and adapts to
              each name’s own volatility. Level-based factors use a robust median/MAD z-score, resistant
              to the single-outlier distortion a plain mean and standard deviation would suffer.
              Everything is winsorized to a fixed bound so no one factor can dominate purely by having
              an extreme reading.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Sleeve aggregation & regime adaptation</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              Factors combine into one score per family; families combine into the composite score.
              Weights are not static: in a detected high-volatility regime, momentum’s weight is cut
              and the short-term reversal sleeve — near-zero in calm markets — is funded by that cut,
              reflecting that sharp short-term moves are more likely to partially revert once volatility
              is already elevated. Around an earnings release, the news sleeve carries more weight and
              the analyst-target factor is muted, since price targets are least reliable in the days
              immediately around a surprise.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Macro-stress gate</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              A probabilistic stress read, built from the yield curve, financial-conditions index,
              credit spreads and volatility percentile, scales down the momentum sleeve specifically
              during high-stress regimes. Value, quality and news are deliberately never macro-suppressed
              — momentum is the sleeve most prone to sharp regime-change reversals, so it’s the only one
              gated.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Confidence</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              Confidence starts at 100 and is reduced by named, itemized deductions rather than one
              opaque number: disagreement between active families, data completeness, proximity to an
              earnings or FOMC event, data staleness, the model’s own recently measured skill on this
              name, and how often the verdict has recently flipped. Every deduction that actually applies
              is shown on the research report — nothing is folded silently into the headline figure.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Risk</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              A separate 0–100 score, deliberately independent of the verdict — a Strong Buy can carry
              high risk, and a Hold can carry low risk. Nine components, each expressed as a percentile
              against the stock’s own history (downside deviation, tail risk, drawdown, volatility
              regime, beta level and stability, idiosyncratic share, liquidity, macro exposure, and
              sector), are combined as weight × percentile = contribution, and every component’s
              contribution is visible, not just the total.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Missing factors</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              A factor whose required input isn’t available is omitted, never estimated from
              incomplete data. The composite score is a weighted average of whatever factors did
              compute; a data-completeness figure travels with every scorecard so thin coverage is
              visible rather than silently backfilled.
            </p>
          </div>
          <div>
            <h4 className="h-panel" style={{ fontSize: '0.8125rem', marginBottom: 6 }}>Verdict</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6 }}>
              The composite score maps to Strong Buy, Buy, Hold, Sell or Strong Sell once it crosses a
              fixed threshold in either direction. An “ungated” verdict — what the sleeves said before
              any macro-stress gate was applied — is computed alongside the live one, so a bullish read
              that’s being actively suppressed by macro stress is visible rather than hidden.
            </p>
          </div>
        </div>
      </Section>

      <Section id="meth-validation" title="Validation methodology">
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6, maxWidth: '80ch' }}>
          OmniSignal validates the engine the way a quant desk grades any signal before trusting it:
          by replaying it walk-forward over real price history and checking whether higher scores
          actually preceded higher subsequent returns. Each historical point is scored using only
          information that would have been available at that point in time — no look-ahead. The
          backtest recomputes on an expanding window at a weekly cadence and is measured against a
          naive baseline (the sign of the trailing 12-1 return, with no engine at all), so the model
          has to beat a strategy that requires no model to run. The long/flat directional test does
          not account for transaction costs, slippage, taxes or borrow fees, and validates one ticker
          at a time — it is not a portfolio-level backtest. The Validation tab runs this process live
          for any ticker and reports the full set of resulting metrics — IC, hit rate, Sharpe, Sortino,
          Calmar, drawdown, calibration, and distribution-drift — each with its own definition and
          interpretation attached.
        </p>
      </Section>

      <Section id="meth-faq" title="Frequently asked questions">
        <div className="hairline-top">
          {FAQ.map((item) => (
            <details key={item.q} className="faq-item">
              <summary>{item.q}</summary>
              <div className="faq-body">{item.a}</div>
            </details>
          ))}
        </div>
      </Section>

      <Section id="meth-limitations" title="Limitations" defaultOpen>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {LIMITATIONS.map((item) => (
            <li key={item} style={{ display: 'flex', gap: 9, fontSize: '0.8125rem', lineHeight: 1.55, color: 'var(--muted)' }}>
              <span aria-hidden="true" style={{ flexShrink: 0, marginTop: 7, width: 6, height: 6, borderRadius: 1, background: 'var(--faint)' }} />
              {item}
            </li>
          ))}
        </ul>
        <p style={{ fontSize: '0.75rem', color: 'var(--faint)', lineHeight: 1.6, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
          Trust matters more than marketing here — if something above changes (a factor is retired, a
          vendor is swapped, a threshold is retuned), this page is meant to be updated alongside the
          code, not treated as a one-time description.
        </p>
      </Section>
    </div>
  )
}
