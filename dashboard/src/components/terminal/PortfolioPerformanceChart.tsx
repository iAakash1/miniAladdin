'use client'

/**
 * Portfolio value over time, against what it cost.
 *
 * ## What is plotted, and what it is not
 *
 * Each point is `Σ shares × that day's real close`, summed across the
 * holdings the provider returned a series for. The closes are the same ones
 * the price chart on a company report draws — no separate market-data path,
 * no synthesised points, no interpolation across gaps.
 *
 * What this is **not** is a track record. It holds *today's* share counts
 * fixed across the whole window, so a position opened last week appears at
 * full size a month ago. That makes it an honest answer to "what would this
 * book have been worth" and a dishonest answer to "what did I make", and the
 * distinction is printed under the chart rather than left in a comment —
 * a curve labelled "portfolio performance" that quietly meant the other
 * thing would be the most misleading element on the page.
 *
 * ## Why an area against a baseline rather than a line
 *
 * The question a holder has is not "what shape did this trace" but "am I
 * above or below what I paid". A flat reference line at cost turns that into
 * a spatial fact — the fill sits above or below it — which is readable
 * before any axis label is. The fill is tinted by the *current* standing so
 * the whole chart reads green or red at a glance, and the crossing point is
 * where the book moved from loss to profit.
 */

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { fmtDate } from '@/lib/format'
import type { PortfolioBenchmark, PortfolioCurve } from '@/lib/persistence'

interface Point {
  date: string
  value: number
  dateLabel: string
  /** Signed gain against cost at that point — carried into the tooltip so it
   *  is read off the same object that positioned the mark. */
  delta: number
}

function money(value: number, currency: string): string {
  // Intl gives the right symbol and grouping for the code the server sent,
  // so nothing here hardcodes a currency the product may not be denominated
  // in. Fractions are dropped: a portfolio axis in cents is noise.
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(value)
  } catch {
    return `${Math.round(value).toLocaleString()}`
  }
}

function moneyExact(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  } catch {
    return value.toFixed(2)
  }
}

/** Portfolio against a benchmark, both rebased to 100 at the first shared
 *  session.
 *
 *  Rebasing is not cosmetic. The two series live on incomparable scales, and
 *  rebasing each to *its own* first date rather than to a shared one would
 *  compare different windows and manufacture outperformance out of a
 *  calendar mismatch — which is why the shared start comes from the server,
 *  computed on the intersection of the two date axes. */
function RebasedChart({ benchmark }: { benchmark: PortfolioBenchmark }) {
  const data = benchmark.points.map((p) => ({ ...p, dateLabel: fmtDate(p.date) }))
  const ahead = benchmark.outperformance_pct >= 0
  const values = data.flatMap((d) => [d.portfolio, d.benchmark])
  const low = Math.min(...values)
  const high = Math.max(...values)
  const pad = (high - low || 1) * 0.08

  return (
    <div className="pfchart">
      <div className="pfchart__frame">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="dateLabel" tick={{ fill: 'var(--faint)', fontSize: 10 }}
                   tickLine={false} axisLine={{ stroke: 'var(--line)' }} minTickGap={44} />
            <YAxis domain={[low - pad, high + pad]} width={44}
                   tick={{ fill: 'var(--faint)', fontSize: 10 }} tickLine={false} axisLine={false}
                   tickFormatter={(v: number) => v.toFixed(0)} />
            <Tooltip content={<RebasedTooltip label={benchmark.label} />}
                     cursor={{ stroke: 'var(--line-strong)', strokeWidth: 1 }} />
            {/* 100 is the shared starting point, so the reference line is
                literally "where both began". */}
            <ReferenceLine y={100} stroke="var(--muted)" strokeDasharray="4 4" />
            {/* The benchmark is drawn first and unfilled: it is the yardstick,
                not the subject, and a filled index would compete with the
                portfolio for the eye. */}
            <Area type="monotone" dataKey="benchmark" stroke="var(--muted)" strokeWidth={1.25}
                  fill="none" strokeDasharray="3 3" dot={false} isAnimationActive={false} />
            <Area type="monotone" dataKey="portfolio"
                  stroke={ahead ? 'var(--pos)' : 'var(--neg)'} strokeWidth={1.75}
                  fill="none" dot={false} isAnimationActive={false}
                  activeDot={{ r: 3, fill: ahead ? 'var(--pos)' : 'var(--neg)',
                               stroke: 'var(--surface)', strokeWidth: 2 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="pfchart__note">
        Both rebased to 100 on {fmtDate(benchmark.from)} · {benchmark.sessions} shared sessions.
        Portfolio {benchmark.portfolio_return_pct >= 0 ? '+' : '−'}
        {Math.abs(benchmark.portfolio_return_pct).toFixed(2)}% vs {benchmark.label}{' '}
        {benchmark.benchmark_return_pct >= 0 ? '+' : '−'}
        {Math.abs(benchmark.benchmark_return_pct).toFixed(2)}%. {benchmark.basis}.
      </p>
    </div>
  )
}

function RebasedTooltip({
  active, payload, label,
}: {
  active?: boolean
  payload?: Array<{ payload: { dateLabel: string; portfolio: number; benchmark: number } }>
  label: string
}) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  const gap = p.portfolio - p.benchmark
  return (
    <div className="pfchart__tip">
      <div className="pfchart__tip-date">{p.dateLabel}</div>
      <div className="num pfchart__tip-value">Portfolio {p.portfolio.toFixed(1)}</div>
      <div className="num pfchart__tip-delta" style={{ color: 'var(--muted)' }}>
        {label} {p.benchmark.toFixed(1)}
      </div>
      <div className="num pfchart__tip-delta"
           style={{ color: gap >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
        {gap >= 0 ? '+' : '−'}{Math.abs(gap).toFixed(1)} pts
      </div>
    </div>
  )
}

function ChartTooltip({
  active,
  payload,
  currency,
}: {
  active?: boolean
  payload?: Array<{ payload: Point }>
  currency: string
}) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  const tone = point.delta > 0 ? 'var(--pos)' : point.delta < 0 ? 'var(--neg)' : 'var(--muted)'
  return (
    <div className="pfchart__tip">
      <div className="pfchart__tip-date">{point.dateLabel}</div>
      <div className="num pfchart__tip-value">{moneyExact(point.value, currency)}</div>
      <div className="num pfchart__tip-delta" style={{ color: tone }}>
        {point.delta >= 0 ? '+' : '−'}
        {moneyExact(Math.abs(point.delta), currency)} vs cost
      </div>
    </div>
  )
}

export default function PortfolioPerformanceChart({
  curve,
  currency,
  benchmark,
}: {
  curve: PortfolioCurve
  currency: string
  /** When present the chart switches to a rebased comparison: both series
   *  start at 100 on the first shared session, because a portfolio worth
   *  $52k and an index at 6,300 cannot share a money axis. */
  benchmark?: PortfolioBenchmark | null
}) {
  const baseline = curve.invested_baseline
  const data: Point[] = curve.points.map((p) => ({
    ...p,
    dateLabel: fmtDate(p.date),
    delta: p.value - baseline,
  }))

  if (benchmark && benchmark.points.length > 1) {
    return <RebasedChart benchmark={benchmark} />
  }

  const last = data[data.length - 1]
  const up = last.delta >= 0
  const stroke = up ? 'var(--pos)' : 'var(--neg)'

  // The domain is padded around *both* the series and the cost line, so the
  // baseline is always on screen. Without it, a book far above cost would
  // push the reference line off the axis and the chart would lose the one
  // comparison it exists to make.
  const values = data.map((d) => d.value).concat(baseline)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const pad = (high - low || Math.abs(high) || 1) * 0.08

  return (
    <div className="pfchart">
      <div className="pfchart__frame">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
            <defs>
              {/* Two gradients, one per direction, rather than one recoloured:
                  a fill that changes hue mid-transition reads as a glitch. */}
              <linearGradient id="pf-fill-up" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--pos)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--pos)" stopOpacity={0.02} />
              </linearGradient>
              <linearGradient id="pf-fill-down" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--neg)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--neg)" stopOpacity={0.02} />
              </linearGradient>
            </defs>

            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="dateLabel"
              tick={{ fill: 'var(--faint)', fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: 'var(--line)' }}
              minTickGap={44}
            />
            <YAxis
              domain={[low - pad, high + pad]}
              tick={{ fill: 'var(--faint)', fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={62}
              tickFormatter={(v: number) => money(v, currency)}
            />
            <Tooltip
              content={<ChartTooltip currency={currency} />}
              cursor={{ stroke: 'var(--line-strong)', strokeWidth: 1 }}
            />
            {/* Cost. The whole chart is a comparison against this line. */}
            <ReferenceLine
              y={baseline}
              stroke="var(--muted)"
              strokeDasharray="4 4"
              label={{
                value: 'cost',
                position: 'insideTopLeft',
                fill: 'var(--faint)',
                fontSize: 10,
              }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={stroke}
              strokeWidth={1.75}
              fill={up ? 'url(#pf-fill-up)' : 'url(#pf-fill-down)'}
              // A dot per day turns a 60-session window into a beaded line;
              // the hover dot is what a reader actually needs.
              dot={false}
              activeDot={{ r: 3, fill: stroke, stroke: 'var(--surface)', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* The window's meaning, from the payload rather than restated here —
          the backend owns that sentence so it cannot drift from the maths. */}
      <p className="pfchart__note">
        {curve.points.length} sessions · {curve.tickers.length} holding
        {curve.tickers.length === 1 ? '' : 's'} plotted. {curve.assumption}
        {curve.excluded_tickers.length > 0 && (
          <> Excluded for want of price history: {curve.excluded_tickers.join(', ')}.</>
        )}
      </p>
    </div>
  )
}
