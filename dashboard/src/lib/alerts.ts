'use client'

/**
 * Price alerts and the in-app inbox.
 *
 * Alerts are evaluated on the server by a scheduled job, not in this browser:
 * this module only creates, edits and reads them. `last_result` is what the
 * evaluator concluded on its last pass — including "skipped: quote is stale"
 * when it could not evaluate — and the interface shows it as such.
 */

import { useEffect, useSyncExternalStore } from 'react'

import { authFetch } from './persistence'

export type AlertKind = 'cross_above' | 'cross_below' | 'day_move' | 'period_move' | 'range_exit' | 'new_filing'

export interface PriceAlert {
  id: string
  ticker: string
  kind: AlertKind
  threshold: number | null
  threshold_high: number | null
  direction: 'up' | 'down' | 'either' | null
  period_days: number | null
  form_types: string[]
  status: 'active' | 'paused' | 'triggered'
  repeat: boolean
  armed: boolean
  note: string | null
  condition: string
  last_evaluated_at: string | null
  last_observed_value: number | null
  last_observed_at: string | null
  last_source: string | null
  last_result: string | null
  last_triggered_at: string | null
  created_at: string
}

export interface AlertDraft {
  ticker: string
  kind: AlertKind
  threshold?: number | null
  threshold_high?: number | null
  direction?: 'up' | 'down' | 'either' | null
  period_days?: number | null
  form_types?: string[]
  repeat?: boolean
  note?: string | null
}

export const KIND_LABEL: Record<AlertKind, string> = {
  cross_above: 'Price crosses above',
  cross_below: 'Price crosses below',
  day_move: 'Moves in a day by',
  period_move: 'Moves over a period by',
  range_exit: 'Leaves a price range',
  new_filing: 'Files with the SEC',
}

export const FILING_FORMS = ['10-K', '10-Q', '8-K', 'S-1', 'DEF 14A', '4', '13D', '13G', '10-K/A', '10-Q/A', '8-K/A']

/** The server's rules, mirrored so the form can say what is wrong first. */
export function draftProblems(d: AlertDraft): string[] {
  const out: string[] = []
  if (!/^[A-Z][A-Z0-9.^-]{0,9}$/.test((d.ticker || '').toUpperCase())) out.push('Enter a valid ticker.')
  const t = d.threshold
  if (d.kind === 'cross_above' || d.kind === 'cross_below') {
    if (!(typeof t === 'number' && Number.isFinite(t) && t > 0)) out.push('Enter a price above zero.')
  }
  if (d.kind === 'day_move' || d.kind === 'period_move') {
    if (!(typeof t === 'number' && t > 0 && t <= 100)) out.push('Enter a move between 0 and 100%.')
    if (d.kind === 'period_move' && !(Number.isInteger(d.period_days) && (d.period_days as number) >= 2 && (d.period_days as number) <= 260)) {
      out.push('The period is 2 to 260 trading days.')
    }
  }
  if (d.kind === 'range_exit') {
    const hi = d.threshold_high
    if (!(typeof t === 'number' && typeof hi === 'number' && t > 0 && hi > t)) out.push('Enter a low and a high price, low below high.')
  }
  return out
}

export function describeResult(a: PriceAlert): string {
  if (a.status === 'paused') return 'paused'
  if (!a.last_result) return 'waiting for the first evaluation'
  return a.last_result
}

/* ── store ──────────────────────────────────────────────────────────────── */

let alerts: PriceAlert[] = []
export type AlertsStatus = 'idle' | 'loading' | 'ready' | 'error' | 'signed-out'
let loaded: AlertsStatus = 'idle'
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

export async function refreshAlerts(): Promise<void> {
  loaded = 'loading'; emit()
  try {
    const r = await authFetch('/api/alerts')
    // A refused session is not an outage: say "sign in", not "unavailable".
    if (r.status === 401) { alerts = []; loaded = 'signed-out'; emit(); return }
    if (!r.ok) throw new Error(String(r.status))
    alerts = ((await r.json()) as { alerts: PriceAlert[] }).alerts
    loaded = 'ready'
  } catch {
    loaded = 'error'
  }
  emit()
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  if (loaded === 'idle') void refreshAlerts()
  return () => { listeners.delete(cb) }
}

const EMPTY: PriceAlert[] = []
export function useAlerts(): PriceAlert[] {
  return useSyncExternalStore(subscribe, () => alerts, () => EMPTY)
}
export function useAlertsStatus(): AlertsStatus {
  return useSyncExternalStore(subscribe, () => loaded, () => 'idle' as const)
}

async function detail(r: Response): Promise<string> {
  try {
    const b = await r.json() as { detail?: unknown }
    if (typeof b.detail === 'string') return b.detail
    if (Array.isArray(b.detail)) return 'Some fields are not valid.'
  } catch { /* fall through */ }
  return `the request returned ${r.status}`
}

export async function createAlert(d: AlertDraft): Promise<PriceAlert> {
  const r = await authFetch('/api/alerts', { method: 'POST', body: JSON.stringify({ ...d, ticker: d.ticker.toUpperCase() }) })
  if (!r.ok) throw new Error(await detail(r))
  const created = await r.json() as PriceAlert
  alerts = [created, ...alerts]; emit()
  return created
}

/** Change an alert's condition. The server starts it from scratch, and a
 *  triggered alert is re-armed: a changed condition is a new question. */
export async function updateAlert(a: PriceAlert, d: AlertDraft): Promise<PriceAlert> {
  const body: Record<string, unknown> = { definition: { ...d, ticker: a.ticker } }
  if (a.status === 'triggered') body.status = 'active'
  const r = await authFetch(`/api/alerts/${encodeURIComponent(a.id)}`, { method: 'PATCH', body: JSON.stringify(body) })
  if (!r.ok) throw new Error(await detail(r))
  const updated = await r.json() as PriceAlert
  alerts = alerts.map((x) => (x.id === a.id ? updated : x)); emit()
  return updated
}

export async function setAlertStatus(id: string, status: 'active' | 'paused'): Promise<void> {
  const r = await authFetch(`/api/alerts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ status }) })
  if (!r.ok) throw new Error(await detail(r))
  const updated = await r.json() as PriceAlert
  alerts = alerts.map((a) => (a.id === id ? updated : a)); emit()
}

export async function deleteAlert(id: string): Promise<void> {
  const r = await authFetch(`/api/alerts/${encodeURIComponent(id)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await detail(r))
  alerts = alerts.filter((a) => a.id !== id); emit()
}

/** Active alerts per ticker, for row indicators. */
export function alertCounts(list: PriceAlert[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const a of list) if (a.status === 'active') out[a.ticker] = (out[a.ticker] ?? 0) + 1
  return out
}

/* ── inbox ──────────────────────────────────────────────────────────────── */

export interface InboxItem {
  id: string
  kind: string
  title: string
  body: string | null
  link: string | null
  read: boolean
  createdAt: string
  event: {
    ticker: string; kind: string; condition_text: string; observed_value: number | null; observed_text: string | null
    threshold: number | null; source: string | null; source_timestamp: string | null
    freshness: 'live' | 'delayed' | 'end_of_day' | 'stale' | null; triggered_at: string
  } | null
}

export type InboxStatus = 'idle' | 'loading' | 'ready' | 'error' | 'signed-out'

export interface InboxState {
  notifications: InboxItem[]
  /** The server's count of unread notifications, never a local tally. */
  unread: number
  status: InboxStatus
}

let inbox: InboxState = { notifications: [], unread: 0, status: 'idle' }
const inboxListeners = new Set<() => void>()
const emitInbox = () => inboxListeners.forEach((l) => l())

export async function refreshInbox(): Promise<void> {
  if (inbox.status === 'idle') { inbox = { ...inbox, status: 'loading' }; emitInbox() }
  try {
    const r = await authFetch('/api/notifications?limit=100')
    if (r.status === 401) { inbox = { notifications: [], unread: 0, status: 'signed-out' }; emitInbox(); return }
    if (!r.ok) throw new Error(String(r.status))
    const body = await r.json() as { notifications: InboxItem[]; unread: number }
    inbox = { notifications: body.notifications, unread: body.unread, status: 'ready' }
  } catch {
    // Keep what was last read, and say the read failed.
    inbox = { ...inbox, status: 'error' }
  }
  emitInbox()
}

const EMPTY_INBOX: InboxState = { notifications: [], unread: 0, status: 'idle' }
export function useInbox(): InboxState {
  return useSyncExternalStore(
    (cb) => { inboxListeners.add(cb); if (inbox.status === 'idle') void refreshInbox(); return () => { inboxListeners.delete(cb) } },
    () => inbox, () => EMPTY_INBOX,
  )
}

/** Poll the unread count while the page is visible. The evaluator runs on a schedule; this only reads. */
export function useInboxPolling(intervalMs = 120_000) {
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void refreshInbox() }, intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
}

/** Mark one notification (or all) read on the server, then re-read the server's count. */
export async function markRead(id?: string): Promise<boolean> {
  try {
    const r = await authFetch(id ? `/api/notifications/${encodeURIComponent(id)}/read` : '/api/notifications/read-all', { method: 'POST' })
    await refreshInbox()
    return r.ok
  } catch {
    return false
  }
}
