'use client'

/* Recharts-based validation charts — code-split behind next/dynamic so the
   charting bundle loads only on the Validation page. Split into two named
   exports (rather than one combined component) so each chart can sit in its
   own narrative section — the equity curve belongs with Historical
   Performance, rolling IC belongs with Prediction Quality. */

import { useState } from 'react'
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
import type { BacktestData } from '@/lib/backtest'

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
  // Which series are drawn. Both start on; the benchmark is the whole point
  // of the chart, and hiding it by default would flatter the strategy.
  const [show, setShow] = useState({ strategy: true, buy_hold: true })
  const toggle = (key: 'strategy' | 'buy_hold') =>
    setShow((current) => {
      const next = { ...current, [key]: !current[key] }
      // Never allow an empty chart — the last visible series stays on.
      return next.strategy || next.buy_hold ? next : current
    })

  return (
    <section aria-label="Equity curve" className="panel" style={{ padding: '16px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <h3 className="h-panel" style={{ marginBottom: 4 }}>Growth of $1 — signal vs buy &amp; hold</h3>
        {/* A legend that does something. Two lines on one axis with similar
            shapes are hard to separate by eye; isolating one answers "what
            did the strategy actually do" without a second chart. Checkbox
            semantics so it is operable and announced as a toggle. */}
        <div className="chart-legend" role="group" aria-label="Series shown">
          {([['strategy', 'Strategy', 'var(--accent)'], ['buy_hold', 'Buy & hold', 'var(--faint)']] as const).map(
            ([key, text, colour]) => (
              <button
                key={key}
                type="button"
                role="checkbox"
                aria-checked={show[key]}
                className={`chart-legend__item${show[key] ? '' : ' is-off'}`}
                onClick={() => toggle(key)}
              >
                <span className="chart-legend__swatch" style={{ background: colour }} aria-hidden />
                {text}
              </button>
            ),
          )}
        </div>
      </div>
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
          {show.strategy && (
            <Line type="monotone" dataKey="strategy" name="strategy" stroke="var(--accent)"
                  strokeWidth={1.6} dot={false} />
          )}
          {show.buy_hold && (
            <Line type="monotone" dataKey="buy_hold" name="buy & hold" stroke="var(--faint)"
                  strokeWidth={1.2} dot={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}

/** Windows offered over the rolling-IC series, as counts of signals rather
 *  than calendar spans — the series is one point per weekly signal, so a
 *  "3 month" label would be an approximation the data does not support. */
export const IC_WINDOWS = [
  { id: 'all', label: 'All', keep: Number.POSITIVE_INFINITY },
  { id: 'last26', label: 'Last 26', keep: 26 },
  { id: 'last12', label: 'Last 12', keep: 12 },
] as const

export type IcWindow = (typeof IC_WINDOWS)[number]['id']

/** Trailing slice of the series. Always the most recent points: the question
 *  a shorter window answers is "is it working *now*", so dropping from the
 *  front is the only correct direction. */
export function sliceIc<T>(series: T[], window: IcWindow): T[] {
  const spec = IC_WINDOWS.find((w) => w.id === window) ?? IC_WINDOWS[0]
  if (!Number.isFinite(spec.keep) || series.length <= spec.keep) return series
  return series.slice(series.length - spec.keep)
}

export function RollingIcChart({ data }: { data: BacktestData }) {
  const [window, setWindow] = useState<IcWindow>('all')
  const series = sliceIc(data.rolling_ic, window)
  return (
    <section aria-label="Rolling information coefficient" className="panel" style={{ padding: '16px 20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <h3 className="h-panel" style={{ marginBottom: 4 }}>Rolling IC (26 signals ≈ 6 months)</h3>
        {/* Narrowing the window is how you separate "this never worked" from
            "this stopped working" — the two readings the full series blends
            together. Counts, not dates, because the series is per-signal. */}
        <span className="u-note" style={{ marginLeft: 'auto', marginRight: 6 }}>Window</span>
        <div className="seg" role="group" aria-label="Rolling IC window">
          {IC_WINDOWS.map((w) => (
            <button
              key={w.id}
              type="button"
              className="seg__btn num"
              aria-pressed={window === w.id}
              disabled={Number.isFinite(w.keep) && data.rolling_ic.length <= w.keep}
              onClick={() => setWindow(w.id)}
              style={{ fontSize: '0.75rem' }}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
      <p style={{ fontSize: '0.6875rem', color: 'var(--faint)', marginBottom: 10, lineHeight: 1.6 }}>
        Signal quality over time. IC decays and revives with market regime — sustained
        readings above zero matter more than the average.
        {series.length !== data.rolling_ic.length && (
          <> Showing the most recent {series.length} of {data.rolling_ic.length} signals.</>
        )}
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
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
