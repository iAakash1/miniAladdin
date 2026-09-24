/**
 * Provider health, as the interface states it.
 *
 * The backend's `health_state` is derived from the last events it saw. Two of
 * its states need more precision before they are shown to a reader:
 *
 *   HEALTHY with zero requests — configured, but nothing has asked it anything
 *   in this process. That is "idle", not evidence of health.
 *   HEALTHY with local-limiter rejections — the vendor answers; our own pacing
 *   held some calls back. Healthy, with that stated.
 */

export interface VendorSnapshot {
  vendor: string
  configured: boolean
  cooling_down?: boolean
  cooldown_remaining_seconds?: number
  health_state?: string
  requests: number
  success_pct: number | null
  failures: number
  rate_limited: number
  avg_latency_ms?: number | null
  max_latency_ms?: number | null
  last_error?: string | null
  last_failure_class?: string | null
  last_success_at?: number | null
  last_attempt_at?: number | null
  shared?: boolean
}

export type HealthTone = 'pos' | 'warn' | 'neg' | 'muted' | 'info'

export type HealthState =
  | 'HEALTHY' | 'IDLE' | 'DEGRADED' | 'RATE_LIMITED' | 'AUTH_FAILURE'
  | 'NOT_ENTITLED' | 'TIMEOUT' | 'UNAVAILABLE' | 'COOLDOWN'
  | 'NOT_CONFIGURED' | 'DEV_ONLY'

export interface VendorHealth {
  state: HealthState
  tone: HealthTone
  label: string
  /** One line a reader can act on. Never a raw upstream error. */
  note: string | null
}

const FAILURE_LABEL: Record<string, string> = {
  rate_limited: 'rate limited by the vendor',
  auth_failure: 'credential rejected',
  not_entitled: 'plan does not include this data',
  timeout: 'timed out',
  upstream_failure: 'vendor returned an error',
  parse_failure: 'response could not be parsed',
  local_limiter: 'held back by local rate limit',
  unavailable: 'vendor unreachable',
}

export function failureLabel(cls: string | null | undefined): string | null {
  if (!cls) return null
  return FAILURE_LABEL[cls] ?? cls.replace(/_/g, ' ')
}

/**
 * The upstream error with anything URL-shaped removed. Error strings from
 * HTTP clients embed the request URL; that is diagnostic detail, not
 * something to print in a table.
 */
export function sanitizeError(raw: string | null | undefined): string | null {
  if (!raw) return null
  const cleaned = raw
    .replace(/\bfor url:?\s*\S+/gi, '')
    .replace(/https?:\/\/\S+/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
    .replace(/[·:,-]\s*$/, '')
    .trim()
  return cleaned.length ? cleaned.slice(0, 140) : null
}

export function classifyVendor(v: VendorSnapshot): VendorHealth {
  if (!v.configured || v.health_state === 'NOT_CONFIGURED') {
    return { state: 'NOT_CONFIGURED', tone: 'muted', label: 'Not configured', note: 'No credential in this deployment' }
  }
  if (v.health_state === 'DEV_ONLY') {
    return { state: 'DEV_ONLY', tone: 'muted', label: 'Development only', note: 'Disabled outside local development' }
  }
  if (v.cooling_down || v.health_state === 'COOLDOWN') {
    const s = v.cooldown_remaining_seconds
    return {
      state: 'COOLDOWN', tone: 'warn', label: 'Cooling down',
      note: `Paused after repeated failures${s ? ` · retries in ${Math.ceil(s)}s` : ''}`,
    }
  }
  switch (v.health_state) {
    case 'AUTH_FAILURE':
      return { state: 'AUTH_FAILURE', tone: 'neg', label: 'Auth failure', note: 'The vendor rejected the credential' }
    case 'NOT_ENTITLED':
      return { state: 'NOT_ENTITLED', tone: 'warn', label: 'Not entitled', note: 'The current plan does not include this data' }
    case 'RATE_LIMITED':
      return {
        state: 'RATE_LIMITED', tone: 'warn', label: 'Rate limited',
        note: v.last_failure_class === 'local_limiter' ? 'Held back by the local rate limit' : 'The vendor is throttling requests',
      }
    case 'TIMEOUT':
      return { state: 'TIMEOUT', tone: 'warn', label: 'Timing out', note: 'Recent requests exceeded the time budget' }
    case 'UNAVAILABLE':
      return { state: 'UNAVAILABLE', tone: 'neg', label: 'Unavailable', note: failureLabel(v.last_failure_class) ?? 'Recent requests failed' }
    case 'DEGRADED':
      return {
        state: 'DEGRADED', tone: 'warn', label: 'Degraded',
        note: `${v.failures} of ${v.requests} requests failed`,
      }
    default:
      break
  }
  if (v.requests === 0) {
    return { state: 'IDLE', tone: 'info', label: 'Idle', note: 'Configured · not called since the server started' }
  }
  const throttled = v.rate_limited > 0 && v.last_failure_class === 'local_limiter'
  return {
    state: 'HEALTHY', tone: 'pos', label: 'Healthy',
    note: throttled ? `${v.rate_limited} calls held back by the local rate limit` : null,
  }
}

export interface ProviderSummary {
  vendors: number
  configured: number
  healthy: number
  idle: number
  constrained: number
  failing: number
  notConfigured: number
}

/** Counts over distinct vendors — one vendor can serve several capabilities. */
export function summarize(byCapability: Record<string, VendorSnapshot[]>): ProviderSummary {
  const worst = new Map<string, VendorHealth>()
  const rank: Record<HealthTone, number> = { neg: 4, warn: 3, pos: 2, info: 1, muted: 0 }
  for (const list of Object.values(byCapability)) {
    for (const v of list) {
      const h = classifyVendor(v)
      const held = worst.get(v.vendor)
      if (!held || rank[h.tone] > rank[held.tone]) worst.set(v.vendor, h)
    }
  }
  const values = [...worst.values()]
  return {
    vendors: values.length,
    configured: values.filter((h) => h.state !== 'NOT_CONFIGURED').length,
    healthy: values.filter((h) => h.state === 'HEALTHY').length,
    idle: values.filter((h) => h.state === 'IDLE').length,
    constrained: values.filter((h) => h.tone === 'warn').length,
    failing: values.filter((h) => h.tone === 'neg').length,
    notConfigured: values.filter((h) => h.state === 'NOT_CONFIGURED').length,
  }
}
