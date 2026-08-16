'use client'

/**
 * Small visual primitives driven entirely by values the caller already has.
 *
 * Each of these replaces a number that was being read character by character
 * with a shape that can be compared down a column at a glance. None of them
 * invent data: given nothing, they render nothing rather than a zero, an
 * empty bar or a flat line — an absent confidence is not a confidence of 0,
 * and a flat sparkline would assert a stable price that was never measured.
 */

import { useState } from 'react'

import { faviconFor, sourceDomain } from '@/lib/identity'

/* ── Source favicon ─────────────────────────────────────────────────────── */

/** Recognisable mark for an evidence source, from its own domain.
 *
 *  Uses the public favicon service rather than bundling provider logos,
 *  which would be both a licensing question and a maintenance burden. Falls
 *  back to the domain's first letter, so a blocked or missing icon still
 *  reads as an attributed source. */
export function SourceMark({ url, name }: { url?: string | null; name?: string | null }) {
  const [failed, setFailed] = useState(false)
  // Shared with SourceBadge and the macro cards, so a source that resolves
  // on one surface resolves identically on every other.
  const host = sourceDomain(name, url)
  const letter = (name ?? host ?? '?').trim().charAt(0).toUpperCase() || '?'

  return (
    <span className="smark" title={host || name || undefined} aria-hidden>
      {letter}
      {/* Intentionally not next/image: a fixed-size third-party mark that
          must be allowed to fail silently. Routing it through the optimizer
          would need a remotePatterns entry per provider and would turn a 404
          into a build-time concern. */}
      {host && !failed && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="smark__img"
          src={faviconFor(host, 32)}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  )
}

/* ── Sparkline ──────────────────────────────────────────────────────────── */

/** A path through real values. Returns null below two points, because one
 *  point is not a trend and drawing it flat would imply one. */
export function Sparkline({
  points,
  width = 56,
  height = 16,
}: {
  points: number[]
  width?: number
  height?: number
}) {
  if (!points || points.length < 2) return null
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = width / (points.length - 1)
  // Inset by the stroke so the extremes are not clipped at the box edge.
  const pad = 1.5
  const usable = height - pad * 2
  const d = points
    .map((value, i) => {
      const x = i * step
      const y = pad + usable - ((value - min) / span) * usable
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
  const rising = points[points.length - 1] >= points[0]

  return (
    <svg
      className="spark-inline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
    >
      <path className={`spark-inline__line spark-inline__line--${rising ? 'pos' : 'neg'}`} d={d} />
    </svg>
  )
}

/* ── Confidence ─────────────────────────────────────────────────────────── */

/** Confidence as a length as well as a number.
 *
 *  Banding matches the thresholds the product already uses elsewhere for
 *  this value, so the colour agrees with the written verdict rather than
 *  introducing a second opinion. */
export function ConfidenceBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <span className="u-note">—</span>
  }
  const pct = Math.min(100, Math.max(0, value))
  const band = pct >= 60 ? 'high' : pct >= 40 ? 'mid' : 'low'
  return (
    <span className={`confbar confbar--${band}`}>
      <span
        className="confbar__track"
        role="img"
        aria-label={`Confidence ${Math.round(pct)} percent`}
      >
        <span className="confbar__fill" style={{ transform: `scaleX(${pct / 100})` }} />
      </span>
      <span className="num">{Math.round(pct)}%</span>
    </span>
  )
}

/* ── Trend ──────────────────────────────────────────────────────────────── */

/** Direction as a glyph, so a column of moves is legible before any digit
 *  is read. Zero is a bar rather than an arrow: a flat reading is a fact,
 *  and rounding it up to "rose" or "fell" would be an assertion. */
export function TrendMark({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : 'flat'
  const word = dir === 'up' ? 'rising' : dir === 'down' ? 'falling' : 'unchanged'
  return <span className={`trendmark trendmark--${dir}`} role="img" aria-label={word} />
}

/* ── Allocation ─────────────────────────────────────────────────────────── */

/** A share of a whole, drawn against the largest share present.
 *
 *  Scaled to `max` rather than to 100% because portfolio weights are rarely
 *  near 100 and a bar that never leaves its first tenth conveys nothing.
 *  The number stays alongside, so the bar adds comparison without becoming
 *  the only reading of the value. */
export function AllocBar({
  value,
  max,
}: {
  value: number | null | undefined
  max: number
}) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <span className="u-note">—</span>
  }
  const ceiling = Number.isFinite(max) && max > 0 ? max : 1
  const ratio = Math.min(1, Math.max(0, value / ceiling))
  return (
    <span className="allocbar">
      <span className="allocbar__track" role="img" aria-label={`${value.toFixed(1)} percent of portfolio`}>
        <span className="allocbar__fill" style={{ transform: `scaleX(${ratio})` }} />
      </span>
      <span className="num allocbar__num">{value.toFixed(1)}%</span>
    </span>
  )
}

/* ── Status ─────────────────────────────────────────────────────────────── */

export type StatusTone = 'pos' | 'neg' | 'warn' | 'muted' | 'accent'

/** A state as a dot plus a word.
 *
 *  The dot carries a ring rather than a fill for pending states, so the two
 *  read apart in a monochrome screenshot and under forced colours — colour
 *  is the second signal here, never the only one. */
export function StatusPill({
  tone,
  label,
  pulse = false,
}: {
  tone: StatusTone
  label: string
  /** Only for states that are genuinely still moving. A pulse on a settled
   *  state is a claim that something is happening when nothing is. */
  pulse?: boolean
}) {
  return (
    <span className={`spill spill--${tone}${pulse ? ' spill--live' : ''}`}>
      <span className="spill__dot" aria-hidden />
      {label}
    </span>
  )
}
