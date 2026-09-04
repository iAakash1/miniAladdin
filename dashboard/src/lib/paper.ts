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

import { readResource } from './resource'

/** Whether trading is possible at all, and if not, a sentence saying why. */
export interface PaperStatus {
  configured: boolean
  reason: string | null
  environment: string
  /** The paper hostname orders would reach. Public, and shown deliberately. */
  endpoint: string
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
  qty: number
  side: 'buy' | 'sell'
  order_type: 'market' | 'limit'
  time_in_force: 'day' | 'gtc'
  limit_price?: number | null
}

export interface OrderPreview {
  ok: boolean
  /** Everything wrong with the order, not just the first thing. */
  problems: string[]
  symbol: string
  qty: number
  side: string
  order_type: string
  time_in_force: string
  estimate: {
    last_price: number | null
    notional: number | null
    /** Why this is an estimate and not a price. Rendered, never dropped. */
    basis: string
    source: string | null
  }
  buying_power: number | null
  asset: { tradable: boolean | null; fractionable: boolean | null; exchange: string | null }
  environment: string
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
  return readResource<{ account: PaperAccount }>('/api/paper/account', 'snapshot')
}

export function fetchPaperPositions(): Promise<{ positions: PaperPosition[] }> {
  return readResource<{ positions: PaperPosition[] }>('/api/paper/positions', 'snapshot')
}

export function fetchPaperOrders(): Promise<{ orders: PaperOrder[] }> {
  return readResource<{ orders: PaperOrder[] }>('/api/paper/orders', 'snapshot')
}

/** Validate and price an order without placing it. */
export async function previewOrder(intent: OrderIntent): Promise<OrderPreview> {
  const r = await fetch('/api/paper/orders/preview', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(intent),
  })
  if (!r.ok) throw new Error(await describe(r))
  return r.json() as Promise<OrderPreview>
}

/** Place the order. Returns the broker's own reply, unmodified. */
export async function placeOrder(intent: OrderIntent): Promise<{ order: PaperOrder }> {
  const r = await fetch('/api/paper/orders', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(intent),
  })
  if (!r.ok) throw new Error(await describe(r))
  return r.json() as Promise<{ order: PaperOrder }>
}

async function describe(r: Response): Promise<string> {
  try {
    const body = await r.json() as { detail?: string }
    if (body.detail) return body.detail
  } catch { /* fall through to the status */ }
  return `the broker request returned ${r.status}`
}
