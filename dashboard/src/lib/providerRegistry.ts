/**
 * The providers page's model of `/api/providers/registry`.
 *
 * The backend sends one record per vendor — catalogue, capabilities, merged
 * health, recent calls — so nothing here lists vendors or names them. This
 * module only reads the payload defensively, states each vendor's health with
 * the same classifier as the rest of the product, and computes the summary and
 * the filters from those records. Every count on the page comes from here,
 * never from a number someone typed.
 */

import { classifyVendor, type HealthTone, type VendorHealth, type VendorSnapshot } from './providerHealth'

export interface RecentCall {
  at: number
  operation: string
  /** "ok", "empty" (answered: nothing matches), or a failure class. */
  outcome: string
  latency_ms: number
  status_code: number | null
  attempt: number
  /** "request": about one input (a 404 for an unknown symbol); "vendor": about the vendor. */
  scope: 'request' | 'vendor'
  request_id: string | null
}

export interface ProviderHealthRecord {
  state: string
  requests: number
  failures: number
  success_pct: number | null
  avg_latency_ms: number | null
  max_latency_ms: number | null
  held_back_locally: number
  last_success_at: number | null
  last_failure_at: number | null
  last_attempt_at: number | null
  last_failure_class: string | null
  last_error: string | null
  cooling_down: boolean
  cooldown_remaining_seconds: number
  restricted_operations: string[]
  /** Inside the health window. `failed` counts the vendor's faults only;
   *  `declined` is a 404 about one input, a plan boundary or our own pacing. */
  window: { ok: number; failed: number; declined?: number }
}

export interface ProviderRecord {
  id: string
  display_name: string
  domain: string | null
  source_kind: string | null
  endpoint: string | null
  catalogued: boolean
  groups: string[]
  capabilities: string[]
  instances: number
  configuration: {
    credential_env: string | null
    keyless: boolean
    configured: boolean
    disabled: boolean
    credential_state: string
    optional_env: Array<{ name: string; set: boolean }>
  }
  policy: {
    requests_per_minute: number
    timeout_seconds: number
    max_retries: number
    cooldown_after_failures: number
    cooldown_seconds: number
  }
  health: ProviderHealthRecord
  recent: RecentCall[]
  terms: {
    terms_status: 'reviewed' | 'located' | 'not_located'
    terms_url: string | null
    notes: string | null
    attribution: string | null
    terms_checked_on: string
  } | null
  advisories: Array<{ kind: 'configuration' | 'license' | 'catalog'; text: string }>
}

export interface CapabilityRecord {
  key: string
  label: string
  description: string
  reconciliation: string
  fanout_limit: number | null
  implemented_by: string[]
  eligible: string[]
}

export interface Registry {
  generated_at: number
  process_started_at: number
  health_window_seconds: number
  adapter_version: string | null
  disabled: string[]
  providers: ProviderRecord[]
  capabilities: CapabilityRecord[]
}

/**
 * The payload, or null when it is not one. A proxy error page, an older
 * backend without the endpoint, or a truncated reply must read as "could not
 * be read" — not as a registry with no providers in it.
 */
export function parseRegistry(raw: unknown): Registry | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Partial<Registry>
  if (!Array.isArray(r.providers) || !Array.isArray(r.capabilities)) return null
  if (typeof r.health_window_seconds !== 'number' || typeof r.process_started_at !== 'number') return null
  const providers = r.providers.filter(
    (p): p is ProviderRecord =>
      Boolean(p) && typeof p.id === 'string' && typeof p.display_name === 'string'
      && Boolean(p.health) && typeof p.health.state === 'string' && typeof p.health.requests === 'number'
      && Boolean(p.health.window) && typeof p.health.window.ok === 'number' && typeof p.health.window.failed === 'number'
      && Boolean(p.configuration) && Array.isArray(p.capabilities) && Array.isArray(p.recent),
  )
  const capabilities = r.capabilities.filter(
    (c): c is CapabilityRecord =>
      Boolean(c) && typeof c.key === 'string' && typeof c.label === 'string'
      && Array.isArray(c.implemented_by) && Array.isArray(c.eligible),
  )
  return { ...(r as Registry), providers, capabilities }
}

/** The record in the shape the shared classifier reads. */
export function toSnapshot(p: ProviderRecord): VendorSnapshot {
  return {
    vendor: p.id,
    configured: p.configuration.configured,
    cooling_down: p.health.cooling_down,
    cooldown_remaining_seconds: p.health.cooldown_remaining_seconds,
    health_state: p.health.state,
    requests: p.health.requests,
    success_pct: p.health.success_pct,
    failures: p.health.failures,
    rate_limited: p.health.held_back_locally,
    avg_latency_ms: p.health.avg_latency_ms,
    max_latency_ms: p.health.max_latency_ms,
    last_error: p.health.last_error,
    last_failure_class: p.health.last_failure_class,
    last_success_at: p.health.last_success_at,
    last_attempt_at: p.health.last_attempt_at,
    restricted_operations: p.health.restricted_operations,
  }
}

export function classify(p: ProviderRecord): VendorHealth {
  return classifyVendor(toSnapshot(p))
}

export interface RegistrySummary {
  registered: number
  configured: number
  /** Answered at least once inside the health window. Evidence, not a key. */
  answeringNow: number
  failing: number
  constrained: number
  staleOrIdle: number
  notConfigured: number
  disabled: number
  /** Capabilities no configured, enabled, un-benched vendor can answer. */
  uncovered: CapabilityRecord[]
}

export function summarizeRegistry(reg: Registry): RegistrySummary {
  const health = reg.providers.map((p) => ({ p, h: classify(p) }))
  return {
    registered: reg.providers.length,
    configured: reg.providers.filter((p) => p.configuration.configured && !p.configuration.disabled).length,
    answeringNow: reg.providers.filter((p) => p.health.window.ok > 0).length,
    failing: health.filter(({ h }) => h.tone === 'neg').length,
    constrained: health.filter(({ h }) => h.tone === 'warn').length,
    staleOrIdle: health.filter(({ h }) => h.state === 'STALE' || h.state === 'IDLE').length,
    notConfigured: health.filter(({ h }) => h.state === 'NOT_CONFIGURED').length,
    disabled: health.filter(({ h }) => h.state === 'DISABLED').length,
    uncovered: reg.capabilities.filter((c) => c.eligible.length === 0),
  }
}

export type StateFilter =
  | 'all' | 'failing' | 'constrained' | 'healthy' | 'no_recent_success'
  | 'stale_or_idle' | 'not_configured' | 'disabled'

export const STATE_FILTERS: Array<{ value: StateFilter; label: string }> = [
  { value: 'all', label: 'Any state' },
  { value: 'failing', label: 'Failing' },
  { value: 'constrained', label: 'Rate limited or degraded' },
  { value: 'healthy', label: 'Healthy' },
  { value: 'no_recent_success', label: 'No success in the window' },
  { value: 'stale_or_idle', label: 'Stale or idle' },
  { value: 'not_configured', label: 'Not configured' },
  { value: 'disabled', label: 'Disabled' },
]

export interface Filters {
  query: string
  domain: string
  capability: string
  state: StateFilter
}

export const NO_FILTERS: Filters = { query: '', domain: 'all', capability: 'all', state: 'all' }

function matchesState(p: ProviderRecord, h: VendorHealth, state: StateFilter): boolean {
  switch (state) {
    case 'all': return true
    case 'failing': return h.tone === 'neg'
    case 'constrained': return h.tone === 'warn'
    case 'healthy': return h.state === 'HEALTHY'
    case 'no_recent_success':
      return p.configuration.configured && !p.configuration.disabled && p.health.window.ok === 0
    case 'stale_or_idle': return h.state === 'STALE' || h.state === 'IDLE'
    case 'not_configured': return h.state === 'NOT_CONFIGURED'
    case 'disabled': return h.state === 'DISABLED'
  }
}

/** Providers matching every active filter. The query matches name, id, endpoint and capability. */
export function filterProviders(list: ProviderRecord[], f: Filters): ProviderRecord[] {
  const q = f.query.trim().toLowerCase()
  return list.filter((p) => {
    if (f.domain !== 'all' && p.domain !== f.domain) return false
    if (f.capability !== 'all' && !p.capabilities.includes(f.capability)) return false
    if (!matchesState(p, classify(p), f.state)) return false
    if (!q) return true
    return [p.display_name, p.id, p.endpoint ?? '', ...p.capabilities]
      .some((field) => field.toLowerCase().includes(q))
  })
}

export function filtersActive(f: Filters): boolean {
  return f.query.trim() !== '' || f.domain !== 'all' || f.capability !== 'all' || f.state !== 'all'
}

const OUTCOME_LABEL: Record<string, string> = {
  ok: 'answered',
  empty: 'answered: nothing matches',
  rate_limited: 'rate limited by the vendor',
  local_limiter: 'held back by the local limit',
  auth_failure: 'credential rejected',
  not_entitled: 'not in the plan',
  timeout: 'timed out',
  upstream_failure: 'vendor error',
  parse_failure: 'unreadable reply',
  unavailable: 'no usable answer',
}

export function outcomeLabel(outcome: string): string {
  return OUTCOME_LABEL[outcome] ?? outcome.replace(/_/g, ' ')
}

export function outcomeTone(outcome: string): HealthTone {
  if (outcome === 'ok' || outcome === 'empty') return 'pos'
  if (outcome === 'auth_failure' || outcome === 'unavailable' || outcome === 'upstream_failure' || outcome === 'parse_failure') return 'neg'
  return 'warn'
}

/**
 * A fingerprint of everything the page shows about health, so a refresh can
 * say truthfully whether anything changed.
 */
export function healthFingerprint(reg: Registry): string {
  return JSON.stringify(reg.providers.map((p) => [
    p.id, p.health.state, p.health.requests, p.health.failures,
    p.health.last_success_at, p.health.last_failure_at, p.configuration.configured, p.configuration.disabled,
  ]))
}

export const DOMAIN_LABEL: Record<string, string> = {
  market_data: 'Market data', fundamentals: 'Fundamentals', filings: 'Filings', macro: 'Macro',
  news: 'News', search: 'Search', identity: 'Identity', official_record: 'Official record',
  knowledge: 'Knowledge', visual: 'Visual identity',
}

export const SOURCE_KIND_LABEL: Record<string, string> = {
  commercial: 'Commercial API', government: 'Government agency', intergovernmental: 'Intergovernmental body',
  open_data: 'Open data', unofficial: 'Unofficial library', platform: 'Scraping platform',
}

export const TERMS_STATUS_LABEL: Record<string, string> = {
  reviewed: 'Terms reviewed',
  located: 'Terms located, not reviewed',
  not_located: 'Terms not located',
}

/** "4m ago", "3h ago", "2d ago", or null. Seconds since the epoch in, relative to `now`. */
export function ago(epochSeconds: number | null | undefined, now = Date.now() / 1000): string | null {
  if (!epochSeconds) return null
  const m = Math.round((now - epochSeconds) / 60)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  return h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`
}

export function windowLabel(seconds: number): string {
  return seconds % 3600 === 0 ? `${seconds / 3600}h` : `${Math.round(seconds / 60)}m`
}
