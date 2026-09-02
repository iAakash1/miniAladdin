/**
 * Signal research lab.
 *
 * The question is whether an idea works, and the thing that most often makes
 * the answer no is not the idea — it is how many ideas were tried before it.
 * So the multiple-testing account is the headline, and the winning
 * configuration's own statistics come after it.
 *
 * A signal's predictive power and a portfolio's profitability are shown in
 * separate sections and never in the same row. An information coefficient is a
 * rank correlation; it is not a return, and reading it as one is the single
 * easiest mistake this surface can invite.
 */
'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { Panel, Section, StateBlock, Status, Strip, Table, Value, type Column } from '@/components/system'

interface Finalist {
  config_id: string
  stage?: string
  family?: string
  arm?: string
  params?: Record<string, unknown>
}
interface Economics {
  config_id: string
  family?: string
  arm?: string
  target?: string
  feature_count?: number
  mean_ic?: number | null
  [k: string]: unknown
}
interface DeflatedSharpe {
  observed_sharpe?: number
  deflated_probability?: number | null
  expected_max_sharpe_under_null?: number
  trials?: number
  observations?: number
  skew?: number
  excess_kurtosis?: number
  significant?: boolean | null
  variance_source?: string
  note?: string
}
interface Selection {
  available?: boolean
  experiment?: string
  finalists?: Finalist[]
  economics?: Record<string, Economics>
  significance?: Record<string, { deflated_sharpe?: DeflatedSharpe }>
  multiple_testing?: {
    prior_trials?: number
    new_trials?: number
    cumulative_trials?: number
    expected_max_abs_t_under_null?: number
    bonferroni_threshold_5pct?: number
    interpretation?: string
  }
  probability_of_backtest_overfitting?: Record<string, unknown>
  selected?: string | Record<string, unknown>
  verdict?: { status: string; passed: boolean; failed: string[] }
  dataset?: Record<string, unknown>
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export default function SignalLab() {
  const [data, setData] = useState<Selection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/selection/EXP-007')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Selection) => {
        if (!alive) return
        setData(d)
        const first = d.finalists?.[0]?.config_id ?? null
        setSelected(first)
      })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const finalists = useMemo(() => data?.finalists ?? [], [data])

  const columns: Column<Finalist>[] = useMemo(() => [
    { key: 'id', header: 'Config', width: '20%', render: (f) => <span style={{ fontFamily: 'var(--font-mono)' }}>{f.config_id}</span> },
    { key: 'family', header: 'Family', width: '18%', render: (f) => f.family ?? '—' },
    { key: 'arm', header: 'Arm', width: '14%', render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.arm ?? '—'}</span> },
    { key: 'stage', header: 'Stage', width: '16%', render: (f) => <Status state="recorded" label={f.stage ?? 'recorded'} /> },
    {
      key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true,
      render: (f) => <Value value={num(data?.economics?.[f.config_id]?.mean_ic)} digits={4} signed tone title="A rank correlation between prediction and forward rank. Not a return." />,
    },
  ], [data])

  if (error) {
    return <Panel title="Signal lab" state="unavailable"><StateBlock state="unavailable" title="The search record could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!data) return <Panel title="Signal lab" state="waking"><StateBlock state="waking" title="Reading the search record" /></Panel>
  if (data.available === false) {
    return <Panel title="Signal lab" state="unavailable"><StateBlock state="unavailable" title="No search record is available" detail="Nothing is shown in its place." /></Panel>
  }

  const mt = data.multiple_testing ?? {}
  const dsr = selected ? data.significance?.[selected]?.deflated_sharpe : undefined
  const econ = selected ? data.economics?.[selected] : undefined

  return (
    <>
      {/* The account of how many ideas were tried comes before any result. */}
      <Panel title="Multiple testing" subtitle={data.experiment} state="recorded">
        <Strip metrics={[
          { label: 'Prior trials', value: mt.prior_trials ?? null, digits: 0 },
          { label: 'This search', value: mt.new_trials ?? null, digits: 0 },
          { label: 'Cumulative', value: mt.cumulative_trials ?? null, digits: 0, title: 'The count every significance claim is corrected against' },
          { label: 'Expected max |t| under null', value: mt.expected_max_abs_t_under_null ?? null, digits: 2, title: 'The best of this many zero-skill configurations would reach roughly this t by chance' },
          { label: 'Bonferroni 5%', value: mt.bonferroni_threshold_5pct ?? null, digits: 2 },
        ]} />
        {mt.interpretation ? (
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)', maxWidth: '86ch' }}>
            {mt.interpretation}
          </p>
        ) : null}
      </Panel>

      <Panel title="Finalists" subtitle={`${finalists.length} survived the search`} flush>
        <Table columns={columns} rows={finalists} rowKey={(f) => f.config_id} density="compact" selectedKey={selected ?? undefined} onSelect={(f) => setSelected(f.config_id)} />
      </Panel>

      {selected ? (
        <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))' }}>
          <Panel title="Signal quality" subtitle="rank units" state="recorded">
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Target</td><td className="num">{econ?.target ?? '—'}</td></tr>
                <tr><td>Features</td><td className="num"><Value value={num(econ?.feature_count)} digits={0} /></td></tr>
                <tr><td>Mean IC</td><td className="num"><Value value={num(econ?.mean_ic)} digits={4} signed tone /></td></tr>
              </tbody>
            </table>
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)' }}>
              An information coefficient is a cross-sectional rank correlation. It
              is not a return, and it does not become one by being annualised.
            </p>
          </Panel>

          <Panel
            title="Deflated Sharpe"
            state={dsr?.significant ? 'candidate' : 'blocked'}
          >
            {dsr ? (
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Observed Sharpe</td><td className="num"><Value value={num(dsr.observed_sharpe)} digits={4} signed /></td></tr>
                  <tr><td>Expected max under null</td><td className="num"><Value value={num(dsr.expected_max_sharpe_under_null)} digits={4} /></td></tr>
                  <tr><td>Deflated probability</td><td className="num"><Value value={num(dsr.deflated_probability)} digits={4} /></td></tr>
                  <tr><td>Trials</td><td className="num"><Value value={num(dsr.trials)} digits={0} /></td></tr>
                  <tr><td>Observations</td><td className="num"><Value value={num(dsr.observations)} digits={0} /></td></tr>
                  <tr><td>Skew</td><td className="num"><Value value={num(dsr.skew)} digits={3} signed /></td></tr>
                  <tr><td>Excess kurtosis</td><td className="num"><Value value={num(dsr.excess_kurtosis)} digits={3} /></td></tr>
                  <tr><td>Variance source</td><td className="num">{dsr.variance_source ?? '—'}</td></tr>
                  <tr><td>Significant</td><td className="num">{dsr.significant === undefined ? '—' : String(dsr.significant)}</td></tr>
                </tbody>
              </table>
            ) : <StateBlock state="unavailable" title="No deflated Sharpe recorded for this configuration" />}
            {dsr?.note ? (
              <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>{dsr.note}</p>
            ) : null}
          </Panel>

          <Panel title="Configuration">
            {finalists.find((f) => f.config_id === selected)?.params ? (
              <table className="sys-table sys-table--compact">
                <tbody>
                  {Object.entries(finalists.find((f) => f.config_id === selected)!.params ?? {}).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td>
                      <td className="num">{typeof v === 'number' ? <Value value={v} digits={0} /> : String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <StateBlock state="unavailable" title="No parameters recorded" />}
          </Panel>
        </div>
      ) : null}

      <Panel title="Verdict" state={data.verdict?.passed ? 'candidate' : 'blocked'}>
        <Section title={data.verdict?.status ?? 'unknown'}>
          {data.verdict?.failed?.length ? (
            <p style={{ margin: 0, fontSize: 'var(--t-body)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              Unmet: {data.verdict.failed.join(', ')}.{' '}
              <Link href="/terminal/evidence" style={{ color: 'var(--ink)' }}>Inspect the evidence chain →</Link>
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: 'var(--t-body)', color: 'var(--ink-muted)' }}>No unmet gate recorded.</p>
          )}
        </Section>
      </Panel>
    </>
  )
}
