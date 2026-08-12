'use client'

/**
 * Market map — the whole market on one screen.
 *
 * Rebuilt a second time, because the first rebuild was too polite: it kept
 * the original panel's shape and improved it, which meant the before and
 * after were hard to tell apart. This one starts from a different question.
 *
 * The old panel asked "what is the breadth score?" and arranged everything
 * around a number. This one asks **"what is the market doing?"** and
 * arranges everything around eleven sectors, each drawn as ninety days of
 * real price action. The breadth score becomes the left-hand read on that
 * map rather than its subject.
 *
 * Three decisions worth stating:
 *
 * **Sparklines per sector, on a shared rebased scale.** Every sector is
 * rebased to 100 at the start of the window, so eleven instruments trading
 * between $30 and $250 become directly comparable. A number tells you where
 * a sector ended; the line tells you how it got there, and those are
 * different facts — a sector up 4% in a straight line and one up 4% after a
 * 12% round trip are not the same market.
 *
 * **Colour is reserved for meaning.** Sectors are drawn in ink; red and
 * green mark only the sign of a move and the active row. Eleven saturated
 * blocks compete with each other and nothing reads as important, so
 * typography and position carry the hierarchy instead.
 *
 * **Everything is real.** Breadth history and sector paths are recomputed
 * from the same price series the panel already fetched — no fabricated
 * trend, no placeholder series, no smoothing that invents shape.
 */

import Link from 'next/link'
import { Fragment, useMemo, useState } from 'react'
import Tooltip from '@/components/ui/Tooltip'
import { type Breadth, type SectorRow } from '@/lib/dashboardInsights'

/* ── interpretation ───────────────────────────────────────────────────────── */

export interface Verdict {
  headline: string
  detail: string
  tone: 'pos' | 'warn' | 'neg' | 'neutral'
}

/** The score alone is a number. This is what it means. */
export function readScore(score: number | null, positive21: number, count: number): Verdict {
  if (score === null) {
    return { headline: 'Unavailable', detail: 'Sector data did not load.', tone: 'neutral' }
  }
  const shortTerm = count > 0 ? (positive21 / count) * 100 : 0
  const narrowing = score >= 60 && shortTerm < score - 25

  if (narrowing) {
    return {
      headline: 'Narrowing',
      detail: `${score}% hold their 50-day average but only ${Math.round(shortTerm)}% are positive over 21 days — leadership is thinning.`,
      tone: 'warn',
    }
  }
  if (score >= 80) {
    return {
      headline: 'Broad participation',
      detail: 'Nearly every sector is above its 50-day average. Rallies this wide are rarely driven by a single theme.',
      tone: 'pos',
    }
  }
  if (score >= 60) {
    return { headline: 'Healthy', detail: 'A clear majority of sectors are trending above their 50-day average.', tone: 'pos' }
  }
  if (score >= 40) {
    return { headline: 'Mixed', detail: 'Sectors are split. Moves here tend to be rotation rather than direction.', tone: 'neutral' }
  }
  if (score >= 20) {
    return { headline: 'Narrow', detail: 'Most sectors are below their 50-day average. Index strength, if any, rests on few names.', tone: 'warn' }
  }
  return { headline: 'Broad weakness', detail: 'Participation has collapsed across almost every sector.', tone: 'neg' }
}

const TONE: Record<Verdict['tone'], string> = {
  pos: 'var(--pos)', warn: 'var(--warn)', neg: 'var(--neg)', neutral: 'var(--muted)',
}

const signed = (v: number | null, digits = 1) =>
  v === null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(digits)}%`

/* ── the read: score, verdict, trend ──────────────────────────────────────── */

function BreadthRead({ breadth, verdict, positive21, positive63, total }: {
  breadth: Breadth; verdict: Verdict
  positive21: number; positive63: number; total: number
}) {
  const history = useMemo(() => breadth.history ?? [], [breadth.history])
  const score = breadth.breadth_score

  const path = useMemo(() => {
    if (history.length < 8) return null
    const w = 260, h = 58
    const x = (i: number) => (i / (history.length - 1)) * w
    const y = (s: number) => h - (s / 100) * h
    const line = history.map((p, i) => `${x(i)},${y(p.score)}`).join(' ')
    return { w, h, line, area: `${x(0)},${h} ${line} ${x(history.length - 1)},${h}`, y50: y(50) }
  }, [history])

  const change = history.length > 1 ? history[history.length - 1].score - history[0].score : null

  return (
    <div className="mm-read">
      <div className="mm-read__score">
        <span className="mm-read__number" style={{ color: TONE[verdict.tone] }}>{score ?? '—'}</span>
        <span className="mm-read__unit">/ 100<br />breadth</span>
      </div>

      <span className="mm-read__verdict">{verdict.headline}</span>
      <p className="mm-read__detail">{verdict.detail}</p>

      {path && (
        <div className="mm-read__trend">
          <svg viewBox={`0 0 ${path.w} ${path.h}`} width="100%" height={58}
               preserveAspectRatio="none" role="img"
               aria-label={`Breadth over ${history.length} trading days, ${history[0].score} to ${history[history.length - 1].score}`}>
            <line x1="0" y1={path.y50} x2={path.w} y2={path.y50}
                  stroke="var(--line)" strokeWidth="1" strokeDasharray="2 4" />
            <polygon points={path.area} fill={TONE[verdict.tone]} opacity="0.09" />
            <polyline points={path.line} fill="none" stroke={TONE[verdict.tone]}
                      strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
          </svg>
          <div className="mm-read__trendfoot">
            <span>{history.length} sessions</span>
            <span style={{ color: change !== null && change >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
              {change !== null ? `${change >= 0 ? '+' : ''}${change} pts` : ''}
            </span>
          </div>
        </div>
      )}

      <dl className="mm-read__stats">
        {([
          ['Above 50-day', breadth.sectors_above_50d, breadth.sector_count],
          ['Up 21 days', positive21, total],
          ['Up 63 days', positive63, total],
        ] as const).map(([label, n, d]) => (
          <div key={label} className="mm-read__stat">
            <dt>{label}</dt>
            <dd><strong>{n}</strong><span>/{d}</span></dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/* ── the map: eleven sectors, ninety days each ────────────────────────────── */

function Spark({ points, positive, active }: {
  points: number[]; positive: boolean; active: boolean
}) {
  if (points.length < 4) return <span className="mm-spark" aria-hidden />
  const w = 140, h = 26
  const lo = Math.min(...points)
  const hi = Math.max(...points)
  const span = hi - lo || 1
  const y = (v: number) => h - ((v - lo) / span) * (h - 5) - 2.5
  const d = points.map((v, i) => `${(i / (points.length - 1)) * w},${y(v)}`).join(' ')

  return (
    <svg className="mm-spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden>
      <line x1="0" y1={y(points[0])} x2={w} y2={y(points[0])}
            stroke="var(--line)" strokeWidth="0.75" strokeDasharray="2 3" />
      <polyline points={d} fill="none" strokeWidth={active ? 2 : 1.25}
                stroke={positive ? 'var(--pos)' : 'var(--neg)'}
                vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

function SectorMap({ sectors, active, onActive }: {
  sectors: SectorRow[]; active: string | null; onActive: (s: string | null) => void
}) {
  // Only one sector is open at a time: this is a scan surface, and a
  // column of simultaneously expanded rows destroys the comparison the
  // table exists for.
  const [open, setOpen] = useState<string | null>(null)
  /* Which horizon ranks the sectors.
     Leadership over 21 days and over 63 days are different questions, and
     the gap between them is itself the signal — a sector top of the short
     list and mid-table on the long one is rotating in. The map used to
     answer only the first. */
  const [horizon, setHorizon] = useState<'strength_21d' | 'momentum_63d'>('strength_21d')
  const sorted = useMemo(
    () => [...sectors].sort((a, b) => ((b[horizon] ?? -999) as number) - ((a[horizon] ?? -999) as number)),
    [sectors, horizon],
  )

  return (
    <div className="mm-map">
      <div className="mm-map__sortbar">
        {/* Keyboard affordance. The arrow-key walk existed but nothing
            announced it, so it may as well not have. */}
        <span className="u-note kbd-hint">
          <kbd>↑</kbd><kbd>↓</kbd> walk · <kbd>↵</kbd> open
        </span>
        <span className="u-note" style={{ marginLeft: 'auto' }}>Rank by</span>
        {/* A two-position switch rather than two buttons: the thumb's
            position *is* the state, so the control reads at a glance from
            across the table. Adapted from the Uiverse switch family, whose
            mechanism is a sibling-driven thumb translating between discrete
            stops — here it carries a real analytical choice rather than
            on/off. */}
        <button
          type="button"
          role="switch"
          aria-checked={horizon === 'momentum_63d'}
          aria-label="Rank sectors by 63-day momentum instead of 21-day strength"
          className={`hswitch${horizon === 'momentum_63d' ? ' is-long' : ''}`}
          onClick={() => setHorizon((h) => (h === 'strength_21d' ? 'momentum_63d' : 'strength_21d'))}
        >
          <span className="hswitch__opt">21d</span>
          <span className="hswitch__opt">63d</span>
          <span className="hswitch__thumb" aria-hidden />
        </button>
      </div>
      <div className="mm-map__head">
        <span>Sector</span>
        <span className="mm-map__sparkh">90 sessions, rebased</span>
        <span className="mm-num">21d</span>
        <span className="mm-num">63d</span>
        <span className="mm-num">Vol</span>
        <span className="mm-map__mah">50d</span>
      </div>

      {sorted.map((s) => {
        const up = (s.strength_21d ?? 0) >= 0
        const isActive = active === s.symbol
        const isOpen = open === s.symbol
        return (
          <Fragment key={s.symbol}>
          <div
            key={s.symbol}
            className={`mm-map__row rail${isActive ? ' is-active' : ''}${isOpen ? ' is-open' : ''}`}
            tabIndex={0}
            role="button"
            aria-expanded={isOpen}
            onMouseEnter={() => onActive(s.symbol)}
            onMouseLeave={() => onActive(null)}
            onFocus={() => onActive(s.symbol)}
            onBlur={() => onActive(null)}
            onClick={() => setOpen(isOpen ? null : s.symbol)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setOpen(isOpen ? null : s.symbol)
              }
              if (event.key === 'Escape' && isOpen) setOpen(null)
              /* Arrow keys walk the sector list.
                 The map is a ranked table people scan top-to-bottom; making
                 them Tab through it means every row also stops on whatever
                 controls the disclosure exposed. Home/End jump to the
                 strongest and weakest sector, which is the comparison the
                 ranking exists for. */
              const rows = Array.from(
                event.currentTarget.parentElement?.parentElement?.querySelectorAll<HTMLElement>('.mm-map__row') ?? [],
              )
              const here = rows.indexOf(event.currentTarget)
              const go = (to: number) => {
                const target = rows[Math.max(0, Math.min(rows.length - 1, to))]
                if (target) { event.preventDefault(); target.focus() }
              }
              if (event.key === 'ArrowDown') go(here + 1)
              if (event.key === 'ArrowUp') go(here - 1)
              if (event.key === 'Home') go(0)
              if (event.key === 'End') go(rows.length - 1)
            }}
            aria-label={`${s.name}, ${signed(s.strength_21d)} over 21 days, ${s.above_50d ? 'above' : 'below'} its 50-day average, verdict ${s.verdict}`}
          >
            <span className="mm-map__name">
              <span className="mm-map__symbol">{s.symbol}</span>
              <span className="mm-map__label">{s.name}</span>
            </span>
            <span className="mm-map__sparkcell">
              <Spark points={s.history ?? []} positive={up} active={isActive} />
            </span>
            <span className="mm-num mm-map__lead" style={{ color: up ? 'var(--pos)' : 'var(--neg)' }}>
              {signed(s.strength_21d)}
            </span>
            <span className="mm-num mm-map__muted">{signed(s.momentum_63d)}</span>
            <span className="mm-num mm-map__muted">{s.volatility.toFixed(0)}%</span>
            <span className={`mm-map__ma${s.above_50d ? ' is-above' : ''}`}>
              {s.above_50d ? 'above' : 'below'}
            </span>
          </div>
          {/* Opening a sector turns a reading into a next step. The row
              carries no constituent list — the dashboard payload does not
              contain one and inventing holdings would be fabricated
              research — so the action offered is the one the data actually
              supports: the sector ETF is itself a real ticker with a real
              report at /company/{symbol}. */}
          {isOpen && (
            <div className="mm-map__detail" role="region" aria-label={`${s.name} detail`}>
              <span className="mm-map__verdict">
                Engine verdict on {s.symbol}: <strong>{s.verdict}</strong>
              </span>
              <Link href={`/company/${s.symbol}`} className="btn btn--secondary btn--xs">
                Research {s.symbol}
              </Link>
            </div>
          )}
          </Fragment>
        )
      })}
    </div>
  )
}

/* ── panel ────────────────────────────────────────────────────────────────── */

export default function BreadthHeatmap({ breadth, sectors }: {
  breadth: Breadth; sectors: SectorRow[]
}) {
  const [active, setActive] = useState<string | null>(null)

  const positive21 = sectors.filter((s) => (s.strength_21d ?? 0) > 0).length
  const positive63 = sectors.filter((s) => (s.momentum_63d ?? 0) > 0).length
  const verdict = readScore(breadth.breadth_score, positive21, sectors.length)

  return (
    <section aria-labelledby="mm-h" className="market-map">
      <header className="mm-head">
        <div className="mm-head__id">
          <span id="mm-h" className="mm-head__title">
            Market map
            <Tooltip label="How breadth is measured">{breadth.explain}</Tooltip>
          </span>
          <span className="mm-head__sub">{sectors.length} sectors · 90 sessions · rebased to 100</span>
        </div>
        <div className="mm-tape">
          {breadth.indexes.map((i) => (
            <span key={i.symbol} className="mm-tape__item">
              <span className="mm-tape__sym">{i.symbol}</span>
              <span className="mm-tape__px">{i.price}</span>
              {i.change_1d !== null && (
                <span style={{ color: i.change_1d >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                  {signed(i.change_1d, 2)}
                </span>
              )}
            </span>
          ))}
        </div>
      </header>

      <div className="mm-body">
        <BreadthRead breadth={breadth} verdict={verdict}
                     positive21={positive21} positive63={positive63} total={sectors.length} />
        {sectors.length > 0
          ? <SectorMap sectors={sectors} active={active} onActive={setActive} />
          : <p className="mm-read__detail">Sector data did not load.</p>}
      </div>
    </section>
  )
}
