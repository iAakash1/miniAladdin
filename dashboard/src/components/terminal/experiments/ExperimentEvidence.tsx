/**
 * The evidence an experiment recorded beyond its leaderboard.
 *
 * Four families, and the order is deliberate. Negative controls come first
 * because they are the only ones that can invalidate everything after them: a
 * control that fires means the pipeline finds signal in data that has none, and
 * every number downstream is then a measurement of the bug.
 *
 * Fold geometry is next, because purge and embargo are what make the validation
 * results mean anything. A fold whose gap is smaller than the label horizon is
 * training on the answer.
 *
 * Cost sensitivity is the one that most often changes a conclusion. A Sharpe
 * quoted at one spread assumption is a claim about that assumption; the curve
 * across assumptions is a claim about the strategy.
 *
 * PBO closes it, because it measures the thing the leaderboard cannot: whether
 * picking the best in-sample configuration tells you anything at all.
 */
'use client'

import { useMemo } from 'react'

import { TimeSeries } from '@/components/system/charts'
import { Panel, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'

interface Control {
  control: string
  description?: string
  mean_ic?: number | null
  t_stat?: number | null
  observations?: number
  fold_positive_rate?: number | null
  passed?: boolean
  blocking?: boolean
}

interface Fold {
  index: number
  train_start: string
  train_end: string
  purge_end?: string
  validation_start: string
  validation_end: string
  label_horizon_sessions?: number
  embargo_sessions?: number
  gap_sessions?: number
}

interface CostPoint {
  half_spread_bps: number
  gross_sharpe?: number | null
  net_sharpe?: number | null
  net_cagr?: number | null
  annualised_turnover?: number | null
  cost_share_of_gross?: number | null
  net_max_drawdown?: number | null
}

interface Integrity {
  comparisons?: number
  clean?: boolean
  failed?: string[]
  rows_compared?: number
  columns_compared?: number
  cutoffs?: string[]
}

interface Pbo {
  pbo?: number
  configurations?: number
  splits_evaluated?: number
  blocks?: number
  median_logit?: number
  interpretation?: string
}

const n = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function pboState(p: number | null): ResearchState {
  if (p === null) return 'unknown'
  if (p < 0.2) return 'candidate'
  if (p < 0.4) return 'stale'
  return 'blocked'
}

export default function ExperimentEvidence({
  integrity, controls, plan, costSensitivity, pbo,
}: {
  integrity?: Integrity | null
  controls?: { controls?: Control[] } | null
  plan?: { scheme?: string; folds?: Fold[] } | null
  costSensitivity?: Record<string, CostPoint[]> | null
  pbo?: Pbo | null
}) {
  const controlRows = useMemo(() => controls?.controls ?? [], [controls])
  const folds = useMemo(() => plan?.folds ?? [], [plan])
  const models = useMemo(() => Object.keys(costSensitivity ?? {}), [costSensitivity])

  const foldColumns: DataColumn<Fold>[] = [
    { key: 'i', header: 'Fold', numeric: true, width: '8%', sort: (f) => f.index, render: (f) => <Value value={f.index} digits={0} /> },
    { key: 'tr', header: 'Train', width: '22%', sort: (f) => f.train_start, render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.train_start} → {f.train_end}</span> },
    {
      key: 'gap', header: 'Gap', unit: 'sessions', numeric: true, sort: (f) => n(f.gap_sessions),
      render: (f) => (
        <Value
          value={n(f.gap_sessions)} digits={0}
          tone={false}
          title="Purge plus embargo. Must exceed the label horizon, or training sees the answer."
        />
      ),
    },
    { key: 'hz', header: 'Horizon', unit: 'sessions', numeric: true, sort: (f) => n(f.label_horizon_sessions), render: (f) => <Value value={n(f.label_horizon_sessions)} digits={0} /> },
    { key: 'emb', header: 'Embargo', unit: 'sessions', numeric: true, sort: (f) => n(f.embargo_sessions), render: (f) => <Value value={n(f.embargo_sessions)} digits={0} /> },
    { key: 'val', header: 'Validate', width: '22%', sort: (f) => f.validation_start, render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.validation_start} → {f.validation_end}</span> },
    {
      key: 'safe', header: 'Gap covers horizon', width: '13%',
      sort: (f) => ((n(f.gap_sessions) ?? 0) >= (n(f.label_horizon_sessions) ?? 0) ? 1 : 0),
      render: (f) => {
        const ok = (n(f.gap_sessions) ?? 0) >= (n(f.label_horizon_sessions) ?? 0)
        return <Status state={ok ? 'recorded' : 'blocked'} label={ok ? 'yes' : 'no'} />
      },
    },
  ]

  const blockingFailed = controlRows.filter((c) => c.blocking && c.passed === false)
  const pboValue = n(pbo?.pbo)

  return (
    <>
      {controlRows.length ? (
        <Panel
          title="Negative controls"
          subtitle={`${controlRows.length} run`}
          state={blockingFailed.length ? 'blocked' : 'recorded'}
        >
          <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            Each control destroys the signal deliberately and asks whether the
            pipeline still finds one. A control that fires means the apparatus
            finds structure in data that has none, and every result downstream is
            then a measurement of that fault rather than of the strategy — which
            is why these are read before anything else.
          </p>
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr><th>Control</th><th className="num">Mean IC</th><th className="num">t</th><th className="num">Observations</th><th>Blocking</th><th>Result</th></tr>
              </thead>
              <tbody>
                {controlRows.map((c) => (
                  <tr key={c.control}>
                    <td style={{ fontFamily: 'var(--font-mono)' }} title={c.description}>{c.control}</td>
                    <td className="num"><Value value={n(c.mean_ic)} digits={5} signed /></td>
                    <td className="num"><Value value={n(c.t_stat)} digits={3} signed /></td>
                    <td className="num"><Value value={n(c.observations)} digits={0} /></td>
                    <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{c.blocking ? 'yes' : 'no'}</span></td>
                    <td>
                      {c.passed === undefined
                        ? <span className="sys-null">—</span>
                        : <Status state={c.passed ? 'recorded' : 'blocked'} label={c.passed ? 'passed' : 'FIRED'} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {controlRows.some((c) => c.description) ? (
            <div style={{ marginTop: 'var(--d-3)' }}>
              {controlRows.filter((c) => c.description).map((c) => (
                <p key={c.control} style={{ margin: '0 0 var(--d-1)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  <strong style={{ color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>{c.control}</strong> — {c.description}
                </p>
              ))}
            </div>
          ) : null}
        </Panel>
      ) : null}

      {integrity ? (
        <Panel title="Leakage check" state={integrity.clean ? 'recorded' : 'blocked'}>
          <Strip metrics={[
            { label: 'Comparisons', value: n(integrity.comparisons), digits: 0 },
            { label: 'Rows compared', value: n(integrity.rows_compared), digits: 0 },
            { label: 'Columns compared', value: n(integrity.columns_compared), digits: 0 },
            { label: 'Failures', value: integrity.failed?.length ?? 0, digits: 0 },
          ]} />
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            The panel was rebuilt as of {integrity.cutoffs?.join(', ') ?? 'several cutoffs'} and
            compared against the panel built with full history. Any column that
            differs at a past date was reading information that did not exist then.
            {integrity.clean ? ' No column differed.' : ''}
          </p>
          {integrity.failed?.length ? (
            <ul style={{ margin: 'var(--d-2) 0 0', paddingLeft: 'var(--d-4)', fontSize: 'var(--t-meta)', color: 'var(--e-neg)' }}>
              {integrity.failed.map((f) => <li key={f}>{f}</li>)}
            </ul>
          ) : null}
        </Panel>
      ) : null}

      {folds.length ? (
        <Panel title="Fold geometry" subtitle={plan?.scheme} flush>
          <DataTable
            columns={foldColumns} rows={folds} rowKey={(f) => String(f.index)}
            density="compact" filterPlaceholder="filter folds"
            initialSort={{ key: 'i', direction: 'asc' }}
          />
          <p style={{ margin: 0, padding: 'var(--d-2) var(--d-3)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', borderTop: '1px solid var(--rule)' }}>
            The gap is purge plus embargo. It has to exceed the label horizon: a
            label formed on the last training day resolves that many sessions
            later, which is inside the validation window unless the gap covers it.
            Where it does not, the model is being trained on the answer.
          </p>
        </Panel>
      ) : null}

      {models.length ? (
        <Panel title="Cost sensitivity" subtitle={`${models.length} models across the spread assumption`}>
          <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            A Sharpe quoted at one spread assumption is a claim about that
            assumption. The curve across assumptions is a claim about the strategy,
            and the point where it crosses zero is the friction the edge can bear.
          </p>
          <TimeSeries
            series={models.slice(0, 6).map((m, i) => ({
              name: m,
              points: (costSensitivity?.[m] ?? []).map((p) => ({ x: `${p.half_spread_bps}bp`, y: n(p.net_sharpe) })),
              color: ['var(--ink)', 'var(--s-candidate)', 'var(--s-experimental)', 'var(--s-stale)', 'var(--s-live)', 'var(--ink-faint)'][i],
            }))}
            unit="net Sharpe against half-spread"
            method="the same backtest re-costed at each spread"
            zeroLine
            height={230}
          />
          <div className="sys-scroll-x" style={{ marginTop: 'var(--d-3)' }}>
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th>Model</th><th className="num">Half-spread</th><th className="num">Gross Sharpe</th>
                  <th className="num">Net Sharpe</th><th className="num">Turnover</th><th className="num">Cost share</th>
                </tr>
              </thead>
              <tbody>
                {models.flatMap((m) => (costSensitivity?.[m] ?? []).map((p, i) => (
                  <tr key={`${m}-${p.half_spread_bps}-${i}`}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{m}</td>
                    <td className="num"><Value value={n(p.half_spread_bps)} digits={1} unit="bp" /></td>
                    <td className="num"><Value value={n(p.gross_sharpe)} digits={3} signed tone /></td>
                    <td className="num"><Value value={n(p.net_sharpe)} digits={3} signed tone /></td>
                    <td className="num"><Value value={n(p.annualised_turnover)} digits={2} unit="×" /></td>
                    <td className="num"><Value value={n(p.cost_share_of_gross)} digits={3} /></td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {pbo ? (
        <Panel title="Probability of backtest overfitting" state={pboState(pboValue)}>
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.4fr)' }}>
            <Section title="Measurement">
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-3)', marginBottom: 'var(--d-2)' }}>
                <span className="sys-title"><Value value={pboValue} digits={4} /></span>
                <Status state={pboState(pboValue)} />
              </div>
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Configurations</td><td className="num"><Value value={n(pbo.configurations)} digits={0} /></td></tr>
                  <tr><td>Splits evaluated</td><td className="num"><Value value={n(pbo.splits_evaluated)} digits={0} /></td></tr>
                  <tr><td>Blocks</td><td className="num"><Value value={n(pbo.blocks)} digits={0} /></td></tr>
                  <tr><td>Median logit</td><td className="num"><Value value={n(pbo.median_logit)} digits={4} signed /></td></tr>
                </tbody>
              </table>
            </Section>
            <Section title="What it measures">
              <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                {pbo.interpretation}
              </p>
              <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
                This is the one measurement the leaderboard cannot make. A ranking
                says which configuration scored best; this says whether scoring best
                in-sample predicts anything out of sample at all. At 0.5 it does
                not, and the ranking is then a list ordered by noise.
              </p>
            </Section>
          </div>
        </Panel>
      ) : null}

      {!controlRows.length && !folds.length && !models.length && !pbo ? (
        <Panel title="Evidence">
          <StateBlock state="unavailable" title="This experiment recorded no controls, folds or sensitivity" />
        </Panel>
      ) : null}
    </>
  )
}
