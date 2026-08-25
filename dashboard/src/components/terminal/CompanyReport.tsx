'use client'

import dynamicImport from 'next/dynamic'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { useHistory } from '@/lib/history'
import AiPanel from '@/components/terminal/AiPanel'
import CompanyBand from '@/components/terminal/CompanyBand'
import CompanySnapshot from '@/components/terminal/CompanySnapshot'
import DecisionProvenance from '@/components/terminal/DecisionProvenance'
import MacroContextPanel from '@/components/terminal/MacroContextPanel'
import OwnershipPanel from '@/components/terminal/OwnershipPanel'
import RatioPanel from '@/components/terminal/RatioPanel'
import SecFilings from '@/components/terminal/SecFilings'
import StatementUnionPanel from '@/components/terminal/StatementUnionPanel'
import CompanyCrossLinks from '@/components/terminal/CompanyCrossLinks'
import CompanyEcosystem from '@/components/terminal/CompanyEcosystem'
import Fundamentals from '@/components/terminal/Fundamentals'
import Headlines from '@/components/terminal/Headlines'
import KeyStats from '@/components/terminal/KeyStats'
import MacroPanel from '@/components/terminal/MacroPanel'
import QuantPanel from '@/components/terminal/QuantPanel'
import SentimentPanel from '@/components/terminal/SentimentPanel'
import StreetIntelligence from '@/components/terminal/StreetIntelligence'
import TechnicalIntelligence from '@/components/terminal/TechnicalIntelligence'
import VerdictTimeline from '@/components/terminal/VerdictTimeline'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { fetchChart, normalizeChart } from '@/lib/api'
import type { Analysis, PricePoint } from '@/lib/types'

const PriceChart = dynamicImport(() => import('@/components/terminal/PriceChart'), {
  ssr: false,
  loading: () => <Skeleton height={260} />,
})

const PERIODS: Array<{ value: string; label: string }> = [
  { value: '1mo', label: '1M' },
  { value: '3mo', label: '3M' },
  { value: '6mo', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: '5y', label: '5Y' },
]

/** What the nav can know beyond the analysis payload. The verdict timeline
 *  lives in client-side history rather than on `Analysis`, so a predicate
 *  that only sees the payload cannot tell whether that section will render. */
interface NavContext {
  /** Stored snapshots for this ticker. `VerdictTimeline` needs two to draw. */
  historyPoints: number
}

/** The in-page research map: id anchors → section labels. Sections whose
 *  data is absent for a given company simply don't render, so the nav
 *  filters itself against what the report actually contains — every
 *  `present` here must agree with whether its component renders anything. */
const SECTIONS: Array<{
  id: string; label: string; present: (a: Analysis, ctx: NavContext) => boolean
}> = [
  { id: 'overview', label: 'Overview', present: () => true },
  { id: 'report', label: 'Report', present: (a) => a.ai !== null },
  { id: 'scorecard', label: 'Scorecard', present: (a) => a.quant !== null },
  { id: 'price', label: 'Price', present: () => true },
  { id: 'technical', label: 'Technical', present: (a) => a.technicalIntelligence !== null },
  { id: 'street', label: 'Street', present: (a) => a.streetIntelligence !== null },
  { id: 'company', label: 'Company', present: (a) => a.profile !== null },
  { id: 'statements', label: 'Statements', present: (a) => (a.statements?.providers.length ?? 0) > 0 },
  { id: 'ratios', label: 'Ratios', present: (a) => a.ratios !== null },
  { id: 'ownership', label: 'Ownership', present: (a) => a.ownership !== null || a.analyst !== null },
  { id: 'macro', label: 'Macro', present: (a) => a.macroContext !== null },
  { id: 'filings', label: 'Filings', present: (a) => (a.filings?.filings.length ?? 0) > 0 },
  { id: 'fundamentals', label: 'Fundamentals', present: () => true },
  { id: 'news', label: 'News', present: (a) => a.headlines.length > 0 },
  { id: 'provenance', label: 'Provenance', present: (a) => a.provenance !== null },
  { id: 'ecosystem', label: 'Ecosystem', present: () => true },
  // Was hardcoded `true`, while `VerdictTimeline` returns null below two
  // snapshots — the common case for a ticker analysed once. The nav
  // therefore always offered a "History" link that scrolled to an empty
  // element, which is a dead end rather than an empty section.
  { id: 'history', label: 'History', present: (_a, ctx) => ctx.historyPoints >= 2 },
  { id: 'related', label: 'Related', present: () => true },
]

/** Which section the reader is currently in.
 *
 *  The rule: the last section whose top has crossed the reading line. That
 *  is deliberately not "the most visible section" — a 900px section and a
 *  150px one are both fully read by the time the next heading arrives, and
 *  ranking by visible area makes the highlight jump back to whichever block
 *  happens to be tallest.
 *
 *  Exported because it is the actual decision this nav makes; the scroll
 *  plumbing around it is not worth a test, but getting this wrong shows up
 *  as a highlight that lags or skips.
 */
export function currentSectionId(
  tops: Array<{ id: string; top: number }>, line: number,
): string | null {
  if (tops.length === 0) return null
  let best = tops[0].id
  for (const entry of tops) {
    if (entry.top <= line) best = entry.id
  }
  return best
}

function SectionNav({ analysis }: { analysis: Analysis }) {
  const timeline = useHistory(analysis.ticker)
  // Memoised: a fresh array each render would tear down and re-create the
  // IntersectionObserver on every state update, including the ones this
  // observer itself causes.
  const present = useMemo(
    () => SECTIONS.filter((s) => s.present(analysis, { historyPoints: timeline.length })),
    [analysis, timeline.length],
  )
  const [current, setCurrent] = useState<string | null>(null)

  /* Which section is actually being read.
   *
   * The report is ~4,700px of continuous content and the nav had no notion
   * of position, so it told you where you could go but never where you were
   * — on a page this long that is the more useful half.
   *
   * A scroll listener rather than IntersectionObserver, deliberately: the
   * observer is the more elegant API, but the section that "wins" here is
   * the one whose top has most recently passed the reading line, which is a
   * different question from "what fraction is visible" and is awkward to
   * express in thresholds. Reads are batched into a rAF so the handler does
   * at most one layout pass per frame regardless of scroll rate, and there
   * are eleven elements to measure, not hundreds.
   */
  useEffect(() => {
    if (present.length === 0) return undefined
    let last = 0

    const measure = () => {
      last = Date.now()
      // The reading line sits a third down the viewport — where the eye
      // actually rests, not at the very top edge.
      const line = window.innerHeight * 0.33
      const tops = present
        .map((section) => {
          const el = document.getElementById(section.id)
          return el ? { id: section.id, top: el.getBoundingClientRect().top } : null
        })
        .filter((entry): entry is { id: string; top: number } => entry !== null)
      setCurrent(currentSectionId(tops, line))
    }

    // Time-throttled rather than rAF-throttled. rAF is the usual choice, but
    // it only runs while the document is painting, so the highlight silently
    // stops updating in any context that is not actively rendering — which
    // is exactly where this was first caught. A 100 ms floor bounds the work
    // to ~10 layout reads a second over eleven elements.
    const onScroll = () => {
      if (Date.now() - last >= 100) measure()
    }

    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [present])

  return (
    <nav aria-label="Report sections" className="section-nav">
      {present.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className={`section-nav__link num${current === s.id ? ' is-current' : ''}`}
          aria-current={current === s.id ? 'true' : undefined}
        >
          {s.label}
        </a>
      ))}
    </nav>
  )
}

interface CompanyReportProps {
  analysis: Analysis
  initialChart: PricePoint[]
  isPro: boolean
  requestUpgrade: (reason?: 'limit' | 'feature') => void
}

/**
 * The complete single-page research report for one company — the center of
 * the product. Renders every engine's output in the research narrative
 * order with a sticky section map; owns only chart-timeframe state (the
 * verdict never changes with the chart window).
 */
export default function CompanyReport({ analysis, initialChart, isPro, requestUpgrade }: CompanyReportProps) {
  const [chart, setChart] = useState<PricePoint[]>(initialChart)
  const [chartLoading, setChartLoading] = useState(false)
  const [period, setPeriod] = useState('3mo')

  const changePeriod = useCallback(
    async (next: string) => {
      if (!isPro && next !== '3mo') {
        requestUpgrade('feature')
        return
      }
      setPeriod(next)
      setChartLoading(true)
      try {
        setChart(normalizeChart(await fetchChart(analysis.ticker, next)))
      } finally {
        setChartLoading(false)
      }
    },
    [analysis.ticker, isPro, requestUpgrade],
  )

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* The report is the product's most important page and it had no h1 —
          its outline started at the ticker band's h2. This names the page
          without adding chrome above a hero that already states the ticker,
          the company and the verdict far better than a title bar could.
          Hidden rather than visible, and placed here rather than inside
          CompanyBand, because the band is reused in the Vault detail view
          under that page's own h1 — a second h1 there would be wrong. */}
      <h1 className="visually-hidden">
        {analysis.companyName ? `${analysis.companyName} (${analysis.ticker})` : analysis.ticker} research report
      </h1>
      <SectionNav analysis={analysis} />

      <div id="overview" className="report-section">
        <CompanyBand analysis={analysis} />
      </div>

      <div id="report" className="report-section">
        <AiPanel analysis={analysis} />
      </div>

      <div id="scorecard" className="report-section">
        <QuantPanel analysis={analysis} />
      </div>

      <div id="price" className="report-section terminal-grid-main">
        <section aria-label="Price history" className="panel panel--pad">
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              flexWrap: 'wrap',
              marginBottom: 12,
            }}
          >
            <h3 className="h-panel">Price</h3>
            <div className="seg" role="group" aria-label="Chart timeframe">
              {PERIODS.map((p) => (
                <button
                  key={p.value}
                  type="button"
                  className="seg__btn num"
                  aria-pressed={period === p.value}
                  onClick={() => changePeriod(p.value)}
                  style={{ fontSize: '0.75rem' }}
                >
                  {p.label}
                  {!isPro && p.value !== '3mo' && (
                    <span aria-label="Pro feature" style={{ fontSize: '0.625rem', color: 'var(--warn)' }}>
                      PRO
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {chartLoading ? (
            <Skeleton height={260} />
          ) : chart.length > 0 ? (
            <PriceChart
              data={chart}
              ticker={analysis.ticker}
              periodLabel={PERIODS.find((p) => p.value === period)?.label ?? period}
            />
          ) : (
            <EmptyState title="No price history" description="The chart service returned no data for this window." />
          )}
        </section>

        <KeyStats analysis={analysis} />
      </div>

      <div id="technical" className="report-section">
        <TechnicalIntelligence block={analysis.technicalIntelligence} />
      </div>

      <div id="street" className="report-section">
        <StreetIntelligence block={analysis.streetIntelligence} />
      </div>

      {analysis.profile && (
        <div id="company" className="report-section">
          <CompanySnapshot profile={analysis.profile} />
        </div>
      )}

      {analysis.statements && analysis.statements.providers.length > 0 && (
        <div id="statements" className="report-section">
          <StatementUnionPanel statements={analysis.statements} />
        </div>
      )}

      {analysis.ratios && (
        <div id="ratios" className="report-section">
          <RatioPanel ratios={analysis.ratios} />
        </div>
      )}

      {analysis.macroContext && (
        <div id="macro" className="report-section">
          <MacroContextPanel macro={analysis.macroContext} />
        </div>
      )}

      {(analysis.ownership || analysis.analyst) && (
        <div id="ownership" className="report-section">
          <OwnershipPanel ownership={analysis.ownership} analyst={analysis.analyst} />
        </div>
      )}

      {analysis.filings && analysis.filings.filings.length > 0 && (
        <div id="filings" className="report-section">
          <SecFilings block={analysis.filings} />
        </div>
      )}

      <div id="fundamentals" className="report-section terminal-grid-three">
        <Fundamentals analysis={analysis} />
        <MacroPanel macro={analysis.macro} />
        <SentimentPanel analysis={analysis} />
      </div>

      <div id="news" className="report-section">
        <Headlines
          headlines={analysis.headlines}
          isPro={isPro}
          onUpgrade={() => requestUpgrade('feature')}
          stream={analysis.newsStream}
        />
      </div>

      {/* Placed after the evidence it describes and before the history that
          follows from it: a reader who has just read the news and the factor
          decomposition is exactly the reader asking "where did this come
          from". */}
      {analysis.provenance && (
        <div id="provenance" className="report-section">
          <DecisionProvenance provenance={analysis.provenance} />
        </div>
      )}

      <div id="ecosystem" className="report-section">
        <CompanyEcosystem ticker={analysis.ticker} />
      </div>

      <div id="history" className="report-section">
        <VerdictTimeline ticker={analysis.ticker} />
      </div>

      <div id="related" className="report-section">
        <CompanyCrossLinks analysis={analysis} />
      </div>

      <p style={{ fontSize: '0.75rem', color: 'var(--faint)', textAlign: 'center', padding: '8px 0' }}>
        Research and education only — not investment advice.
      </p>
    </div>
  )
}
