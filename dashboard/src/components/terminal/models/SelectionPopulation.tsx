'use client'

/**
 * Every model evaluated against one label — losers included — and the
 * population the winner was selected from.
 *
 * This is the panel that answers "is this skill or is it selection". The
 * leaderboard elsewhere in the product is sorted, and a sorted list read on its
 * own is an argument for its own top row. Here nothing is filtered: the
 * baselines that lost sit in the same table as the model that won, and the
 * distribution across experiments sits above both.
 *
 * The comparison that carries the weight is best against median. If the best of
 * thirteen experiments is roughly twice the median of those thirteen, the
 * winner is as consistent with a lucky draw from that population as it is with
 * a better model — and the honest response is to read the deflated Sharpe and
 * the overfitting probability rather than the rank.
 *
 * Baselines are marked rather than hidden. A model that cannot beat the
 * historical mean has not shown anything, and putting that mean in the same
 * table is the cheapest way to keep the question in front of the reader.
 */

import { useEffect, useMemo, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'

interface ModelRow {
  model_id: string
  kind: 'baseline' | 'learned'
  mean_ic: number | null
  ic_t_stat: number | null
  ic_ir: number | null
  train_mean_ic: number | null
  train_ic_gap: number | null
  fold_ic_positive_rate: number | null
  folds: number | null
  directional_edge?: number | null
}

interface Distribution {
  experiments: number
  metric: string
  best: number | null
  median: number | null
  worst: number | null
  mean: number | null
  std: number | null
  above_zero: number | null
  note?: string
}

interface Pbo {
  pbo?: number | null
  configurations?: number | null
  splits_evaluated?: number | null
  interpretation?: string
}

interface Report {
  status: string
  reason?: string
  label?: string
  horizon_sessions?: number
  models?: ModelRow[]
  experiment_distribution?: Distribution
  probability_of_backtest_overfitting?: Pbo
}

export default function SelectionPopulation({ label = 'fwd_rank_21' }: { label?: string }) {
  const [data, setData] = useState<Report | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/ml/labels/${encodeURIComponent(label)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Report) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [label])

  const columns = useMemo<DataColumn<ModelRow>[]>(() => [
    {
      key: 'model', header: 'Model', sort: (r) => r.model_id,
      render: (r) => (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--d-2)' }}>
          <span className="sys-mono">{r.model_id}</span>
          {/* Marked, never hidden. A model that cannot beat the historical mean
              has not shown anything, and the mean has to be visible to say so. */}
          {r.kind === 'baseline' ? <Status state="recorded" label="BASELINE" /> : null}
        </span>
      ),
    },
    { key: 'ic', header: 'IC', numeric: true, sort: (r) => r.mean_ic, render: (r) => <Value value={r.mean_ic} kind="ic" /> },
    { key: 't', header: 't', numeric: true, sort: (r) => r.ic_t_stat, render: (r) => <Value value={r.ic_t_stat} kind="tstat" /> },
    { key: 'ir', header: 'IC IR', numeric: true, optional: true, sort: (r) => r.ic_ir, render: (r) => <Value value={r.ic_ir} kind="ratio" /> },
    {
      key: 'train', header: 'Train IC', numeric: true, optional: true, sort: (r) => r.train_mean_ic,
      render: (r) => <Value value={r.train_mean_ic} kind="ic" />,
    },
    {
      key: 'gap', header: 'Train gap', numeric: true, sort: (r) => r.train_ic_gap,
      render: (r) => <Value value={r.train_ic_gap} kind="ic" />,
    },
    {
      key: 'pos', header: 'Folds positive', numeric: true, sort: (r) => r.fold_ic_positive_rate,
      render: (r) => <Value value={r.fold_ic_positive_rate} kind="share" />,
    },
    {
      key: 'folds', header: 'Folds', numeric: true, optional: true, sort: (r) => r.folds,
      render: (r) => <Value value={r.folds} kind="count" />,
    },
  ], [])

  if (error) {
    return (
      <Panel title="The population this was selected from" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The label report could not be read"
          detail={`Request failed: ${error}. Nothing is shown in its place.`}
        />
      </Panel>
    )
  }
  if (!data) return null
  if (data.status !== 'available') {
    return (
      <Panel title="The population this was selected from" state="unavailable">
        <StateBlock
          state="unavailable"
          title={`Nothing was evaluated for ${label}`}
          detail={data.reason}
        />
      </Panel>
    )
  }

  const models = data.models ?? []
  const dist = data.experiment_distribution
  const pbo = data.probability_of_backtest_overfitting

  // How far the winner sits above the middle of its own population. A ratio
  // near one means the best experiment was not much better than a typical one.
  const spread = dist?.best != null && dist?.median != null && dist.median !== 0
    ? dist.best / dist.median
    : null

  return (
    <>
      <Panel
        title="The population this was selected from"
        subtitle={data.label}
        state="recorded"
        badge={`${models.length} MODELS · NOTHING FILTERED`}
        badgeTone="muted"
      >
        {dist ? (
          <>
            <Strip metrics={[
              { label: 'Experiments', value: dist.experiments, kind: 'count' },
              { label: 'Best', value: dist.best, kind: 'ic' },
              { label: 'Median', value: dist.median, kind: 'ic' },
              { label: 'Worst', value: dist.worst, kind: 'ic', method: 'worst_realization' },
              { label: 'Dispersion', value: dist.std, kind: 'ic' },
              { label: 'Above zero', value: dist.above_zero, kind: 'count' },
            ]} />
            {spread !== null ? (
              <Prose tone="strong">
                The best experiment measures{' '}
                <Value value={spread} kind="multiple" /> the median of the{' '}
                {dist.experiments} run against this label. A winner that far above
                the middle of its own population is as consistent with a lucky
                draw as with a better model, which is why the deflated Sharpe and
                the overfitting probability decide it and the rank does not.
              </Prose>
            ) : null}
            {dist.note ? <Prose caution>{dist.note}</Prose> : null}
          </>
        ) : (
          <StateBlock
            state="unavailable"
            title="No experiment distribution was recorded"
            detail="Without it, the best result here cannot be read against the population it came from, so nothing on this page should be taken as evidence of skill."
          />
        )}

        {pbo?.pbo != null ? (
          <div style={{ marginTop: 'var(--d-4)' }}>
            <Strip metrics={[
              { label: 'Overfitting probability', value: pbo.pbo, kind: 'probability' },
              { label: 'Configurations', value: pbo.configurations ?? null, kind: 'count' },
              { label: 'Splits evaluated', value: pbo.splits_evaluated ?? null, kind: 'count' },
            ]} />
            {pbo.interpretation ? <Prose size="tight">{pbo.interpretation}</Prose> : null}
          </div>
        ) : null}
      </Panel>

      <Panel title="Every model, losers included" state="recorded">
        <Prose size="tight">
          Sorted by information coefficient, filtered by nothing. The baselines
          are in the same table as the learned models on purpose — a leaderboard
          read on its own is an argument for its own top row.
        </Prose>
        <DataTable
          columns={columns}
          rows={models}
          rowKey={(r) => r.model_id}
          density="compact"
          initialSort={{ key: 'ic', direction: 'desc' }}
          focusKey={(r) => r.model_id}
        />
      </Panel>
    </>
  )
}
