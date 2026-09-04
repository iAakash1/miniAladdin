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

import { Panel, StateBlock, Status, Strip, Prose, Value, type ResearchState } from '@/components/system'
import { TimeSeries } from '@/components/system/charts'
import { fetchBars, fetchIdentity, windowShortfall, type Bar, type SecurityIdentity } from '@/lib/security'
import { format } from '@/lib/quantity'
import { titleCase, venueLabel } from '@/lib/text'
import { fetchResearch } from '@/lib/research-cache'
import { useQuotes } from '@/lib/use-quotes'
import { isWatched, recentSnapshot, toggleWatch } from '@/lib/symbols'

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
  // The same hub the watchlist reads. Opening a security already on the
  // watchlist costs no extra request, and the two cannot disagree on its price.
  const { quotes, error: quoteError, at: quoteAt } = useQuotes([symbol])
  const [bars, setBars] = useState<Settled<Bar[]> | null>(null)
  const [range, setRange] = useState('1y')
  const [watched, setWatched] = useState(false)

  const [identity, setIdentity] = useState<Settled<SecurityIdentity | null> | null>(null)

  useEffect(() => { setWatched(isWatched(symbol)) }, [symbol])

  /* The listing venue and the vendor's own casing of the name arrive with the
     research payload — slow, but this is the same shared request the profile
     panel below already issues, so reading it here costs no second fetch. The
     field is complete without it and gains the venue when it lands. */
  const [profile, setProfile] = useState<Settled<{ name?: string; exchange?: string }> | null>(null)
  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((d) => { if (alive) setProfile({ for: symbol, value: (d as { profile?: { name?: string; exchange?: string } }).profile ?? {} }) })
      .catch(() => { /* identity already stands on the fast path */ })
    return () => { alive = false }
  }, [symbol])

  /* The company's name, from the symbol database rather than the research
     payload. Half a second against twenty-five, and the name is the first
     thing a reader looks for. A failure here is silent: the ticker is already
     on screen and is a truthful, if terse, way to name the company. */
  useEffect(() => {
    let alive = true
    fetchIdentity(symbol)
      .then((v) => { if (alive) setIdentity({ for: symbol, value: v }) })
      .catch((e: Error) => { if (alive) setIdentity({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  // The most recent other symbol this browser opened, as the default
  // comparison partner. Null on a first visit, where the action is hidden
  // rather than offered against nothing.
  const against = recentSnapshot().find((s) => s !== symbol) ?? null

  useEffect(() => {
    const tag = `${symbol}:${range}`
    const c = new AbortController()
    fetchBars(symbol, range, c.signal)
      .then((b) => setBars({ for: tag, value: b }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setBars({ for: tag, error: e.message }) })
    return () => c.abort()
  }, [symbol, range])

  const b = bars?.for === `${symbol}:${range}` ? bars : null
  const price = quotes[symbol] ?? null
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

  /* The range control names a window. When the provider cannot reach that far
     back, the control is the only thing on screen still claiming it can. */
  const shortfall = windowShortfall(range, first?.date, last?.date)

  const ident = identity?.for === symbol ? identity : null
  /* Title-cased: the symbol database returns "APPLE INC", and a page whose
     largest text is shouting reads as a banner rather than a name. */
  const prof = profile?.for === symbol ? profile.value : undefined
  /* The vendor's own casing wins when it arrives: "Apple Inc." beats anything
     recovered from "APPLE INC" by rule. */
  const name = prof?.name ?? (ident?.value?.name ? titleCase(ident.value.name) : null)
  const venue = venueLabel(prof?.exchange)
  /* Which provider resolved the ticker. Provenance, not a listing venue —
     it goes under the rule with the other sources, never beside the ticker. */
  const identitySource = ident?.value?.via ?? null
  const quoteState: ResearchState = price
    ? (quoteError || price.stale ? 'stale' : 'live')
    : quoteError ? 'unavailable' : quoteAt ? 'unavailable' : 'waking'

  return (
    <>
      {/* Identity, price and provenance as one field rather than a header
          box with a fact strip. See .inst in system.css for why. */}
      <section className="inst" aria-label={`${symbol} summary`}>
        <div>
          <h1
            className={`inst__name${name ? '' : ' inst__name--pending'}`}
            title={name ?? undefined}
          >
            {name ?? symbol}
          </h1>
          <div className="inst__listing">
            <span className="inst__ticker">{symbol}</span>
            {venue ? (
              <>
                <span className="inst__sep">/</span>
                <span title={prof?.exchange}>{venue}</span>
              </>
            ) : null}
            <span className="inst__sep">/</span>
            <Status state={quoteState} />
          </div>
        </div>

        <div className="inst__quote">
          <div className={`inst__price${price?.price == null ? ' inst__price--absent' : ''}`}>
            {price?.price == null ? '—' : format(price.price, 'currency').text}
          </div>
          <div className="inst__moves">
            <div className="inst__move">
              <span className="k">1 day</span>
              <span className="v">
                <Value value={price?.change_1d ?? null} kind="percent" digits={2} signed tone />
              </span>
            </div>
            <div className="inst__move">
              <span className="k">1 week</span>
              <span className="v">
                <Value value={price?.change_1w ?? null} kind="percent" digits={2} signed tone />
              </span>
            </div>
          </div>
        </div>
      </section>

      <div className="inst__foot">
        <div className="inst__prov">
          {identitySource ? <span>name via {identitySource}</span> : null}
          {identitySource && price?.source ? <span className="inst__sep">/</span> : null}
          {price?.source ? <span>quote via {price.source}</span> : null}
          {quoteAt ? <span className="inst__sep">/</span> : null}
          {quoteAt ? <span>{quoteAt.slice(11, 19)}</span> : null}
          {series.length ? <span className="inst__sep">/</span> : null}
          {series.length ? <span>{series.length} sessions</span> : null}
        </div>
        <div className="inst__acts">
          <button
            type="button"
            className="sys-btn"
            aria-pressed={watched}
            onClick={() => { toggleWatch(symbol); setWatched(isWatched(symbol)) }}
          >
            {watched ? 'watching' : 'watch'}
          </button>
          {against ? (
            <a
              className="sys-btn"
              href={`/terminal/compare?a=${encodeURIComponent(symbol)}&b=${encodeURIComponent(against)}`}
            >
              compare with {against}
            </a>
          ) : null}
        </div>
      </div>

      {/* Seamed to the field above: the instrument's rule is this panel's top
          edge, so price and history read as one object rather than as a
          summary followed by the next card down. */}
      <Panel
        seam
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
            {shortfall ? <Prose size="fine" caution>{shortfall}</Prose> : null}
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
    </>
  )
}
