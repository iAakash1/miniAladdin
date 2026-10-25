/**
 * The paper account, as the broker reports it.
 *
 * Every figure here came from Alpaca's paper environment. None of it is
 * computed locally — no fill is simulated, no average price is derived, no
 * profit is inferred from a price this product happens to know. If the broker
 * did not say it, this module does not have it.
 *
 * That restraint is the point. A research terminal that quietly computes what
 * an account "should" be worth is a terminal that will one day disagree with
 * the broker, and the reader will have no way to tell which of the two is
 * wrong.
 */

import { clearAuthResourceCache, readAuthResource } from './auth-resource'
import { authFetch } from './persistence'
import { readResource } from './resource'

/** Whether trading is possible at all, and if not, a sentence saying why. */
export interface PaperStatus {
  configured: boolean
  reason: string | null
  environment: string
  /** The paper hostname orders would reach. Public, and shown deliberately. */
  endpoint: string
  access?: { enabled: boolean; reason: string | null }
  tradable?: boolean
}

export interface PaperAccess {
  authenticated: true
  authorized: true
  environment: 'paper'
}

/** Alpaca's account fields, as strings — the broker returns them that way. */
export interface PaperAccount {
  equity?: string
  last_equity?: string
  cash?: string
  buying_power?: string
  portfolio_value?: string
  status?: string
  currency?: string
  account_number?: string
  pattern_day_trader?: boolean
}

export interface PaperPosition {
  symbol: string
  qty?: string
  avg_entry_price?: string
  current_price?: string
  market_value?: string
  cost_basis?: string
  unrealized_pl?: string
  unrealized_plpc?: string
  unrealized_intraday_pl?: string
  unrealized_intraday_plpc?: string
  side?: string
  asset_class?: string
}

export interface PaperOrder {
  id: string
  client_order_id?: string
  symbol: string
  qty?: string
  notional?: string | null
  updated_at?: string | null
  canceled_at?: string | null
  expired_at?: string | null
  failed_at?: string | null
  filled_qty?: string
  filled_avg_price?: string | null
  side?: string
  type?: string
  time_in_force?: string
  status?: string
  created_at?: string
  submitted_at?: string
  filled_at?: string | null
  limit_price?: string | null
}

export interface OrderIntent {
  symbol: string
  side: 'buy' | 'sell'
  /** Exactly one of qty (shares) and notional (dollars). */
  qty?: number | null
  notional?: number | null
  order_type: 'market' | 'limit'
  time_in_force: 'day' | 'gtc'
  limit_price?: number | null
  /** Issued by the preview and sent back with the confirmation. */
  client_order_id?: string | null
  origin?: 'ticket' | 'watchlist' | 'research' | 'position' | null
}

export type QuoteFreshness = 'live' | 'delayed' | 'end_of_day' | 'stale' | 'undated' | 'unavailable'

export interface OrderPreview {
  ok: boolean
  /** Everything wrong with the order, not just the first thing. */
  problems: string[]
  /** Things the operator should know that do not block the order. */
  warnings: string[]
  order: {
    symbol: string; side: string; order_type: string; time_in_force: string
    qty: number | null; notional: number | null; limit_price: number | null
  }
  client_order_id: string
  quote: { price: number | null; as_of: string | null; source: string | null; freshness: QuoteFreshness }
  estimate: { value: number | null; qty: number | null; basis: string }
  buying_power: number | null
  market_open: boolean | null
  asset: { tradable: boolean | null; fractionable: boolean | null; shortable?: boolean | null; exchange: string | null; name?: string | null } | null
  environment: string
}

/** What a confirmation produced: an order the broker holds, or an outcome still being resolved. */
export type PlacementResult =
  | { kind: 'placed'; order: PaperOrder; clientOrderId: string; replayed: boolean; reconciledAfter: string | null }
  | { kind: 'unknown'; clientOrderId: string; detail: string }

export interface PaperConnection {
  state: 'connected' | 'blocked' | 'not_configured' | 'credentials_rejected' | 'restricted' | 'rate_limited' | 'unavailable'
  detail?: string
  account_status?: string
  trading_blocked?: boolean
  account_blocked?: boolean
  checked_at?: string
}

export interface PaperHistoryPoint { t: number; equity: number; profit_loss: number | null; profit_loss_pct: number | null }

export interface PaperHistory {
  points: PaperHistoryPoint[]
  base_value: number | null
  timeframe: string | null
  period: string
}

export interface PaperAnalytics {
  reported: Record<string, number | null>
  derived: {
    day_change: number | null; day_change_pct: number | null; unrealized_pl_total: number | null
    gross_exposure: number | null; cash_share: number | null; largest_weight: number | null; positions: number
  }
  weights: Array<{ symbol: string; market_value: number | null; weight: number | null; unrealized_pl: number | null; unrealized_plpc: number | null; side?: string }>
  best: { symbol: string; unrealized_plpc: number | null } | null
  worst: { symbol: string; unrealized_plpc: number | null } | null
  order_activity: Record<string, number>
  realized_pl: null
  label: string
}

/** Alpaca statuses after which an order cannot change. */
export const TERMINAL_STATUSES = ['filled', 'canceled', 'expired', 'rejected', 'replaced', 'done_for_day', 'stopped', 'suspended']

export function isOpenOrder(status?: string | null): boolean {
  return Boolean(status) && !TERMINAL_STATUSES.includes(String(status).toLowerCase())
}

/**
 * The ticket's own rules, mirrored from the server so the form can say what
 * is wrong before a round trip. The server checks again and has the last word.
 */
export function ticketProblems(i: OrderIntent): string[] {
  const out: string[] = []
  const hasQty = i.qty !== null && i.qty !== undefined
  const hasNotional = i.notional !== null && i.notional !== undefined
  if (hasQty === hasNotional) out.push('Give a share quantity or a dollar amount.')
  if (hasQty && (!Number.isFinite(i.qty as number) || (i.qty as number) <= 0)) out.push('Quantity must be greater than zero.')
  if (hasNotional && (!Number.isFinite(i.notional as number) || (i.notional as number) < 1)) out.push('A dollar amount must be at least $1.')
  const fractional = hasQty && Number.isFinite(i.qty as number) && !Number.isInteger(i.qty)
  if ((hasNotional || fractional) && (i.order_type !== 'market' || i.time_in_force !== 'day')) {
    out.push('Dollar amounts and fractional shares are market orders good for the day.')
  }
  if (i.order_type === 'limit' && !(Number(i.limit_price) > 0)) out.push('A limit order needs a limit price above zero.')
  return out
}

/**
 * A broker string to a number, or null.
 *
 * Alpaca returns money as strings. Falling back to zero here would turn "the
 * broker did not report this" into "you have nothing", which is a different
 * and alarming claim about someone's account.
 */
export function money(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : null
}

/** Status is cheap and changes only with deployment configuration. */
export function fetchPaperStatus(): Promise<PaperStatus> {
  return readResource<PaperStatus>('/api/paper/status', 'reference')
}

/* Account, positions and orders are broker state. They are snapshot-cached so
   two panels reading the same thing issue one request, and short enough that
   an order placed in one surface shows up in another without a reload. */
export function fetchPaperAccount(): Promise<{ account: PaperAccount }> {
  return readAuthResource<{ account: PaperAccount }>('/api/paper/account', 'snapshot')
}

export function fetchPaperPositions(): Promise<{ positions: PaperPosition[] }> {
  return readAuthResource<{ positions: PaperPosition[] }>('/api/paper/positions', 'snapshot')
}

export function fetchPaperOrders(): Promise<{ orders: PaperOrder[] }> {
  return readAuthResource<{ orders: PaperOrder[] }>('/api/paper/orders', 'snapshot')
}

/** One protected probe before the three broker reads, so denial is rendered once. */
export function fetchPaperAccess(): Promise<PaperAccess> {
  return readAuthResource<PaperAccess>('/api/paper/access', 'snapshot')
}

/** Validate and price an order without placing it. */
export async function previewOrder(intent: OrderIntent): Promise<OrderPreview> {
  const r = await authFetch('/api/paper/orders/preview', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(intent),
  })
  if (!r.ok) throw new Error(await describe(r))
  return r.json() as Promise<OrderPreview>
}

/**
 * Place the order, carrying the preview's client order id.
 *
 * 201 is a new order, 200 a repeated confirmation answered with the order the
 * first one created, 202 an outcome the broker has not confirmed yet — which
 * is reconciled with `reconcileOrder`, never by confirming again.
 */
export async function placeOrder(intent: OrderIntent): Promise<PlacementResult> {
  const r = await authFetch('/api/paper/orders', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(intent),
  })
  if (!r.ok) throw new Error(await describe(r))
  const body = await r.json() as {
    order?: PaperOrder; client_order_id: string; replayed?: boolean; reconciled_after?: string; outcome?: string; detail?: string
  }
  clearAuthResourceCache()
  if (r.status === 202 || !body.order) {
    return { kind: 'unknown', clientOrderId: body.client_order_id, detail: body.detail ?? 'The broker has not confirmed this order yet.' }
  }
  return {
    kind: 'placed', order: body.order, clientOrderId: body.client_order_id,
    replayed: Boolean(body.replayed), reconciledAfter: body.reconciled_after ?? null,
  }
}

/** What the broker now says about a submission, by its client order id. */
export async function reconcileOrder(clientOrderId: string): Promise<{ found: boolean; order?: PaperOrder; local_status?: string | null }> {
  const r = await authFetch(`/api/paper/orders/by-client/${encodeURIComponent(clientOrderId)}`)
  if (!r.ok) throw new Error(await describe(r))
  clearAuthResourceCache()
  return r.json()
}

/** Resolve submissions a timeout, reload or restart left open. */
export async function reconcileUnresolved(): Promise<void> {
  const r = await authFetch('/api/paper/reconcile', { method: 'POST' })
  if (r.ok) clearAuthResourceCache()
}

export async function fetchOrderDetail(orderId: string): Promise<{ order: PaperOrder }> {
  const r = await authFetch(`/api/paper/orders/${encodeURIComponent(orderId)}`)
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

/** Cancel an open paper order and return what the broker says it is now. */
export async function cancelOrder(orderId: string): Promise<{ requested: boolean; order: PaperOrder | null }> {
  const r = await authFetch(`/api/paper/orders/${encodeURIComponent(orderId)}`, { method: 'DELETE' })
  clearAuthResourceCache()
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

export async function fetchPaperOrdersFiltered(status: 'all' | 'open' | 'closed', limit = 100): Promise<{ orders: PaperOrder[] }> {
  const r = await authFetch(`/api/paper/orders?status=${status}&limit=${limit}`)
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

export async function fetchPaperHistory(period: string, timeframe: string): Promise<PaperHistory> {
  const r = await authFetch(`/api/paper/history?period=${encodeURIComponent(period)}&timeframe=${encodeURIComponent(timeframe)}`)
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

export async function fetchPaperClock(): Promise<{ clock: { is_open?: boolean; next_open?: string; next_close?: string; timestamp?: string } }> {
  const r = await authFetch('/api/paper/clock')
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

export async function fetchPaperConnection(): Promise<PaperConnection> {
  const r = await authFetch('/api/paper/connection')
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

export async function fetchPaperAnalytics(): Promise<PaperAnalytics> {
  const r = await authFetch('/api/paper/analytics')
  if (!r.ok) throw new Error(await describe(r))
  return r.json()
}

async function describe(r: Response): Promise<string> {
  try {
    const body = await r.json() as { detail?: string }
    if (body.detail) return body.detail
  } catch { /* fall through to the status */ }
  return `the broker request returned ${r.status}`
}
