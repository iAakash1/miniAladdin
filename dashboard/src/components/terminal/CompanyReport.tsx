'use client'

import dynamicImport from 'next/dynamic'
import { useCallback, useState } from 'react'

import AiPanel from '@/components/terminal/AiPanel'
import CompanyBand from '@/components/terminal/CompanyBand'
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

/** The in-page research map: id anchors → section labels. Sections whose
 *  data is absent for a given company simply don't render, so the nav
 *  filters itself against what the report actually contains. */
const SECTIONS: Array<{ id: string; label: string; present: (a: Analysis) => boolean }> = [
  { id: 'overview', label: 'Overview', present: () => true },
  { id: 'report', label: 'Report', present: (a) => a.ai !== null },
  { id: 'scorecard', label: 'Scorecard', present: (a) => a.quant !== null },
  { id: 'price', label: 'Price', present: () => true },
  { id: 'technical', label: 'Technical', present: (a) => a.technicalIntelligence !== null },
  { id: 'street', label: 'Street', present: (a) => a.streetIntelligence !== null },
  { id: 'fundamentals', label: 'Fundamentals', present: () => true },
  { id: 'news', label: 'News', present: (a) => a.headlines.length > 0 },
  { id: 'ecosystem', label: 'Ecosystem', present: () => true },
  { id: 'history', label: 'History', present: () => true },
  { id: 'related', label: 'Related', present: () => true },
]

function SectionNav({ analysis }: { analysis: Analysis }) {
  const present = SECTIONS.filter((s) => s.present(analysis))
  return (
    <nav aria-label="Report sections" className="section-nav">
      {present.map((s) => (
        <a key={s.id} href={`#${s.id}`} className="section-nav__link num">
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
        <section aria-label="Price history" className="panel" style={{ padding: '20px 22px' }}>
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
        />
      </div>

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
