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

import Link from 'next/link'

import { Grid, Panel, Prose, StateBlock, Status, Strip, Value } from '@/components/system'
import { BarRows } from '@/components/system/charts'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'

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

/**
 * The handbook key for a reported metric.
 *
 * The report names a measure at a confidence level (`var_historical_95`) while
 * the methodology table keys the same entry without it. Mapping here rather
 * than guessing keeps the link honest: a measure with no handbook entry gets no
 * link instead of one that lands on nothing.
 */
const HANDBOOK_KEY: Record<string, string> = {
  var_historical_95: 'var_historical_95',
  var_historical_99: 'var_historical_99',
  var_parametric_95: 'var_parametric_95',
  cvar_historical_95: 'cvar_historical_95',
  cvar_historical_99: 'cvar_historical_99',
  entropic_var_95: 'entropic_var_95',
  entropic_drawdown_risk_95: 'entropic_drawdown_risk_95',
  drawdown_at_risk_95: 'drawdown_at_risk_95',
  conditional_drawdown_at_risk_95: 'conditional_drawdown_at_risk_95',
  volatility: 'volatility',
  downside_deviation: 'downside_deviation',
  mean_absolute_deviation: 'mean_absolute_deviation',
  gini_dispersion: 'gini_dispersion',
  semi_variance: 'semi_variance',
  max_drawdown: 'max_drawdown',
  average_drawdown: 'average_drawdown',
  ulcer_index: 'ulcer_index',
  ulcer_performance_index: 'ulcer_performance_index',
  sharpe: 'sharpe',
  sortino: 'sortino',
  calmar: 'calmar',
  omega: 'omega',
  worst_realization: 'worst_realization',
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
          const handbook = HANDBOOK_KEY[key]
          return (
            <tr key={key}>
              <td>
                {handbook ? (
                  <Link
                    href={`/terminal/handbook?measure=${encodeURIComponent(handbook)}`}
                    style={{ color: 'inherit' }}
                    title="How this is computed, and what makes it fail"
                  >
                    {label}
                  </Link>
                ) : label}
              </td>
              <td className="num">
                {/* Every measure here has a handbook entry, so every figure on
                    this page opens into its method and failure conditions. */}
                <Value
                  value={m.value}
                  digits={4}
                  unit={unitFor(m)}
                  measure={handbook}
                  inspect={{
                    measure: handbook,
                    label,
                    display: '',
                    unit: meth?.unit,
                    method: m.method,
                    status: 'recorded',
                    note: m.caveat ?? undefined,
                  }}
                  title={title || undefined}
                />
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
    return (
      <>
        <StripSkeleton items={7} />
        <Grid>
          {['Dispersion', 'Tail', 'Drawdown', 'Risk-adjusted'].map((g) => (
            <Panel key={g} title={g} state="waking" flush><TableSkeleton rows={5} columns={4} /></Panel>
          ))}
        </Grid>
      </>
    )
  }

  const metrics = data.risk?.metrics ?? {}
  const suppressed = Object.entries(metrics).filter(([, m]) => m.value === null)

  return (
    <>
      <ObjectHeader
        glyph="R"
        name="Risk"
        kind={data.model_id ? `${data.model_id} · ${data.target ?? ''}` : 'research book'}
        state={data.risk_contributions_unavailable ? 'blocked' : 'recorded'}
        detail={data.as_of ? `as of ${data.as_of}` : undefined}
        facts={[
          { label: 'Volatility', value: metrics.volatility?.value ?? null, digits: 3, unit: 'ann.', title: 'Annualised standard deviation of the book return series' , kind: 'volatility'},
          { label: 'CVaR 95', value: metrics.cvar_historical_95?.value ?? null, digits: 4, title: 'Mean loss beyond the empirical 95% quantile' , kind: 'magnitude'},
          { label: 'EVaR 95', value: metrics.entropic_var_95?.value ?? null, digits: 4, title: 'Entropic bound; at or above CVaR by construction' , kind: 'magnitude'},
          { label: 'Max DD', value: metrics.max_drawdown?.value ?? null, digits: 3, tone: true, title: 'Worst peak-to-trough decline on the wealth path' , kind: 'drawdown'},
          { label: 'Sharpe', value: metrics.sharpe?.value ?? null, digits: 2, signed: true, tone: true, title: 'Excess return per unit of volatility' , kind: 'sharpe'},
          { label: 'Measures', value: Object.keys(metrics).length, digits: 0 , kind: 'count'},
        ]}
      />

      <Strip metrics={[
        { label: 'Volatility', value: metrics.volatility?.value ?? null, digits: 4, unit: 'ann.', method: 'volatility' , kind: 'volatility'},
        { label: 'CVaR 95', value: metrics.cvar_historical_95?.value ?? null, digits: 4, method: 'cvar_historical_95' , kind: 'magnitude'},
        { label: 'EVaR 95', value: metrics.entropic_var_95?.value ?? null, digits: 4, method: 'entropic_var_95', title: 'Upper bound on VaR; at or above CVaR by construction' , kind: 'magnitude'},
        { label: 'Max drawdown', value: metrics.max_drawdown?.value ?? null, digits: 4, tone: true, method: 'max_drawdown' , kind: 'drawdown'},
        { label: 'Ulcer index', value: metrics.ulcer_index?.value ?? null, digits: 4, method: 'ulcer_index' , kind: 'magnitude'},
        { label: 'Sharpe', value: metrics.sharpe?.value ?? null, digits: 3, signed: true, tone: true, method: 'sharpe' , kind: 'sharpe'},
        { label: 'Omega', value: metrics.omega?.value ?? null, digits: 3, method: 'omega' , kind: 'ratio'},
      ]} />

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/covariance" className="sys-btn" style={{ textDecoration: 'none' }}>covariance</Link>
          <Link href="/terminal/book" className="sys-btn" style={{ textDecoration: 'none' }}>book</Link>
          <Link href="/terminal/performance" className="sys-btn" style={{ textDecoration: 'none' }}>path</Link>
          <Link href="/terminal/handbook" className="sys-btn" style={{ textDecoration: 'none' }}>handbook</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">
          {suppressed.length ? `${suppressed.length} measures suppressed` : `${Object.keys(metrics).length} measures reported`}
        </span>
      </Toolbar>

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
          <Prose>
            {data.risk.note}
          </Prose>
        </Panel>
      ) : null}

      <Grid>
        <Panel title="The tail, three ways" subtitle="ordered by construction">
          <BarRows
            unit="loss magnitude"
            rows={[
              { label: 'VaR 95', value: metrics.var_historical_95?.value ?? null, note: 'the empirical quantile' },
              { label: 'CVaR 95', value: metrics.cvar_historical_95?.value ?? null, note: 'the average beyond it' },
              { label: 'EVaR 95', value: metrics.entropic_var_95?.value ?? null, note: 'the tightest bound above that' },
              { label: 'Worst', value: metrics.worst_realization?.value ?? null, note: 'the single worst observed period' },
            ]}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            The first three rise by construction, so the gap between them is the
            information: a wide spread means the tail is heavier than a quantile
            alone can express.
          </p>
        </Panel>

        <Panel title="Drawdown, four ways" subtitle="depth against path">
          <BarRows
            unit="loss magnitude"
            rows={[
              { label: 'Max DD', value: Math.abs(metrics.max_drawdown?.value ?? Number.NaN) || null, note: 'the deepest single decline' },
              { label: 'Average DD', value: Math.abs(metrics.average_drawdown?.value ?? Number.NaN) || null, note: 'mean of the path, zeros included' },
              { label: 'Ulcer', value: metrics.ulcer_index?.value ?? null, note: 'root mean square of the path' },
              { label: 'CDaR 95', value: metrics.conditional_drawdown_at_risk_95?.value ?? null, note: 'mean beyond the 95th percentile' },
              { label: 'EDaR 95', value: metrics.entropic_drawdown_risk_95?.value ?? null, note: 'entropic bound on the path' },
            ]}
          />
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            A large gap between maximum and average drawdown says one decline
            dominates; a small gap says the book is underwater most of the time.
          </p>
        </Panel>

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
      </Grid>

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
