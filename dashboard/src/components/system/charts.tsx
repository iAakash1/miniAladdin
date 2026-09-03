/**
 * Analytical chart primitives.
 *
 * Hand-built SVG rather than a charting library, for three reasons that matter
 * here. Units and methodology have to travel with the plot, which no generic
 * library models. Missing data has to be visibly missing rather than
 * interpolated across, and every library's default is to interpolate. And a
 * terminal draws many small plots at once, where a library's per-chart runtime
 * cost is paid over and over.
 *
 * Every chart takes an explicit `unit` and renders an honest empty state. None
 * of them invent a point, smooth a gap, or extend a series to fill the frame.
 */
'use client'

import { useId, useMemo, useState, type ReactNode } from 'react'

import { useChartCursor } from './ChartCursor'

export interface Point {
  /** x is a date string or an index. Rendering treats it as ordinal. */
  x: string | number
  /** null is a gap, and is drawn as a gap. */
  y: number | null
}

const PAD = { top: 8, right: 8, bottom: 18, left: 44 }

function extent(values: number[]): [number, number] {
  if (!values.length) return [0, 1]
  let lo = values[0]
  let hi = values[0]
  for (const v of values) {
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  if (lo === hi) {
    const pad = Math.abs(lo) * 0.1 || 1
    return [lo - pad, hi + pad]
  }
  return [lo, hi]
}

function niceTicks(lo: number, hi: number, count = 4): number[] {
  const span = hi - lo
  if (span <= 0) return [lo]
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / mag
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag
  const start = Math.ceil(lo / step) * step
  const out: number[] = []
  for (let v = start; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(10)))
  return out
}

function fmtTick(v: number): string {
  const a = Math.abs(v)
  if (a === 0) return '0'
  if (a < 0.0001) return v.toExponential(1)
  if (a < 1) return v.toFixed(a < 0.01 ? 4 : 3)
  if (a < 1000) return v.toFixed(2)
  if (a < 1e6) return `${(v / 1000).toFixed(1)}k`
  return `${(v / 1e6).toFixed(1)}M`
}

/* ── shared frame ─────────────────────────────────────────────────────── */

export function ChartFrame({
  title, unit, method, height = 180, children, empty, footer,
}: {
  title?: string
  unit?: string
  method?: string
  height?: number
  children: ReactNode
  empty?: boolean
  footer?: ReactNode
}) {
  return (
    <figure style={{ margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--d-1)' }}>
      {title || unit ? (
        <figcaption style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--d-2)' }}>
          {title ? <span className="sys-label" style={{ fontSize: 'var(--t-micro)' }}>{title}</span> : <span />}
          {unit ? <span className="sys-meta" title={method}>{unit}</span> : null}
        </figcaption>
      ) : null}
      {empty ? (
        <div
          style={{
            height, display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px dashed var(--rule)', color: 'var(--ink-faint)',
            fontSize: 'var(--t-meta)', fontFamily: 'var(--font-mono)',
          }}
        >
          no observations
        </div>
      ) : children}
      {footer}
    </figure>
  )
}

/* ── sparkline ─────────────────────────────────────────────────────────── */

export function Sparkline({
  values, width = 96, height = 22, tone = true,
}: {
  values: (number | null)[]
  width?: number
  height?: number
  tone?: boolean
}) {
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v))
  if (finite.length < 2) {
    return <span className="sys-null" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>—</span>
  }
  const [lo, hi] = extent(finite)
  const step = width / Math.max(1, values.length - 1)
  const y = (v: number) => height - ((v - lo) / (hi - lo)) * height

  // Gaps break the path rather than being bridged.
  const segments: string[] = []
  let current: string[] = []
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      if (current.length > 1) segments.push(current.join(' '))
      current = []
      return
    }
    current.push(`${current.length ? 'L' : 'M'}${(i * step).toFixed(2)},${y(v).toFixed(2)}`)
  })
  if (current.length > 1) segments.push(current.join(' '))

  const last = finite[finite.length - 1]
  const first = finite[0]
  const stroke = tone
    ? last >= first ? 'var(--e-pos)' : 'var(--e-neg)'
    : 'var(--ink-muted)'

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="sparkline" style={{ display: 'block', overflow: 'visible' }}>
      {segments.map((d) => (
        <path key={d.slice(0, 24)} d={d} fill="none" stroke={stroke} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  )
}

/* ── time series ───────────────────────────────────────────────────────── */

export function TimeSeries({
  series, height = 190, unit, method, title, zeroLine = false, band,
}: {
  series: { name: string; points: Point[]; color?: string; dashed?: boolean }[]
  height?: number
  unit?: string
  method?: string
  title?: string
  zeroLine?: boolean
  /** An optional confidence band, drawn behind the lines. */
  band?: { points: Point[]; upper: (number | null)[]; lower: (number | null)[] }
}) {
  const [hover, setHover] = useState<number | null>(null)
  const cursor = useChartCursor()
  const id = useId()

  const all = useMemo(
    () => series.flatMap((s) => s.points.map((p) => p.y)).filter((v): v is number => v !== null && Number.isFinite(v)),
    [series],
  )
  const bandValues = useMemo(
    () => (band ? [...band.upper, ...band.lower].filter((v): v is number => v !== null && Number.isFinite(v)) : []),
    [band],
  )

  const n = series[0]?.points.length ?? 0
  if (!n || !all.length) return <ChartFrame title={title} unit={unit} method={method} height={height} empty>{null}</ChartFrame>

  const [lo, hi] = extent([...all, ...bandValues, ...(zeroLine ? [0] : [])])
  const W = 640
  const H = height
  const iw = W - PAD.left - PAD.right
  const ih = H - PAD.top - PAD.bottom
  const px = (i: number) => PAD.left + (n === 1 ? iw / 2 : (i / (n - 1)) * iw)
  const py = (v: number) => PAD.top + ih - ((v - lo) / (hi - lo)) * ih

  const path = (points: Point[]) => {
    const out: string[] = []
    let started = false
    points.forEach((p, i) => {
      if (p.y === null || !Number.isFinite(p.y)) { started = false; return }
      out.push(`${started ? 'L' : 'M'}${px(i).toFixed(2)},${py(p.y).toFixed(2)}`)
      started = true
    })
    return out.join(' ')
  }

  const ticks = niceTicks(lo, hi, 4)
  const labels = series[0].points

  // The shared cursor is a date, not an index: these charts have different
  // lengths and start points, and an index would align the ninth observation
  // of one series with the ninth of another and call that the same moment.
  const shared = cursor.at !== null
    ? labels.findIndex((p) => String(p.x) === cursor.at)
    : -1
  const marked = hover ?? (shared >= 0 ? shared : null)

  return (
    <ChartFrame
      title={title} unit={unit} method={method}
      footer={
        series.length > 1 ? (
          <div style={{ display: 'flex', gap: 'var(--d-3)', flexWrap: 'wrap' }}>
            {series.map((s) => (
              <span key={s.name} className="sys-meta" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ width: 8, height: 2, background: s.color ?? 'var(--ink)' }} />
                {s.name}
              </span>
            ))}
          </div>
        ) : null
      }
    >
      <svg
        viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img"
        aria-label={title ?? 'time series'}
        onMouseLeave={() => { setHover(null); cursor.set(null) }}
        onMouseMove={(e) => {
          const rect = (e.target as SVGElement).ownerSVGElement?.getBoundingClientRect()
          if (!rect) return
          const rel = ((e.clientX - rect.left) / rect.width) * W
          const i = Math.round(((rel - PAD.left) / iw) * (n - 1))
          const next = i >= 0 && i < n ? i : null
          setHover(next)
          cursor.set(next === null ? null : String(labels[next]?.x ?? ''))
        }}
        style={{ display: 'block', cursor: 'crosshair' }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={py(t)} y2={py(t)} stroke="var(--rule)" strokeWidth={1} />
            <text x={PAD.left - 5} y={py(t) + 3} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">
              {fmtTick(t)}
            </text>
          </g>
        ))}
        {zeroLine && lo < 0 && hi > 0 ? (
          <line x1={PAD.left} x2={W - PAD.right} y1={py(0)} y2={py(0)} stroke="var(--rule-strong)" strokeWidth={1} />
        ) : null}

        {band ? (
          <path
            d={[
              ...band.upper.map((v, i) => (v === null ? '' : `${i === 0 ? 'M' : 'L'}${px(i)},${py(v)}`)),
              ...band.lower.map((v, i) => (v === null ? '' : `L${px(band.lower.length - 1 - i)},${py(band.lower[band.lower.length - 1 - i] as number)}`)),
              'Z',
            ].filter(Boolean).join(' ')}
            fill="var(--ink-faint)" opacity={0.12} stroke="none"
          />
        ) : null}

        {series.map((s) => (
          <path
            key={s.name}
            d={path(s.points)}
            fill="none"
            stroke={s.color ?? 'var(--ink)'}
            strokeWidth={1.4}
            strokeDasharray={s.dashed ? '3 2' : undefined}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {marked !== null ? (
          <g>
            {/* Solid when this chart owns the cursor, dashed when it is
                following another — so the reader can tell which chart they are
                driving from the one they are reading. */}
            <line
              x1={px(marked)} x2={px(marked)} y1={PAD.top} y2={H - PAD.bottom}
              stroke="var(--accent)" strokeWidth={1}
              strokeDasharray={hover === null ? '3 3' : undefined}
              opacity={hover === null ? 0.7 : 1}
            />
            {series.map((s) => {
              const p = s.points[marked]
              if (!p || p.y === null) return null
              return <circle key={`${id}-${s.name}`} cx={px(marked)} cy={py(p.y)} r={2.5} fill={s.color ?? 'var(--ink)'} />
            })}
          </g>
        ) : null}

        <text x={PAD.left} y={H - 4} fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">
          {String(labels[0]?.x ?? '')}
        </text>
        <text x={W - PAD.right} y={H - 4} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">
          {String(labels[n - 1]?.x ?? '')}
        </text>
        {marked !== null ? (
          <text x={W / 2} y={H - 4} textAnchor="middle" fontSize={9} fill="var(--ink)" fontFamily="var(--font-mono)">
            {String(labels[marked]?.x ?? '')}
            {series.map((s) => {
              const v = s.points[marked]?.y
              return v === null || v === undefined ? '' : `  ${s.name} ${v.toFixed(4)}`
            }).join('')}
          </text>
        ) : null}
      </svg>
    </ChartFrame>
  )
}

/* ── drawdown ──────────────────────────────────────────────────────────── */

export function DrawdownChart({ points, height = 150, title = 'Drawdown' }: { points: Point[]; height?: number; title?: string }) {
  const finite = points.map((p) => p.y).filter((v): v is number => v !== null && Number.isFinite(v))
  if (finite.length < 2) return <ChartFrame title={title} height={height} empty>{null}</ChartFrame>

  const W = 640
  const H = height
  const iw = W - PAD.left - PAD.right
  const ih = H - PAD.top - PAD.bottom
  const lo = Math.min(...finite, 0)
  const px = (i: number) => PAD.left + (i / (points.length - 1)) * iw
  const py = (v: number) => PAD.top + (v / lo) * ih

  const area = [
    `M${px(0)},${PAD.top}`,
    ...points.map((p, i) => (p.y === null ? '' : `L${px(i).toFixed(2)},${py(p.y).toFixed(2)}`)).filter(Boolean),
    `L${px(points.length - 1)},${PAD.top}`, 'Z',
  ].join(' ')

  const trough = finite.reduce((a, b) => Math.min(a, b), 0)

  return (
    <ChartFrame title={title} unit="return, from peak" method="peak_to_trough on the wealth path">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="drawdown" style={{ display: 'block' }}>
        <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top} y2={PAD.top} stroke="var(--rule-strong)" />
        <path d={area} fill="var(--e-neg)" opacity={0.16} stroke="var(--e-neg)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        <text x={PAD.left - 5} y={PAD.top + 3} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">0</text>
        <text x={PAD.left - 5} y={PAD.top + ih} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">{fmtTick(trough)}</text>
      </svg>
    </ChartFrame>
  )
}

/* ── histogram ─────────────────────────────────────────────────────────── */

export function Histogram({
  values, bins = 28, height = 160, title, unit, marks,
}: {
  values: number[]
  bins?: number
  height?: number
  title?: string
  unit?: string
  /** Vertical rules — a VaR cutoff, a mean, a threshold. */
  marks?: { at: number; label: string; color?: string }[]
}) {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length < 2) return <ChartFrame title={title} unit={unit} height={height} empty>{null}</ChartFrame>

  const [lo, hi] = extent(finite)
  const width = (hi - lo) / bins
  const counts = new Array(bins).fill(0)
  for (const v of finite) {
    const i = Math.min(bins - 1, Math.max(0, Math.floor((v - lo) / width)))
    counts[i] += 1
  }
  const peak = Math.max(...counts)

  const W = 640
  const H = height
  const iw = W - PAD.left - PAD.right
  const ih = H - PAD.top - PAD.bottom
  const bx = (i: number) => PAD.left + (i / bins) * iw
  const bw = iw / bins - 1
  const mx = (v: number) => PAD.left + ((v - lo) / (hi - lo)) * iw

  return (
    <ChartFrame title={title} unit={unit} method={`${finite.length} observations, ${bins} bins`}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="distribution" style={{ display: 'block' }}>
        {counts.map((c, i) => (
          <rect
            key={i}
            x={bx(i)} width={Math.max(1, bw)}
            y={PAD.top + ih - (c / peak) * ih}
            height={(c / peak) * ih}
            fill={lo + i * width < 0 ? 'var(--e-neg)' : 'var(--ink-muted)'}
            opacity={0.55}
          />
        ))}
        {marks?.map((m) => (
          <g key={m.label}>
            <line x1={mx(m.at)} x2={mx(m.at)} y1={PAD.top} y2={PAD.top + ih} stroke={m.color ?? 'var(--ink)'} strokeWidth={1} strokeDasharray="3 2" />
            <text x={mx(m.at) + 3} y={PAD.top + 8} fontSize={9} fill={m.color ?? 'var(--ink)'} fontFamily="var(--font-mono)">{m.label}</text>
          </g>
        ))}
        <text x={PAD.left} y={H - 4} fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">{fmtTick(lo)}</text>
        <text x={W - PAD.right} y={H - 4} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">{fmtTick(hi)}</text>
      </svg>
    </ChartFrame>
  )
}

/* ── correlation / covariance matrix ───────────────────────────────────── */

export function Matrix({
  labels, values, title, unit = 'correlation', diverging = true,
}: {
  labels: string[]
  /** Row-major. null is an unmeasured pair and is drawn as such, not as 0. */
  values: (number | null)[][]
  title?: string
  unit?: string
  diverging?: boolean
}) {
  const [hover, setHover] = useState<{ i: number; j: number } | null>(null)
  if (!labels.length) return <ChartFrame title={title} unit={unit} empty>{null}</ChartFrame>

  const n = labels.length
  const cell = Math.max(12, Math.min(30, Math.floor(560 / n)))
  const gutter = Math.min(96, Math.max(48, ...labels.map((l) => l.length * 5.4)))
  const W = gutter + n * cell + 8
  const H = gutter + n * cell + 8

  const fill = (v: number | null) => {
    if (v === null || !Number.isFinite(v)) return 'transparent'
    const a = Math.min(1, Math.abs(v))
    if (!diverging) return `color-mix(in srgb, var(--ink) ${a * 70}%, transparent)`
    return v >= 0
      ? `color-mix(in srgb, var(--e-pos) ${a * 72}%, transparent)`
      : `color-mix(in srgb, var(--e-neg) ${a * 72}%, transparent)`
  }

  return (
    <ChartFrame title={title} unit={unit} method="an unmeasured pair is drawn hatched, never as zero">
      <div className="sys-scroll-x">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={title ?? 'matrix'} style={{ display: 'block', maxWidth: '100%' }}>
          <defs>
            <pattern id="sys-nomeasure" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="4" stroke="var(--ink-faint)" strokeWidth="1" opacity="0.5" />
            </pattern>
          </defs>
          {labels.map((l, i) => (
            <text key={`r${l}`} x={gutter - 4} y={gutter + i * cell + cell / 2 + 3} textAnchor="end" fontSize={9} fill="var(--ink-muted)" fontFamily="var(--font-mono)">
              {l.length > 16 ? `${l.slice(0, 15)}…` : l}
            </text>
          ))}
          {labels.map((l, j) => (
            <text
              key={`c${l}`} x={gutter + j * cell + cell / 2} y={gutter - 5}
              textAnchor="start" fontSize={9} fill="var(--ink-muted)" fontFamily="var(--font-mono)"
              transform={`rotate(-60 ${gutter + j * cell + cell / 2} ${gutter - 5})`}
            >
              {l.length > 16 ? `${l.slice(0, 15)}…` : l}
            </text>
          ))}
          {values.map((row, i) =>
            row.map((v, j) => (
              <rect
                key={`${i}-${j}`}
                x={gutter + j * cell} y={gutter + i * cell}
                width={cell - 1} height={cell - 1}
                fill={v === null ? 'url(#sys-nomeasure)' : fill(v)}
                stroke={hover && hover.i === i && hover.j === j ? 'var(--rule-focus)' : 'var(--rule)'}
                strokeWidth={hover && hover.i === i && hover.j === j ? 1.5 : 0.5}
                onMouseEnter={() => setHover({ i, j })}
                onMouseLeave={() => setHover(null)}
              >
                <title>
                  {`${labels[i]} × ${labels[j]}: ${v === null ? 'never observed together' : v.toFixed(3)}`}
                </title>
              </rect>
            )),
          )}
        </svg>
      </div>
    </ChartFrame>
  )
}

/* ── horizontal contribution bars ──────────────────────────────────────── */

export function BarRows({
  rows, unit, title, max,
}: {
  rows: { label: string; value: number | null; note?: string }[]
  unit?: string
  title?: string
  max?: number
}) {
  const finite = rows.map((r) => r.value).filter((v): v is number => v !== null && Number.isFinite(v))
  if (!finite.length) return <ChartFrame title={title} unit={unit} empty>{null}</ChartFrame>
  const bound = max ?? Math.max(...finite.map(Math.abs))
  const hasNegative = finite.some((v) => v < 0)

  return (
    <ChartFrame title={title} unit={unit}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {rows.map((r) => {
          const v = r.value
          const pct = v === null ? 0 : (Math.abs(v) / bound) * (hasNegative ? 50 : 100)
          return (
            <div key={r.label} style={{ display: 'grid', gridTemplateColumns: '108px 1fr 68px', alignItems: 'center', gap: 'var(--d-2)', height: 'var(--row-compact)' }}>
              <span className="sys-meta" style={{ color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.note ?? r.label}>
                {r.label}
              </span>
              <div style={{ position: 'relative', height: 9, background: 'var(--p-sunken)', border: '1px solid var(--rule)' }}>
                {hasNegative ? <span style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--rule-strong)' }} /> : null}
                {v === null ? null : (
                  <span
                    style={{
                      position: 'absolute', top: 0, bottom: 0,
                      left: hasNegative ? (v >= 0 ? '50%' : `${50 - pct}%`) : 0,
                      width: `${pct}%`,
                      background: v >= 0 ? 'var(--e-pos)' : 'var(--e-neg)',
                      opacity: 0.65,
                    }}
                  />
                )}
              </div>
              <span className="sys-num" style={{ fontSize: 'var(--t-meta)' }}>
                {v === null ? <span className="sys-null">—</span> : v.toFixed(4)}
              </span>
            </div>
          )
        })}
      </div>
    </ChartFrame>
  )
}

/* ── scatter ───────────────────────────────────────────────────────────── */

export function Scatter({
  points, xLabel, yLabel, height = 220, title,
}: {
  points: { x: number; y: number; label?: string }[]
  xLabel?: string
  yLabel?: string
  height?: number
  title?: string
}) {
  const usable = points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))
  if (usable.length < 2) return <ChartFrame title={title} height={height} empty>{null}</ChartFrame>

  const [xlo, xhi] = extent(usable.map((p) => p.x))
  const [ylo, yhi] = extent(usable.map((p) => p.y))
  const W = 640
  const H = height
  const iw = W - PAD.left - PAD.right
  const ih = H - PAD.top - PAD.bottom
  const px = (v: number) => PAD.left + ((v - xlo) / (xhi - xlo)) * iw
  const py = (v: number) => PAD.top + ih - ((v - ylo) / (yhi - ylo)) * ih

  return (
    <ChartFrame title={title} unit={xLabel && yLabel ? `${xLabel} × ${yLabel}` : undefined}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="scatter" style={{ display: 'block' }}>
        {niceTicks(ylo, yhi, 4).map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={py(t)} y2={py(t)} stroke="var(--rule)" />
            <text x={PAD.left - 5} y={py(t) + 3} textAnchor="end" fontSize={9} fill="var(--ink-faint)" fontFamily="var(--font-mono)">{fmtTick(t)}</text>
          </g>
        ))}
        {xlo < 0 && xhi > 0 ? <line x1={px(0)} x2={px(0)} y1={PAD.top} y2={PAD.top + ih} stroke="var(--rule-strong)" /> : null}
        {ylo < 0 && yhi > 0 ? <line x1={PAD.left} x2={W - PAD.right} y1={py(0)} y2={py(0)} stroke="var(--rule-strong)" /> : null}
        {usable.map((p, i) => (
          <circle key={i} cx={px(p.x)} cy={py(p.y)} r={2.4} fill="var(--ink-muted)" opacity={0.72}>
            {p.label ? <title>{`${p.label}: ${p.x.toFixed(4)}, ${p.y.toFixed(4)}`}</title> : null}
          </circle>
        ))}
      </svg>
    </ChartFrame>
  )
}
