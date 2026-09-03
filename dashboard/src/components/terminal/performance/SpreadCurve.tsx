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
import Link from 'next/link'

import { BarRows, DrawdownChart, Histogram, TimeSeries } from '@/components/system/charts'
import { Grid, Panel, Prose, Section, StateBlock, Strip, Value } from '@/components/system'
import { ChartSkeleton, ObjectHeader, StripSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'

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

  // Cost as a share of the gross earned so far, walked forward. A single
  // total hides whether friction is eating a stable fraction or a growing one.
  const costShare = useMemo(() => {
    // Built by folding rather than by mutating accumulators, so the memo has no
    // state that could survive a render and drift.
    return periods.reduce<{ points: { x: string; y: number | null }[]; gross: number; cost: number }>(
      (acc, p) => {
        const gross = acc.gross + p.gross_period
        const cost = acc.cost + p.cost
        // Undefined until cumulative gross turns positive: a share of a loss is
        // not a cost share, it is the same sign error the backtest summary had.
        acc.points.push({ x: p.date, y: gross > 1e-9 ? cost / gross : null })
        return { points: acc.points, gross, cost }
      },
      { points: [], gross: 0, cost: 0 },
    ).points
  }, [periods])

  // Dispersion over one rebalance year, so a quiet stretch and a violent one
  // are distinguishable on a curve that only shows their sum.
  const rollingDispersion = useMemo(() => {
    const w = 52
    if (periods.length < w) return []
    return periods.map((p, i) => {
      if (i + 1 < w) return { x: p.date, y: null }
      const slice = periods.slice(i + 1 - w, i + 1).map((q) => q.net_period)
      const mean = slice.reduce((s, v) => s + v, 0) / w
      const variance = slice.reduce((s, v) => s + (v - mean) ** 2, 0) / (w - 1)
      return { x: p.date, y: Math.sqrt(variance) }
    })
  }, [periods])

  const byYear = useMemo(() => {
    const map = periods.reduce<Map<string, number>>((acc, p) => {
      const y = p.date.slice(0, 4)
      acc.set(y, (acc.get(y) ?? 0) + p.net_period)
      return acc
    }, new Map())
    return [...map.entries()].sort()
  }, [periods])

  if (error) {
    return <Panel title="Spread curve" state="unavailable"><StateBlock state="unavailable" title="The series could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!curve) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Cumulative spread" state="waking"><ChartSkeleton height={230} /></Panel>
      </>
    )
  }
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
        <Prose tone="strong">
          {String(curve.assumptions?.not_a_return_series ?? '')}
        </Prose>
      </Panel>

      <ObjectHeader
        glyph="∿"
        name="Performance"
        kind="quantile spread in rank points"
        state="experimental"
        detail={`${curve.model_id} · ${curve.target}`}
        facts={[
          { label: 'Periods', value: s.periods ?? null, digits: 0 , kind: 'count'},
          { label: 'Net cumulative', value: s.net_cumulative ?? null, digits: 2, unit: 'rp', signed: true, tone: true },
          { label: 'Cost paid', value: s.total_cost ?? null, digits: 3, unit: 'rp' },
          { label: 'Turnover', value: s.mean_turnover ?? null, digits: 3 , kind: 'multiple'},
          { label: 'Max DD', value: s.net_max_drawdown_rank_points ?? null, digits: 2, unit: 'rp', tone: true , kind: 'drawdown'},
        ]}
      />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/evidence" className="sys-btn" style={{ textDecoration: 'none' }}>evidence</Link>
          <Link href="/terminal/experiments" className="sys-btn" style={{ textDecoration: 'none' }}>experiment</Link>
          <Link href="/terminal/risk" className="sys-btn" style={{ textDecoration: 'none' }}>risk</Link>
          <Link href="/terminal/handbook" className="sys-btn" style={{ textDecoration: 'none' }}>handbook</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">rank points, not returns</span>
      </Toolbar>

      <Strip metrics={[
        { label: 'Periods', value: s.periods ?? null, digits: 0 , kind: 'count'},
        { label: 'Gross cumulative', value: s.gross_cumulative ?? null, digits: 3, unit: 'rank pts', signed: true },
        { label: 'Net cumulative', value: s.net_cumulative ?? null, digits: 3, unit: 'rank pts', signed: true, tone: true },
        { label: 'Cost paid', value: s.total_cost ?? null, digits: 4, unit: 'rank pts' },
        { label: 'Mean turnover', value: s.mean_turnover ?? null, digits: 4, title: 'One-way. Costs are charged on the round-trip figure, which is twice this.' , kind: 'multiple'},
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

      <Grid>
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
      </Grid>

      <Grid>
        <Panel title="Cost share of gross" subtitle="cumulative, walked forward">
          <TimeSeries
            series={[{ name: 'cost share', points: costShare, color: 'var(--e-neg)' }]}
            unit="cumulative cost over cumulative gross"
            method="both accumulated additively in rank points"
            height={160}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            A single total hides whether friction is eating a stable fraction of
            the edge or a growing one. It is undefined wherever cumulative gross
            has not yet turned positive, and it is left blank there rather than
            plotted against a negative denominator.
          </p>
        </Panel>

        <Panel title="Rolling dispersion" subtitle="52 rebalances">
          {rollingDispersion.length ? (
            <>
              <TimeSeries
                series={[{ name: 'dispersion', points: rollingDispersion, color: 'var(--ink)' }]}
                unit="standard deviation of the per-period spread"
                height={160}
              />
              <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                A cumulative curve shows the sum and not the ride. Two stretches
                reaching the same level through very different volatility look
                identical above and are separated here.
              </p>
            </>
          ) : (
            <StateBlock state="unavailable" title="Too few periods for a rolling window" detail="Fewer than 52 rebalances are recorded, so no window is drawn." />
          )}
        </Panel>

        <Panel title="By year" subtitle="net spread accumulated per calendar year">
          <BarRows
            unit="rank points"
            rows={byYear.map(([year, value]) => ({ label: year, value }))}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            The first and last years are usually partial. They are shown as
            recorded rather than annualised, since scaling a partial year to a
            full one invents observations that were never made.
          </p>
        </Panel>
      </Grid>

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
            <Prose>
              Whether the signal separates the top quantile from the bottom, and
              whether that separation survives the friction of rebalancing. It is
              a diagnostic of the signal, not a statement about money.
            </Prose>
            <Prose size="tight">
              Every Sharpe, return and cost figure quoted as evidence elsewhere in
              the product comes from the artifact&apos;s costed backtest, not from
              this curve.
            </Prose>
          </Section>
        </div>
      </Panel>
    </>
  )
}
