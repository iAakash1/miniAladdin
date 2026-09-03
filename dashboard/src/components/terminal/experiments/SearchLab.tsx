'use client'

/**
 * The hyperparameter search — progress, families, overfitting, and what the
 * search costs itself in significance.
 *
 * Three rules this file exists to enforce visually.
 *
 * **A running search is progress, not a result.** While the state is RUNNING
 * every panel says so, and no configuration is styled as a winner before
 * selection has run. Selection happens separately, behind predeclared gates.
 *
 * **Green means a gate passed, not that a number is positive.** The leaderboard
 * is toned by each row's overfitting diagnosis rather than by its information
 * coefficient, so the highest IC in the table can — and here does — render as a
 * warning. A configuration that fit the training folds beautifully and the
 * validation folds poorly is the single most dangerous row on this page,
 * because it is also the one that sorts to the top.
 *
 * **The bar is shown beside the number.** An observed maximum |t| is meaningless
 * without the threshold a search of this size has to clear, so the two are never
 * displayed apart. A search wide enough will always produce an impressive-looking
 * statistic; the question is only ever whether it beat what noise would give you
 * for free.
 */

import { useEffect, useMemo, useState } from 'react'

import { Grid, Panel, Prose, StateBlock, Status, Strip, Value } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { BarRows } from '@/components/system/charts'
import type { ResearchState } from '@/components/system'

interface ConfigRow {
  config_id: string
  family: string
  stage: string
  arm: string | null
  target: string | null
  feature_count: number | null
  mean_ic: number | null
  ic_t_stat: number | null
  ic_ir: number | null
  train_mean_ic: number | null
  train_ic_gap: number | null
  fold_ic_positive_rate: number | null
  folds: number | null
  diagnosis: 'HEALTHY' | 'OVERFIT' | 'UNSTABLE' | 'UNDERFIT' | 'FAILED'
}

interface FamilyRow {
  family: string
  evaluated: number
  failed: number
  overfit: number
  best_ic: number | null
  best_t: number | null
  best_gap: number | null
  worst_gap: number | null
  seconds: number | null
}

interface MultipleTesting {
  prior_trials: number | null
  new_trials: number | null
  cumulative_trials: number | null
  expected_max_abs_t_under_null: number | null
  bonferroni_threshold_5pct?: number | null
  observed_max_abs_t: number | null
  observed_clears_threshold: boolean | null
  interpretation?: string
  caveat?: string
}

interface SearchState {
  available: boolean
  experiment_id: string
  state: 'RUNNING' | 'COMPLETE' | 'NOT STARTED'
  detail?: string
  configurations_evaluated?: number
  configurations_planned?: number | null
  configurations_failed?: number
  progress_pct?: number | null
  stages?: { stage: string; evaluated: number; failed: number; worker_seconds: number }[]
  families?: FamilyRow[]
  diagnoses?: Record<string, number>
  leaderboard?: ConfigRow[]
  multiple_testing?: MultipleTesting
  families_advanced?: string[] | null
  workers?: number | null
  runtime_seconds?: number | null
  generated_at?: string | null
  holdout?: { touched?: boolean; note?: string } | null
  note?: string
}

/** The sequence the stages actually run in. Order is the point. */
const STAGE_LABEL: Record<string, string> = {
  screen: 'screen — every family, coarse',
  tune: 'tune — the families that competed',
  context: 'context — arms × targets',
  robustness: 'robustness — neighbours of each finalist',
}

/**
 * A diagnosis maps to a research state, not to a colour directly. OVERFIT is
 * `stale` rather than `blocked`: the configuration is real and was measured,
 * it just cannot be trusted out of sample, which is a different claim from
 * "this failed".
 */
const DIAGNOSIS_STATE: Record<string, ResearchState> = {
  HEALTHY: 'recorded',
  OVERFIT: 'stale',
  UNSTABLE: 'stale',
  UNDERFIT: 'unavailable',
  FAILED: 'blocked',
}

export default function SearchLab({ experimentId = 'EXP-007' }: { experimentId?: string }) {
  const [data, setData] = useState<SearchState | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/quant/search/${encodeURIComponent(experimentId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: SearchState) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [experimentId])

  const columns = useMemo<DataColumn<ConfigRow>[]>(() => [
    {
      key: 'config', header: 'Configuration', sort: (r) => r.config_id,
      render: (r) => <span className="sys-mono">{r.config_id}</span>,
    },
    { key: 'family', header: 'Family', sort: (r) => r.family, render: (r) => <span className="sys-meta">{r.family}</span> },
    { key: 'stage', header: 'Stage', optional: true, sort: (r) => r.stage, render: (r) => <span className="sys-meta">{r.stage}</span> },
    {
      key: 'diagnosis', header: 'Diagnosis', sort: (r) => r.diagnosis,
      // Toned by diagnosis, never by IC. The highest coefficient in this table
      // is frequently the least trustworthy row in it.
      render: (r) => <Status state={DIAGNOSIS_STATE[r.diagnosis] ?? 'unavailable'} label={r.diagnosis} />,
    },
    { key: 'ic', header: 'IC', numeric: true, sort: (r) => r.mean_ic, render: (r) => <Value value={r.mean_ic} kind="ic" /> },
    { key: 't', header: 't', numeric: true, sort: (r) => r.ic_t_stat, render: (r) => <Value value={r.ic_t_stat} kind="tstat" /> },
    {
      key: 'gap', header: 'Train gap', numeric: true, sort: (r) => r.train_ic_gap,
      render: (r) => <Value value={r.train_ic_gap} kind="ic" />,
    },
    {
      key: 'pos', header: 'Folds positive', numeric: true, optional: true, sort: (r) => r.fold_ic_positive_rate,
      render: (r) => <Value value={r.fold_ic_positive_rate} kind="share" />,
    },
    {
      key: 'folds', header: 'Folds', numeric: true, optional: true, sort: (r) => r.folds,
      render: (r) => <Value value={r.folds} kind="count" />,
    },
  ], [])

  if (error) {
    return (
      <Panel title="Search" state="unavailable">
        <StateBlock state="unavailable" title="The search could not be read" detail={`Request failed: ${error}. Nothing is shown in its place.`} />
      </Panel>
    )
  }
  if (!data) return null
  if (!data.available || data.state === 'NOT STARTED') {
    return (
      <Panel title="Search" state="unavailable">
        <StateBlock
          state="unavailable"
          title={`No search has run for ${data.experiment_id ?? experimentId}`}
          detail={data.detail}
        />
      </Panel>
    )
  }

  const running = data.state === 'RUNNING'
  const mt = data.multiple_testing
  const diagnoses = data.diagnoses ?? {}
  const totalDiagnosed = Object.values(diagnoses).reduce((a, b) => a + b, 0)
  const overfit = diagnoses.OVERFIT ?? 0

  return (
    <>
      <Panel
        title="Search"
        subtitle={data.experiment_id}
        state={running ? 'experimental' : 'recorded'}
        badge={running ? 'PARTIAL — SEARCH RUNNING' : 'COMPLETE'}
        badgeTone={running ? 'warn' : 'muted'}
        asOf={data.generated_at ?? undefined}
      >
        <Strip metrics={[
          { label: 'Evaluated', value: data.configurations_evaluated ?? null, kind: 'count' },
          { label: 'Planned', value: data.configurations_planned ?? null, kind: 'count' },
          { label: 'Failed', value: data.configurations_failed ?? null, kind: 'count' },
          { label: 'Workers', value: data.workers ?? null, kind: 'count' },
          { label: 'Worker time', value: data.runtime_seconds ?? null, kind: 'seconds' },
        ]} />

        {running ? (
          <Prose caution>
            This search has not finished. Nothing below is a result, and no
            configuration here has been selected — selection runs separately,
            behind gates declared before the search started.
          </Prose>
        ) : data.note ? (
          <Prose>{data.note}</Prose>
        ) : null}

        {data.stages?.length ? (
          <div style={{ marginTop: 'var(--d-4)' }}>
            <BarRows
              rows={data.stages.map((s) => ({
                label: STAGE_LABEL[s.stage] ?? s.stage,
                value: s.evaluated,
                note: `${s.failed} failed · ${Math.round(s.worker_seconds / 3600)}h worker time`,
              }))}
            />
          </div>
        ) : null}
      </Panel>

      {mt ? (
        <Panel
          title="What the search cost itself in significance"
          state="recorded"
          badge={mt.observed_clears_threshold ? 'CLEARS THE NULL BAR' : 'BELOW THE NULL BAR'}
          badgeTone={mt.observed_clears_threshold ? 'pass' : 'fail'}
        >
          {/* Never the observed statistic without the bar it has to clear. */}
          <Strip metrics={[
            { label: 'Prior trials', value: mt.prior_trials, kind: 'count' },
            { label: 'This search', value: mt.new_trials, kind: 'count' },
            { label: 'Cumulative', value: mt.cumulative_trials, kind: 'count' },
            { label: 'Observed max |t|', value: mt.observed_max_abs_t, kind: 'tstat' },
            { label: 'Expected under null', value: mt.expected_max_abs_t_under_null, kind: 'tstat' },
            { label: 'Bonferroni 5%', value: mt.bonferroni_threshold_5pct ?? null, kind: 'tstat' },
          ]} />
          {mt.interpretation ? <Prose>{mt.interpretation}</Prose> : null}
          {mt.caveat ? <Prose caution>{mt.caveat}</Prose> : null}
        </Panel>
      ) : null}

      {totalDiagnosed > 0 ? (
        <Panel title="How the search fit" state="recorded">
          <Grid>
            {Object.entries(diagnoses).map(([name, count]) => (
              <div key={name} className="sys-panel-inset" data-tone={name === 'HEALTHY' ? 'pass' : name === 'FAILED' ? 'fail' : undefined}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--d-2)' }}>
                  <Status state={DIAGNOSIS_STATE[name] ?? 'unavailable'} label={name} />
                  <Value value={count} kind="count" />
                </div>
                <span className="sys-meta">
                  <Value value={count / totalDiagnosed} kind="share" /> of configurations
                </span>
              </div>
            ))}
          </Grid>
          <Prose caution>
            {overfit > totalDiagnosed / 2 ? (
              <>
                <strong>Most of this search overfitted.</strong> {overfit} of{' '}
                {totalDiagnosed} configurations fit their training folds
                substantially better than their validation folds. That is not a
                fault in the search — a wide search is supposed to find the edges
                of what the data supports — but it means the leaderboard below is
                mostly a ranking of how well configurations memorised, and the
                diagnosis column matters more than the coefficient column.
              </>
            ) : (
              <>
                The diagnosis column matters more than the coefficient column. A
                configuration that fit the training folds well and the validation
                folds poorly sorts to the top of an IC ranking while being the
                least trustworthy row in it.
              </>
            )}
          </Prose>
        </Panel>
      ) : null}

      {data.families?.length ? (
        <Panel title="By family" state="recorded">
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th>Family</th><th className="num">Evaluated</th><th className="num">Overfit</th>
                  <th className="num">Best IC</th><th className="num">Best t</th>
                  <th className="num">Best gap</th><th className="num">Worst gap</th>
                  <th className="num">Worker time</th>
                </tr>
              </thead>
              <tbody>
                {data.families.map((fam) => (
                  <tr key={fam.family}>
                    <td className="sys-mono">{fam.family}</td>
                    <td className="num"><Value value={fam.evaluated} kind="count" /></td>
                    <td className="num">
                      <Value value={fam.overfit} kind="count" />
                      <span className="sys-meta"> / <Value value={fam.overfit / Math.max(1, fam.evaluated)} kind="share" /></span>
                    </td>
                    <td className="num"><Value value={fam.best_ic} kind="ic" /></td>
                    <td className="num"><Value value={fam.best_t} kind="tstat" /></td>
                    <td className="num"><Value value={fam.best_gap} kind="ic" /></td>
                    <td className="num"><Value value={fam.worst_gap} kind="ic" /></td>
                    <td className="num"><Value value={fam.seconds} kind="seconds" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.families_advanced?.length ? (
            <Prose size="tight">
              Advanced to the next stage: {data.families_advanced.join(', ')}.
            </Prose>
          ) : null}
        </Panel>
      ) : null}

      {data.leaderboard?.length ? (
        <Panel
          title="Leaderboard"
          subtitle={`${data.leaderboard.length} configurations`}
          state={running ? 'experimental' : 'recorded'}
          badge={running ? 'PARTIAL' : undefined}
          badgeTone="warn"
        >
          <Prose size="tight">
            Sorted by information coefficient, coloured by diagnosis. Those two
            orderings disagree, and where they disagree the diagnosis is the one
            to read.
          </Prose>
          <DataTable
            columns={columns}
            rows={data.leaderboard}
            rowKey={(r) => r.config_id}
            density="compact"
            initialSort={{ key: 'ic', direction: 'desc' }}
            focusKey={(r) => r.family}
          />
        </Panel>
      ) : null}

      {data.holdout ? (
        <Panel title="Holdout" state={data.holdout.touched ? 'blocked' : 'recorded'}>
          <Prose>
            {data.holdout.touched
              ? 'The holdout has been touched by this search.'
              : 'The holdout was not touched by this search.'}
            {data.holdout.note ? ` ${data.holdout.note}` : ''}
          </Prose>
        </Panel>
      ) : null}
    </>
  )
}
