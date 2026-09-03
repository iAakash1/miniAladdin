'use client'

/**
 * A company, opened fast.
 *
 * The previous security workspace led with research infrastructure: model
 * state, provenance, relationship counts, point-in-time classification. All of
 * that is real and none of it is what someone wants in the first second after
 * typing AAPL.
 *
 * This leads with identity, price and the chart, because that is what a
 * terminal is for. Research sits below it, and evidence sits inside research.
 *
 * **Nothing waits on the slow path.** Quotes answer in about 250ms and bars in
 * about 330ms; the full research payload takes around twenty-four seconds. They
 * are fetched independently, so the page is useful long before the last of them
 * lands, and a section that has not arrived says so rather than blocking the
 * ones that have.
 *
 * **No section is rendered for data that did not come back.** If the provider
 * has no fundamentals for a symbol, there is no fundamentals block — not an
 * empty one, and certainly not a placeholder shaped like data.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Strip } from '@/components/system'
import { TimeSeries } from '@/components/system/charts'
import { ObjectHeader } from '@/components/system/composition'
import { fetchBars, fetchQuotes, type Bar, type Quote } from '@/lib/security'
import { isWatched, toggleWatch } from '@/lib/symbols'

const RANGES = [
  { key: '1mo', label: '1M' },
  { key: '3mo', label: '3M' },
  { key: '6mo', label: '6M' },
  { key: '1y', label: '1Y' },
  { key: '5y', label: '5Y' },
]

/** Tagged with the request it answers, so a slow reply cannot overwrite a new one. */
interface Settled<T> { for: string; value?: T; error?: string }

export default function SecurityView({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState<Settled<Quote | null> | null>(null)
  const [bars, setBars] = useState<Settled<Bar[]> | null>(null)
  const [range, setRange] = useState('1y')
  const [watched, setWatched] = useState(false)

  useEffect(() => { setWatched(isWatched(symbol)) }, [symbol])

  useEffect(() => {
    const c = new AbortController()
    fetchQuotes([symbol], c.signal)
      .then((q) => setQuote({ for: symbol, value: q[symbol] ?? null }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setQuote({ for: symbol, error: e.message }) })
    return () => c.abort()
  }, [symbol])

  useEffect(() => {
    const tag = `${symbol}:${range}`
    const c = new AbortController()
    fetchBars(symbol, range, c.signal)
      .then((b) => setBars({ for: tag, value: b }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setBars({ for: tag, error: e.message }) })
    return () => c.abort()
  }, [symbol, range])

  const q = quote?.for === symbol ? quote : null
  const b = bars?.for === `${symbol}:${range}` ? bars : null
  const price = q?.value ?? null
  const series = b?.value ?? []

  const last = series.length ? series[series.length - 1] : null
  const first = series.length ? series[0] : null
  /* A fraction, scaled once, here.
     (324.96 − 229.72) / 229.72 is 0.4146 — which is 41.5%, not 0.4%. The
     `percent` kind deliberately never multiplies, because a formatter that
     scales cannot tell 0.61 from 61. So the conversion happens at the one
     place that knows the value is a ratio. */
  const windowChange = last?.close != null && first?.close != null && first.close !== 0
    ? ((last.close - first.close) / first.close) * 100
    : null

  return (
    <>
      <ObjectHeader
        glyph="T"
        name={symbol}
        kind="security"
        state={price ? (price.stale ? 'stale' : 'live') : q?.error ? 'unavailable' : 'waking'}
        detail={price?.source ? `quote via ${price.source}` : undefined}
        facts={[
          { label: 'Last', value: price?.price ?? null, kind: 'currency' },
          { label: '1 day', value: price?.change_1d ?? null, kind: 'percent', digits: 2, signed: true, tone: true },
          { label: '1 week', value: price?.change_1w ?? null, kind: 'percent', digits: 2, signed: true, tone: true },
          { label: 'Bars', value: series.length || null, kind: 'count' },
        ]}
        actions={
          <button
            type="button"
            className="sys-btn"
            aria-pressed={watched}
            onClick={() => { toggleWatch(symbol); setWatched(isWatched(symbol)) }}
          >
            {watched ? 'watching' : 'watch'}
          </button>
        }
      />

      <Panel
        title="Price"
        subtitle={price?.source ? `${price.source}${price.stale ? ' · stale' : ''}` : undefined}
        state={b?.error ? 'unavailable' : series.length ? 'live' : 'waking'}
        actions={
          <div className="sys-run">
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                className={`sys-btn sys-btn--micro${range === r.key ? ' is-active' : ''}`}
                aria-pressed={range === r.key}
                onClick={() => setRange(r.key)}
              >
                {r.label}
              </button>
            ))}
          </div>
        }
      >
        {b?.error ? (
          <StateBlock
            state="unavailable"
            title="No price history was returned"
            detail={`${b.error}. Nothing is drawn in its place — an empty chart is indistinguishable from a flat one.`}
          />
        ) : series.length ? (
          <>
            <TimeSeries
              series={[{
                name: symbol,
                points: series.map((p) => ({ x: p.date, y: p.close })),
                kind: 'currency',
                object: { kind: 'security', id: symbol, label: symbol },
                method: 'daily closes as the price provider reports them',
              }]}
              unit="close"
              kind="currency"
              xLabel="session"
              frequency="daily"
              height={260}
            />
            <Strip metrics={[
              { label: 'Window change', value: windowChange, kind: 'percent', digits: 2, signed: true, tone: true,
                title: 'First to last close in the selected range' },
              { label: 'First close', value: first?.close ?? null, kind: 'currency' },
              { label: 'Last close', value: last?.close ?? null, kind: 'currency' },
              { label: 'Last volume', value: last?.volume ?? null, kind: 'count' },
              { label: 'Sessions', value: series.length, kind: 'count' },
            ]} />
          </>
        ) : (
          <StateBlock state="waking" title={`Reading ${symbol} price history`} />
        )}
      </Panel>

      {/* Research sits below the market data and behind a link rather than
          expanded in place. It is real and it is slow — the full payload takes
          around twenty-four seconds — and a page that waits for it is a page
          nobody opens twice. */}
      <Panel title="Research" subtitle="what the research layer holds on this name" state="recorded">
        <Prose>
          Factor exposure, signals, filings and the model record are available
          for this security. They are not loaded with the page: the research
          payload is an order of magnitude slower than the market data above it,
          and the price should not wait for it.
        </Prose>
        <div className="sys-run" style={{ marginTop: 'var(--d-3)' }}>
          <a className="sys-btn" href={`/company/${encodeURIComponent(symbol)}`}>
            open the full research report
          </a>
          <a className="sys-btn" href="/terminal/factorlab">factors</a>
          <a className="sys-btn" href="/terminal/evidence">evidence</a>
        </div>
        <Prose size="fine">
          No production model is deployed, so nothing here scores this security.
          The research archive records why.
        </Prose>
      </Panel>
    </>
  )
}
