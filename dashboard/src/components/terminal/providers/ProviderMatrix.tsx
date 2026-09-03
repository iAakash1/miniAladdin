'use client'

/**
 * Who supplies what, and whether they are answering.
 *
 * This workspace was reading a payload that does not exist. `/api/providers/health`
 * nests vendors by capability — `{ market_data: [...], news: [...] }` — and the
 * component treated it as a flat map of vendor to status, spreading arrays into
 * objects. The result was a table whose column headers were the payload's own
 * top-level keys (BY_CAPABILITY, RECONCILIATION_STRATEGIES, TOTALS), whose rows
 * were array indices, and whose every cell was an em dash.
 *
 * It reads the recorded shape now: seven market-data vendors, six for
 * fundamentals, six for news, and one each for macro and filings, with the
 * request counts, failure counts, success rate and latency each one actually
 * reports.
 *
 * A vendor's state is derived from what it reports rather than from a flag it
 * does not have. Cooling down is a real field and means the orchestrator has
 * stopped calling it after consecutive failures; unconfigured means no
 * credential, which is a different thing from failing and must not be coloured
 * the same.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Strip, Value } from '@/components/system'
import type { ResearchState } from '@/components/system'

interface Vendor {
  vendor: string
  configured: boolean
  cooling_down: boolean
  requests: number
  success_pct: number | null
  failures: number
  rate_limited: number
  consecutive_failures: number
  avg_latency_ms: number | null
  max_latency_ms: number | null
  last_error: string | null
  shared: boolean
}

interface Health {
  providers?: Record<string, Vendor[]>
  deduplicated_requests?: number
  cache?: Record<string, unknown>
}

interface Capability {
  label?: string
  implemented_by?: string[]
  live?: string[]
  unconfigured?: string[]
}

interface Capabilities {
  by_capability?: Record<string, Capability>
  totals?: Record<string, unknown>
}

/**
 * What a vendor's own numbers say about it.
 *
 * Unconfigured is not failing — there is no credential, so it was never asked.
 * Cooling down is the orchestrator having stopped calling it. A vendor that has
 * been asked and never answered is unavailable; one that has answered is live.
 */
function vendorState(v: Vendor): ResearchState {
  if (!v.configured) return 'unknown'
  if (v.cooling_down) return 'blocked'
  if (v.requests === 0) return 'waking'
  if (v.success_pct !== null && v.success_pct === 0) return 'unavailable'
  if (v.success_pct !== null && v.success_pct < 100) return 'stale'
  return 'live'
}

function vendorLabel(v: Vendor): string {
  if (!v.configured) return 'no credential'
  if (v.cooling_down) return 'cooling down'
  if (v.requests === 0) return 'not called'
  return v.success_pct === null ? 'answering' : `${Math.round(v.success_pct)}% ok`
}

export default function ProviderMatrix() {
  const [health, setHealth] = useState<{ d?: Health; error?: string } | null>(null)
  const [caps, setCaps] = useState<{ d?: Capabilities; error?: string } | null>(null)

  useEffect(() => {
    const c = new AbortController()
    fetch('/api/providers/health', { signal: c.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`health returned ${r.status}`))))
      .then((d: Health) => setHealth({ d }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setHealth({ error: e.message }) })
    fetch('/api/providers/capabilities', { signal: c.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`capabilities returned ${r.status}`))))
      .then((d: Capabilities) => setCaps({ d }))
      .catch((e: Error) => { if (e.name !== 'AbortError') setCaps({ error: e.message }) })
    return () => c.abort()
  }, [])

  const byCategory = health?.d?.providers ?? {}
  const categories = Object.keys(byCategory).sort()
  const all = categories.flatMap((k) => byCategory[k])
  const configured = all.filter((v) => v.configured)
  const answering = configured.filter((v) => v.requests > 0 && (v.success_pct ?? 0) > 0)
  const cooling = configured.filter((v) => v.cooling_down)

  return (
    <>
      <Panel
        title="Providers"
        subtitle={categories.length ? `${all.length} vendors across ${categories.length} capabilities` : undefined}
        state={health?.error ? 'unavailable' : health ? 'live' : 'waking'}
      >
        {health?.error ? (
          <StateBlock
            state="unavailable"
            title="Provider health could not be read"
            detail={`${health.error}. No vendor is described as healthy on the strength of a failed request.`}
          />
        ) : !health ? (
          <StateBlock state="waking" title="Reading provider health" />
        ) : (
          <>
            <Strip metrics={[
              { label: 'Vendors', value: all.length, kind: 'count' },
              { label: 'With credentials', value: configured.length, kind: 'count' },
              { label: 'Answering', value: answering.length, kind: 'count' },
              { label: 'Cooling down', value: cooling.length, kind: 'count' },
              { label: 'Deduplicated requests', value: health.d?.deduplicated_requests ?? null, kind: 'count',
                title: 'Requests the orchestrator satisfied without a second vendor call' },
            ]} />
            <Prose size="tight">
              A vendor with no credential was never called, which is a different
              state from one that was called and failed. Cooling down means the
              orchestrator has stopped calling it after consecutive failures and
              will retry.
            </Prose>
          </>
        )}
      </Panel>

      {categories.map((cat) => (
        <Panel key={cat} title={cat.replace(/_/g, ' ')} subtitle={`${byCategory[cat].length} vendors`} state="live" flush>
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>State</th>
                  <th className="num">Requests</th>
                  <th className="num">Failures</th>
                  <th className="num">Rate limited</th>
                  <th className="num">Mean latency</th>
                  <th>Last error</th>
                </tr>
              </thead>
              <tbody>
                {byCategory[cat].map((v) => (
                  <tr key={`${cat}:${v.vendor}`}>
                    <td className="sys-mono">
                      {v.vendor}
                      {v.shared ? <span className="sys-meta"> · shared</span> : null}
                    </td>
                    <td><Status state={vendorState(v)} label={vendorLabel(v)} /></td>
                    <td className="num"><Value value={v.requests} kind="count" /></td>
                    <td className="num"><Value value={v.failures} kind="count" /></td>
                    <td className="num"><Value value={v.rate_limited} kind="count" /></td>
                    <td className="num">
                      {/* Latency reported as zero on a vendor never called is
                          not a measurement of speed. */}
                      <Value value={v.requests > 0 ? v.avg_latency_ms : null} kind="count" unit="ms" />
                    </td>
                    <td><span className="sys-meta">{v.last_error ?? '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ))}

      <Panel
        title="Capabilities"
        subtitle="what each capability has behind it"
        state={caps?.error ? 'unavailable' : caps ? 'recorded' : 'waking'}
        flush
      >
        {caps?.error ? (
          <StateBlock state="unavailable" title="The capability registry could not be read" detail={caps.error} />
        ) : !caps ? (
          <StateBlock state="waking" title="Reading the capability registry" />
        ) : (
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact">
              <thead>
                <tr><th>Capability</th><th>Live vendors</th><th>Unconfigured</th></tr>
              </thead>
              <tbody>
                {Object.entries(caps.d?.by_capability ?? {}).sort().map(([key, c]) => (
                  <tr key={key}>
                    <td>
                      <span className="sys-mono">{key}</span>
                      {c.label ? <span className="sys-meta"> · {c.label}</span> : null}
                    </td>
                    <td>
                      {c.live?.length
                        ? <span className="sys-meta sys-meta--strong">{c.live.join(', ')}</span>
                        : <Status state="unavailable" label="none live" />}
                    </td>
                    <td>
                      <span className="sys-meta">
                        {c.unconfigured?.length ? c.unconfigured.join(', ') : '—'}
                      </span>
                    </td>
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
