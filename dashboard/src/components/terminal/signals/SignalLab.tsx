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

import { Grid, Panel, Section, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'
import { ObjectHeader, StripSkeleton, TableSkeleton } from '@/components/system/composition'
import { EnvelopeGrid, type Envelope } from '@/components/system/EnvelopeMetric'

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
  envelopes?: Record<string, Envelope>
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

  const columns: DataColumn<Finalist>[] = useMemo(() => [
    { key: 'id', header: 'Config', width: '20%', sort: (f) => f.config_id, text: (f) => f.config_id, render: (f) => <span style={{ fontFamily: 'var(--font-mono)' }}>{f.config_id}</span> },
    { key: 'family', header: 'Family', width: '18%', sort: (f) => f.family ?? null, text: (f) => f.family ?? '', render: (f) => f.family ?? '—' },
    { key: 'arm', header: 'Arm', width: '14%', sort: (f) => f.arm ?? null, text: (f) => f.arm ?? '', render: (f) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{f.arm ?? '—'}</span> },
    { key: 'stage', header: 'Stage', width: '16%', sort: (f) => f.stage ?? null, text: (f) => f.stage ?? '', render: (f) => <Status state="recorded" label={f.stage ?? 'recorded'} /> },
    {
      key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true,
      sort: (f) => num(data?.economics?.[f.config_id]?.mean_ic),
      render: (f) => <Value measure="mean_ic" kind="ic" value={num(data?.economics?.[f.config_id]?.mean_ic)} digits={4} signed tone title="A rank correlation between prediction and forward rank. Not a return." />,
    },
    {
      key: 'dsr', header: 'Deflated Sharpe', unit: 'probability', numeric: true, optional: true,
      sort: (f) => num(data?.significance?.[f.config_id]?.deflated_sharpe?.deflated_probability),
      render: (f) => <Value measure="deflated_sharpe_probability" kind="probability" value={num(data?.significance?.[f.config_id]?.deflated_sharpe?.deflated_probability)} digits={4} />,
    },
  ], [data])

  if (error) {
    return <Panel title="Signal lab" state="unavailable"><StateBlock state="unavailable" title="The search record could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!data) {
    return (
      <>
        <StripSkeleton items={5} />
        <Panel title="Finalists" state="waking" flush><TableSkeleton rows={6} columns={6} /></Panel>
      </>
    )
  }
  if (data.available === false) {
    return <Panel title="Signal lab" state="unavailable"><StateBlock state="unavailable" title="No search record is available" detail="Nothing is shown in its place." /></Panel>
  }

  const mt = data.multiple_testing ?? {}
  const dsr = selected ? data.significance?.[selected]?.deflated_sharpe : undefined
  const econ = selected ? data.economics?.[selected] : undefined

  return (
    <>
      <ObjectHeader
        glyph="S"
        name="Signals"
        kind={data.experiment ? `search record · ${data.experiment}` : 'search record'}
        state={data.verdict?.passed ? 'candidate' : 'blocked'}
        detail={data.verdict?.status}
        facts={[
          { label: 'Cumulative trials', value: mt.cumulative_trials ?? null, digits: 0, title: 'What every significance claim is corrected against' },
          { label: 'This search', value: mt.new_trials ?? null, digits: 0 },
          { label: 'Expected max |t|', value: mt.expected_max_abs_t_under_null ?? null, digits: 2 },
          { label: 'Finalists', value: finalists.length, digits: 0 },
          { label: 'Unmet gates', value: data.verdict?.failed?.length ?? null, digits: 0 },
        ]}
      />

      {data.envelopes && Object.keys(data.envelopes).length ? (
        <Panel
          title="Decision figures"
          subtitle="click a number for its envelope"
          state="recorded"
        >
          <EnvelopeGrid
            metrics={[
              { label: 'IC t-stat', envelope: data.envelopes.ic_t_stat, digits: 3, signed: true },
              { label: 'Gross Sharpe', envelope: data.envelopes.gross_sharpe, digits: 4, signed: true, tone: true },
              { label: 'Net Sharpe', envelope: data.envelopes.net_sharpe, digits: 4, signed: true, tone: true },
              { label: 'Alpha t-stat', envelope: data.envelopes.alpha_t_stat, digits: 3, signed: true },
              { label: 'Deflated Sharpe', envelope: data.envelopes.deflated_sharpe_probability, digits: 4 },
              { label: 'PBO', envelope: data.envelopes.pbo, digits: 4 },
            ]}
          />
          <p style={{ margin: 'var(--d-3) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '86ch' }}>
            These are the six numbers a promotion decision turns on. Each carries
            the artifact it was read from, the method that produced it and the
            moment it was retrieved, so none of them has to be taken on trust.
          </p>
        </Panel>
      ) : null}

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
        <DataTable
          columns={columns} rows={finalists} rowKey={(f) => f.config_id}
          density="compact" filterPlaceholder="filter configurations"
          initialSort={{ key: 'ic', direction: 'desc' }}
          selectedKey={selected ?? undefined}
          onSelect={(f) => {
            setSelected(f.config_id)
            recordVisit({ kind: 'signal', id: f.config_id, label: f.config_id, detail: f.family })
          }}
        />
      </Panel>

      {selected ? (
        <Grid>
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
            ) : <StateBlock
              state="unavailable"
              title="No deflated Sharpe recorded for this configuration"
              detail="The deflation needs the trial-Sharpe dispersion. Where the search did not record it, no probability is reported rather than one computed from a substitute."
            />}
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
            ) : <StateBlock
              state="unavailable"
              title="No parameters recorded"
              detail="The search artifact stored this configuration by identifier without its hyperparameters."
            />}
          </Panel>
        </Grid>
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
