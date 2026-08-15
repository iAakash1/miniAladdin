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

/* ── Source favicon ─────────────────────────────────────────────────────── */

/** Recognisable mark for an evidence source, from its own domain.
 *
 *  Uses the public favicon service rather than bundling provider logos,
 *  which would be both a licensing question and a maintenance burden. Falls
 *  back to the domain's first letter, so a blocked or missing icon still
 *  reads as an attributed source. */
export function SourceMark({ url, name }: { url?: string | null; name?: string | null }) {
  const [failed, setFailed] = useState(false)
  let host = ''
  try {
    if (url) host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    host = ''
  }
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
          src={`https://www.google.com/s2/favicons?sz=32&domain=${encodeURIComponent(host)}`}
          alt=""
          loading="lazy"
          decoding="async"
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
