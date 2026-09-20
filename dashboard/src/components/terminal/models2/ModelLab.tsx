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
  campaign_results?: CampaignResults | null
}

interface ModelCard {
  model: string
  family: string
  research_status: string
  ordering: {
    mean_rank_ic?: number | null
    hac_t_stat?: number | null
    icir?: number | null
    positive_fold_count: number
    worst_fold_rank_ic?: number | null
    train_validation_ic_gap?: number | null
    overfit_warning: boolean
  }
  economics: {
    cost_sweep: Record<string, {
      gross_sharpe?: number | null
      net_sharpe?: number | null
      annualised_turnover?: number | null
      net_max_drawdown?: number | null
      cost_share_of_gross?: number | null
    }>
  }
  runtime: { outer_wall_seconds?: number | null }
  method_commit: string
}

interface CampaignResults {
  outer_oos_only: boolean
  method_commit: string
  models: Record<string, ModelCard>
  prediction_diversity: Record<string, Record<string, number>>
  multiple_testing: {
    total_registry_attempts: number
    hyperparameter_trials: number
    inner_fits: number
    outer_evaluations: number
    invalid_trials: number
    failed_trials: number
    pbo_selected_family_returns?: { pbo?: number | null }
  }
  candidate_eligibility: { count: number; status: string }
  ensemble: { status: string; reason?: string }
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

  const modelCards = Object.values(data?.campaign_results?.models ?? {})
  const cardColumns: DataColumn<ModelCard>[] = useMemo(() => [
    { key: 'model', header: 'Model', text: (row) => row.model, render: (row) => <span className="sys-mono">{row.model}</span> },
    { key: 'ic', header: 'Mean Rank IC', sort: (row) => row.ordering.mean_rank_ic ?? null, text: (row) => fmt(row.ordering.mean_rank_ic), render: (row) => <span className="sys-num">{fmt(row.ordering.mean_rank_ic)}</span> },
    { key: 'hac', header: 'HAC t', sort: (row) => row.ordering.hac_t_stat ?? null, text: (row) => fmt(row.ordering.hac_t_stat, 2), render: (row) => <span className="sys-num">{fmt(row.ordering.hac_t_stat, 2)}</span> },
    { key: 'folds', header: '+ folds', sort: (row) => row.ordering.positive_fold_count, text: (row) => String(row.ordering.positive_fold_count), render: (row) => `${row.ordering.positive_fold_count}/8` },
    { key: 'worst', header: 'Worst fold', sort: (row) => row.ordering.worst_fold_rank_ic ?? null, text: (row) => fmt(row.ordering.worst_fold_rank_ic), render: (row) => <span className="sys-num">{fmt(row.ordering.worst_fold_rank_ic)}</span> },
    { key: 'gap', header: 'Train − validation', sort: (row) => row.ordering.train_validation_ic_gap ?? null, text: (row) => fmt(row.ordering.train_validation_ic_gap), render: (row) => <Status state={row.ordering.overfit_warning ? 'blocked' : 'recorded'} label={fmt(row.ordering.train_validation_ic_gap)} /> },
    { key: 'net', header: 'Net Sharpe · 10 bp', sort: (row) => row.economics.cost_sweep['10bp']?.net_sharpe ?? null, text: (row) => fmt(row.economics.cost_sweep['10bp']?.net_sharpe), render: (row) => <span className="sys-num">{fmt(row.economics.cost_sweep['10bp']?.net_sharpe)}</span> },
    { key: 'turnover', header: 'Turnover', sort: (row) => row.economics.cost_sweep['10bp']?.annualised_turnover ?? null, text: (row) => fmt(row.economics.cost_sweep['10bp']?.annualised_turnover, 2), render: (row) => <span className="sys-num">{fmt(row.economics.cost_sweep['10bp']?.annualised_turnover, 2)}×</span> },
    { key: 'runtime', header: 'Outer runtime', sort: (row) => row.runtime.outer_wall_seconds ?? null, text: (row) => fmt(row.runtime.outer_wall_seconds, 1), render: (row) => <span className="sys-meta">{fmt(row.runtime.outer_wall_seconds, 1)} s</span> },
  ], [])

  const diversityRows = Object.entries(data?.campaign_results?.prediction_diversity ?? {}).map(([model, values]) => ({ model, values }))
  const diversityModels = Object.keys(data?.campaign_results?.prediction_diversity ?? {})
  const diversityColumns: DataColumn<{ model: string; values: Record<string, number> }>[] = [
    { key: 'model', header: 'Model', text: (row) => row.model, render: (row) => <span className="sys-mono">{row.model}</span> },
    ...diversityModels.map((model) => ({
      key: model, header: model, sort: (row: { values: Record<string, number> }) => row.values[model] ?? null,
      text: (row: { values: Record<string, number> }) => fmt(row.values[model], 2),
      render: (row: { values: Record<string, number> }) => <span className="sys-num">{fmt(row.values[model], 2)}</span>,
    })),
  ]

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

      {data.campaign_results ? (
        <>
          <Panel title="Complete outer-OOS model cards" subtitle="eight folds · frozen 21-session economics" flush>
            <DataTable columns={cardColumns} rows={modelCards} rowKey={(row) => row.model} density="compact" filterPlaceholder="compare completed model cards" />
          </Panel>
          <Panel title="Multiple-testing context" subtitle="selection evidence, not a significance badge">
            <Strip metrics={[
              { label: 'Registry attempts', value: data.campaign_results.multiple_testing.total_registry_attempts, kind: 'count' },
              { label: 'Hyperparameter trials', value: data.campaign_results.multiple_testing.hyperparameter_trials, kind: 'count' },
              { label: 'Inner fits', value: data.campaign_results.multiple_testing.inner_fits, kind: 'count' },
              { label: 'Outer fits', value: data.campaign_results.multiple_testing.outer_evaluations, kind: 'count' },
              { label: 'Eligible candidates', value: data.campaign_results.candidate_eligibility.count, kind: 'count' },
            ]} />
            <Prose>
              {data.campaign_results.candidate_eligibility.status}. PBO on selected-family OOS return series:{' '}
              {fmt(data.campaign_results.multiple_testing.pbo_selected_family_returns?.pbo, 3)}. Ensemble:{' '}
              {data.campaign_results.ensemble.status}{data.campaign_results.ensemble.reason ? ` — ${data.campaign_results.ensemble.reason}` : ''}.
            </Prose>
          </Panel>
          <Panel title="Prediction diversity" subtitle="pairwise rank correlation on identical outer-OOS rows" flush>
            <DataTable columns={diversityColumns} rows={diversityRows} rowKey={(row) => row.model} density="compact" filterPlaceholder="filter prediction families" />
          </Panel>
        </>
      ) : (
        <StateBlock state="unknown" title="Complete campaign report pending" detail="Partial folds are retained, but cross-family comparison waits for all eight outer folds." />
      )}

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
