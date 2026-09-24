'use client'

/**
 * Who supplies what, and whether they are answering.
 *
 * `/api/providers/health` nests vendor snapshots by capability — market data,
 * fundamentals, news, macro, search, filings — and one vendor can appear under
 * several. This page folds them into one card per vendor, keeps each
 * capability's own state on the card, and draws the coverage as a matrix.
 *
 * States come from `classifyVendor`, never from a flag read at face value: a
 * vendor reporting HEALTHY with no requests is idle, not proven healthy; a
 * missing credential is not a failure; and an upstream error is shown as a
 * sanitised reason, never as the raw string with its URL.
 */

import { useEffect, useMemo, useState } from 'react'

import RoutingFigure from './RoutingFigure'
import { Panel, StateBlock } from '@/components/system'
import EntityMark from '@/components/visual/EntityMark'
import { providerDomain } from '@/lib/identity'
import {
  type HealthTone, type VendorHealth, type VendorSnapshot, classifyVendor, failureLabel, sanitizeError, summarize,
} from '@/lib/providerHealth'

interface Health {
  providers?: Record<string, VendorSnapshot[]>
  deduplicated_requests?: number
}

interface Capability {
  label?: string
  implemented_by?: string[]
  live?: string[]
  unconfigured?: string[]
  fanout_limit?: number | null
}

interface Capabilities {
  by_capability?: Record<string, Capability>
}

const VENDOR_LABEL: Record<string, string> = {
  polygon: 'Polygon', massive: 'Massive', finnhub: 'Finnhub', twelvedata: 'Twelve Data',
  fmp: 'Financial Modeling Prep', marketstack: 'Marketstack', tiingo: 'Tiingo',
  alpha_vantage: 'Alpha Vantage', yfinance: 'Yahoo Finance', yahoo_rss: 'Yahoo Finance RSS',
  newsapi: 'NewsAPI', gnews: 'GNews', tavily: 'Tavily', exa: 'Exa', fred: 'FRED', sec: 'SEC EDGAR',
}

const TONE_RANK: Record<HealthTone, number> = { neg: 4, warn: 3, pos: 2, info: 1, muted: 0 }

interface VendorCard {
  id: string
  worst: VendorHealth
  capabilities: Array<{ key: string; health: VendorHealth; snap: VendorSnapshot }>
  requests: number
  failures: number
  latency: number | null
  lastSuccess: number | null
  error: string | null
  shared: boolean
}

function ago(epochSeconds: number | null): string | null {
  if (!epochSeconds) return null
  const m = Math.round((Date.now() / 1000 - epochSeconds) / 60)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  return h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
}

function cards(byCapability: Record<string, VendorSnapshot[]>): VendorCard[] {
  const map = new Map<string, VendorCard>()
  for (const [key, list] of Object.entries(byCapability)) {
    for (const snap of list) {
      const health = classifyVendor(snap)
      const card = map.get(snap.vendor) ?? {
        id: snap.vendor, worst: health, capabilities: [], requests: 0, failures: 0,
        latency: null, lastSuccess: null, error: null, shared: false,
      }
      card.capabilities.push({ key, health, snap })
      if (TONE_RANK[health.tone] > TONE_RANK[card.worst.tone]) card.worst = health
      // A shared client reports the same counters under each capability;
      // counting them twice would double its traffic.
      if (!snap.shared || !card.shared) {
        card.requests += snap.requests
        card.failures += snap.failures
      }
      card.shared = card.shared || Boolean(snap.shared)
      if (snap.requests > 0 && snap.avg_latency_ms) card.latency = Math.max(card.latency ?? 0, snap.avg_latency_ms)
      if (snap.last_success_at) card.lastSuccess = Math.max(card.lastSuccess ?? 0, snap.last_success_at)
      card.error = card.error ?? sanitizeError(snap.last_error)
      map.set(snap.vendor, card)
    }
  }
  return [...map.values()].sort((a, b) =>
    Number(b.worst.state !== 'NOT_CONFIGURED') - Number(a.worst.state !== 'NOT_CONFIGURED')
    || TONE_RANK[b.worst.tone] - TONE_RANK[a.worst.tone]
    || b.requests - a.requests
    || a.id.localeCompare(b.id))
}

function Card({ c }: { c: VendorCard }) {
  const label = VENDOR_LABEL[c.id] ?? c.id
  const configured = c.worst.state !== 'NOT_CONFIGURED'
  const ok = c.requests - c.failures
  return (
    <article className="pv-card" data-tone={c.worst.tone} data-configured={configured ? '' : undefined}>
      <header className="pv-card__head">
        <EntityMark domain={providerDomain(c.id)} label={label} size={28} />
        <div className="pv-card__id">
          <h3>{label}</h3>
          <span className="pv-card__vid">{c.id}{c.shared ? ' · shared client' : ''}</span>
        </div>
        <span className="pv-state" data-tone={c.worst.tone}>
          <span className="dot" data-tone={c.worst.tone} aria-hidden />{c.worst.label}
        </span>
      </header>
      {c.worst.note ? <p className="pv-card__note">{c.worst.note}</p> : null}
      <ul className="pv-caps" aria-label={`${label} capabilities`}>
        {c.capabilities.map((cap) => (
          <li key={cap.key} title={cap.health.note ?? cap.health.label}>
            <span className="dot" data-tone={cap.health.tone} aria-hidden />
            {cap.key.replace(/_/g, ' ')}
            <span className="visually-hidden"> — {cap.health.label}</span>
          </li>
        ))}
      </ul>
      {configured ? (
        <dl className="pv-stats">
          <div><dt>Requests</dt><dd className="sys-num">{c.requests.toLocaleString('en-US')}</dd></div>
          <div><dt>Succeeded</dt><dd className="sys-num">{c.requests ? `${Math.round((ok / c.requests) * 100)}%` : '—'}</dd></div>
          <div><dt>Latency</dt><dd className="sys-num">{c.latency ? `${Math.round(c.latency)} ms` : '—'}</dd></div>
          <div><dt>Last success</dt><dd>{ago(c.lastSuccess) ?? '—'}</dd></div>
        </dl>
      ) : null}
      {c.error && c.worst.tone !== 'pos' && c.worst.tone !== 'info' ? (
        <p className="pv-card__err">
          {failureLabel(c.capabilities.find((x) => x.snap.last_failure_class)?.snap.last_failure_class) ?? 'Last error'}: {c.error}
        </p>
      ) : null}
    </article>
  )
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

  const byCapability = useMemo(() => health?.d?.providers ?? {}, [health])
  const list = useMemo(() => cards(byCapability), [byCapability])
  const summary = useMemo(() => summarize(byCapability), [byCapability])
  const live = list.filter((c) => c.worst.state !== 'NOT_CONFIGURED')
  const dormant = list.filter((c) => c.worst.state === 'NOT_CONFIGURED')

  if (health?.error) {
    return (
      <Panel title="Providers" state="unavailable">
        <StateBlock
          state="unavailable"
          title="Provider health could not be read"
          detail="The health endpoint did not answer. No vendor is described as healthy on the strength of a failed request."
        />
      </Panel>
    )
  }
  if (!health) return <Panel title="Providers" state="waking"><StateBlock state="waking" title="Reading provider health" /></Panel>

  const capKeys = Object.keys(caps?.d?.by_capability ?? {}).sort()
  const vendorsForMatrix = list.map((c) => c.id)

  return (
    <div className="pv">
      <dl className="pv-summary">
        {([
          ['Vendors', summary.vendors, 'muted'],
          ['Healthy', summary.healthy, 'pos'],
          ['Idle', summary.idle, 'info'],
          ['Constrained', summary.constrained, 'warn'],
          ['Failing', summary.failing, 'neg'],
          ['Not configured', summary.notConfigured, 'muted'],
        ] as const).map(([k, v, tone]) => (
          <div key={k} data-tone={tone}>
            <dt><span className="dot" data-tone={tone} aria-hidden />{k}</dt>
            <dd className="sys-num">{v}</dd>
          </div>
        ))}
        {typeof health.d?.deduplicated_requests === 'number' ? (
          <div title="Requests the orchestrator satisfied without a second vendor call">
            <dt>Deduplicated</dt>
            <dd className="sys-num">{health.d.deduplicated_requests.toLocaleString('en-US')}</dd>
          </div>
        ) : null}
      </dl>
      <p className="pv-lede">
        Counters are since this server started. Idle means configured but not yet called — not proven healthy.
        A vendor with no credential was never asked, which is a different state from one that was asked and failed.
      </p>

      <RoutingFigure />

      <section aria-label="Configured providers">
        <h2 className="pv-h">Configured in this deployment</h2>
        <div className="pv-grid">{live.map((c) => <Card key={c.id} c={c} />)}</div>
      </section>

      {dormant.length ? (
        <section aria-label="Providers without credentials">
          <h2 className="pv-h">Not configured</h2>
          <div className="pv-grid pv-grid--dormant">{dormant.map((c) => <Card key={c.id} c={c} />)}</div>
        </section>
      ) : null}

      <Panel
        title="Coverage"
        subtitle="which vendor can answer which capability, and its state for it now"
        state={caps?.error ? 'unavailable' : caps ? 'recorded' : 'waking'}
        flush
      >
        {caps?.error ? (
          <StateBlock state="unavailable" title="The capability registry could not be read" detail="The coverage map needs the registry; the cards above are unaffected." />
        ) : !caps ? (
          <StateBlock state="waking" title="Reading the capability registry" />
        ) : (
          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact pv-matrix">
              <thead>
                <tr>
                  <th scope="col">Capability</th>
                  {vendorsForMatrix.map((v) => (
                    <th key={v} scope="col" className="pv-matrix__v" title={VENDOR_LABEL[v] ?? v}>
                      <span>{v.replace(/_/g, ' ')}</span>
                    </th>
                  ))}
                  <th scope="col" className="num">Fan-out</th>
                </tr>
              </thead>
              <tbody>
                {capKeys.map((key) => {
                  const cap = caps.d?.by_capability?.[key] ?? {}
                  return (
                    <tr key={key}>
                      <th scope="row">
                        <span className="pv-matrix__cap">{cap.label ?? key.replace(/_/g, ' ')}</span>
                        <span className="pv-matrix__key">{key}</span>
                      </th>
                      {vendorsForMatrix.map((v) => {
                        const offers = cap.implemented_by?.includes(v)
                        const tone: HealthTone | null = !offers ? null
                          : cap.live?.includes(v) ? (list.find((c) => c.id === v)?.worst.tone ?? 'pos')
                            : 'muted'
                        const text = !offers ? 'not offered' : cap.live?.includes(v) ? 'available' : 'no credential'
                        return (
                          <td key={v} className="pv-matrix__cell" title={`${VENDOR_LABEL[v] ?? v}: ${text}`}>
                            {tone ? <span className="pv-matrix__mark" data-tone={tone} data-live={cap.live?.includes(v) ? '' : undefined} /> : <span className="pv-matrix__none" aria-hidden>·</span>}
                            <span className="visually-hidden">{text}</span>
                          </td>
                        )
                      })}
                      <td className="num">{cap.fanout_limit ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
