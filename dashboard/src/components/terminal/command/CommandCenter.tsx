/**
 * Command centre.
 *
 * The entry point answers one question — what deserves attention — and the
 * honest answer for this product is usually "nothing is promotable, and here
 * is precisely why". So blockers come first and headline performance comes
 * after, which is the reverse of how a dashboard is normally built.
 *
 * That ordering is deliberate. A net Sharpe shown above the reason it does not
 * count is an invitation to read the Sharpe and stop.
 */
'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Grid, Panel, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { ObjectHeader } from '@/components/system/composition'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'

interface Status_ {
  deployment_status?: string
  registry_available?: boolean
  production?: number | null
  candidates?: number | null
  validated?: number | null
  retired?: number | null
  total_entries?: number | null
  serving_predictions?: boolean
  message?: string
  firewall?: {
    contract_armed?: boolean
    contract_state?: string
    engaged?: boolean
    headline?: string
    breaches_prevented?: number
  }
}

interface ExperimentRow {
  experiment_id: string
  void: boolean
  void_reason?: string | null
  status?: string
  detail?: string | null
}

interface Gate { gate: string; passed: boolean; observed: unknown; required: string }
interface Selection {
  available?: boolean
  experiment?: string
  verdict?: { passed: boolean; status: string; gates: Gate[]; failed: string[]; note?: string }
  holdout?: { touched?: boolean; note?: string }
}

function fmt(v: unknown): string {
  if (typeof v === 'number') return v.toFixed(4)
  if (v === null || v === undefined) return '—'
  return String(v)
}

export default function CommandCenter() {
  const [status, setStatus] = useState<Status_ | null>(null)
  const [experiments, setExperiments] = useState<ExperimentRow[] | null>(null)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [errors, setErrors] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    const fail = (what: string) => (e: Error) => { if (alive) setErrors((p) => [...p, `${what}: ${e.message}`]) }
    fetch('/api/quant/status').then((r) => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then((d) => alive && setStatus(d)).catch(fail('status'))
    fetch('/api/quant/experiments').then((r) => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then((d) => alive && setExperiments(d.experiments ?? [])).catch(fail('experiments'))
    fetch('/api/quant/selection/EXP-007').then((r) => r.ok ? r.json() : Promise.reject(new Error(String(r.status))))
      .then((d) => alive && setSelection(d)).catch(fail('selection'))
    return () => { alive = false }
  }, [])

  const expColumns: DataColumn<ExperimentRow>[] = [
    {
      key: 'id', header: 'Experiment', width: '18%',
      sort: (r) => r.experiment_id, text: (r) => r.experiment_id,
      render: (r) => (
        <Link
          href={`/terminal/experiments?id=${r.experiment_id}`}
          style={{ color: 'inherit', fontFamily: 'var(--font-mono)' }}
          onClick={() => recordVisit({ kind: 'experiment', id: r.experiment_id, label: r.experiment_id })}
        >
          {r.experiment_id}
        </Link>
      ),
    },
    {
      key: 'status', header: 'State', width: '16%',
      sort: (r) => (r.void ? 'void' : r.status ?? ''), text: (r) => (r.void ? 'void' : r.status ?? ''),
      render: (r) => <Status state={r.void ? 'unavailable' : 'recorded'} label={r.void ? 'void' : (r.status ?? 'recorded')} />,
    },
    { key: 'detail', header: 'Detail', text: (r) => `${r.detail ?? ''} ${r.void_reason ?? ''}`, render: (r) => <span className="sys-meta sys-meta--strong">{r.detail ?? r.void_reason ?? '—'}</span> },
  ]

  const failedGates = (selection?.verdict?.gates ?? []).filter((g) => !g.passed)
  const deployment = status?.deployment_status ?? 'UNKNOWN'
  const deployState: ResearchState =
    deployment === 'NO_MODEL' ? 'unavailable' : deployment === 'SERVING' ? 'production' : 'unknown'

  return (
    <>
      {/* Blockers first. A headline figure above the reason it does not count
          invites the reader to take the figure and stop. */}
      <Panel
        title="Why nothing is promoted"
        subtitle={selection?.experiment ?? 'EXP-007'}
        state={selection?.verdict?.passed ? 'candidate' : 'blocked'}
      >
        {selection?.verdict ? (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-3)', marginBottom: 'var(--d-3)' }}>
              <span className="sys-title">{selection.verdict.status}</span>
              <span className="sys-meta">
                {failedGates.length} of {selection.verdict.gates.length} gates unmet
              </span>
            </div>
            {failedGates.length ? (
              <table className="sys-table sys-table--compact">
                <thead><tr><th>Gate</th><th className="num">Observed</th><th>Required</th></tr></thead>
                <tbody>
                  {failedGates.map((g) => (
                    <tr key={g.gate}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{g.gate}</td>
                      <td className="num sys-neg">{fmt(g.observed)}</td>
                      <td><span className="sys-meta sys-meta--strong">{g.required}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <StateBlock state="candidate" title="Every gate passed" detail={selection.verdict.note} />
            )}
            <p style={{ marginTop: 'var(--d-3)', marginBottom: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)', maxWidth: '82ch' }}>
              {selection.verdict.note}
            </p>
            <p style={{ marginTop: 'var(--d-2)', marginBottom: 0 }}>
              <Link href="/terminal/evidence" className="sys-meta sys-meta--strong">Inspect the evidence chain →</Link>
            </p>
          </>
        ) : errors.some((e) => e.startsWith('selection')) ? (
          <StateBlock state="unavailable" title="The selection verdict could not be read" detail={errors.find((e) => e.startsWith('selection'))} />
        ) : (
          <StateBlock state="waking" title="Reading the verdict" />
        )}
      </Panel>

      <ObjectHeader
        glyph="⌘"
        name="Command"
        kind="what deserves attention"
        state={selection?.verdict?.passed ? 'candidate' : 'blocked'}
        detail={selection?.verdict?.status ?? deployment}
        facts={[
          { label: 'Production', value: status?.production ?? null, digits: 0 },
          { label: 'Candidates', value: status?.candidates ?? null, digits: 0 },
          { label: 'Registered', value: status?.total_entries ?? null, digits: 0 , kind: 'count'},
          { label: 'Experiments', value: experiments?.length ?? null, digits: 0 , kind: 'count'},
          { label: 'Unmet gates', value: failedGates.length || null, digits: 0 },
        ]}
      />

      <Strip metrics={[
        { label: 'Production', value: status?.production ?? null, digits: 0, title: 'Models armed and serving' },
        { label: 'Candidates', value: status?.candidates ?? null, digits: 0 },
        { label: 'Validated', value: status?.validated ?? null, digits: 0 },
        { label: 'Registered', value: status?.total_entries ?? null, digits: 0 , kind: 'count'},
        { label: 'Retired', value: status?.retired ?? null, digits: 0 },
        { label: 'Experiments', value: experiments?.length ?? null, digits: 0 , kind: 'count'},
      ]} />

      <Grid>
        <Panel title="Deployment" state={deployState}>
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Status</td><td className="num">{deployment}</td></tr>
              <tr><td>Registry readable</td><td className="num">{status?.registry_available === undefined ? '—' : String(status.registry_available)}</td></tr>
              <tr><td>Serving predictions</td><td className="num">{status?.serving_predictions === undefined ? '—' : String(status.serving_predictions)}</td></tr>
            </tbody>
          </table>
          {status?.message ? (
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>{status.message}</p>
          ) : null}
        </Panel>

        <Panel
          title="Firewall"
          state={status?.firewall?.contract_armed ? 'production' : 'blocked'}
        >
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Contract</td><td className="num">{status?.firewall?.contract_state ?? '—'}</td></tr>
              <tr><td>Armed</td><td className="num">{status?.firewall?.contract_armed === undefined ? '—' : String(status.firewall.contract_armed)}</td></tr>
              <tr><td>Engaged</td><td className="num">{status?.firewall?.engaged === undefined ? '—' : String(status.firewall.engaged)}</td></tr>
              <tr><td>Breaches prevented</td><td className="num"><Value value={status?.firewall?.breaches_prevented ?? null} digits={0} /></td></tr>
            </tbody>
          </table>
          {status?.firewall?.headline ? (
            <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>{status.firewall.headline}</p>
          ) : null}
        </Panel>

        <Panel title="Holdout" state={selection?.holdout?.touched ? 'unavailable' : 'blocked'}>
          <table className="sys-table sys-table--compact">
            <tbody>
              <tr><td>Touched</td><td className="num">{selection?.holdout?.touched === undefined ? '—' : String(selection.holdout.touched)}</td></tr>
            </tbody>
          </table>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
            {selection?.holdout?.note ?? 'A sealed holdout is spent once. Until it is, no result measured on it exists.'}
          </p>
        </Panel>
      </Grid>

      <Panel title="Experiments" subtitle={experiments ? `${experiments.length} recorded` : undefined} flush>
        {experiments
          ? <DataTable columns={expColumns} rows={experiments} rowKey={(r) => r.experiment_id} density="compact" filterPlaceholder="filter" />
          : <StateBlock state="waking" title="Reading experiments" />}
      </Panel>

      <Panel title="Start here">
        <div style={{ display: 'flex', gap: 'var(--d-2)', flexWrap: 'wrap' }}>
          <Link href="/terminal/gates" className="sys-btn">Which gate blocks everything</Link>
          <Link href="/terminal/signals" className="sys-btn">How many ideas were tried</Link>
          <Link href="/terminal/covariance" className="sys-btn">How much risk depends on the estimator</Link>
          <Link href="/terminal/data" className="sys-btn">What the data contract says</Link>
          <Link href="/terminal/provenance" className="sys-btn">Where a prediction came from</Link>
          <Link href="/terminal/memos" className="sys-btn">Write it down</Link>
        </div>
        <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-micro)', color: 'var(--ink-faint)' }}>
          Press ⌘K to search every object, or ? for the keyboard map.
        </p>
      </Panel>

      {errors.length ? (
        <Panel title="Unavailable" state="unavailable">
          <ul style={{ margin: 0, paddingLeft: 'var(--d-4)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>
            {errors.map((e) => <li key={e}>{e}</li>)}
          </ul>
          <p style={{ margin: 'var(--d-2) 0 0', fontSize: 'var(--t-meta)', color: 'var(--ink-faint)' }}>
            Nothing is shown in place of these. A surface that failed to load is not a surface with no data.
          </p>
        </Panel>
      ) : null}
    </>
  )
}
