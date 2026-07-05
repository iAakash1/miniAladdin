'use client'

/* Recharts-based validation charts — code-split behind next/dynamic so the
   charting bundle loads only on the Validation page. Split into two named
   exports (rather than one combined component) so each chart can sit in its
   own narrative section — the equity curve belongs with Historical
   Performance, rolling IC belongs with Prediction Quality. */

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { BacktestData } from './ValidationView'

const AXIS_TICK = { fill: 'var(--faint)', fontSize: 10, fontFamily: 'var(--font-mono)' }

interface TooltipRow {
  name: string
  value: number
  color?: string
}

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipRow[]; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--line-strong)',
      borderRadius: 'var(--r-md)', padding: '8px 12px', fontSize: '0.75rem',
      boxShadow: 'var(--shadow-2)',
    }}>
      <div style={{ color: 'var(--faint)', marginBottom: 3 }}>{label}</div>
      {payload.map((row) => (
        <div key={row.name} className="num" style={{ color: row.color ?? 'var(--text)' }}>
          {row.name}: {typeof row.value === 'number' ? row.value.toFixed(3) : row.value}
        </div>
      ))}
    </div>
  )
}

export function EquityCurveChart({ data }: { data: BacktestData }) {
  return (
    <section aria-label="Equity curve" className="panel" style={{ padding: '16px 20px' }}>
      <h3 className="h-panel" style={{ marginBottom: 4 }}>Growth of $1 — signal vs buy &amp; hold</h3>
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 10, lineHeight: 1.6 }}>
        The long/flat strategy holds only when the composite score clears +0.15. Tracking below
        buy &amp; hold with lower drawdown is the expected profile of a dampening signal.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.equity_curve} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey="date" tick={AXIS_TICK} axisLine={false} tickLine={false} minTickGap={64} />
          <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={44}
                 domain={['auto', 'auto']} tickFormatter={(value: number) => value.toFixed(1)} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--line-strong)', strokeWidth: 1 }} />
          <ReferenceLine y={1} stroke="var(--line-strong)" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="strategy" name="strategy" stroke="var(--accent)"
                strokeWidth={1.6} dot={false} />
          <Line type="monotone" dataKey="buy_hold" name="buy & hold" stroke="var(--faint)"
                strokeWidth={1.2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}

export function RollingIcChart({ data }: { data: BacktestData }) {
  return (
    <section aria-label="Rolling information coefficient" className="panel" style={{ padding: '16px 20px' }}>
      <h3 className="h-panel" style={{ marginBottom: 4 }}>Rolling IC (26 signals ≈ 6 months)</h3>
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 10, lineHeight: 1.6 }}>
        Signal quality over time. IC decays and revives with market regime — sustained
        readings above zero matter more than the average.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data.rolling_ic} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--line)" vertical={false} />
          <XAxis dataKey="date" tick={AXIS_TICK} axisLine={false} tickLine={false} minTickGap={64} />
          <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} width={44} domain={[-1, 1]} />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'var(--line-strong)', strokeWidth: 1 }} />
          <ReferenceLine y={0} stroke="var(--line-strong)" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="ic" name="rolling IC" stroke="var(--pos)"
                strokeWidth={1.6} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}
