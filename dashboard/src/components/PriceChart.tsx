'use client'

import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'

interface PricePoint { date: string; close: number }
interface Props       { data: PricePoint[]; ticker: string }

function TooltipContent({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div
      style={{
        background: '#0a1628',
        border: '1px solid rgba(56,189,248,0.18)',
        borderRadius: 6,
        padding: '7px 12px',
      }}
    >
      <div style={{ fontSize: '0.62rem', color: '#4b6480', marginBottom: 2 }}>{label}</div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '0.85rem',
          fontWeight: 700,
          color: '#dde6f5',
        }}
      >
        ${payload[0].value.toFixed(2)}
      </div>
    </div>
  )
}

export default function PriceChart({ data, ticker }: Props) {
  if (!data?.length) return null

  const start     = data[0]?.close ?? 0
  const end       = data[data.length - 1]?.close ?? 0
  const positive  = end >= start
  const pct       = ((end - start) / start * 100).toFixed(2)
  const color     = positive ? '#10b981' : '#ef4444'
  const gradId    = `grad-${ticker}`

  const formatted = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  const values  = data.map(d => d.close)
  const minY    = Math.floor(Math.min(...values) * 0.995)
  const maxY    = Math.ceil (Math.max(...values) * 1.005)

  return (
    <div className="card" style={{ padding: '20px 22px 10px' }}>
      {/* Header row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <div className="section-heading" style={{ marginBottom: 0 }}>
          <span>{ticker} · 3-Month Price</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '1.1rem',
              fontWeight: 700,
              color: 'var(--text)',
              letterSpacing: '-0.01em',
            }}
          >
            ${end.toFixed(2)}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.72rem',
              fontWeight: 600,
              color,
              background: positive ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
              border: `1px solid ${positive ? 'rgba(16,185,129,0.28)' : 'rgba(239,68,68,0.28)'}`,
              borderRadius: 4,
              padding: '2px 9px',
            }}
          >
            {positive ? '▲' : '▼'} {positive ? '+' : ''}{pct}%
          </span>
        </div>
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart
          data={formatted}
          margin={{ top: 4, right: 2, bottom: 0, left: -16 }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor={color} stopOpacity={0.28} />
              <stop offset="100%" stopColor={color} stopOpacity={0}    />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fill: '#4b6480', fontSize: 9, fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[minY, maxY]}
            tick={{ fill: '#4b6480', fontSize: 9, fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={v => `$${v}`}
          />
          <Tooltip content={<TooltipContent />} cursor={{ stroke: 'rgba(56,189,248,0.2)', strokeWidth: 1 }} />
          {/* Baseline */}
          <ReferenceLine
            y={start}
            stroke="rgba(255,255,255,0.08)"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradId})`}
            dot={false}
            activeDot={{ r: 3, fill: color, stroke: 'var(--bg-card)', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
