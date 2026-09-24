'use client'

import { useEffect, useId, useMemo, useRef, useState } from 'react'

import type { PricePoint } from '@/lib/types'

const PAD = { top: 12, right: 56, bottom: 22, left: 8 }

function niceStep(span: number, count: number): number {
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  return (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag
}

function fmtPrice(v: number): string {
  return v >= 1000 ? v.toLocaleString('en-US', { maximumFractionDigits: 0 }) : v.toFixed(2)
}

function fmtVolume(v: number | null): string {
  if (v === null) return '—'
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
  return String(v)
}

function fmtDay(iso: string, long = false): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-US', long ? { month: 'short', day: 'numeric', year: 'numeric' } : { month: 'short', day: 'numeric' })
}

/**
 * Daily closes with a volume track. Missing volume is drawn as missing, and
 * nothing is interpolated between sessions.
 */
export default function PriceChart({
  points, height = 300, label,
}: {
  points: PricePoint[]
  height?: number
  /** Accessible description, e.g. "AAPL daily close, 3 months". */
  label: string
}) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  const gradient = useId()

  useEffect(() => {
    const el = box.current
    if (!el) return undefined
    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0]?.contentRect.width ?? 0)
      setWidth((prev) => (prev === w ? prev : w))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const geo = useMemo(() => {
    const n = points.length
    if (!n || width < 80) return null
    const closes = points.map((p) => p.close)
    let lo = Math.min(...closes)
    let hi = Math.max(...closes)
    if (lo === hi) { lo -= 1; hi += 1 }
    const padY = (hi - lo) * 0.08
    lo -= padY
    hi += padY
    const iw = width - PAD.left - PAD.right
    const ih = height - PAD.top - PAD.bottom
    const volH = ih * 0.18
    const priceH = ih - volH - 6
    const x = (i: number) => PAD.left + (n === 1 ? iw / 2 : (i / (n - 1)) * iw)
    const y = (v: number) => PAD.top + priceH - ((v - lo) / (hi - lo)) * priceH
    const vols = points.map((p) => p.volume).filter((v): v is number => v !== null && v > 0)
    const vmax = vols.length ? Math.max(...vols) : 0
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.close).toFixed(1)}`).join(' ')
    const area = `${line} L${x(n - 1).toFixed(1)},${(PAD.top + priceH).toFixed(1)} L${x(0).toFixed(1)},${(PAD.top + priceH).toFixed(1)} Z`
    const step = niceStep(hi - lo, 4)
    const ticks: number[] = []
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(Number(v.toFixed(8)))
    const xCount = Math.max(2, Math.min(6, Math.floor(iw / 120)))
    const xTicks = Array.from({ length: xCount }, (_, k) => Math.round((k / (xCount - 1)) * (n - 1)))
    const barW = Math.max(1, Math.min(6, iw / n - 1))
    return { n, x, y, line, area, ticks, xTicks, lo, hi, priceH, volH, vmax, barW, iw }
  }, [points, width, height])

  const first = points[0]?.close ?? null
  const last = points[points.length - 1]?.close ?? null
  const change = first !== null && last !== null && first !== 0 ? last / first - 1 : null
  const at = hover !== null ? points[hover] : null
  const atChange = at && first ? at.close / first - 1 : null

  const indexAt = (clientX: number) => {
    const rect = box.current?.getBoundingClientRect()
    if (!rect || !geo) return null
    const rel = clientX - rect.left - PAD.left
    const i = Math.round((rel / geo.iw) * (geo.n - 1))
    return Math.max(0, Math.min(geo.n - 1, i))
  }

  const summary = first !== null && last !== null
    ? `${label}: ${fmtPrice(first)} to ${fmtPrice(last)}${change !== null ? ` (${change >= 0 ? '+' : ''}${(change * 100).toFixed(2)}%)` : ''} over ${points.length} sessions.`
    : label

  return (
    <div
      ref={box}
      className="pchart"
      style={{ height }}
      role="img"
      aria-label={summary}
      tabIndex={0}
      onPointerMove={(e) => setHover(indexAt(e.clientX))}
      onPointerLeave={() => setHover(null)}
      onKeyDown={(e) => {
        if (!geo) return
        if (e.key === 'ArrowLeft') { e.preventDefault(); setHover((h) => Math.max(0, (h ?? geo.n) - 1)) }
        if (e.key === 'ArrowRight') { e.preventDefault(); setHover((h) => Math.min(geo.n - 1, (h ?? -1) + 1)) }
        if (e.key === 'Escape') setHover(null)
      }}
      onBlur={() => setHover(null)}
    >
      {geo ? (
        <svg width={width} height={height} aria-hidden>
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {geo.ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(t)} y2={geo.y(t)} className="pchart__grid" />
              <text x={width - PAD.right + 8} y={geo.y(t) + 3.5} className="pchart__tick">{fmtPrice(t)}</text>
            </g>
          ))}

          {first !== null ? (
            <line x1={PAD.left} x2={width - PAD.right} y1={geo.y(first)} y2={geo.y(first)} className="pchart__base" />
          ) : null}

          <path d={geo.area} fill={`url(#${gradient})`} />
          <path d={geo.line} className="pchart__line" />

          {geo.vmax > 0 ? points.map((p, i) => (
            p.volume !== null && p.volume > 0 ? (
              <rect
                key={p.date}
                x={geo.x(i) - geo.barW / 2}
                width={geo.barW}
                y={PAD.top + geo.priceH + 6 + geo.volH - (p.volume / geo.vmax) * geo.volH}
                height={(p.volume / geo.vmax) * geo.volH}
                className={hover === i ? 'pchart__vol is-hover' : 'pchart__vol'}
              />
            ) : null
          )) : null}

          {geo.xTicks.map((i) => (
            <text
              key={`x${i}`}
              x={geo.x(i)}
              y={height - 6}
              textAnchor={i === 0 ? 'start' : i === geo.n - 1 ? 'end' : 'middle'}
              className="pchart__tick"
            >
              {fmtDay(points[i].date)}
            </text>
          ))}

          {at && hover !== null ? (
            <g>
              <line x1={geo.x(hover)} x2={geo.x(hover)} y1={PAD.top} y2={PAD.top + geo.priceH + 6 + geo.volH} className="pchart__cross" />
              <circle cx={geo.x(hover)} cy={geo.y(at.close)} r={3.5} className="pchart__dot" />
              <rect x={width - PAD.right + 1} y={geo.y(at.close) - 9} width={PAD.right - 2} height={18} rx={2} className="pchart__tag" />
              <text x={width - PAD.right + 8} y={geo.y(at.close) + 4} className="pchart__tag-text">{fmtPrice(at.close)}</text>
            </g>
          ) : null}
        </svg>
      ) : null}

      <div className="pchart__readout" aria-hidden>
        {at ? (
          <>
            <span>{fmtDay(at.date, true)}</span>
            <b>{fmtPrice(at.close)}</b>
            {atChange !== null ? (
              <span className={atChange >= 0 ? 'sys-pos' : 'sys-neg'}>
                {atChange >= 0 ? '+' : ''}{(atChange * 100).toFixed(2)}% vs window start
              </span>
            ) : null}
            <span>vol {fmtVolume(at.volume)}</span>
          </>
        ) : change !== null ? (
          <>
            <span>{fmtDay(points[0].date, true)} – {fmtDay(points[points.length - 1].date, true)}</span>
            <span className={change >= 0 ? 'sys-pos' : 'sys-neg'}>{change >= 0 ? '+' : ''}{(change * 100).toFixed(2)}% over window</span>
          </>
        ) : null}
      </div>
    </div>
  )
}
