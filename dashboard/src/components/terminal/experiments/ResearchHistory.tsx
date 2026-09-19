/**
 * Research history: every study, including the negative and the not-yet-run.
 *
 * Nothing on this table can read as promoted. Each row carries what the study
 * asked, what it found and what it did not, and whether the sealed holdout was
 * spent. A study that has not been run says so; a negative result stays visible.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import { Panel, StateBlock, Status } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { TableSkeleton } from '@/components/system/composition'
import { readResource } from '@/lib/resource'

export interface HistoryRow {
  id: string
  status: 'COMPLETE' | 'PREREGISTERED_NOT_RUN' | 'PREPARED_NOT_RUN'
  result: string
  title: string
  summary: string
  caveat?: string
  negative_or_inconclusive: boolean
  promoted: boolean
  holdout_touched: boolean
}

export interface HistoryPayload {
  experiments: HistoryRow[]
  promoted_models: number
  holdout: { window: string; state: string; note: string }
}

/** The label a reader sees for a row's run state. Not-run studies are never dressed as results. */
export function runStateLabel(status: HistoryRow['status']): string {
  if (status === 'COMPLETE') return 'complete'
  if (status === 'PREREGISTERED_NOT_RUN') return 'preregistered · not run'
  return 'prepared · not run'
}

export default function ResearchHistory() {
  const [data, setData] = useState<HistoryPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    readResource<HistoryPayload>('/api/quant/research-history', 'artifact')
      .then((d) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const columns: DataColumn<HistoryRow>[] = useMemo(() => [
    { key: 'id', header: 'Study', width: '11%', sort: (r) => r.id, text: (r) => r.id, render: (r) => <span className="sys-mono">{r.id}</span> },
    {
      key: 'state', header: 'Run state', width: '16%', sort: (r) => r.status, text: (r) => runStateLabel(r.status),
      render: (r) => <Status state={r.status === 'COMPLETE' ? 'recorded' : 'unknown'} label={runStateLabel(r.status)} />,
    },
    {
      key: 'result', header: 'Recorded result', width: '20%', sort: (r) => r.result, text: (r) => r.result,
      render: (r) => (r.status === 'COMPLETE'
        ? <Status state={r.negative_or_inconclusive ? 'blocked' : 'recorded'} label={r.result} />
        : <span className="sys-null" title="no result exists">—</span>),
    },
    { key: 'summary', header: 'What it found', text: (r) => `${r.title} ${r.summary} ${r.caveat ?? ''}`, render: (r) => <span className="sys-meta">{r.title}. {r.summary}{r.caveat ? ` Caveat: ${r.caveat}.` : ''}</span> },
    { key: 'holdout', header: 'Holdout', width: '10%', text: (r) => (r.holdout_touched ? 'spent' : 'untouched'), render: (r) => <span className="sys-meta sys-meta--strong">{r.holdout_touched ? 'spent' : 'untouched'}</span> },
  ], [])

  if (error) {
    return (
      <Panel title="Research history" state="unavailable">
        <StateBlock state="unavailable" title="The research history could not be read" detail={`Request failed: ${error}. No list is shown in its place.`} />
      </Panel>
    )
  }
  if (!data) {
    return <Panel title="Research history" state="waking" flush><TableSkeleton rows={6} columns={3} /></Panel>
  }
  if (data.experiments.length === 0) {
    return (
      <Panel title="Research history">
        <StateBlock state="unknown" title="No studies recorded" detail="An empty history is reported as empty, not as a clean record." />
      </Panel>
    )
  }
  return (
    <Panel
      title="Research history"
      subtitle={`${data.experiments.length} studies · ${data.promoted_models} models promoted · holdout ${data.holdout.state.toLowerCase()} (${data.holdout.window})`}
      flush
    >
      <DataTable columns={columns} rows={data.experiments} rowKey={(r) => r.id} density="compact" filterPlaceholder="filter studies" />
    </Panel>
  )
}
