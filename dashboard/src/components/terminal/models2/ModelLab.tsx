'use client'

import { useEffect, useMemo, useState } from 'react'

import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { Panel, Prose, StateBlock, Status, Strip } from '@/components/system'
import { TableSkeleton } from '@/components/system/composition'
import { readResource } from '@/lib/resource'

interface FamilyRow {
  family: string
  model_name: string
  route: string
  configurations: Array<Record<string, unknown>>
  status: 'READY' | 'BLOCKED'
  reason: string
}

interface TrialRow {
  trial_id: string
  phase: string
  model_family: string
  model_name: string
  outer_fold: number
  status: string
  hyperparameters: Record<string, unknown>
  metrics: {
    mean_rank_ic?: number | null
    hac_t_stat?: number | null
    train_validation_ic_gap?: number | null
    runtime_warnings?: string[]
  }
  runtime: { wall_seconds?: number | null }
}

interface RetainedTrialRow extends TrialRow {
  error?: string | null
  git_commit: string
}

interface Payload {
  status: string
  message?: string
  campaign_id: string
  research_status: string
  campaign_stage: string
  trials: number
  statuses: Record<string, number>
  declared_families: FamilyRow[]
  completed_trials: TrialRow[]
  retained_noncomplete_trials: RetainedTrialRow[]
  smoke_outcome: {
    outer_evaluations: number
    positive_outer_rank_ic: number
    negative_outer_rank_ic: number
    candidate_eligible: boolean
    reason: string
  }
  dataset: {
    dataset_id: string
    feature_set_id: string
    integrity_status: string
    revenue_affected_feature_sets: string
  }
  holdout: { start: string; end: string; touched: boolean }
  exp012: { status: string }
}

const fmt = (value: number | null | undefined, digits = 4) =>
  value === null || value === undefined ? '—' : value.toFixed(digits)

export default function ModelLab() {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    readResource<Payload>('/api/quant/model-lab', 'artifact')
      .then((payload) => { if (alive) setData(payload) })
      .catch((reason: Error) => { if (alive) setError(reason.message) })
    return () => { alive = false }
  }, [])

  const familyColumns: DataColumn<FamilyRow>[] = useMemo(() => [
    { key: 'family', header: 'Family', text: (row) => row.family, render: (row) => <span className="sys-mono">{row.family}</span> },
    { key: 'model', header: 'Model', text: (row) => row.model_name, render: (row) => row.model_name },
    { key: 'route', header: 'Compute', text: (row) => row.route, render: (row) => <span className="sys-meta">{row.route}</span> },
    { key: 'space', header: 'Declared configs', sort: (row) => row.configurations.length, text: (row) => String(row.configurations.length), render: (row) => row.configurations.length },
    { key: 'state', header: 'State', text: (row) => row.status, render: (row) => <Status state={row.status === 'READY' ? 'experimental' : 'blocked'} label={row.status} /> },
    { key: 'reason', header: 'Reason', text: (row) => row.reason, render: (row) => <span className="sys-meta">{row.reason}</span> },
  ], [])

  const outer = data?.completed_trials.filter((trial) => trial.phase === 'OUTER_EVALUATION') ?? []
  const trialColumns: DataColumn<TrialRow>[] = useMemo(() => [
    { key: 'model', header: 'Model', text: (row) => row.model_name, render: (row) => <span className="sys-mono">{row.model_name}</span> },
    { key: 'fold', header: 'Outer fold', sort: (row) => row.outer_fold, text: (row) => String(row.outer_fold), render: (row) => row.outer_fold },
    { key: 'ic', header: 'Rank IC', sort: (row) => row.metrics.mean_rank_ic ?? null, text: (row) => fmt(row.metrics.mean_rank_ic), render: (row) => <span className="sys-num">{fmt(row.metrics.mean_rank_ic)}</span> },
    { key: 't', header: 'HAC t', sort: (row) => row.metrics.hac_t_stat ?? null, text: (row) => fmt(row.metrics.hac_t_stat, 2), render: (row) => <span className="sys-num">{fmt(row.metrics.hac_t_stat, 2)}</span> },
    { key: 'gap', header: 'Train − validation IC', sort: (row) => row.metrics.train_validation_ic_gap ?? null, text: (row) => fmt(row.metrics.train_validation_ic_gap), render: (row) => <span className="sys-num">{fmt(row.metrics.train_validation_ic_gap)}</span> },
    { key: 'runtime', header: 'Runtime', sort: (row) => row.runtime.wall_seconds ?? null, text: (row) => fmt(row.runtime.wall_seconds, 1), render: (row) => <span className="sys-meta">{fmt(row.runtime.wall_seconds, 1)} s</span> },
    { key: 'status', header: 'Research state', text: () => 'EXPLORATORY', render: () => <Status state="experimental" label="EXPLORATORY" /> },
  ], [])

  const retainedColumns: DataColumn<RetainedTrialRow>[] = useMemo(() => [
    { key: 'model', header: 'Model', text: (row) => row.model_name, render: (row) => <span className="sys-mono">{row.model_name}</span> },
    { key: 'phase', header: 'Phase', text: (row) => row.phase, render: (row) => <span className="sys-meta">{row.phase}</span> },
    { key: 'fold', header: 'Fold', sort: (row) => row.outer_fold, text: (row) => String(row.outer_fold), render: (row) => row.outer_fold },
    { key: 'state', header: 'State', text: (row) => row.status, render: (row) => <Status state={row.status === 'FAILED' ? 'blocked' : 'unknown'} label={row.status} /> },
    { key: 'reason', header: 'Retained reason', text: (row) => row.error ?? '', render: (row) => <span className="sys-meta">{row.error || 'No reason recorded'}</span> },
    { key: 'commit', header: 'Method commit', text: (row) => row.git_commit, render: (row) => <span className="sys-mono">{row.git_commit.slice(0, 8)}</span> },
  ], [])

  if (error) return <StateBlock state="unavailable" title="Model Lab unavailable" detail={error} />
  if (!data) return <Panel title="Model Lab" state="waking" flush><TableSkeleton rows={8} columns={6} /></Panel>
  if (data.status !== 'AVAILABLE') return <StateBlock state="unknown" title="Model Lab not configured" detail={data.message} />

  return (
    <>
      <Panel title={data.campaign_id} subtitle={`declared universe · nested temporal CV · ${data.campaign_stage}`} state="experimental">
        <Strip metrics={[
          { label: 'Declared families', value: data.declared_families.length, kind: 'count' },
          { label: 'Recorded trials', value: data.trials, kind: 'count' },
          { label: 'Complete', value: data.statuses.COMPLETE ?? 0, kind: 'count' },
          { label: 'Failed', value: data.statuses.FAILED ?? 0, kind: 'count' },
          { label: 'Invalid retained', value: data.statuses.INVALID ?? 0, kind: 'count' },
        ]} />
        <Prose>
          Exploratory only. Hyperparameters are selected inside each outer training window;
          outer validation is evaluated once. There is no winner score and no automatic promotion.
        </Prose>
        <Prose>
          Smoke outcome: {data.smoke_outcome.positive_outer_rank_ic} positive and{' '}
          {data.smoke_outcome.negative_outer_rank_ic} negative outer Rank IC observations across{' '}
          {data.smoke_outcome.outer_evaluations} model families. Candidate eligible:{' '}
          {String(data.smoke_outcome.candidate_eligible)}. {data.smoke_outcome.reason}
        </Prose>
        <Prose size="fine">
          Dataset {data.dataset.dataset_id} · {data.dataset.feature_set_id} · {data.dataset.integrity_status}.
          Revenue-affected feature sets: {data.dataset.revenue_affected_feature_sets}. Final holdout touched: {String(data.holdout.touched)}.
          EXP-012: {data.exp012.status}.
        </Prose>
      </Panel>

      <Panel title="Declared model universe" subtitle="blocked families stay visible" flush>
        <DataTable columns={familyColumns} rows={data.declared_families} rowKey={(row) => row.model_name} density="compact" filterPlaceholder="filter model families" />
      </Panel>

      <Panel title="Outer-fold evidence" subtitle="no best-seed selection" flush>
        {outer.length ? (
          <DataTable columns={trialColumns} rows={outer} rowKey={(row) => row.trial_id} density="compact" filterPlaceholder="filter trial evidence" />
        ) : (
          <StateBlock state="unknown" title="No outer evaluations published" detail="The declared universe remains visible; no result is invented." />
        )}
      </Panel>

      <Panel title="Retained failures and invalid trials" subtitle="nothing disappears from the ledger" flush>
        {data.retained_noncomplete_trials.length ? (
          <DataTable columns={retainedColumns} rows={data.retained_noncomplete_trials} rowKey={(row) => row.trial_id} density="compact" filterPlaceholder="filter retained trial evidence" />
        ) : (
          <StateBlock state="unknown" title="No failed or invalid trials" detail="Future failures and invalidations will remain visible here." />
        )}
      </Panel>
    </>
  )
}
