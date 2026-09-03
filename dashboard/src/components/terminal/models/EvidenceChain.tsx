/**
 * Model evidence chain.
 *
 * The question a model workspace has to answer is not "which model is best".
 * It is "should I trust this one", and the honest answer is usually a list of
 * things that have not been established yet.
 *
 * So the leaderboard is demoted to a selector and the workspace is the chain:
 * data, label, validation geometry, signal quality, portfolio behaviour after
 * costs, multiple-testing correction, and finally promotion — with the gates
 * that are unmet shown as the headline rather than buried under a rank.
 *
 * Every field comes from /api/ml/registry, which records all of this already
 * and which nothing in the product had ever called. `thresholds_not_met` is
 * the registry's own answer to "why is this blocked"; it is rendered verbatim,
 * including its "not recorded" entries, because absent evidence failing a gate
 * is the behaviour and not a gap in the display.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'

import Link from 'next/link'

import { Grid, Panel, Section, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { DataTable, type DataColumn } from '@/components/system/DataTable'
import { recordVisit, togglePin } from '@/lib/research/history'
import { ObjectHeader, StripSkeleton, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'
import Inspector from '@/components/system/Inspector'
import type { ResearchObject } from '@/lib/research/objects'

interface LeaderboardRow {
  key: string
  model_id: string
  label: string
  status: string
  mean_ic: number | null
  ic_t_stat: number | null
  fold_ic_positive_rate: number | null
  net_sharpe: number | null
  net_cagr: number | null
  max_drawdown: number | null
  annualised_turnover: number | null
  cost_share_of_gross?: number | null
}

interface Entry {
  key: string
  model_id: string
  label: string
  status: string
  version?: string
  task?: string
  features?: string[] | number
  seed?: number | null
  fingerprint?: string
  dataset_version?: string
  dataset_sources?: unknown[]
  training_start?: string
  training_end?: string
  validation_methodology?: string
  walk_forward?: Record<string, unknown>
  baseline_comparison?: Record<string, unknown>
  backtest?: Record<string, unknown>
  holdout_metrics?: Record<string, unknown>
  multiple_testing?: Record<string, unknown>
  leakage_evidence?: Record<string, unknown>
  reproducibility?: Record<string, unknown>
  thresholds_not_met?: Record<string, unknown>
  candidate_thresholds_not_met?: Record<string, unknown>
  eligible_for?: string[]
  git_commit?: string
  created_at?: string
}

interface Registry {
  status?: string
  summary: { entries: number; by_status: Record<string, number>; labels: string[]; path: string }
  leaderboard: LeaderboardRow[]
  entries: Entry[]
  promotion_gates: Record<string, string[]>
}

function statusState(status: string): ResearchState {
  switch (status) {
    case 'production': return 'production'
    case 'production_candidate': return 'candidate'
    case 'validated': return 'candidate'
    case 'retired': return 'unavailable'
    default: return 'experimental'
  }
}

/** A gate outcome. "not recorded" is a distinct thing from a numeric failure. */
function GateRow({ name, observed }: { name: string; observed: unknown }) {
  const missing = observed === 'not recorded' || observed === null || observed === undefined
  return (
    <tr>
      <td style={{ fontFamily: 'var(--font-mono)' }}>{name}</td>
      <td className="num">
        {missing
          ? <span className="sys-num sys-null" title="No value was recorded. Absent evidence is not passing evidence, so the gate is unmet.">not recorded</span>
          : typeof observed === 'number'
            ? <Value value={observed} digits={4} tone />
            : <span className="sys-num sys-neg">{String(observed)}</span>}
      </td>
      <td><Status state="blocked" label="unmet" /></td>
    </tr>
  )
}

function KeyValues({ data }: { data: Record<string, unknown> | undefined }) {
  const rows = Object.entries(data ?? {})
  if (!rows.length) {
    return <span className="sys-meta">not recorded</span>
  }
  return (
    <table className="sys-table sys-table--compact">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td style={{ fontFamily: 'var(--font-mono)', width: '55%' }}>{k}</td>
            <td className="num">
              {typeof v === 'number'
                ? <Value value={v} digits={4} />
                : v === null || v === undefined
                  ? <span className="sys-null">—</span>
                  : <span className="sys-meta" style={{ color: 'var(--ink)' }}>{String(v)}</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function EvidenceChain() {
  const [registry, setRegistry] = useState<Registry | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [inspecting, setInspecting] = useState<ResearchObject | null>(null)

  useEffect(() => {
    let alive = true
    fetch('/api/ml/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`registry ${r.status}`))))
      .then((d: Registry) => { if (alive) setRegistry(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])

  const columns: DataColumn<LeaderboardRow>[] = useMemo(() => [
    { key: 'model', header: 'Model', width: '26%', sort: (r) => r.model_id, text: (r) => r.model_id, render: (r) => <span style={{ fontFamily: 'var(--font-mono)' }}>{r.model_id}</span> },
    { key: 'label', header: 'Label', width: '14%', sort: (r) => r.label, text: (r) => r.label, render: (r) => <span className="sys-meta" style={{ color: 'var(--ink)' }}>{r.label}</span> },
    { key: 'status', header: 'Status', width: '14%', sort: (r) => r.status, text: (r) => r.status, render: (r) => <Status state={statusState(r.status)} label={r.status} /> },
    { key: 'ic', header: 'Mean IC', unit: 'rank corr.', numeric: true, sort: (r) => r.mean_ic, render: (r) => <Value measure="mean_ic" kind="ic" value={r.mean_ic} digits={4} signed tone /> },
    { key: 't', header: 'IC t-stat', unit: 'Newey-West', numeric: true, sort: (r) => r.ic_t_stat, render: (r) => <Value measure="ic_t_stat" kind="tstat" value={r.ic_t_stat} digits={2} signed /> },
    { key: 'ns', header: 'Net Sharpe', unit: 'after costs', numeric: true, sort: (r) => r.net_sharpe, render: (r) => <Value measure="net_sharpe" kind="sharpe" value={r.net_sharpe} digits={3} signed tone /> },
    { key: 'dd', header: 'Max DD', unit: 'return', numeric: true, sort: (r) => r.max_drawdown, render: (r) => <Value measure="max_drawdown" kind="drawdown" value={r.max_drawdown} digits={3} tone /> },
    { key: 'to', header: 'Turnover', unit: 'ann. one-way', numeric: true, sort: (r) => r.annualised_turnover, render: (r) => <Value measure="annualised_turnover" kind="multiple" value={r.annualised_turnover} digits={2} unit="×" /> },
    { key: 'fold', header: 'Fold IC positive', unit: 'share', numeric: true, optional: true, sort: (r) => r.fold_ic_positive_rate, render: (r) => <Value value={r.fold_ic_positive_rate} digits={3} /> },
    { key: 'cagr', header: 'Net CAGR', unit: 'ann. return', numeric: true, optional: true, sort: (r) => r.net_cagr, render: (r) => <Value value={r.net_cagr} digits={4} signed tone /> },
  ], [])

  if (error) {
    return (
      <Panel title="Model registry" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The registry could not be read"
          detail={`The request failed with: ${error}. No leaderboard is shown in its place — a registry that cannot be read is not a registry with no models in it.`}
        />
      </Panel>
    )
  }
  if (!registry) {
    return (
      <>
        <StripSkeleton />
        <Panel title="Registry" state="waking" flush><TableSkeleton rows={12} columns={8} /></Panel>
      </>
    )
  }

  const entry = registry.entries.find((e) => e.key === selected)
  const unmet = Object.entries(entry?.thresholds_not_met ?? {})
  const candidateUnmet = Object.entries(entry?.candidate_thresholds_not_met ?? {})
  const by = registry.summary.by_status

  const inspectedEntry = inspecting
    ? registry.entries.find((e) => e.model_id === inspecting.id)
    : undefined

  return (
    <>
      <ObjectHeader
        glyph="E"
        name="Evidence"
        kind="model registry and promotion gates"
        state={by.production ? 'production' : by.production_candidate ? 'candidate' : 'blocked'}
        detail={`${registry.summary.entries} entries · ${registry.summary.labels.join(', ')}`}
        facts={[
          { label: 'Registered', value: registry.summary.entries, digits: 0 , kind: 'count'},
          { label: 'Experimental', value: by.experimental ?? 0, digits: 0 },
          { label: 'Validated', value: by.validated ?? 0, digits: 0 },
          { label: 'Candidates', value: by.production_candidate ?? 0, digits: 0 },
          { label: 'Production', value: by.production ?? 0, digits: 0 },
          { label: 'Retired', value: by.retired ?? 0, digits: 0 },
        ]}
        actions={
          <>
            <Link href="/terminal/gates" className="sys-btn" style={{ textDecoration: 'none' }}>gates</Link>
            <Link href="/terminal/compare" className="sys-btn" style={{ textDecoration: 'none' }}>compare</Link>
          </>
        }
      />

      {inspecting && inspectedEntry ? (
        <Inspector
          object={inspecting}
          state={statusState(inspectedEntry.status)}
          onClose={() => setInspecting(null)}
          sections={[
            {
              title: 'Identity',
              fields: [
                { label: 'Label', value: inspectedEntry.label },
                { label: 'Task', value: inspectedEntry.task ?? '—' },
                { label: 'Status', value: inspectedEntry.status },
                { label: 'Dataset version', value: inspectedEntry.dataset_version ?? '—' },
                { label: 'Training', value: `${inspectedEntry.training_start ?? '—'} → ${inspectedEntry.training_end ?? '—'}` },
                { label: 'Eligible for', value: inspectedEntry.eligible_for?.join(', ') || 'nothing' },
              ],
            },
            {
              title: 'Unmet gates',
              body: Object.keys(inspectedEntry.thresholds_not_met ?? {}).length ? (
                <table className="sys-table sys-table--compact">
                  <tbody>
                    {Object.entries(inspectedEntry.thresholds_not_met ?? {}).map(([k, v]) => (
                      <tr key={k}>
                        <td style={{ fontFamily: 'var(--font-mono)' }}>{k}</td>
                        <td className="num">
                          {v === 'not recorded'
                            ? <span className="sys-null">not recorded</span>
                            : <span className="sys-neg">{String(v)}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <span className="sys-meta">none recorded</span>,
            },
          ]}
          actions={
            <>
              <Link href="/terminal/gates" className="sys-btn" style={{ textDecoration: 'none' }}>gate matrix</Link>
              <Link href="/terminal/compare" className="sys-btn" style={{ textDecoration: 'none' }}>compare</Link>
              <Link
                href={`/terminal/provenance?label=${encodeURIComponent(inspectedEntry.label)}&model=${encodeURIComponent(inspectedEntry.model_id)}`}
                className="sys-btn" style={{ textDecoration: 'none' }}
              >
                provenance
              </Link>
            </>
          }
        />
      ) : null}

      <Toolbar>
        <ToolbarGroup label="source">
          <span className="sys-meta" style={{ color: 'var(--ink)', fontFamily: 'var(--font-mono)' }}>
            {registry.summary.path}
          </span>
        </ToolbarGroup>
        <ToolbarSpacer />
        <ToolbarGroup label="trace">
          <Link href="/terminal/gates" className="sys-btn" style={{ textDecoration: 'none' }}>gate matrix</Link>
          <Link href="/terminal/experiments" className="sys-btn" style={{ textDecoration: 'none' }}>experiments</Link>
          <Link href="/terminal/provenance" className="sys-btn" style={{ textDecoration: 'none' }}>provenance</Link>
        </ToolbarGroup>
      </Toolbar>

      <Strip metrics={[
        { label: 'Registered', value: registry.summary.entries, digits: 0 , kind: 'count'},
        { label: 'Experimental', value: by.experimental ?? 0, digits: 0, title: 'Measured, but not promotable' },
        { label: 'Validated', value: by.validated ?? 0, digits: 0 },
        { label: 'Candidates', value: by.production_candidate ?? 0, digits: 0, title: 'Cleared development gates; holdout not yet spent' },
        { label: 'Production', value: by.production ?? 0, digits: 0, title: 'Armed and serving' },
        { label: 'Retired', value: by.retired ?? 0, digits: 0 },
      ]} />

      <Panel
        title="Registry"
        subtitle={`${registry.leaderboard.length} entries · ${registry.summary.labels.join(', ')}`}
        flush
        actions={
          <div style={{ display: 'flex', gap: 'var(--d-1)' }}>
            <Link href="/terminal/gates" className="sys-btn" style={{ textDecoration: 'none' }}>gate matrix</Link>
            <Link href="/terminal/compare" className="sys-btn" style={{ textDecoration: 'none' }}>compare</Link>
          </div>
        }
      >
        <DataTable
          columns={columns}
          rows={registry.leaderboard}
          rowKey={(r) => r.key}
          density="compact"
          filterPlaceholder="filter models"
          initialSort={{ key: 't', direction: 'desc' }}
          selectedKey={selected ?? undefined}
          onSelect={(r) => {
            setSelected(r.key)
            const obj = { kind: 'model' as const, id: r.model_id, label: r.model_id, detail: r.label, state: r.status }
            recordVisit(obj)
            setInspecting(obj)
          }}
          actions={[
            {
              label: 'Inspect', glyph: 'i', key: 'i', title: 'Open the inspector without leaving the table',
              onAct: (r) => setInspecting({ kind: 'model', id: r.model_id, label: r.model_id, detail: r.label, state: r.status }),
            },
            {
              label: 'Pin', glyph: '◆', key: 'p', title: 'Pin to the rail',
              onAct: (r) => togglePin({ kind: 'model', id: r.model_id, label: r.model_id, detail: r.label, state: r.status }),
            },
          ]}
        />
      </Panel>

      {!entry ? (
        <Panel title="Evidence">
          <StateBlock
            state="unknown"
            title="No model selected"
            detail="Choose a row above. The workspace then shows the evidence chain for that model — its data, its validation geometry, its behaviour after costs, its multiple-testing correction, and the specific gates standing between it and promotion."
          />
        </Panel>
      ) : (
        <>
          <Panel
            title="Promotion"
            subtitle={entry.model_id}
            state={statusState(entry.status)}
            actions={
              entry.eligible_for?.length
                ? <span className="sys-meta">eligible for: {entry.eligible_for.join(', ')}</span>
                : null
            }
          >
            {unmet.length || candidateUnmet.length ? (
              <div style={{ display: 'grid', gap: 'var(--d-4)', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
                <Section title={`Production gates unmet (${unmet.length})`}>
                  <table className="sys-table sys-table--compact">
                    <thead><tr><th>Gate</th><th className="num">Observed</th><th>Outcome</th></tr></thead>
                    <tbody>{unmet.map(([k, v]) => <GateRow key={k} name={k} observed={v} />)}</tbody>
                  </table>
                </Section>
                <Section title={`Candidate gates unmet (${candidateUnmet.length})`}>
                  {candidateUnmet.length ? (
                    <table className="sys-table sys-table--compact">
                      <thead><tr><th>Gate</th><th className="num">Observed</th><th>Outcome</th></tr></thead>
                      <tbody>{candidateUnmet.map(([k, v]) => <GateRow key={k} name={k} observed={v} />)}</tbody>
                    </table>
                  ) : <span className="sys-meta">none</span>}
                </Section>
              </div>
            ) : (
              <StateBlock
                state="candidate"
                title="No unmet gate is recorded for this entry"
                detail="Either every threshold was met, or none was evaluated. The registry does not distinguish those, so this is not on its own evidence of clearance."
              />
            )}
            <p style={{ marginTop: 'var(--d-3)', marginBottom: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-faint)', lineHeight: 'var(--lh-body)', maxWidth: '80ch' }}>
              A gate with no recorded value counts as unmet. Absent evidence is not
              passing evidence, and treating it as such is how an unmeasured model
              reaches production.
            </p>
          </Panel>

          <Grid variant="halves">
            <Panel title="Data & label">
              <table className="sys-table sys-table--compact">
                <tbody>
                  <tr><td>Label</td><td className="num">{entry.label}</td></tr>
                  <tr><td>Task</td><td className="num">{entry.task ?? '—'}</td></tr>
                  <tr><td>Features</td><td className="num"><Value value={Array.isArray(entry.features) ? entry.features.length : entry.features ?? null} digits={0} /></td></tr>
                  <tr><td>Dataset version</td><td className="num">{entry.dataset_version ?? '—'}</td></tr>
                  <tr><td>Training start</td><td className="num">{entry.training_start ?? '—'}</td></tr>
                  <tr><td>Training end</td><td className="num">{entry.training_end ?? '—'}</td></tr>
                  <tr><td>Seed</td><td className="num"><Value value={entry.seed ?? null} digits={0} /></td></tr>
                </tbody>
              </table>
            </Panel>

            <Panel title="Validation geometry">
              {entry.validation_methodology ? (
                <p style={{ margin: '0 0 var(--d-2)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
                  {entry.validation_methodology}
                </p>
              ) : null}
              <KeyValues data={entry.walk_forward} />
            </Panel>

            <Panel title="Portfolio after costs">
              <KeyValues data={entry.backtest} />
            </Panel>

            <Panel title="Multiple testing">
              <KeyValues data={entry.multiple_testing} />
            </Panel>

            <Panel title="Holdout">
              <KeyValues data={entry.holdout_metrics} />
            </Panel>

            <Panel title="Leakage & reproducibility">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--d-3)' }}>
                <Section title="Leakage evidence"><KeyValues data={entry.leakage_evidence} /></Section>
                <Section title="Reproducibility"><KeyValues data={entry.reproducibility} /></Section>
              </div>
            </Panel>
          </Grid>
        </>
      )}
    </>
  )
}
