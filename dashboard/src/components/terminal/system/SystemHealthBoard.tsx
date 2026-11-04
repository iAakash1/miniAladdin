'use client'

import { formatTimestamp } from '@/lib/quantity'
import Link from 'next/link'
import { useEffect, useState } from 'react'

import { Grid, Panel, Prose, StateBlock, Status, Strip, type ResearchState } from '@/components/system'

type HealthState = 'READY' | 'DEGRADED' | 'BLOCKED' | 'UNAVAILABLE' | 'NOT_CONFIGURED'

interface ComponentHealth {
  component: string
  status: HealthState
  critical: boolean
  reason: string
  version?: string | null
  detail: Record<string, unknown>
}

interface SystemHealth {
  status: HealthState
  checked_at: string
  components: ComponentHealth[]
  summary: Record<HealthState, number>
  process_memory?: {
    rss_mb?: number | null
    peak_rss_mb?: number | null
    memory_limit_mb?: number | null
    memory_utilization_percent?: number | null
    rss_source?: string
  }
  provider_concurrency?: {
    limit?: number
    active?: number
    peak_active?: number
  }
}

const STATE: Record<HealthState, ResearchState> = {
  READY: 'live',
  DEGRADED: 'stale',
  BLOCKED: 'blocked',
  UNAVAILABLE: 'unavailable',
  NOT_CONFIGURED: 'unknown',
}

/** The states as a reader says them; the wire names are an enum. */
const STATE_LABEL: Record<HealthState, string> = {
  READY: 'Ready',
  DEGRADED: 'Degraded',
  BLOCKED: 'Blocked',
  UNAVAILABLE: 'Unavailable',
  NOT_CONFIGURED: 'Not configured',
}

/** Most serious first, so a constraint is the first thing on the list. */
const SEVERITY: Record<HealthState, number> = {
  BLOCKED: 0, UNAVAILABLE: 1, DEGRADED: 2, NOT_CONFIGURED: 3, READY: 4,
}

const LABEL: Record<string, string> = {
  api: 'API',
  persistence: 'Persistence',
  authentication: 'Authentication',
  agent_graph: 'Agent graph',
  research_registry: 'Research registry',
  data_registry: 'PIT data registry',
  final_holdout: 'Final holdout',
  quant_inference: 'Quant inference',
  'providers.market': 'Market providers',
  'providers.fundamentals': 'Fundamental providers',
  'providers.news': 'News providers',
  'providers.macro': 'Macro providers',
  'providers.filings': 'Filing providers',
  narrative_pipeline: 'Narrative pipeline',
}

/** A component the table above does not name still reads as words. */
function componentLabel(id: string): string {
  if (LABEL[id]) return LABEL[id]
  const words = id.replace(/[._]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export default function SystemHealthBoard({ compact = false }: { compact?: boolean }) {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    fetch('/api/system/health')
      .then((response) => response.ok ? response.json() : Promise.reject())
      .then((payload: SystemHealth) => { if (live) setHealth(payload) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [])

  if (failed) {
    return <StateBlock state="unavailable" title="System health unavailable" detail="The canonical component report could not be read." />
  }
  if (!health) {
    return <StateBlock state="waking" title="Reading system state" detail="registries, providers, graph and governance" />
  }

  if (compact) {
    const critical = health.components.filter((row) => row.critical && row.status !== 'READY')
    return (
      <Panel
        title="System state"
        state={STATE[health.status]}
        actions={<Link href="/terminal/system" className="sys-meta sys-meta--strong">Inspect system →</Link>}
      >
        <Strip metrics={[
          { label: 'Ready', value: health.summary.READY, kind: 'count' },
          { label: 'Degraded', value: health.summary.DEGRADED, kind: 'count' },
          { label: 'Blocked', value: health.summary.BLOCKED, kind: 'count' },
          { label: 'Unavailable', value: health.summary.UNAVAILABLE, kind: 'count' },
          { label: 'Process RSS', value: health.process_memory?.rss_mb, kind: 'count', unit: 'MB' },
        ]} />
        <Prose size="fine">
          {critical.length
            ? `Critical constraints: ${critical.map((row) => componentLabel(row.component)).join(', ')}.`
            : 'No critical component reports a constraint.'}
        </Prose>
      </Panel>
    )
  }

  const bySeverity = (a: ComponentHealth, b: ComponentHealth) =>
    SEVERITY[a.status] - SEVERITY[b.status] || componentLabel(a.component).localeCompare(componentLabel(b.component), 'en-US')
  // Three groups, decided only by the report's own flags. A critical
  // component that is not ready limits what research can say; an optional
  // one that is off or impaired does not, and an optional provider left
  // unconfigured is a choice, not an outage.
  const constraints = health.components.filter((row) => row.critical && row.status !== 'READY').sort(bySeverity)
  const optional = health.components.filter((row) => !row.critical && row.status !== 'READY').sort(bySeverity)
  const ready = health.components.filter((row) => row.status === 'READY').sort(bySeverity)
  const groups: Array<{ key: string; title: string; note: string; rows: ComponentHealth[] }> = [
    { key: 'constraints', title: 'Limits research output', note: 'critical components that are not ready', rows: constraints },
    { key: 'optional', title: 'Optional, not fully running', note: 'research continues without these', rows: optional },
    { key: 'ready', title: 'Ready', note: 'answering normally', rows: ready },
  ]

  return (
    <>
      <Panel title="System state" state={STATE[health.status]} subtitle="canonical component report">
        <p className="hb-verdict">
          {constraints.length
            ? <>{constraints.length} critical component{constraints.length === 1 ? '' : 's'} limit{constraints.length === 1 ? 's' : ''} research output: {constraints.map((row) => componentLabel(row.component)).join(', ')}.</>
            : 'No critical component reports a constraint; research output is not limited by the system.'}
        </p>
        <Strip metrics={[
          { label: 'Ready', value: health.summary.READY, kind: 'count' },
          { label: 'Degraded', value: health.summary.DEGRADED, kind: 'count' },
          { label: 'Blocked', value: health.summary.BLOCKED, kind: 'count' },
          { label: 'Unavailable', value: health.summary.UNAVAILABLE, kind: 'count' },
          { label: 'Not configured', value: health.summary.NOT_CONFIGURED, kind: 'count' },
        ]} />
        <Prose size="fine">Checked {formatTimestamp(health.checked_at)} UTC. READY is withheld whenever a critical research constraint remains.</Prose>
      </Panel>
      <Grid variant="halves">
        <Panel
          title="Process memory"
          subtitle={health.process_memory?.rss_source ?? 'runtime measurement'}
          state={!health.process_memory ? 'unavailable' : (health.process_memory.memory_utilization_percent ?? 0) >= 85 ? 'blocked' : 'live'}
          badge={health.process_memory?.memory_limit_mb ? 'Measured' : 'Limit unknown'}
          badgeTone={health.process_memory?.memory_limit_mb ? 'pass' : 'muted'}
        >
          <Strip metrics={[
            { label: 'RSS', value: health.process_memory?.rss_mb, kind: 'count', unit: 'MB' },
            { label: 'Peak RSS', value: health.process_memory?.peak_rss_mb, kind: 'count', unit: 'MB' },
            { label: 'Limit', value: health.process_memory?.memory_limit_mb, kind: 'count', unit: 'MB' },
            { label: 'Utilization', value: health.process_memory?.memory_utilization_percent, kind: 'percent' },
          ]} />
          <Prose size="fine">Current and high-water RSS come from the running API process; the limit is reported only when the platform or deployment declares it.</Prose>
        </Panel>
        <Panel title="Provider concurrency" subtitle="process-wide bounded executor" state="live">
          <Strip metrics={[
            { label: 'Active', value: health.provider_concurrency?.active, kind: 'count' },
            { label: 'Peak active', value: health.provider_concurrency?.peak_active, kind: 'count' },
            { label: 'Worker limit', value: health.provider_concurrency?.limit, kind: 'count' },
          ]} />
          <Prose size="fine">Evidence collection shares one bounded pool. Capability budgets further limit how many upstream vendors one request may consult.</Prose>
        </Panel>
      </Grid>
      <Panel title="Components" subtitle={`${health.components.length} checked`}>
        {groups.filter((g) => g.rows.length).map((g) => (
          <section key={g.key} className="hb-group" data-group={g.key} aria-labelledby={`hb-${g.key}`}>
            <h3 id={`hb-${g.key}`} className="hb-group__title">
              {g.title} <span className="hb-group__count">{g.rows.length}</span>
              <span className="hb-group__note">{g.note}</span>
            </h3>
            <ul className="hb-list">
              {g.rows.map((row) => (
                <li key={row.component} className="hb-row" data-status={row.status}>
                  <div className="hb-row__name">
                    <span className="hb-row__title">{componentLabel(row.component)}</span>
                    <span className="hb-row__tier">{row.critical ? 'Critical' : 'Optional'}</span>
                  </div>
                  <Status state={STATE[row.status]} label={STATE_LABEL[row.status]} />
                  <p className="hb-row__reason">
                    {row.reason}
                    {row.version ? <span className="hb-row__ver">{row.version}</span> : null}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </Panel>
    </>
  )
}
