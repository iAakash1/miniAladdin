/**
 * Model workbench.
 *
 * Answers what a model is and what it learned, where Evidence answers whether
 * it can be trusted. The split matters: merging them is what produces a
 * leaderboard, where a rank stands in for an argument.
 *
 * The number given the most room is the train/validation IC gap, because it is
 * the one that says whether the model learned the data or memorised it. A
 * training IC of 0.19 against a validation IC of 0.03 is not a good model with
 * a caveat; it is mostly memorisation, and the headline should say so.
 */
'use client'

import Link from 'next/link'

import RegimePerformance, { type RegimeRow } from './RegimePerformance'
import { useEffect, useState } from 'react'

import { Grid, Panel, Prose, Section, StateBlock, Status, Strip, Table, Value, type Column } from '@/components/system'
import { ObjectHeader, StripSkeleton, TableSkeleton } from '@/components/system/composition'

interface LabelRow {
  label: string
  horizon_sessions?: number
  best_model?: string
  mean_ic?: number | null
  median_ic?: number | null
  ic_t_stat?: number | null
  fold_ic_positive_rate?: number | null
  train_mean_ic?: number | null
  train_ic_gap?: number | null
  experiments?: number
  net_sharpe?: number | null
  alpha_significant?: boolean | null
  deflated_sharpe_probability?: number | null
}

interface Check { check: string; passed: boolean; detail?: string }

interface Overview {
  status?: string
  validity?: Record<string, unknown>
  generated_at?: string
  git_commit?: string
  experiment_id?: string
  feature_count?: number
  dataset?: { dataset_version?: string; rows?: number; symbols?: number; dates?: number; start?: string; end?: string; content_hash?: string }
  guards?: { passed?: boolean; checks?: Check[] }
  universe?: Record<string, unknown>
  labels?: LabelRow[]
}

function n(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export default function ModelWorkbench() {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [regimes, setRegimes] = useState<Record<string, RegimeRow[]> | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/ml/overview')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Overview) => {
        if (!alive) return
        setData(d)
        setSelected(d.labels?.[0]?.label ?? null)
      })
      .catch((e: Error) => { if (alive) setError(e.message) })

    // The regime breakdown lives on the experiment artifact rather than the
    // overview, so it is fetched alongside rather than folded into it.
    fetch('/api/quant/experiments/EXP-006')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: { regime_performance?: Record<string, RegimeRow[]> }) => {
        if (alive) setRegimes(d.regime_performance ?? null)
      })
      .catch(() => { /* the breakdown is additive; its absence is reported by its own panel */ })

    return () => { alive = false }
  }, [])

  const columns: Column<LabelRow>[] = [
    { key: 'label', header: 'Label', width: '16%', render: (r) => <span className="sys-mono">{r.label}</span> },
    { key: 'h', header: 'Horizon', unit: 'sessions', numeric: true, render: (r) => <Value value={n(r.horizon_sessions)} kind="count" /> },
    { key: 'model', header: 'Best model', width: '18%', render: (r) => r.best_model ?? '—' },
    { key: 'vic', header: 'Validation IC', unit: 'rank corr.', numeric: true, render: (r) => <Value measure="mean_ic" kind="ic" value={n(r.mean_ic)} digits={4} signed tone /> },
    { key: 'tic', header: 'Train IC', unit: 'rank corr.', numeric: true, render: (r) => <Value measure="mean_ic" kind="ic" value={n(r.train_mean_ic)} digits={4} signed /> },
    {
      key: 'gap', header: 'Gap', unit: 'train − val', numeric: true,
      render: (r) => <Value measure="train_ic_gap" kind="ic" value={n(r.train_ic_gap)} digits={4} tone title="How much of the training fit did not survive out of sample" />,
    },
    { key: 't', header: 'IC t-stat', unit: 'Newey-West', numeric: true, render: (r) => <Value measure="ic_t_stat" kind="tstat" value={n(r.ic_t_stat)} digits={2} signed /> },
    { key: 'ns', header: 'Net Sharpe', unit: 'after costs', numeric: true, render: (r) => <Value measure="net_sharpe" kind="sharpe" value={n(r.net_sharpe)} digits={3} signed tone /> },
  ]

  if (error) {
    return <Panel title="Models" state="unavailable"><StateBlock state="unavailable" title="The study could not be read" detail={`Request failed: ${error}.`} /></Panel>
  }
  if (!data) {
    return (
      <>
        <StripSkeleton items={7} />
        <Panel title="Labels" state="waking" flush><TableSkeleton rows={4} columns={8} /></Panel>
      </>
    )
  }

  const labels = data.labels ?? []
  const row = labels.find((l) => l.label === selected)
  const guards = data.guards
  const ds = data.dataset ?? {}

  // The share of the training fit that did not survive out of sample.
  const retained = row && n(row.train_mean_ic) && n(row.mean_ic) !== null
    ? (row.mean_ic as number) / (row.train_mean_ic as number)
    : null

  return (
    <>
      <ObjectHeader
        glyph="µ"
        name="Models"
        kind="what was learned, and what survived"
        state="experimental"
        detail={data.experiment_id}
        facts={[
          { label: 'Rows', value: n(ds.rows), digits: 0 , kind: 'count'},
          { label: 'Symbols', value: n(ds.symbols), digits: 0 , kind: 'count'},
          { label: 'Dates', value: n(ds.dates), digits: 0 , kind: 'count'},
          { label: 'Features', value: n(data.feature_count), digits: 0 , kind: 'count'},
          { label: 'Labels', value: labels.length, digits: 0, kind: 'count' },
          { label: 'Guards', value: guards?.passed ? 'pass' : 'fail', digits: 0, kind: 'count' },
        ]}
      />

      <Strip metrics={[
        { label: 'From', value: ds.start ?? null, digits: 0, kind: 'count' },
        { label: 'To', value: ds.end ?? null, digits: 0, kind: 'count' },
      ]} />

      <Panel
        title="Labels"
        subtitle={data.experiment_id}
        flush
        actions={<Link href="/terminal/evidence" className="sys-meta sys-meta--strong">Evidence →</Link>}
      >
        <Table columns={columns} rows={labels} rowKey={(r) => r.label} density="compact" selectedKey={selected ?? undefined} onSelect={(r) => setSelected(r.label)} />
      </Panel>

      {row ? (
        <Panel
          title="Generalization"
          subtitle={`${row.label} · ${row.best_model ?? ''}`}
          state={retained !== null && retained < 0.25 ? 'blocked' : 'experimental'}
        >
          <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.2fr)' }}>
            <Section title="Train against validation">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Training IC</td><td className="num"><Value value={n(row.train_mean_ic)} digits={4} signed /></td></tr>
                  <tr><td>Validation IC</td><td className="num"><Value value={n(row.mean_ic)} digits={4} signed tone /></td></tr>
                  <tr><td>Median validation IC</td><td className="num"><Value value={n(row.median_ic)} digits={4} signed /></td></tr>
                  <tr><td>Gap</td><td className="num"><Value value={n(row.train_ic_gap)} digits={4} tone /></td></tr>
                  <tr><td>Retained out of sample</td><td className="num"><Value value={retained} digits={3} tone /></td></tr>
                  <tr><td>Folds with positive IC</td><td className="num"><Value value={n(row.fold_ic_positive_rate)} digits={3} /></td></tr>
                </tbody>
              </table>
            </Section>
            <Section title="What the gap says">
              <Prose>
                {retained === null
                  ? 'No training IC was recorded for this label, so the share of the fit that survived out of sample cannot be computed. Nothing is assumed in its place.'
                  : retained < 0.25
                    ? `Roughly ${(retained * 100).toFixed(0)}% of the training fit survived out of sample. That is mostly memorisation, and the validation figure should be read as the model's real signal — not as a good result with a caveat.`
                    : `Roughly ${(retained * 100).toFixed(0)}% of the training fit survived out of sample.`}
              </Prose>
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Deflated Sharpe probability</td><td className="num"><Value value={n(row.deflated_sharpe_probability)} digits={4} /></td></tr>
                  <tr><td>Alpha significant</td><td className="num">{row.alpha_significant === undefined || row.alpha_significant === null ? '—' : String(row.alpha_significant)}</td></tr>
                  <tr><td>Experiments on this label</td><td className="num"><Value value={n(row.experiments)} kind="count" /></td></tr>
                </tbody>
              </table>
            </Section>
          </div>
        </Panel>
      ) : null}

      <RegimePerformance byModel={regimes} />

      <Grid>
        <Panel title="Guards" state={guards ? (guards.passed ? 'recorded' : 'blocked') : 'unavailable'} flush>
          {guards?.checks?.length ? (
            <table className="sys-table sys-table--compact">
              <thead><tr><th>Check</th><th>Result</th><th>Detail</th></tr></thead>
              <tbody>
                {guards.checks.map((c) => (
                  <tr key={c.check}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{c.check}</td>
                    <td><Status state={c.passed ? 'recorded' : 'blocked'} label={c.passed ? 'pass' : 'fail'} /></td>
                    <td><span className="sys-meta sys-meta--strong">{c.detail ?? '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <StateBlock
              state="unavailable"
              title="No guard results recorded"
              detail="The study artifact stored no guard block. The guards may not have run, and their absence is not a pass."
            />}
        </Panel>

        <Panel title="Dataset">
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Version</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{ds.dataset_version ?? '—'}</td></tr>
              <tr><td>Content hash</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{ds.content_hash ?? '—'}</td></tr>
              <tr><td>Generated</td><td className="num">{data.generated_at ?? '—'}</td></tr>
              <tr><td>Commit</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{data.git_commit ?? '—'}</td></tr>
            </tbody>
          </table>
          <p style={{ margin: 'var(--d-2) 0 0' }}>
            <Link href="/terminal/data" className="sys-meta sys-meta--strong">Dataset and feature contracts →</Link>
          </p>
        </Panel>
      </Grid>
    </>
  )
}
