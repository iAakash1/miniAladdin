/**
 * Experiment registry.
 *
 * Experiments were a developer artifact reachable through a validation page.
 * They are the product's evidence base and belong at the top level.
 *
 * A void experiment is shown, not filtered out. An experiment that was
 * invalidated is a fact about the research record, and a registry that quietly
 * omits its failures is not a registry.
 */
'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { Panel, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit } from '@/lib/research/history'
import { ObjectHeader, StripSkeleton, TableSkeleton } from '@/components/system/composition'
import ExperimentEvidence from './ExperimentEvidence'

interface Row {
  experiment_id: string
  void: boolean
  void_reason?: string | null
  status?: string
  detail?: string | null
}

interface Detail {
  integrity?: Record<string, unknown> | null
  negative_controls?: { controls?: unknown[] } | null
  walk_forward_plan?: Record<string, unknown> | null
  cost_sensitivity?: Record<string, unknown[]> | null
  probability_of_backtest_overfitting?: Record<string, unknown> | null
  experiment_id?: string
  void?: boolean
  void_reason?: string | null
  definition?: Record<string, unknown>
  features_used?: string[]
  dataset_sources?: { dataset_id: string; role?: string; rows?: number; min_date?: string; max_date?: string; point_in_time_status?: string; survivorship_status?: string }[]
  leaderboard?: Record<string, unknown>[]
  fold_rows?: Record<string, unknown>[]
  generated_at?: string
  fingerprint?: string
}

export default function ExperimentRegistry() {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  // The fetched detail is tagged with the id it was fetched for, so a stale
  // response is filtered at render rather than cleared inside the effect. The
  // clear-then-refetch shape drops a render with neither the old nor the new
  // value, which reads as "no data" for a frame.
  const [detail, setDetail] = useState<{ id: string; data: Detail } | null>(null)
  const [detailError, setDetailError] = useState<{ id: string; message: string } | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/quant/experiments')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setRows(d.experiments ?? []) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (!selected) return
    let alive = true
    const id = selected
    fetch(`/api/quant/experiments/${id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Detail) => { if (alive) setDetail({ id, data: d }) })
      .catch((e: Error) => { if (alive) setDetailError({ id, message: e.message }) })
    return () => { alive = false }
  }, [selected])

  const columns: DataColumn<Row>[] = useMemo(() => [
    { key: 'id', header: 'Experiment', width: '18%', sort: (r) => r.experiment_id, text: (r) => r.experiment_id, render: (r) => <span style={{ fontFamily: 'var(--font-mono)' }}>{r.experiment_id}</span> },
    { key: 'state', header: 'State', width: '14%', sort: (r) => (r.void ? 'void' : r.status ?? ''), text: (r) => (r.void ? 'void' : r.status ?? ''), render: (r) => <Status state={r.void ? 'unavailable' : 'recorded'} label={r.void ? 'void' : (r.status ?? 'recorded')} /> },
    { key: 'detail', header: 'Detail', text: (r) => `${r.detail ?? ''} ${r.void_reason ?? ''}`, render: (r) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.detail ?? r.void_reason ?? '—'}</span> },
  ], [])

  if (error) {
    return (
      <Panel title="Experiments" state="unavailable">
        <StateBlock state="unavailable" title="The registry could not be read" detail={`Request failed: ${error}. No list is shown in its place.`} />
      </Panel>
    )
  }
  if (!rows) {
    return (
      <>
        <StripSkeleton items={3} />
        <Panel title="Registry" state="waking" flush><TableSkeleton rows={6} columns={3} /></Panel>
      </>
    )
  }

  const live = rows.filter((r) => !r.void).length

  return (
    <>
      <ObjectHeader
        glyph="X"
        name="Experiments"
        kind="the research record"
        state="recorded"
        detail={`${live} valid · ${rows.length - live} void`}
        facts={[
          { label: 'Experiments', value: rows.length, digits: 0 , kind: 'count'},
          { label: 'Valid', value: live, digits: 0 },
          { label: 'Void', value: rows.length - live, digits: 0, title: 'Invalidated, and kept in the record rather than removed from it' },
        ]}
      />

      <Strip metrics={[
        { label: 'Experiments', value: rows.length, digits: 0 , kind: 'count'},
        { label: 'Valid', value: live, digits: 0 },
        { label: 'Void', value: rows.length - live, digits: 0, title: 'Invalidated, and kept in the record rather than removed from it' },
      ]} />

      <Panel title="Registry" subtitle={`${rows.length} recorded`} flush>
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.experiment_id}
          density="compact" filterPlaceholder="filter experiments"
          selectedKey={selected ?? undefined}
          onSelect={(r) => {
            setSelected(r.experiment_id)
            recordVisit({ kind: 'experiment', id: r.experiment_id, label: r.experiment_id, detail: r.void ? 'void' : r.status })
          }}
        />
      </Panel>

      {!selected ? (
        <Panel title="Detail">
          <StateBlock state="unknown" title="No experiment selected" detail="Choose a row to see its dataset sources, the features it used, and its fold results." />
        </Panel>
      ) : detailError?.id === selected ? (
        <Panel title="Detail" state="unavailable">
          <StateBlock state="unavailable" title={`${selected} could not be read`} detail={detailError.message} />
        </Panel>
      ) : detail?.id !== selected ? (
        <Panel title="Detail" state="waking"><StateBlock state="waking" title={`Reading ${selected}`} /></Panel>
      ) : (
        <>
          <Panel
            title="Experiment"
            subtitle={detail.data.experiment_id ?? selected}
            state={detail.data.void ? 'unavailable' : 'recorded'}
            actions={<Link href="/terminal/evidence" className="sys-meta" style={{ color: 'var(--ink)' }}>Evidence →</Link>}
          >
            {detail.data.void ? (
              <StateBlock state="unavailable" title="This experiment is void" detail={detail.data.void_reason ?? undefined} />
            ) : null}
            <table className="sys-table sys-table--compact">
              <tbody>
                <tr><td>Generated</td><td className="num">{detail.data.generated_at ?? '—'}</td></tr>
                <tr><td>Fingerprint</td><td className="num" style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--t-micro)' }}>{detail.data.fingerprint ?? '—'}</td></tr>
                <tr><td>Features used</td><td className="num"><Value value={detail.data.features_used?.length ?? null} digits={0} /></td></tr>
                <tr><td>Dataset sources</td><td className="num"><Value value={detail.data.dataset_sources?.length ?? null} digits={0} /></td></tr>
                <tr><td>Folds</td><td className="num"><Value value={detail.data.fold_rows?.length ?? null} digits={0} /></td></tr>
              </tbody>
            </table>
          </Panel>

          <ExperimentEvidence
            integrity={detail.data.integrity as never}
            controls={detail.data.negative_controls as never}
            plan={detail.data.walk_forward_plan as never}
            costSensitivity={detail.data.cost_sensitivity as never}
            pbo={detail.data.probability_of_backtest_overfitting as never}
          />

          {detail.data.dataset_sources?.length ? (
            <Panel title="Dataset sources" subtitle="point-in-time and survivorship as recorded at run time" flush>
              <div className="sys-scroll-x">
                <table className="sys-table sys-table--compact">
                  <thead>
                    <tr>
                      <th>Dataset</th><th>Role</th><th className="num">Rows</th>
                      <th>From</th><th>To</th><th>Point in time</th><th>Survivorship</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.dataset_sources.map((d) => (
                      <tr key={`${d.dataset_id}-${d.role ?? ''}`}>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{d.dataset_id}</td>
                        <td>{d.role ?? '—'}</td>
                        <td className="num"><Value value={d.rows ?? null} digits={0} /></td>
                        <td className="num">{d.min_date ?? '—'}</td>
                        <td className="num">{d.max_date ?? '—'}</td>
                        <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{d.point_in_time_status ?? '—'}</span></td>
                        <td><span className="sys-meta" style={{ color: 'var(--ink)' }}>{d.survivorship_status ?? '—'}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          ) : null}
        </>
      )}
    </>
  )
}
