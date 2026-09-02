/**
 * Risk workbench.
 *
 * Risk was reachable only from inside the portfolio page, which makes it look
 * like a property of a particular book rather than the question it actually is.
 * It gets its own workspace here.
 *
 * The grouping is the point. Measures are shown beside the ones that answer the
 * same question with different assumptions, so the reader can see the spread
 * between them rather than picking whichever single number is at hand:
 *
 *   VaR  <=  CVaR  <=  EVaR      a quantile, its tail average, and its bound
 *   MaxDD, AvgDD, Ulcer, EDaR    depth, typical depth, path, and tail of path
 *   sigma, downside, MAD, Gini   dispersion under four different assumptions
 *
 * Every value carries the unit the engine declares. Nothing is re-derived here;
 * a workspace that recomputes a metric is a second implementation waiting to
 * disagree with the first.
 */
'use client'

import { useEffect, useState } from 'react'

import { Panel, StateBlock, Status, Strip, Value } from '@/components/system'

interface Metric {
  value: number | null
  method: string
  observations: number
  caveat: string | null
  methodology?: {
    unit?: string
    annualisation?: string
    frequency?: string
    periods_per_year?: number
    inputs?: string[]
  }
}

interface RiskReport {
  metrics: Record<string, Metric>
  distribution?: Record<string, unknown>
  drawdown_profile?: Record<string, unknown>
  note?: string | null
}

interface PortfolioPayload {
  status: string
  as_of?: string
  method?: string
  model_id?: string
  target?: string
  risk?: RiskReport
  risk_contributions_unavailable?: string | null
  weights?: { symbol: string; weight: number; side: string; risk_share: number | null }[]
}

/** Groups follow the question each family answers, not the source module. */
const GROUPS: { title: string; note: string; keys: [string, string][] }[] = [
  {
    title: 'Dispersion',
    note: 'Four answers to "how much does it move", under four different assumptions about shape.',
    keys: [
      ['volatility', 'Volatility'],
      ['downside_deviation', 'Downside deviation'],
      ['mean_absolute_deviation', 'Mean absolute deviation'],
      ['gini_dispersion', 'Gini mean difference'],
      ['semi_variance', 'Semi-variance'],
    ],
  },
  {
    title: 'Tail',
    note: 'A quantile, the average beyond it, and the tightest bound above that. They are ordered by construction: VaR ≤ CVaR ≤ EVaR.',
    keys: [
      ['var_historical_95', 'VaR 95 (historical)'],
      ['var_parametric_95', 'VaR 95 (parametric)'],
      ['cvar_historical_95', 'CVaR 95'],
      ['entropic_var_95', 'EVaR 95'],
      ['var_historical_99', 'VaR 99'],
      ['cvar_historical_99', 'CVaR 99'],
      ['worst_realization', 'Worst realization'],
    ],
  },
  {
    title: 'Drawdown',
    note: 'Depth alone cannot separate a brief plunge from a long grind to the same trough. The path measures do.',
    keys: [
      ['max_drawdown', 'Maximum drawdown'],
      ['average_drawdown', 'Average drawdown'],
      ['ulcer_index', 'Ulcer index'],
      ['drawdown_at_risk_95', 'Drawdown at risk 95'],
      ['conditional_drawdown_at_risk_95', 'Conditional DaR 95'],
      ['entropic_drawdown_risk_95', 'Entropic DaR 95'],
    ],
  },
  {
    title: 'Risk-adjusted',
    note: 'Each divides return by a different notion of risk, so they disagree — and the disagreement is the information.',
    keys: [
      ['sharpe', 'Sharpe'],
      ['sortino', 'Sortino'],
      ['calmar', 'Calmar'],
      ['ulcer_performance_index', 'Ulcer performance index'],
      ['omega', 'Omega'],
    ],
  },
]

function unitFor(m: Metric | undefined): string | undefined {
  const u = m?.methodology?.unit
  if (!u) return undefined
  if (u === 'annualised_volatility') return 'ann.'
  if (u === 'ratio') return undefined
  return undefined
}

function MetricTable({ keys, metrics }: { keys: [string, string][]; metrics: Record<string, Metric> }) {
  return (
    <table className="sys-table sys-table--compact">
      <thead>
        <tr>
          <th scope="col">Measure</th>
          <th scope="col" className="num">Value</th>
          <th scope="col">Method</th>
          <th scope="col" className="num">Obs</th>
        </tr>
      </thead>
      <tbody>
        {keys.map(([key, label]) => {
          const m = metrics[key]
          if (!m) {
            return (
              <tr key={key}>
                <td>{label}</td>
                <td className="num"><span className="sys-null">—</span></td>
                <td><Status state="unavailable" label="not reported" /></td>
                <td className="num"><span className="sys-null">—</span></td>
              </tr>
            )
          }
          const meth = m.methodology
          const title = [
            meth?.unit ? `unit: ${meth.unit}` : null,
            meth?.annualisation ? `annualisation: ${meth.annualisation}` : null,
            meth?.frequency ? `frequency: ${meth.frequency}` : null,
            m.caveat,
          ].filter(Boolean).join(' · ')
          return (
            <tr key={key}>
              <td>{label}</td>
              <td className="num">
                <Value value={m.value} digits={4} unit={unitFor(m)} title={title || undefined} />
              </td>
              <td>
                <span className="sys-meta" style={{ color: 'var(--ink)' }} title={m.caveat ?? undefined}>
                  {m.method}
                </span>
              </td>
              <td className="num"><Value value={m.observations} digits={0} /></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default function RiskWorkbench() {
  const [data, setData] = useState<PortfolioPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/portfolio')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`portfolio ${r.status}`))))
      .then((d: PortfolioPayload) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  if (error) {
    return (
      <Panel title="Risk" state="unavailable">
        <StateBlock
          state="unavailable"
          title="No risk report is available"
          detail={`The request failed with: ${error}. Nothing is shown in its place — a report that could not be computed is not a report of zero risk.`}
        />
      </Panel>
    )
  }
  if (!data) {
    return <Panel title="Risk" state="waking"><StateBlock state="waking" title="Computing the risk report" /></Panel>
  }

  const metrics = data.risk?.metrics ?? {}
  const suppressed = Object.entries(metrics).filter(([, m]) => m.value === null)

  return (
    <>
      <Strip metrics={[
        { label: 'Volatility', value: metrics.volatility?.value ?? null, digits: 4, unit: 'ann.' },
        { label: 'CVaR 95', value: metrics.cvar_historical_95?.value ?? null, digits: 4 },
        { label: 'EVaR 95', value: metrics.entropic_var_95?.value ?? null, digits: 4, title: 'Upper bound on VaR; at or above CVaR by construction' },
        { label: 'Max drawdown', value: metrics.max_drawdown?.value ?? null, digits: 4, tone: true },
        { label: 'Ulcer index', value: metrics.ulcer_index?.value ?? null, digits: 4 },
        { label: 'Sharpe', value: metrics.sharpe?.value ?? null, digits: 3, signed: true, tone: true },
        { label: 'Omega', value: metrics.omega?.value ?? null, digits: 3 },
      ]} />

      {data.risk_contributions_unavailable ? (
        <Panel title="Risk decomposition" state="unavailable">
          <StateBlock
            state="unavailable"
            title="Contributions cannot be computed for this book"
            detail={data.risk_contributions_unavailable}
          />
        </Panel>
      ) : null}

      {data.risk?.note ? (
        <Panel title="Note">
          <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
            {data.risk.note}
          </p>
        </Panel>
      ) : null}

      <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
        {GROUPS.map((g) => (
          <Panel key={g.title} title={g.title} flush>
            <p style={{
              margin: 0, padding: 'var(--d-2) var(--d-3)',
              fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)',
              color: 'var(--ink-muted)', borderBottom: '1px solid var(--rule)',
            }}>{g.note}</p>
            <MetricTable keys={g.keys} metrics={metrics} />
          </Panel>
        ))}
      </div>

      {suppressed.length ? (
        <Panel title="Not reported" subtitle={`${suppressed.length} measures`}>
          <p style={{ margin: '0 0 var(--d-2)', fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '80ch' }}>
            These were suppressed rather than computed. A measure that presupposes
            a return scale is not applied to a series in rank units, and a measure
            with too few observations reports nothing rather than a number its
            sample cannot support.
          </p>
          <table className="sys-table sys-table--compact">
            <thead><tr><th>Measure</th><th>Reason</th></tr></thead>
            <tbody>
              {suppressed.map(([k, m]) => (
                <tr key={k}>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td>
                  <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{m.caveat ?? m.method}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}
    </>
  )
}
