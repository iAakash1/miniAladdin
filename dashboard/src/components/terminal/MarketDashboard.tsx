'use client'

import { useEffect, useState } from 'react'
import Skeleton from '@/components/ui/Skeleton'
import EmptyState from '@/components/ui/EmptyState'
import { fmtNum } from '@/lib/format'

/* ── Types (mirror /api/dashboard) ─────────────────────────────────────────── */

interface MacroCard {
  id: string
  label: string
  value: number
  previous: number | null
  change: number | null
  direction: 'up' | 'down' | 'flat'
  unit: string
  trend: number[]
  updated: string
  explain: string
}

interface Regime {
  available: boolean
  risk_multiplier?: number
  status?: string
  yield_curve?: string
  recession_warning?: boolean
  explain?: string
}

interface IndexQuote {
  symbol: string
  price: number
  change_1d: number | null
  change_1w: number | null
}

interface Breadth {
  indexes: IndexQuote[]
  sectors_above_50d: number
  sector_count: number
  breadth_score: number | null
  explain: string
  leadership: string | null
  laggard: string | null
}

interface SectorRow {
  symbol: string
  name: string
  price: number
  strength_21d: number | null
  momentum_63d: number | null
  volatility: number
  above_50d: boolean
  verdict: string
}

interface EventRow {
  date: string
  type: string
  title: string
  importance: string
  days_away: number
  historical_move: number | null
  explain: string
}

interface DashboardData {
  macro: { cards: MacroCard[]; regime: Regime; note: string }
  breadth: Breadth
  sectors: SectorRow[]
  events: EventRow[]
  generated_at: string
}

/* ── Small pieces ──────────────────────────────────────────────────────────── */

function TrendSpark({ points, direction }: { points: number[]; direction: string }) {
  if (points.length < 2) return null
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const coords = points
    .map((value, index) => {
      const x = (index / (points.length - 1)) * 56
      const y = 18 - ((value - min) / span) * 14 - 2
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  const color = direction === 'up' ? 'var(--pos)' : direction === 'down' ? 'var(--neg)' : 'var(--faint)'
  return (
    <svg width="56" height="18" viewBox="0 0 56 18" aria-hidden="true">
      <polyline points={coords} fill="none" stroke={color} strokeWidth="1.25" />
    </svg>
  )
}

function ChangeTag({ change, unit }: { change: number | null; unit: string }) {
  if (change === null) return null
  const color = change > 0 ? 'var(--pos)' : change < 0 ? 'var(--neg)' : 'var(--faint)'
  return (
    <span className="num" style={{ fontSize: '0.6875rem', color }}>
      {change > 0 ? '+' : ''}
      {change}
      {unit.startsWith('%') ? 'pp' : ''}
    </span>
  )
}

function VerdictBadgeMini({ verdict }: { verdict: string }) {
  const tone = verdict.includes('Buy') ? 'badge--pos' : verdict.includes('Sell') ? 'badge--neg' : 'badge--warn'
  return <span className={`badge ${tone}`} style={{ height: 19, fontSize: '0.625rem' }}>{verdict}</span>
}

/* ── Sections ──────────────────────────────────────────────────────────────── */

function MacroSection({ macro }: { macro: DashboardData['macro'] }) {
  const regime = macro.regime
  return (
    <section aria-labelledby="macro-h">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <h2 id="macro-h" className="h-panel" style={{ fontSize: '1rem' }}>Macro</h2>
        {regime.available && (
          <span style={{ display: 'inline-flex', gap: 8, alignItems: 'center' }}>
            <span className={`badge ${regime.status === 'STABLE' ? 'badge--pos' : 'badge--warn'}`}>
              {regime.status?.toLowerCase()} · SRM {fmtNum(regime.risk_multiplier ?? null, 2)}
            </span>
            <span className="label" style={{ fontSize: '0.625rem' }}>
              curve {regime.yield_curve}
            </span>
          </span>
        )}
      </div>
      <div className="dash-grid">
        {macro.cards.map((card) => (
          <article key={card.id} className="panel" style={{ padding: '14px 16px' }} title={card.explain}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 8 }}>
              <span className="label" style={{ fontSize: '0.625rem' }}>{card.label}</span>
              <TrendSpark points={card.trend} direction={card.direction} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span className="num" style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                {card.value}
                <span style={{ fontSize: '0.6875rem', color: 'var(--faint)', fontWeight: 400 }}>
                  {card.unit && ` ${card.unit}`}
                </span>
              </span>
              <ChangeTag change={card.change} unit={card.unit} />
            </div>
            <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 6, lineHeight: 1.5 }}>
              {card.explain}
            </p>
            <p className="num" style={{ fontSize: '0.5625rem', color: 'var(--faint)', marginTop: 6 }}>
              prev {card.previous ?? '—'} · as of {card.updated}
            </p>
          </article>
        ))}
      </div>
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 10 }}>{macro.note}</p>
    </section>
  )
}

function BreadthSection({ breadth }: { breadth: Breadth }) {
  return (
    <section aria-labelledby="breadth-h">
      <h2 id="breadth-h" className="h-panel" style={{ fontSize: '1rem', marginBottom: 12 }}>
        Market breadth
      </h2>
      <div className="panel" style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(16px, 3vw, 40px)', alignItems: 'center' }}>
          {breadth.indexes.map((index) => (
            <div key={index.symbol}>
              <div className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>{index.symbol}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span className="num" style={{ fontSize: '1rem', fontWeight: 600 }}>{index.price}</span>
                {index.change_1d !== null && (
                  <span className="num" style={{
                    fontSize: '0.6875rem',
                    color: index.change_1d >= 0 ? 'var(--pos)' : 'var(--neg)',
                  }}>
                    {index.change_1d >= 0 ? '+' : ''}{index.change_1d}% d
                  </span>
                )}
              </div>
            </div>
          ))}
          {breadth.breadth_score !== null && (
            <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
              <div className="label" style={{ fontSize: '0.625rem', marginBottom: 4 }}>Breadth score</div>
              <span className="num" style={{
                fontSize: '1.25rem', fontWeight: 600,
                color: breadth.breadth_score >= 60 ? 'var(--pos)' : breadth.breadth_score <= 40 ? 'var(--neg)' : 'var(--warn)',
              }}>
                {breadth.breadth_score}
              </span>
              <span style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}> /100</span>
            </div>
          )}
        </div>
        <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginTop: 12, lineHeight: 1.5 }}>
          {breadth.explain}
          {breadth.leadership && ` Leadership: ${breadth.leadership}; laggard: ${breadth.laggard}.`}
        </p>
      </div>
    </section>
  )
}

function SectorsSection({ sectors }: { sectors: SectorRow[] }) {
  if (sectors.length === 0) return null
  return (
    <section aria-labelledby="sectors-h">
      <h2 id="sectors-h" className="h-panel" style={{ fontSize: '1rem', marginBottom: 12 }}>
        Sectors
      </h2>
      <div className="panel" style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ minWidth: 640 }}>
          <thead>
            <tr>
              <th scope="col">Sector</th>
              <th scope="col" style={{ textAlign: 'right' }}>21d</th>
              <th scope="col" style={{ textAlign: 'right' }}>63d</th>
              <th scope="col" style={{ textAlign: 'right' }}>Vol</th>
              <th scope="col">Trend</th>
              <th scope="col">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((sector) => (
              <tr key={sector.symbol}>
                <td>
                  <span style={{ fontWeight: 550 }}>{sector.name}</span>{' '}
                  <span className="num" style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>{sector.symbol}</span>
                </td>
                <td className="num" style={{ textAlign: 'right', color: (sector.strength_21d ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                  {sector.strength_21d !== null ? `${sector.strength_21d > 0 ? '+' : ''}${sector.strength_21d}%` : '—'}
                </td>
                <td className="num" style={{ textAlign: 'right', color: (sector.momentum_63d ?? 0) >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                  {sector.momentum_63d !== null ? `${sector.momentum_63d > 0 ? '+' : ''}${sector.momentum_63d}%` : '—'}
                </td>
                <td className="num" style={{ textAlign: 'right' }}>{sector.volatility}%</td>
                <td style={{ fontSize: '0.75rem', color: sector.above_50d ? 'var(--pos)' : 'var(--neg)' }}>
                  {sector.above_50d ? 'above 50d' : 'below 50d'}
                </td>
                <td><VerdictBadgeMini verdict={sector.verdict} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function EventsSection({ events }: { events: EventRow[] }) {
  if (events.length === 0) return null
  return (
    <section aria-labelledby="events-h">
      <h2 id="events-h" className="h-panel" style={{ fontSize: '1rem', marginBottom: 12 }}>
        Upcoming events
      </h2>
      <div className="panel" style={{ padding: '6px 18px' }}>
        {events.map((event, index) => (
          <div
            key={`${event.date}-${event.type}`}
            style={{
              display: 'flex', alignItems: 'center', gap: 14, padding: '12px 0',
              borderBottom: index < events.length - 1 ? '1px solid var(--line)' : 'none',
              flexWrap: 'wrap',
            }}
          >
            <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)', width: 84 }}>{event.date}</span>
            <span className={`badge ${event.importance === 'high' ? 'badge--warn' : 'badge--neutral'}`} style={{ height: 19, fontSize: '0.625rem' }}>
              {event.type}
            </span>
            <span style={{ fontSize: '0.8125rem', flex: 1, minWidth: 160 }}>{event.title}</span>
            {event.historical_move !== null && (
              <span className="num" title={event.explain} style={{ fontSize: '0.6875rem', color: 'var(--muted)' }}>
                ±{event.historical_move}% typical
              </span>
            )}
            <span className="num" style={{ fontSize: '0.75rem', color: event.days_away <= 3 ? 'var(--warn)' : 'var(--muted)' }}>
              {event.days_away === 0 ? 'today' : `in ${event.days_away}d`}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ── Root ──────────────────────────────────────────────────────────────────── */

function DashboardSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }} aria-hidden="true">
      <div className="dash-grid">
        {Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} height={110} />)}
      </div>
      <Skeleton height={100} />
      <Skeleton height={320} />
    </div>
  )
}

export default function MarketDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [failed, setFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    fetch('/api/dashboard', { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
      .then((json: DashboardData) => {
        if (alive) {
          setData(json)
          setFailed(false)
        }
      })
      .catch((error: unknown) => {
        if (alive && (error as Error).name !== 'AbortError') setFailed(true)
      })
    return () => {
      alive = false
      controller.abort()
    }
  }, [reloadKey])

  if (failed) {
    return (
      <EmptyState
        title="Market data is unreachable"
        description="The dashboard service didn't respond. This usually resolves quickly."
        action={
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => { setData(null); setFailed(false); setReloadKey((key) => key + 1) }}>
            Try again
          </button>
        }
      />
    )
  }

  if (!data) return <DashboardSkeleton />

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
      <MacroSection macro={data.macro} />
      <BreadthSection breadth={data.breadth} />
      <SectorsSection sectors={data.sectors} />
      <EventsSection events={data.events} />
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', textAlign: 'center' }}>
        Data refreshes every 15 minutes · generated {new Date(data.generated_at).toLocaleTimeString()}
      </p>
    </div>
  )
}
