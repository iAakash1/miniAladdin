/**
 * Quantile spread curve.
 *
 * The most dangerous chart in the product, and the reason its labelling is
 * heavier than anything else here: it looks exactly like an equity curve and
 * is not one. `fwd_rank_21` is a cross-sectional rank in [-1, 1], so this
 * accumulates rank spread additively. Reading 11.30 as "up 1,130%" is the
 * mistake the surface exists to prevent — compounding a rank once produced a
 * +6,553% curve in this repository's own history.
 *
 * So the unit is stated on the axis, in the header, on every summary figure and
 * in a standing note, and the word "return" appears nowhere near it.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { DrawdownChart, Histogram, TimeSeries } from '@/components/system/charts'
import { Panel, Section, StateBlock, Strip, Value } from '@/components/system'

interface Period {
  date: string
  gross_period: number
  net_period: number
  turnover: number
  cost: number
  gross_cumulative: number
  net_cumulative: number
  names: number
  net_drawdown: number
  gross_drawdown: number
}

interface Curve {
  status?: string
  model_id?: string
  target?: string
  periods?: Period[]
  summary?: Record<string, number>
  units?: string
  assumptions?: Record<string, unknown>
  detail?: string
}

type Window = '1y' | '3y' | 'all'

export default function SpreadCurve({ experiment, model }: { experiment: string; model: string }) {
  const [curve, setCurve] = useState<Curve | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [window_, setWindow] = useState<Window>('all')
  const [showGross, setShowGross] = useState(true)

  useEffect(() => {
    let alive = true
    fetch(`/api/quant/experiments/${encodeURIComponent(experiment)}/series/${encodeURIComponent(model)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Curve) => { if (alive) setCurve(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [experiment, model])

  const periods = useMemo(() => {
    const all = curve?.periods ?? []
    if (window_ === 'all' || !all.length) return all
    // The series is one observation per rebalance, not per session, so a
    // window is counted in observations rather than assumed to be daily.
    const perYear = 52
    const take = window_ === '1y' ? perYear : perYear * 3
    return all.slice(-take)
  }, [curve, window_])

  if (error) {
    return <Panel title="Spread curve" state="unavailable"><StateBlock state="unavailable" title="The series could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!curve) return <Panel title="Spread curve" state="waking"><StateBlock state="waking" title="Reading the series" /></Panel>
  if (curve.status !== 'ok' || !periods.length) {
    return <Panel title="Spread curve" state="unavailable"><StateBlock state="unavailable" title="No series is recorded" detail={curve.detail} /></Panel>
  }

  const s = curve.summary ?? {}
  const unit = curve.units ?? 'rank points'

  const cumulative = [
    { name: 'net', points: periods.map((p) => ({ x: p.date, y: p.net_cumulative })), color: 'var(--ink)' },
    ...(showGross
      ? [{ name: 'gross', points: periods.map((p) => ({ x: p.date, y: p.gross_cumulative })), color: 'var(--ink-faint)', dashed: true }]
      : []),
  ]

  return (
    <>
      {/* The unit warning is a panel, not a footnote. */}
      <Panel title="This is not an equity curve" state="experimental">
        <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink)', maxWidth: '86ch' }}>
          {String(curve.assumptions?.not_a_return_series ?? '')}
        </p>
      </Panel>

      <Strip metrics={[
        { label: 'Periods', value: s.periods ?? null, digits: 0 },
        { label: 'Gross cumulative', value: s.gross_cumulative ?? null, digits: 3, unit: 'rank pts', signed: true },
        { label: 'Net cumulative', value: s.net_cumulative ?? null, digits: 3, unit: 'rank pts', signed: true, tone: true },
        { label: 'Cost paid', value: s.total_cost ?? null, digits: 4, unit: 'rank pts' },
        { label: 'Mean turnover', value: s.mean_turnover ?? null, digits: 4, title: 'One-way. Costs are charged on the round-trip figure, which is twice this.' },
        { label: 'Net max drawdown', value: s.net_max_drawdown_rank_points ?? null, digits: 3, unit: 'rank pts', tone: true },
      ]} />

      <Panel
        title="Cumulative spread"
        subtitle={`${curve.model_id} · ${curve.target}`}
        actions={
          <div style={{ display: 'flex', gap: 'var(--d-2)', alignItems: 'center' }}>
            <div className="sys-seg">
              {(['1y', '3y', 'all'] as Window[]).map((w) => (
                <button key={w} className="sys-btn" aria-pressed={window_ === w} onClick={() => setWindow(w)}>{w}</button>
              ))}
            </div>
            <button className="sys-btn" aria-pressed={showGross} onClick={() => setShowGross((v) => !v)}>gross</button>
          </div>
        }
      >
        <TimeSeries
          series={cumulative}
          unit={unit}
          method="additive accumulation of the top-minus-bottom quantile rank spread"
          zeroLine
          height={230}
        />
      </Panel>

      <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
        <Panel title="Drawdown" subtitle="on the net spread path">
          <DrawdownChart points={periods.map((p) => ({ x: p.date, y: p.net_drawdown }))} title="" />
        </Panel>

        <Panel title="Per-period spread">
          <Histogram
            values={periods.map((p) => p.net_period)}
            unit={unit}
            title=""
            marks={[{ at: 0, label: '0', color: 'var(--rule-focus)' }]}
          />
        </Panel>

        <Panel title="Turnover">
          <TimeSeries
            series={[{ name: 'turnover', points: periods.map((p) => ({ x: p.date, y: p.turnover })), color: 'var(--ink-muted)' }]}
            unit="one-way, per rebalance"
            method="sum|dw| / 2"
            height={150}
          />
        </Panel>

        <Panel title="Cost">
          <TimeSeries
            series={[{ name: 'cost', points: periods.map((p) => ({ x: p.date, y: p.cost })), color: 'var(--e-neg)' }]}
            unit="rank points per rebalance"
            height={150}
          />
        </Panel>
      </div>

      <Panel title="Assumptions" state="recorded">
        <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.4fr)' }}>
          <Section title="Execution">
            <table className="sys-table sys-table--compact">
              <tbody>
                {Object.entries(curve.assumptions ?? {})
                  .filter(([k, v]) => k !== 'not_a_return_series' && (typeof v === 'number' || typeof v === 'string'))
                  .map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ fontFamily: 'var(--font-mono)', width: '48%' }}>{k}</td>
                      <td className="num" style={{ textAlign: 'left', whiteSpace: 'normal' }}>
                        {typeof v === 'number' ? <Value value={v} digits={2} /> : <span className="sys-meta" style={{ color: 'var(--ink)' }}>{String(v)}</span>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Section>
          <Section title="What this curve is for">
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Whether the signal separates the top quantile from the bottom, and
              whether that separation survives the friction of rebalancing. It is
              a diagnostic of the signal, not a statement about money.
            </p>
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              Every Sharpe, return and cost figure quoted as evidence elsewhere in
              the product comes from the artifact&apos;s costed backtest, not from
              this curve.
            </p>
          </Section>
        </div>
      </Panel>
    </>
  )
}
