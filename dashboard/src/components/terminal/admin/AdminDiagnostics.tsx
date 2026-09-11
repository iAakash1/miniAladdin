'use client'

/**
 * Operational posture, for an operator.
 *
 * The access decision is not made here. This component asks the backend and
 * renders whatever it is given; a reader without the capability receives 403
 * and sees that, which is the honest outcome — the alternative, hiding the
 * link and calling that protection, leaves the endpoint open to anyone who
 * types the path.
 *
 * Everything shown is posture rather than material: whether a capability is
 * configured, never the value that configures it. "Clerk is configured" is
 * operationally useful; the key is not, and it is not here to leak.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock, Status, Strip } from '@/components/system'
import { authFetch } from '@/lib/persistence'

interface Vendor {
  vendor: string
  configured: boolean
  cooling_down: boolean
  requests: number
  success_pct: number | null
}

interface Diagnostics {
  environment: string
  build_commit: string
  persistence: { configured: boolean; reachable: boolean }
  authentication: { clerk_configured: boolean }
  paper_trading: { enabled: boolean; reason: string | null }
  providers: Record<string, unknown>
  metrics: { counters?: Record<string, number>; window_seconds?: number }
}

type Load =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error'; detail: string }
  | { kind: 'ready'; data: Diagnostics }

function vendorRows(providers: Record<string, unknown>): Vendor[] {
  const byCapability = (providers?.['by_capability'] ?? {}) as Record<string, unknown>
  const seen = new Map<string, Vendor>()
  for (const group of Object.values(byCapability)) {
    if (!Array.isArray(group)) continue
    for (const entry of group as Vendor[]) {
      if (entry && typeof entry.vendor === 'string' && !seen.has(entry.vendor)) {
        seen.set(entry.vendor, entry)
      }
    }
  }
  return [...seen.values()].sort((a, b) => a.vendor.localeCompare(b.vendor))
}

export default function AdminDiagnostics() {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const res = await authFetch('/api/admin/diagnostics')
        if (!live) return
        if (res.status === 401 || res.status === 403) {
          setLoad({ kind: 'forbidden' })
          return
        }
        if (!res.ok) {
          setLoad({ kind: 'error', detail: `The server answered ${res.status}.` })
          return
        }
        setLoad({ kind: 'ready', data: (await res.json()) as Diagnostics })
      } catch {
        if (live) setLoad({ kind: 'error', detail: 'The diagnostics endpoint could not be reached.' })
      }
    })()
    return () => {
      live = false
    }
  }, [])

  if (load.kind === 'loading') {
    return <StateBlock state="waking" title="Reading operational state" detail="one request" />
  }

  if (load.kind === 'forbidden') {
    return (
      <StateBlock
        state="blocked"
        title="This account is not an operator"
        detail="the check is server-side"
      >
        <Prose>
          Diagnostics are gated on the backend, not on whether the link was
          drawn. This account is signed in and refused, which is the same
          answer it would get by requesting the path directly.
        </Prose>
      </StateBlock>
    )
  }

  if (load.kind === 'error') {
    return <StateBlock state="unavailable" title="Diagnostics unavailable" detail={load.detail} />
  }

  const d = load.data
  const vendors = vendorRows(d.providers)
  const configured = vendors.filter((v) => v.configured).length
  const cooling = vendors.filter((v) => v.cooling_down).length

  return (
    <>
      <Panel title="Deployment">
        <Strip
          metrics={[
            { label: 'Environment', value: d.environment },
            { label: 'Build', value: d.build_commit.slice(0, 12) || '—' },
            { label: 'Metrics window', value: d.metrics?.window_seconds ?? null, kind: 'sessions' },
          ]}
        />
      </Panel>

      <Panel title="Capabilities configured">
        <Prose>
          Whether each capability has what it needs — never the values that
          configure it.
        </Prose>
        <Strip
          metrics={[
            { label: 'Persistence', value: d.persistence.configured ? 'configured' : 'absent' },
            { label: 'Database reachable', value: d.persistence.reachable ? 'yes' : 'no' },
            { label: 'Clerk', value: d.authentication.clerk_configured ? 'configured' : 'absent' },
            { label: 'Paper trading', value: d.paper_trading.enabled ? 'enabled' : 'closed' },
          ]}
        />
        {!d.paper_trading.enabled && d.paper_trading.reason ? (
          <Prose>{d.paper_trading.reason}</Prose>
        ) : null}
      </Panel>

      <Panel title="Providers">
        {vendors.length === 0 ? (
          <EmptyLine label="Vendors">No vendor reported state on this instance.</EmptyLine>
        ) : (
          <>
            <Strip
              metrics={[
                { label: 'Vendors', value: vendors.length, kind: 'count' },
                { label: 'Configured', value: configured, kind: 'count' },
                { label: 'Cooling down', value: cooling, kind: 'count' },
              ]}
            />
            <ul style={{ listStyle: 'none', margin: 'var(--s-3) 0 0', padding: 0 }}>
              {vendors.map((v) => (
                <li
                  key={v.vendor}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 'var(--s-2)',
                    padding: 'var(--s-1) 0',
                    borderBottom: '1px solid var(--rule)',
                    fontSize: 'var(--t-meta)',
                  }}
                >
                  <span>{v.vendor}</span>
                  <Status
                    state={
                      !v.configured ? 'unavailable' : v.cooling_down ? 'stale' : 'live'
                    }
                    label={
                      !v.configured ? 'no credential' : v.cooling_down ? 'cooling down' : 'answering'
                    }
                  />
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>
    </>
  )
}
