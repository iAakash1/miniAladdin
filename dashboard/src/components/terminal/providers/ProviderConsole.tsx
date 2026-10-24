'use client'

/**
 * The providers console: every data vendor, what it can answer, and what it
 * has actually done.
 *
 * Reads one endpoint, `/api/providers/registry`, which the backend builds from
 * the provider catalog, the capability registry and every live adapter
 * instance. Nothing on this page names a vendor or counts one by hand.
 *
 * Three rules hold throughout:
 *  - configured is not healthy. A key being present says nothing about whether
 *    the vendor accepts it; only an answer inside the health window does.
 *  - a failed read is never shown as an empty registry, and a vendor that was
 *    never asked is never shown as failing.
 *  - no secret reaches the browser. The backend sends the *name* of each
 *    credential variable and whether it is set, never its value.
 */

import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'

import RoutingFigure from './RoutingFigure'
import { Panel, StateBlock, Status, type ResearchState } from '@/components/system'
import { useDrawerFocus } from '@/components/system/useDrawerFocus'
import { failureLabel, type HealthTone } from '@/lib/providerHealth'
import {
  DOMAIN_LABEL, NO_FILTERS, SOURCE_KIND_LABEL, STATE_FILTERS, TERMS_STATUS_LABEL,
  ago, classify, filterProviders, filtersActive, healthFingerprint, outcomeLabel, outcomeTone,
  parseRegistry, summarizeRegistry, windowLabel,
  type CapabilityRecord, type Filters, type ProviderRecord, type Registry, type StateFilter,
} from '@/lib/providerRegistry'

const TONE_STATE: Record<HealthTone, ResearchState> = { neg: 'error', warn: 'warning', pos: 'live', info: 'info', muted: 'unknown' }

type Load =
  | { kind: 'loading' }
  | { kind: 'ready'; reg: Registry; note: string | null }
  | { kind: 'forbidden' }
  | { kind: 'unreadable' }
  | { kind: 'failed'; status: number | null }

function stamp(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return '—'
  return new Date(epochSeconds * 1000).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function ms(v: number | null | undefined): string {
  return typeof v === 'number' && v > 0 ? `${Math.round(v).toLocaleString('en-US')} ms` : '—'
}

function configurationText(p: ProviderRecord): string {
  const c = p.configuration
  if (c.disabled) return 'Disabled'
  if (c.keyless) return 'No key needed'
  if (!c.configured) return 'Not configured'
  return c.credential_state === 'accepted' ? 'Key accepted' : c.credential_state === 'rejected' ? 'Key rejected' : 'Key set, unverified'
}

function useRegistry() {
  const [load, setLoad] = useState<Load>({ kind: 'loading' })
  const [refreshing, setRefreshing] = useState(false)
  const previous = useRef<string | null>(null)

  const read = useCallback(async (signal?: AbortSignal, manual = false) => {
    if (manual) setRefreshing(true)
    try {
      const r = await fetch('/api/providers/registry', { signal, cache: 'no-store' })
      if (r.status === 401 || r.status === 403) { setLoad({ kind: 'forbidden' }); return }
      if (!r.ok) { setLoad({ kind: 'failed', status: r.status }); return }
      const reg = parseRegistry(await r.json().catch(() => null))
      if (!reg) { setLoad({ kind: 'unreadable' }); return }
      const print = healthFingerprint(reg)
      const note = !manual ? null : previous.current === print ? 'No change since the last read.' : 'Updated.'
      previous.current = print
      setLoad({ kind: 'ready', reg, note })
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setLoad({ kind: 'failed', status: null })
    } finally {
      if (manual) setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    const c = new AbortController()
    void read(c.signal)
    return () => c.abort()
  }, [read])

  return { load, refreshing, refresh: () => read(undefined, true) }
}

export function Summary({ reg }: { reg: Registry }) {
  const s = summarizeRegistry(reg)
  const cells: Array<[string, number, HealthTone, string]> = [
    ['Registered', s.registered, 'muted', 'Every adapter the backend knows about'],
    ['Configured', s.configured, 'muted', 'Credential present (or none needed) and not disabled. Not proof it works.'],
    ['Answered recently', s.answeringNow, 'pos', `At least one answer in the last ${windowLabel(reg.health_window_seconds)}`],
    ['Failing', s.failing, 'neg', 'Latest answer was a failure, or the credential was rejected'],
    ['Rate limited or degraded', s.constrained, 'warn', 'Answering with limits, or with failures in the window'],
    ['Stale or idle', s.staleOrIdle, 'info', 'Configured, but nothing observed recently enough to say'],
    ['Not configured', s.notConfigured, 'muted', 'No credential in this deployment, so never asked'],
  ]
  if (s.disabled) cells.push(['Disabled', s.disabled, 'muted', 'Taken out of routing by the operator'])
  return (
    <>
      <dl className="pv-summary">
        {cells.map(([k, v, tone, title]) => (
          <div key={k} data-tone={tone} title={title}>
            <dt><span className="dot" data-tone={tone} aria-hidden />{k}</dt>
            <dd className="sys-num">{v}</dd>
          </div>
        ))}
      </dl>
      {s.uncovered.length ? (
        <p className="pv-alert" role="note">
          <strong>{s.uncovered.length} {s.uncovered.length === 1 ? 'capability has' : 'capabilities have'} no eligible source:</strong>{' '}
          {s.uncovered.map((c) => c.label).join(', ')}. Requests for {s.uncovered.length === 1 ? 'it' : 'them'} return
          “unavailable”, not an empty answer.
        </p>
      ) : null}
    </>
  )
}

function Toolbar({
  reg, filters, setFilters, shown,
}: { reg: Registry; filters: Filters; setFilters: (f: Filters) => void; shown: number }) {
  const domains = useMemo(() => [...new Set(reg.providers.map((p) => p.domain).filter(Boolean) as string[])].sort(), [reg])
  const capabilities = useMemo(() => [...reg.capabilities].sort((a, b) => a.label.localeCompare(b.label)), [reg])
  return (
    <div className="pv-toolbar" role="search" aria-label="Filter providers">
      <label className="pv-field pv-field--grow">
        <span className="sys-label">Search</span>
        <input
          className="sys-input sys-input--block"
          type="search"
          placeholder="Name, id, host or capability"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
      </label>
      <label className="pv-field">
        <span className="sys-label">Domain</span>
        <select className="sys-input" value={filters.domain} onChange={(e) => setFilters({ ...filters, domain: e.target.value })}>
          <option value="all">All domains</option>
          {domains.map((d) => <option key={d} value={d}>{DOMAIN_LABEL[d] ?? d}</option>)}
        </select>
      </label>
      <label className="pv-field">
        <span className="sys-label">Capability</span>
        <select className="sys-input" value={filters.capability} onChange={(e) => setFilters({ ...filters, capability: e.target.value })}>
          <option value="all">Any capability</option>
          {capabilities.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
      </label>
      <label className="pv-field">
        <span className="sys-label">State</span>
        <select className="sys-input" value={filters.state} onChange={(e) => setFilters({ ...filters, state: e.target.value as StateFilter })}>
          {STATE_FILTERS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </label>
      <p className="pv-count" aria-live="polite">
        {shown} of {reg.providers.length} shown
        {filtersActive(filters) ? (
          <button type="button" className="sys-btn sys-btn--ghost sys-btn--xs" onClick={() => setFilters(NO_FILTERS)}>Clear</button>
        ) : null}
      </p>
    </div>
  )
}

/** Calls inside the health window, as the table states them. */
export function windowText(w: ProviderRecord['health']['window']): string {
  const declined = w.declined ?? 0
  if (!w.ok && !w.failed && !declined) return '—'
  return [`${w.ok} ok`, `${w.failed} failed`, declined ? `${declined} declined` : null].filter(Boolean).join(' · ')
}

/** Providers grouped by data domain, in the catalog's order; uncatalogued last. */
export function groupByDomain(list: ProviderRecord[]): Array<{ domain: string | null; providers: ProviderRecord[] }> {
  const order = Object.keys(DOMAIN_LABEL)
  const groups = new Map<string | null, ProviderRecord[]>()
  for (const p of list) groups.set(p.domain, [...(groups.get(p.domain) ?? []), p])
  const rank = (d: string | null) => (d === null ? order.length + 1 : order.includes(d) ? order.indexOf(d) : order.length)
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || String(a).localeCompare(String(b)))
    .map(([domain, providers]) => ({ domain, providers }))
}

export function Catalogue({
  list, capLabel, onOpen, openId,
}: { list: ProviderRecord[]; capLabel: (k: string) => string; onOpen: (p: ProviderRecord, el: HTMLElement) => void; openId: string | null }) {
  return (
    <div className="sys-scroll-x">
      <table className="sys-table sys-table--compact pv-table">
        <caption className="visually-hidden">Data providers by domain, their configuration and observed health</caption>
        <thead>
          <tr>
            <th scope="col">Provider</th>
            <th scope="col">Capabilities</th>
            <th scope="col">Configuration</th>
            <th scope="col">Health</th>
            <th scope="col">Last success</th>
            <th scope="col" className="num" title="Calls inside the health window">In window</th>
            <th scope="col" className="num" title="Mean over every call since the server started">Avg latency</th>
          </tr>
        </thead>
        {groupByDomain(list).map(({ domain, providers: group }) => {
          const answering = group.filter((p) => p.health.window.ok > 0).length
          return (
            <tbody key={domain ?? 'none'}>
              <tr className="pv-group">
                <th scope="rowgroup" colSpan={7}>
                  {domain ? DOMAIN_LABEL[domain] ?? domain : 'Uncatalogued'}
                  <span className="pv-group__meta">{group.length} {group.length === 1 ? 'provider' : 'providers'} · {answering} answered recently</span>
                </th>
              </tr>
              {group.map((p) => {
                const h = classify(p)
                const caps = p.capabilities.map(capLabel)
                return (
                  <tr key={p.id} data-selected={openId === p.id ? 'true' : undefined}>
                    <th scope="row">
                      <button
                        type="button"
                        className="pv-open"
                        aria-haspopup="dialog"
                        aria-expanded={openId === p.id}
                        onClick={(e) => onOpen(p, e.currentTarget)}
                      >
                        <span className="pv-open__name">{p.display_name}</span>
                        <span className="pv-open__id">{p.id}</span>
                      </button>
                    </th>
                    <td className="pv-caps-cell" title={caps.join(', ')}>
                      {caps.length ? `${caps.slice(0, 2).join(', ')}${caps.length > 2 ? ` +${caps.length - 2}` : ''}`
                        : p.groups.length ? <span className="pv-muted">used by {p.groups.join(', ').replace(/_/g, ' ')}</span>
                          : <span className="pv-muted">used directly by a service</span>}
                    </td>
                    <td>{configurationText(p)}</td>
                    <td><Status state={TONE_STATE[h.tone]} label={h.label} title={h.note ?? undefined} /></td>
                    <td>{ago(p.health.last_success_at) ?? 'never'}</td>
                    <td className="num sys-num">{windowText(p.health.window)}</td>
                    <td className="num sys-num">{p.health.requests ? ms(p.health.avg_latency_ms) : 'not measured'}</td>
                  </tr>
                )
              })}
            </tbody>
          )
        })}
      </table>
    </div>
  )
}

export function Detail({
  p, reg, capLabel, onClose,
}: { p: ProviderRecord; reg: Registry; capLabel: (k: string) => string; onClose: () => void }) {
  const panel = useDrawerFocus<HTMLElement>(true, onClose)
  const h = classify(p)
  const c = p.configuration
  const titleId = useId()
  return (
    <aside ref={panel} tabIndex={-1} className="sys-drawer pv-drawer" role="dialog" aria-modal="false" aria-labelledby={titleId}>
      <header className="sys-drawer-head">
        <div className="pv-drawer__id">
          <h2 id={titleId} className="sys-lead">{p.display_name}</h2>
          <div className="sys-meta">{p.id}{p.domain ? ` · ${DOMAIN_LABEL[p.domain] ?? p.domain}` : ''}</div>
        </div>
        <Status state={TONE_STATE[h.tone]} label={h.label} title={h.note ?? undefined} />
        <button type="button" className="sys-btn" onClick={onClose} aria-label="Close provider details">esc</button>
      </header>

      <div className="sys-drawer-body pv-drawer__body">
        {h.note ? <p className="pv-note">{h.note}</p> : null}
        {p.advisories.length ? (
          <ul className="pv-advisories" aria-label="Needs attention">
            {p.advisories.map((a) => (
              <li key={a.text} data-kind={a.kind}><span className="sys-label">{a.kind}</span>{a.text}</li>
            ))}
          </ul>
        ) : null}

        <section>
          <h3 className="sys-label">Configuration</h3>
          <dl className="pv-kv">
            <div><dt>Credential</dt><dd>{c.keyless ? 'None required' : <code>{c.credential_env}</code>}</dd></div>
            <div><dt>State</dt><dd>{configurationText(p)}</dd></div>
            {c.optional_env.map((o) => (
              <div key={o.name}><dt><code>{o.name}</code></dt><dd>{o.set ? 'set' : 'not set'}</dd></div>
            ))}
            <div>
              <dt>Instances</dt>
              <dd>
                {p.instances ? `${p.instances} in this process` : 'Not loaded in this process yet — the service that uses it has not run'}
                {p.groups.length ? ` · serves ${p.groups.join(', ').replace(/_/g, ' ')}` : ''}
              </dd>
            </div>
          </dl>
          {!c.configured && !c.keyless ? (
            <p className="pv-hint">
              To enable it, set <code>{c.credential_env}</code> on the backend service (a Secret Manager binding in
              production) and redeploy. The value is never shown here. See <code>docs/PROVIDERS.md</code>.
            </p>
          ) : null}
          {c.disabled ? (
            <p className="pv-hint">Remove <code>{p.id}</code> from <code>PROVIDER_DISABLED</code> on the backend to return it to routing.</p>
          ) : null}
        </section>

        <section>
          <h3 className="sys-label">Capabilities</h3>
          {p.capabilities.length ? (
            <ul className="pv-chips">
              {p.capabilities.map((k) => {
                const cap = reg.capabilities.find((x) => x.key === k)
                return <li key={k} title={cap?.description}>{capLabel(k)}</li>
              })}
            </ul>
          ) : (
            <p className="pv-hint">
              This adapter answers no capability in the registry; it is called directly
              {p.groups.length ? ` by the ${p.groups.join(', ').replace(/_/g, ' ')} service` : ' by the service that uses it'}.
            </p>
          )}
        </section>

        <section>
          <h3 className="sys-label">Observed since {stamp(reg.process_started_at)}</h3>
          <dl className="pv-kv">
            <div><dt>Requests</dt><dd className="sys-num">{p.health.requests.toLocaleString('en-US')}{p.health.success_pct != null ? ` · ${p.health.success_pct}% succeeded` : ''}</dd></div>
            <div>
              <dt>In the last {windowLabel(reg.health_window_seconds)}</dt>
              <dd className="sys-num">
                {p.health.window.ok} answered · {p.health.window.failed} failed
                {p.health.window.declined ? ` · ${p.health.window.declined} declined (about one input, the plan or local pacing)` : ''}
              </dd>
            </div>
            <div><dt>Latency</dt><dd className="sys-num">{p.health.requests ? `${ms(p.health.avg_latency_ms)} avg · ${ms(p.health.max_latency_ms)} max` : 'not measured — never called'}</dd></div>
            <div><dt>Last success</dt><dd>{stamp(p.health.last_success_at)}{p.health.last_success_at ? ` (${ago(p.health.last_success_at)})` : ''}</dd></div>
            <div><dt>Last failure</dt><dd>{stamp(p.health.last_failure_at)}{p.health.last_failure_class ? ` · ${failureLabel(p.health.last_failure_class)}` : ''}</dd></div>
            {p.health.last_error && h.tone !== 'pos' ? <div><dt>Last error</dt><dd className="pv-err">{p.health.last_error}</dd></div> : null}
            {p.health.restricted_operations.length ? <div><dt>Not in plan</dt><dd>{p.health.restricted_operations.join(', ')}</dd></div> : null}
            {p.health.held_back_locally ? <div><dt>Held back locally</dt><dd className="sys-num">{p.health.held_back_locally}</dd></div> : null}
          </dl>
        </section>

        <section>
          <h3 className="sys-label">Recent calls</h3>
          {p.recent.length ? (
            <div className="sys-scroll-x">
              <table className="sys-table sys-table--compact pv-recent">
                <caption className="visually-hidden">Most recent calls to {p.display_name}, newest first</caption>
                <thead>
                  <tr><th scope="col">Time</th><th scope="col">Operation</th><th scope="col">Outcome</th><th scope="col" className="num">Status</th><th scope="col" className="num">Duration</th><th scope="col">Request</th></tr>
                </thead>
                <tbody>
                  {p.recent.map((e, i) => (
                    <tr key={`${e.at}-${i}`}>
                      <td>{stamp(e.at)}</td>
                      <td><code>{e.operation}</code>{e.attempt ? <span className="sys-meta"> · retry {e.attempt}</span> : null}</td>
                      <td>
                        <span className="dot" data-tone={outcomeTone(e.outcome)} aria-hidden /> {outcomeLabel(e.outcome)}
                        {e.scope === 'request' && e.outcome !== 'ok' ? <span className="sys-meta"> · about this input</span> : null}
                      </td>
                      <td className="num sys-num">{e.status_code ?? '—'}</td>
                      <td className="num sys-num">{ms(e.latency_ms)}</td>
                      <td>{e.request_id ? <code className="pv-rid">{e.request_id}</code> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="pv-hint">No calls since this server started.</p>}
          <p className="pv-hint">Operations only: the symbols and parameters of each call are not recorded, so one reader never sees what another is researching.</p>
        </section>

        <section>
          <h3 className="sys-label">Request policy</h3>
          <dl className="pv-kv">
            <div><dt>Local rate limit</dt><dd className="sys-num">{p.policy.requests_per_minute} per minute</dd></div>
            <div><dt>Timeout</dt><dd className="sys-num">{p.policy.timeout_seconds} s</dd></div>
            <div><dt>Retries</dt><dd>{p.policy.max_retries} on transient failures only, with jittered backoff</dd></div>
            <div><dt>Cooldown</dt><dd>{p.policy.cooldown_seconds} s after {p.policy.cooldown_after_failures} consecutive failures</dd></div>
          </dl>
        </section>

        <section>
          <h3 className="sys-label">Source and terms</h3>
          <dl className="pv-kv">
            <div><dt>Kind</dt><dd>{p.source_kind ? SOURCE_KIND_LABEL[p.source_kind] ?? p.source_kind : '—'}</dd></div>
            <div><dt>Reached via</dt><dd>{p.endpoint ?? '—'}</dd></div>
            {p.terms ? (
              <div>
                <dt>Terms</dt>
                <dd>
                  {TERMS_STATUS_LABEL[p.terms.terms_status]} ({p.terms.terms_checked_on})
                  {p.terms.terms_url ? (
                    <> · <a href={p.terms.terms_url} target="_blank" rel="noopener noreferrer">read<span className="visually-hidden"> {p.display_name} terms (opens in a new tab)</span></a></>
                  ) : null}
                </dd>
              </div>
            ) : null}
          </dl>
          {p.terms?.notes ? <p className="pv-hint">{p.terms.notes}</p> : null}
          {p.terms?.attribution ? <p className="pv-hint">Required notice: “{p.terms.attribution}”</p> : null}
        </section>
      </div>
    </aside>
  )
}

export function Coverage({ reg, capLabel }: { reg: Registry; capLabel: (k: string) => string }) {
  const name = (id: string) => reg.providers.find((p) => p.id === id)?.display_name ?? id
  const rows = [...reg.capabilities].sort((a: CapabilityRecord, b: CapabilityRecord) => a.eligible.length - b.eligible.length || a.label.localeCompare(b.label))
  return (
    <div className="sys-scroll-x">
      <table className="sys-table sys-table--compact pv-coverage">
        <caption className="visually-hidden">Which providers can answer each capability now</caption>
        <thead>
          <tr><th scope="col">Capability</th><th scope="col">Combined by</th><th scope="col">Eligible now</th><th scope="col">Implemented, not eligible</th></tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const idle = c.implemented_by.filter((v) => !c.eligible.includes(v))
            return (
              <tr key={c.key}>
                <th scope="row" title={c.description}>{capLabel(c.key)}<span className="pv-open__id">{c.key}</span></th>
                <td>{c.reconciliation.replace(/_/g, ' ')}{c.fanout_limit ? ` · up to ${c.fanout_limit}` : ''}</td>
                <td>{c.eligible.length ? c.eligible.map(name).join(', ') : <span className="pv-none">none</span>}</td>
                <td className="pv-muted">{idle.length ? idle.map(name).join(', ') : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function ProviderConsole() {
  const { load, refreshing, refresh } = useRegistry()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [open, setOpen] = useState<string | null>(null)
  const opener = useRef<HTMLElement | null>(null)

  const reg = load.kind === 'ready' ? load.reg : null
  const list = useMemo(() => (reg ? filterProviders(reg.providers, filters) : []), [reg, filters])
  const capLabel = useCallback((k: string) => reg?.capabilities.find((c) => c.key === k)?.label ?? k.replace(/_/g, ' '), [reg])
  const openRecord = reg && open ? reg.providers.find((p) => p.id === open) ?? null : null
  const close = useCallback(() => {
    setOpen(null)
    opener.current?.focus()
  }, [])

  if (load.kind === 'loading') {
    return <Panel title="Providers" state="waking"><StateBlock state="waking" title="Reading the provider registry" /></Panel>
  }
  if (load.kind === 'forbidden') {
    return (
      <Panel title="Providers" state="blocked">
        <StateBlock state="blocked" title="Provider diagnostics are not available to this account" detail="Sign in again, or ask the operator for access. Nothing is described as healthy without being read." />
      </Panel>
    )
  }
  if (load.kind === 'unreadable') {
    return (
      <Panel title="Providers" state="unavailable">
        <StateBlock state="unavailable" title="The provider registry answered with something unreadable" detail="This usually means the backend is older than this page or a proxy answered instead. No provider is shown rather than a guessed list." />
      </Panel>
    )
  }
  if (load.kind === 'failed' || !reg) {
    const status = load.kind === 'failed' ? load.status : null
    return (
      <Panel title="Providers" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The provider registry could not be read"
          detail={`${status ? `The backend answered ${status}. ` : 'The request did not complete. '}No vendor is described as healthy on the strength of a failed request.`}
        >
          <button type="button" className="sys-btn" onClick={() => void refresh()}>Try again</button>
        </StateBlock>
      </Panel>
    )
  }

  return (
    <div className="pv">
      <div className="pv-head">
        <p className="pv-lede">
          Counters since this server started ({stamp(reg.process_started_at)}). A vendor is healthy only if it answered in
          the last {windowLabel(reg.health_window_seconds)}; configured but quiet reads as idle or stale, not healthy.
          {reg.adapter_version ? <> Adapters at build <code>{reg.adapter_version}</code>.</> : null}
        </p>
        <div className="pv-refresh">
          <button type="button" className="sys-btn" onClick={() => void refresh()} disabled={refreshing} aria-busy={refreshing}>
            {refreshing ? 'Reading…' : 'Refresh'}
          </button>
          <span className="sys-meta" aria-live="polite">{load.note ?? ''}</span>
        </div>
      </div>

      {reg.providers.length === 0 ? (
        <Panel title="Providers" state="unavailable">
          <StateBlock state="unavailable" title="No providers are registered" detail="The backend reported an empty registry. That is a deployment fault: every build ships its adapters." />
        </Panel>
      ) : (
        <>
          <Summary reg={reg} />
          <Panel title="Catalog" subtitle="select a provider for its configuration, recent calls and terms" flush>
            <Toolbar reg={reg} filters={filters} setFilters={setFilters} shown={list.length} />
            {list.length ? (
              <Catalogue
                list={list}
                capLabel={capLabel}
                openId={open}
                onOpen={(p, el) => { opener.current = el; setOpen(p.id) }}
              />
            ) : (
              <StateBlock
                state="info"
                title="No provider matches these filters"
              >
                <button type="button" className="sys-btn" onClick={() => setFilters(NO_FILTERS)}>Clear filters</button>
              </StateBlock>
            )}
          </Panel>
          <RoutingFigure />
          <Panel title="Coverage" subtitle="who can answer each question right now" flush>
            <Coverage reg={reg} capLabel={capLabel} />
          </Panel>
        </>
      )}

      {openRecord ? <Detail p={openRecord} reg={reg} capLabel={capLabel} onClose={close} /> : null}
    </div>
  )
}
