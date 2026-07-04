'use client'

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fmtPrice } from '@/lib/format'
import type { PricePoint } from '@/lib/types'

interface PriceChartProps {
  data: PricePoint[]
  ticker: string
  periodLabel: string
}

interface TooltipPayload {
  value: number
  dataKey: string
  payload: { dateLabel: string; close: number; volume: number }
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--line-strong)',
        borderRadius: 'var(--r-md)',
        padding: '8px 12px',
        fontSize: '0.75rem',
        boxShadow: 'var(--shadow-2)',
      }}
    >
      <div style={{ color: 'var(--faint)', marginBottom: 3 }}>{point.dateLabel}</div>
      <div className="num" style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text)' }}>
        {fmtPrice(point.close)}
      </div>
      {point.volume > 0 && (
        <div className="num" style={{ color: 'var(--muted)', marginTop: 2 }}>
          Vol {(point.volume / 1e6).toFixed(1)}M
        </div>
      )}
    </div>
  )
}

export default function PriceChart({ data, ticker, periodLabel }: PriceChartProps) {
  if (!data.length) return null

  const first = data[0].close
  const last = data[data.length - 1].close
  const positive = last >= first
  const changePct = ((last - first) / first) * 100
  const lineColor = positive ? 'var(--pos)' : 'var(--neg)'

  const points = data.map((d) => ({
    ...d,
    dateLabel: new Date(d.date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: data.length > 260 ? '2-digit' : undefined,
    }),
  }))

  const values = data.map((d) => d.close)
  const minY = Math.min(...values) * 0.99
  const maxY = Math.max(...values) * 1.01
  const maxVolume = Math.max(...data.map((d) => d.volume), 1)

  return (
    <figure
      role="img"
      aria-label={`${ticker} closing price over ${periodLabel}: ${positive ? 'up' : 'down'} ${Math.abs(changePct).toFixed(1)} percent, from ${fmtPrice(first)} to ${fmtPrice(last)}`}
      style={{ margin: 0 }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <span className="num" style={{ fontSize: '1.0625rem', fontWeight: 600 }}>
          {fmtPrice(last)}
        </span>
        <span
          className="num"
          style={{ fontSize: '0.8125rem', fontWeight: 500, color: lineColor }}
        >
          {positive ? '+' : ''}
          {changePct.toFixed(2)}% · {periodLabel}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`fill-${ticker}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lineColor} stopOpacity={0.18} />
              <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="var(--line)" vertical={false} />

          <XAxis
            dataKey="dateLabel"
            tick={{ fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={48}
          />
          <YAxis
            yAxisId="price"
            domain={[minY, maxY]}
            tick={{ fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
            width={54}
            tickFormatter={(v: number) => `$${v >= 1000 ? v.toFixed(0) : v.toFixed(v < 10 ? 2 : 0)}`}
          />
          {/* Volume on a hidden axis, kept to the lower fifth of the plot */}
          <YAxis yAxisId="volume" domain={[0, maxVolume * 5]} hide />

          <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--line-strong)', strokeWidth: 1 }} />

          <Bar yAxisId="volume" dataKey="volume" fill="var(--ink-3)" opacity={0.28} barSize={3} />

          <ReferenceLine
            yAxisId="price"
            y={first}
            stroke="var(--line-strong)"
            strokeDasharray="4 4"
            strokeWidth={1}
          />

          <Area
            yAxisId="price"
            type="monotone"
            dataKey="close"
            stroke={lineColor}
            strokeWidth={1.6}
            fill={`url(#fill-${ticker})`}
            dot={false}
            activeDot={{ r: 3, fill: lineColor, stroke: 'var(--surface)', strokeWidth: 2 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </figure>
  )
}
