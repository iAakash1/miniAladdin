/**
 * Provider capability matrix.
 *
 * `/api/providers/capabilities` is introspection-driven — a newly added vendor
 * appears without anyone editing a list — and `/api/providers/health` reports
 * what each one is currently doing. Neither had a surface.
 *
 * Nothing here is scored or ranked. A provider's capability is either declared
 * available or it is not, and an unavailable capability shows the reason the
 * backend gives rather than an empty cell, because "no key configured" and
 * "the vendor does not offer this" are different facts.
 */
'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'

import { Panel, StateBlock, Status, Strip, Value, type ResearchState } from '@/components/system'
import { ObjectHeader, TableSkeleton, Toolbar, ToolbarGroup, ToolbarSpacer } from '@/components/system/composition'

interface Capability {
  capability?: string
  available?: boolean
  reason?: string
  detail?: string
  [k: string]: unknown
}

type CapabilityMap = Record<string, Record<string, Capability | boolean>>

interface HealthEntry {
  name?: string
  healthy?: boolean
  state?: string
  calls?: number
  failures?: number
  consecutive_failures?: number
  cooldown_seconds?: number
  last_error?: string
  [k: string]: unknown
}

interface Health {
  providers?: HealthEntry[] | Record<string, HealthEntry>
  cache?: Record<string, unknown>
  deduplicated_requests?: number
}

function normaliseHealth(h: Health | null): HealthEntry[] {
  if (!h?.providers) return []
  if (Array.isArray(h.providers)) return h.providers
  return Object.entries(h.providers).map(([name, v]) => ({ name, ...(v as HealthEntry) }))
}

function healthState(e: HealthEntry): ResearchState {
  if (e.healthy === true) return 'live'
  if (e.healthy === false) return 'unavailable'
  if (typeof e.cooldown_seconds === 'number' && e.cooldown_seconds > 0) return 'stale'
  return 'unknown'
}

export default function ProviderMatrix() {
  const [caps, setCaps] = useState<CapabilityMap | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [failed, setFailed] = useState<string[]>([])

  useEffect(() => {
    let alive = true
    fetch('/api/providers/capabilities')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { if (alive) setCaps((d.capabilities ?? d) as CapabilityMap) })
      .catch((e: Error) => { if (alive) setFailed((p) => [...p, `capabilities: ${e.message}`]) })
    fetch('/api/providers/health')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Health) => { if (alive) setHealth(d) })
      .catch((e: Error) => { if (alive) setFailed((p) => [...p, `health: ${e.message}`]) })
    return () => { alive = false }
  }, [])

  const { providers, capabilities } = useMemo(() => {
    if (!caps) return { providers: [] as string[], capabilities: [] as string[] }
    const provs = Object.keys(caps).sort()
    const capSet = new Set<string>()
    for (const p of provs) for (const c of Object.keys(caps[p] ?? {})) capSet.add(c)
    return { providers: provs, capabilities: [...capSet].sort() }
  }, [caps])

  const healthRows = normaliseHealth(health)

  const cell = (provider: string, capability: string) => {
    const raw = caps?.[provider]?.[capability]
    if (raw === undefined) return { available: null as boolean | null, reason: 'not declared' }
    if (typeof raw === 'boolean') return { available: raw, reason: raw ? undefined : 'declared unavailable' }
    return { available: raw.available ?? null, reason: raw.reason ?? raw.detail }
  }

  return (
    <>
      <ObjectHeader
        glyph="V"
        name="Providers"
        kind="who supplies what"
        state={failed.length ? 'stale' : 'live'}
        facts={[
          { label: 'Providers', value: providers.length || null, digits: 0 },
          { label: 'Capabilities', value: capabilities.length || null, digits: 0 },
          { label: 'Reporting', value: healthRows.length || null, digits: 0 },
          { label: 'Deduplicated', value: health?.deduplicated_requests ?? null, digits: 0 },
        ]}
      />

      <Strip metrics={[
        { label: 'Providers', value: providers.length || null, digits: 0 },
        { label: 'Capabilities', value: capabilities.length || null, digits: 0 },
        { label: 'Health reported', value: healthRows.length || null, digits: 0 },
        { label: 'Deduplicated requests', value: health?.deduplicated_requests ?? null, digits: 0, title: 'Requests served from an in-flight identical call rather than repeated' },
      ]} />

      {failed.length ? (
        <Panel title="Unavailable" state="unavailable">
          <ul style={{ margin: 0, paddingLeft: 'var(--d-4)', fontSize: 'var(--t-meta)', color: 'var(--ink-muted)' }}>
            {failed.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </Panel>
      ) : null}

      <Toolbar>
        <ToolbarGroup label="trace">
          <Link href="/terminal/data" className="sys-btn">datasets</Link>
          <Link href="/terminal/provenance" className="sys-btn">provenance</Link>
        </ToolbarGroup>
        <ToolbarSpacer />
        <span className="sys-meta">introspected from the vendor clients</span>
      </Toolbar>

      <Panel title="Capability matrix" subtitle={providers.length ? `${providers.length} providers × ${capabilities.length} capabilities` : undefined} flush>
        {!caps ? (
          <TableSkeleton rows={8} columns={6} />
        ) : !providers.length ? (
          <StateBlock
            state="unavailable"
            title="No provider declares a capability"
            detail="The matrix is introspected from the vendor clients. An empty one means no client is registered, not that no vendor can supply anything."
          />
        ) : (
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th style={{ position: 'sticky', left: 0, zIndex: 3, background: 'var(--p-sunken)' }}>Capability</th>
                  {providers.map((p) => <th key={p} className="num">{p}</th>)}
                </tr>
              </thead>
              <tbody>
                {capabilities.map((c) => (
                  <tr key={c}>
                    <td style={{ fontFamily: 'var(--font-mono)', position: 'sticky', left: 0, zIndex: 1, background: 'var(--p-panel)' }}>{c}</td>
                    {providers.map((p) => {
                      const { available, reason } = cell(p, c)
                      return (
                        <td key={p} className="num" title={reason}>
                          {available === true
                            ? <Status state="live" label="yes" />
                            : available === false
                              ? <Status state="unavailable" label="no" />
                              : <span className="sys-null">—</span>}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Provider health" subtitle={healthRows.length ? `${healthRows.length} reporting` : undefined} flush>
        {!health ? (
          <TableSkeleton rows={5} columns={7} />
        ) : !healthRows.length ? (
          <StateBlock
            state="unavailable"
            title="No provider reported health"
            detail="Health is recorded as calls are made. A provider that has not been called in this process has nothing to report yet."
          />
        ) : (
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th>Provider</th><th>State</th>
                  <th className="num">Calls</th><th className="num">Failures</th>
                  <th className="num">Consecutive</th><th className="num">Cooldown</th>
                  <th>Last error</th>
                </tr>
              </thead>
              <tbody>
                {healthRows.map((e) => (
                  <tr key={e.name ?? JSON.stringify(e).slice(0, 24)}>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{e.name ?? '—'}</td>
                    <td><Status state={healthState(e)} label={e.state ?? (e.healthy === true ? 'healthy' : e.healthy === false ? 'failing' : 'unknown')} /></td>
                    <td className="num"><Value value={e.calls ?? null} digits={0} /></td>
                    <td className="num"><Value value={e.failures ?? null} digits={0} /></td>
                    <td className="num"><Value value={e.consecutive_failures ?? null} digits={0} /></td>
                    <td className="num"><Value value={e.cooldown_seconds ?? null} digits={0} unit="s" /></td>
                    <td><span className="sys-meta sys-meta--strong">{e.last_error ?? '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  )
}
