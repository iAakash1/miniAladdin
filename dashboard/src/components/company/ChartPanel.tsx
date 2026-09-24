'use client'

import { useState } from 'react'

import PriceChart from './PriceChart'
import { RANGES, usePriceSeries, type Range } from './useCompany'
import { windowShortfall } from '@/lib/security'
import type { ChartSeries } from '@/lib/types'

/**
 * Why there is no line, in the reader's terms. Three different facts: no
 * provider answered; every provider answered and none holds sessions for the
 * window; or the chart service itself did not answer. None of them is shown
 * as a flat line, and none stops the rest of the page.
 */
export function SeriesUnavailable({ series, onRetry }: { series: ChartSeries | null; onRetry?: () => void }) {
  const status = series?.status
  const [title, detail] = status === 'empty'
    ? ['No sessions in this window', 'Every price provider answered and none holds daily closes for this window.']
    : status === 'unavailable'
      ? ['Price history unavailable', 'No price provider returned a series. Other company research remains available.']
      : ['Price history unavailable', 'The historical series could not be retrieved. Other company research remains available.']
  return (
    <div className="cw-series-na" role="status">
      <svg className="cw-series-na__art" viewBox="0 0 120 40" aria-hidden>
        <path d="M0 30 H120 M0 20 H120 M0 10 H120" />
        <path className="cw-series-na__gap" d="M4 26 L22 22 L34 24 M86 14 L100 17 L116 9" />
      </svg>
      <div className="cw-series-na__text">
        <span className="cw-series-na__title">{title}</span>
        <span className="cw-series-na__detail">{detail}</span>
      </div>
      {onRetry && status !== 'empty' ? (
        <button type="button" className="sys-btn sys-btn--ghost" onClick={onRetry}>Retry</button>
      ) : null}
    </div>
  )
}

/**
 * Daily closes for a selectable window. Windows beyond three months are a
 * Pro feature, as the pricing page states.
 */
export default function ChartPanel({
  symbol, isPro, requestUpgrade, height = 300, title = 'Price',
}: {
  symbol: string
  isPro: boolean
  requestUpgrade: (reason?: 'limit' | 'feature') => void
  height?: number
  title?: string
}) {
  const [range, setRange] = useState<Range>('3mo')
  const { series, loading, retry } = usePriceSeries(symbol, range)
  const label = RANGES.find((r) => r.value === range)?.label ?? range
  const points = series?.points ?? []
  const shortfall = points.length
    ? windowShortfall(range, points[0]?.date, points[points.length - 1]?.date)
    : null
  const closes = points.map((p) => p.close)
  const hi = closes.length ? Math.max(...closes) : null
  const lo = closes.length ? Math.min(...closes) : null

  return (
    <section className="sys-panel cw-chart" aria-label={`${symbol} price history`}>
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">{title}</h2>
          <span className="sys-panel-sub">
            daily close{series?.source ? ` · ${series.source}` : ''}{series?.status === 'stale' ? ' · stale' : ''}
          </span>
        </div>
        <div className="sys-panel-head__end">
          <div className="sys-seg" role="group" aria-label="Chart window">
            {RANGES.map((r) => {
              const locked = !isPro && r.value !== '3mo'
              return (
                <button
                  key={r.value}
                  type="button"
                  className="sys-btn"
                  aria-pressed={range === r.value}
                  title={locked ? `${r.label} window — Pro` : `${r.label} window`}
                  onClick={() => (locked ? requestUpgrade('feature') : setRange(r.value))}
                >
                  {r.label}
                  {locked ? <span className="cw-pro" aria-label="Pro">·</span> : null}
                </button>
              )
            })}
          </div>
        </div>
      </header>
      <div className="cw-chart__body">
        {loading ? (
          <div className="sys-skeleton" style={{ height, borderRadius: 0 }} aria-label="Loading price history" />
        ) : points.length ? (
          <PriceChart points={points} height={height} label={`${symbol} daily close, ${label}`} />
        ) : (
          <SeriesUnavailable series={series} onRetry={retry} />
        )}
      </div>
      {points.length ? (
        <footer className="sys-panel-foot">
          <span>window <b>{label}</b> · {points.length} sessions</span>
          {hi !== null && lo !== null ? <span>range <b>{lo.toFixed(2)} – {hi.toFixed(2)}</b></span> : null}
          <span>first <b>{points[0].date.slice(0, 10)}</b></span>
          {shortfall ? <span className="sys-warn">{shortfall}</span> : null}
        </footer>
      ) : null}
    </section>
  )
}
