'use client'

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
}

const STATE: Record<HealthState, ResearchState> = {
  READY: 'live',
  DEGRADED: 'stale',
  BLOCKED: 'blocked',
  UNAVAILABLE: 'unavailable',
  NOT_CONFIGURED: 'unknown',
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
        ]} />
        <Prose size="fine">
          {critical.length
            ? `Critical constraints: ${critical.map((row) => LABEL[row.component] ?? row.component).join(', ')}.`
            : 'No critical component reports a constraint.'}
        </Prose>
      </Panel>
    )
  }

  return (
    <>
      <Panel title="System state" state={STATE[health.status]} subtitle="canonical component report">
        <Strip metrics={[
          { label: 'Ready', value: health.summary.READY, kind: 'count' },
          { label: 'Degraded', value: health.summary.DEGRADED, kind: 'count' },
          { label: 'Blocked', value: health.summary.BLOCKED, kind: 'count' },
          { label: 'Unavailable', value: health.summary.UNAVAILABLE, kind: 'count' },
          { label: 'Not configured', value: health.summary.NOT_CONFIGURED, kind: 'count' },
        ]} />
        <Prose size="fine">Checked {new Date(health.checked_at).toLocaleString()}. READY is withheld whenever a critical research constraint remains.</Prose>
      </Panel>
      <Grid variant="halves">
        {health.components.map((row) => (
          <Panel
            key={row.component}
            title={LABEL[row.component] ?? row.component}
            subtitle={row.critical ? 'critical' : 'optional'}
            state={STATE[row.status]}
            badge={row.status}
            badgeTone={row.status === 'READY' ? 'pass' : row.status === 'BLOCKED' ? 'warn' : 'muted'}
          >
            <Status state={STATE[row.status]} label={row.status} />
            <Prose size="tight">{row.reason}</Prose>
            {row.version ? <Prose size="fine"><span className="sys-mono">{row.version}</span></Prose> : null}
          </Panel>
        ))}
      </Grid>
    </>
  )
}
