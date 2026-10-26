'use client'

/**
 * The paper account.
 *
 * Every figure on this screen was reported by the broker, or is labelled as
 * derived from figures it reported. Nothing is simulated here — not a fill,
 * not an average price, not a profit from a quote this product happens to
 * hold. A terminal that quietly recomputes what an account should be worth
 * will one day disagree with the broker, and the reader will have no way to
 * tell which of the two is wrong.
 *
 * The word PAPER is not a badge in a corner. It is in the ribbon on every
 * state of this screen, in the account line, and on every action that could
 * be mistaken for an instruction to a real broker.
 *
 * Orders are placed by hand only: the ticket opens from here, from a tracked
 * security or from a company page, always prefilled at most, never submitted.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import OrderTicket from './OrderTicket'
import PaperGates from './PaperGates'
import Drawer from '@/components/shell/Drawer'
import CompanyIdentity from '@/components/visual/CompanyIdentity'
import { EmptyLine, Panel, StateBlock, Status, Value } from '@/components/system'
import { TimeSeries } from '@/components/system/charts'
import {
  cancelOrder, fetchOrderDetail, fetchPaperAccess, fetchPaperAccount, fetchPaperAnalytics, fetchPaperClock,
  fetchPaperConnection, fetchPaperHistory, fetchPaperOrdersFiltered, fetchPaperPositions, fetchPaperStatus,
  isOpenOrder, money, reconcileUnresolved,
  type PaperAccount, type PaperAnalytics, type PaperConnection, type PaperHistory, type PaperOrder,
  type PaperPosition, type PaperStatus,
} from '@/lib/paper'
import { formatMoment } from '@/lib/quantity'
import { ResourceError } from '@/lib/resource'
import { watchSymbol } from '@/lib/watchlists'

type WorkspaceState =
  | { at: 'loading' }
  | { at: 'unconfigured'; status: PaperStatus }
  | { at: 'signed-out'; detail: string }
  | { at: 'forbidden'; detail: string }
  | { at: 'unavailable'; detail: string }
  | { at: 'ready' }

type Ticket = { symbol: string; side: 'buy' | 'sell'; qty?: number; origin: 'ticket' | 'watchlist' | 'research' | 'position' } | null

const PERIODS: Array<{ period: string; timeframe: string; label: string }> = [
  { period: '1D', timeframe: '15Min', label: '1D' },
  { period: '1W', timeframe: '1H', label: '1W' },
  { period: '1M', timeframe: '1D', label: '1M' },
  { period: '3M', timeframe: '1D', label: '3M' },
  { period: '6M', timeframe: '1D', label: '6M' },
  { period: '1A', timeframe: '1D', label: '1Y' },
]

/** On every state of this screen, so no arrangement leaves the environment in doubt. */
function Ribbon({ detail }: { detail?: string }) {
  return (
    <p className="paper-ribbon" role="note">
      <span className="paper-ribbon__tag">Paper</span>
      Simulated trading on Alpaca&apos;s paper environment · no real funds{detail ? ` · ${detail}` : ''}
    </p>
  )
}

export default function PaperWorkspace() {
  const [state, setState] = useState<WorkspaceState>({ at: 'loading' })
  const params = useSearchParams()

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const status = await fetchPaperStatus()
        if (!alive) return
        if (!status.configured) {
          setState({ at: 'unconfigured', status })
          return
        }
        try {
          await fetchPaperAccess()
        } catch (error) {
          if (!alive) return
          if (error instanceof ResourceError && error.status === 401) {
            setState({ at: 'signed-out', detail: 'Sign in to access the paper account.' })
            return
          }
          if (error instanceof ResourceError && error.status === 403) {
            setState({ at: 'forbidden', detail: error.message })
            return
          }
          throw error
        }
        if (alive) setState({ at: 'ready' })
      } catch (error) {
        if (alive) setState({ at: 'unavailable', detail: error instanceof Error ? error.message : 'The broker did not answer.' })
      }
    }
    void load()
    return () => { alive = false }
  }, [])

  if (state.at === 'loading') return <><Ribbon /><StateBlock state="waking" title="Reading the paper account" /></>

  if (state.at === 'signed-out') {
    return (
      <>
        <Ribbon />
        <StateBlock state="blocked" title="Sign in required" detail={state.detail} />
        <PaperGates who="closed" where="open" />
      </>
    )
  }

  if (state.at === 'forbidden') {
    return (
      <>
        <Ribbon />
        <section className="paper-closed">
          <div className="paper-closed__head">
            <h2 className="paper__title">Paper trading</h2>
            <Status state="blocked" label="NOT AN OPERATOR" />
          </div>
          <p className="paper-closed__lede">
            The paper account is one shared demonstration account, so being signed in is not enough:
            only named operators may use it. {state.detail}
          </p>
          <PaperGates who="closed" where="open" />
        </section>
      </>
    )
  }

  if (state.at === 'unavailable') {
    return (
      <>
        <Ribbon />
        <StateBlock
          state="unavailable"
          title="Alpaca paper is temporarily unavailable"
          detail={`The paper broker did not answer (${state.detail}). Your watchlists, market data and research are unaffected.`}
        />
      </>
    )
  }

  if (state.at === 'unconfigured') {
    const operatorsSet = state.status.access?.enabled === true
    return (
      <>
        <Ribbon />
        <section className="paper-closed">
          <div className="paper-closed__head">
            <h2 className="paper__title">Paper trading</h2>
            <Status state="recorded" label="NOT CONFIGURED" />
          </div>
          <p className="paper-closed__lede">
            A simulation environment for trying out ideas from the research. It needs an Alpaca paper
            account on the server and a named operator;{' '}
            {operatorsSet
              ? 'operators are named, but no paper account is connected on this deployment.'
              : 'neither is set on this deployment, so no account is connected.'}{' '}
            Market data, research, alerts and watchlists all work without it.
          </p>
          {state.status.reason ? <p className="paper-closed__lede">{state.status.reason}</p> : null}
          <PaperGates who={operatorsSet ? 'unknown' : 'closed'} where="closed" />
          <dl className="paper-closed__needs">
            <div><dt>Broker credentials</dt><dd>APCA_API_KEY_ID and APCA_API_SECRET_KEY from an Alpaca <em>paper</em> account, as backend secrets — never in the browser</dd></div>
            <div><dt>Operators</dt><dd>PAPER_TRADING_OWNERS — the Clerk user ids allowed to use the account</dd></div>
            <div><dt>Endpoint</dt><dd className="sys-mono">{state.status.endpoint ?? 'https://paper-api.alpaca.markets'} (fixed; any other base URL is refused)</dd></div>
          </dl>
        </section>
      </>
    )
  }

  const prefill = params.get('ticket')
  return (
    <Account
      initialTicket={prefill ? {
        symbol: prefill.toUpperCase().slice(0, 10),
        side: params.get('side') === 'sell' ? 'sell' : 'buy',
        origin: (['watchlist', 'research', 'position'] as const).find((o) => o === params.get('origin')) ?? 'ticket',
      } : null}
    />
  )
}

/* ── the operator's account ───────────────────────────────────────────────── */

function Account({ initialTicket }: { initialTicket: Ticket }) {
  const [account, setAccount] = useState<PaperAccount | null>(null)
  const [positions, setPositions] = useState<PaperPosition[]>([])
  const [orders, setOrders] = useState<PaperOrder[]>([])
  const [analytics, setAnalytics] = useState<PaperAnalytics | null>(null)
  const [clock, setClock] = useState<{ is_open?: boolean; next_open?: string; next_close?: string } | null>(null)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState<'all' | 'open' | 'closed'>('all')
  const [ticket, setTicket] = useState<Ticket>(initialTicket)
  const [detail, setDetail] = useState<PaperOrder | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setBusy(true)
    try {
      const [a, p, o, an, c] = await Promise.all([
        fetchPaperAccount(), fetchPaperPositions(), fetchPaperOrdersFiltered(filter),
        fetchPaperAnalytics().catch(() => null), fetchPaperClock().catch(() => null),
      ])
      setAccount(a.account); setPositions(p.positions); setOrders(o.orders); setAnalytics(an)
      setClock(c?.clock ?? null); setUpdatedAt(new Date()); setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The broker did not answer.')
    } finally {
      setBusy(false)
    }
  }, [filter])

  useEffect(() => {
    // Anything a timeout, a reload or a restart left unresolved is settled
    // against the broker before the account is read.
    void reconcileUnresolved().finally(() => { void refresh() })
  }, [refresh])

  const cancel = async (order: PaperOrder) => {
    setNotice(null)
    try {
      const r = await cancelOrder(order.id)
      setNotice(`Cancellation requested for ${order.symbol}. The broker now reports: ${(r.order?.status ?? 'unknown').replace(/_/g, ' ')}.`)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'The cancellation was not accepted.')
    }
    void refresh()
  }

  const openDetail = async (order: PaperOrder) => {
    setDetail(order)
    try { setDetail((await fetchOrderDetail(order.id)).order) } catch { /* keep the list's copy */ }
  }

  if (!account && !error) return <><Ribbon /><StateBlock state="waking" title="Reading the paper account" /></>

  return (
    <>
      <Ribbon detail="orders are placed by hand and confirmed on a review step" />
      <div className="paper-bar">
        <MarketLine clock={clock} />
        <span className="sys-meta">{updatedAt ? `updated ${formatMoment(updatedAt.toISOString())}` : 'not yet read'}</span>
        <button type="button" className="sys-btn" onClick={() => void refresh()} disabled={busy}>{busy ? 'refreshing…' : 'Refresh'}</button>
        <ConnectionTest />
        <NewOrder onOpen={(symbol) => setTicket({ symbol, side: 'buy', origin: 'ticket' })} />
      </div>
      {error ? <StateBlock state="unavailable" title="The broker did not answer the last refresh" detail={error} /> : null}
      {notice ? <p className="paper-notice" role="status">{notice}</p> : null}

      {account ? <AccountBand account={account} /> : null}
      <Performance />
      {analytics ? <Analytics a={analytics} /> : null}
      <Positions positions={positions} onSell={(p) => setTicket({ symbol: p.symbol, side: 'sell', qty: money(p.qty) ?? undefined, origin: 'position' })} />
      <Orders orders={orders} filter={filter} onFilter={setFilter} onCancel={cancel} onDetail={openDetail} />
      <PaperGates who="open" where="open" />

      <Drawer open={ticket !== null} onClose={() => { setTicket(null); void refresh() }} title={ticket ? `Paper order · ${ticket.symbol}` : 'Paper order'} meta="Simulated account — no real money">
        {ticket ? (
          <OrderTicket
            key={`${ticket.symbol}-${ticket.side}`}
            symbol={ticket.symbol} initialSide={ticket.side} initialQty={ticket.qty} origin={ticket.origin}
            onClose={() => { setTicket(null); void refresh() }}
          />
        ) : null}
      </Drawer>
      <Drawer open={detail !== null} onClose={() => setDetail(null)} title={detail ? `Order · ${detail.symbol}` : 'Order'} meta="As reported by the broker">
        {detail ? <OrderLifecycle order={detail} /> : null}
      </Drawer>
    </>
  )
}

function MarketLine({ clock }: { clock: { is_open?: boolean; next_open?: string; next_close?: string } | null }) {
  if (!clock) return <span className="sys-meta">market status unknown</span>
  return (
    <span className="paper-market" data-open={clock.is_open ? 'true' : 'false'}>
      <Status state={clock.is_open ? 'live' : 'recorded'} label={clock.is_open ? 'MARKET OPEN' : 'MARKET CLOSED'} />
      <span className="sys-meta">
        {clock.is_open ? `closes ${fmtTime(clock.next_close)}` : `opens ${fmtTime(clock.next_open)}`}
      </span>
    </span>
  )
}

function fmtTime(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  // Market hours are New York hours, so they are shown in New York time and say so.
  return Number.isNaN(d.getTime()) ? iso : `${d.toLocaleString('en-US', { weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'America/New_York' })} ET`
}

function ConnectionTest() {
  const [result, setResult] = useState<PaperConnection | null>(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try { setResult(await fetchPaperConnection()) } catch (e) {
      setResult({ state: 'unavailable', detail: e instanceof Error ? e.message : 'no answer' })
    } finally { setBusy(false) }
  }
  const label: Record<PaperConnection['state'], string> = {
    connected: 'connected', blocked: 'account blocked', not_configured: 'not configured',
    credentials_rejected: 'credentials rejected', restricted: 'restricted', rate_limited: 'rate limited', unavailable: 'unreachable',
  }
  return (
    <span className="paper-conn">
      <button type="button" className="sys-btn" onClick={() => void run()} disabled={busy}>{busy ? 'testing…' : 'Test connection'}</button>
      {result ? (
        <span className="sys-meta" role="status">
          {label[result.state]}{result.account_status ? ` · ${result.account_status.toLowerCase()}` : ''}{result.detail && result.state !== 'connected' ? ` · ${result.detail}` : ''}
        </span>
      ) : null}
    </span>
  )
}

function NewOrder({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [symbol, setSymbol] = useState('')
  const clean = symbol.trim().toUpperCase().replace(/[^A-Z.\-]/g, '').slice(0, 10)
  return (
    <form className="paper-new" onSubmit={(e) => { e.preventDefault(); if (clean) onOpen(clean) }}>
      <label className="visually-hidden" htmlFor="paper-new-symbol">Symbol for a new paper order</label>
      <input id="paper-new-symbol" className="sys-input" placeholder="Symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} autoComplete="off" />
      <button type="submit" className="sys-btn sys-btn--primary" disabled={!clean}>New paper order</button>
    </form>
  )
}

/* ── account ─────────────────────────────────────────────────────────────── */

function AccountBand({ account: a }: { account: PaperAccount }) {
  const equity = money(a.equity)
  const last = money(a.last_equity)
  // The one arithmetic here: two numbers the broker reported, differenced.
  const dayChange = equity !== null && last !== null ? equity - last : null
  const dayPct = dayChange !== null && last ? (dayChange / last) * 100 : null

  return (
    <section className="paper" aria-label="Paper account">
      <div className="paper__head">
        <h2 className="paper__title">Paper account</h2>
        <Status state="live" label="PAPER · ALPACA" />
        <span className="paper__note">simulated capital — no real money</span>
      </div>
      <div className="paper__equity">
        <div className="paper__big"><Value value={equity} kind="currency" /></div>
        <div className="paper__delta">
          <span className="k">since yesterday&apos;s close</span>
          <span className="v">
            <Value value={dayChange} kind="currency" signed tone />
            {dayPct !== null ? <span className="paper__pct"><Value value={dayPct} kind="percent" digits={2} signed tone /></span> : null}
          </span>
        </div>
      </div>
      <dl className="band__facts">
        <Fact k="Cash"><Value value={money(a.cash)} kind="currency" /></Fact>
        <Fact k="Buying power"><Value value={money(a.buying_power)} kind="currency" /></Fact>
        <Fact k="Portfolio value"><Value value={money(a.portfolio_value)} kind="currency" /></Fact>
        <Fact k="Status">{a.status ?? <span className="band__none">not reported</span>}</Fact>
      </dl>
    </section>
  )
}

function Fact({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="band__fact"><dt>{k}</dt><dd>{children}</dd></div>
}

/* ── performance ─────────────────────────────────────────────────────────── */

function Performance() {
  const [choice, setChoice] = useState(PERIODS[2])
  // Keyed by the window it answers, so a slow reply for an old window is never shown under a new one.
  const [read, setRead] = useState<{ key: string; history?: PaperHistory; error?: string } | null>(null)
  useEffect(() => {
    let alive = true
    fetchPaperHistory(choice.period, choice.timeframe)
      .then((h) => { if (alive) setRead({ key: choice.label, history: h }) })
      .catch((e: Error) => { if (alive) setRead({ key: choice.label, error: e.message }) })
    return () => { alive = false }
  }, [choice])
  const current = read?.key === choice.label ? read : null
  const history = current?.history ?? null
  const error = current?.error ?? null

  const points = history?.points ?? []
  const first = points[0]?.equity ?? null
  const last = points[points.length - 1] ?? null
  return (
    <Panel
      title="Account equity" subtitle="as reported by the broker for each window · simulated results"
      actions={(
        <div className="sys-seg" role="group" aria-label="History range">
          {PERIODS.map((p) => (
            <button key={p.label} type="button" className={`sys-btn${p === choice ? ' is-active' : ''}`} aria-pressed={p === choice} onClick={() => setChoice(p)}>{p.label}</button>
          ))}
        </div>
      )}
    >
      {error ? <StateBlock state="unavailable" title="Portfolio history is unavailable" detail={error} />
        : !history ? <StateBlock state="waking" title="Reading portfolio history" />
          : points.length < 2 ? <StateBlock state="info" title="Not enough history yet" detail="The broker reports fewer than two windows of equity for this range. Nothing is drawn rather than a line invented." />
            : (
              <>
                <TimeSeries
                  kind="currency" frequency={history.timeframe ?? undefined}
                  series={[{ name: 'Equity', points: points.map((p) => ({ x: new Date(p.t * 1000).toISOString().slice(0, 16).replace('T', ' '), y: p.equity })) }]}
                  method="Alpaca portfolio history: equity at the end of each window"
                />
                <p className="sys-meta">
                  {first !== null && last ? `Range change ${(((last.equity / first) - 1) * 100).toFixed(2)}% from ${first.toLocaleString('en-US', { style: 'currency', currency: 'USD' })}. ` : ''}
                  Not annualized. Deposits and withdrawals move equity too.
                </p>
              </>
            )}
    </Panel>
  )
}

function Analytics({ a }: { a: PaperAnalytics }) {
  const pct = (v: number | null) => (v === null ? null : v * 100)
  return (
    <Panel title="Account analytics" subtitle={a.label}>
      <dl className="paper-analytics">
        <div><dt>Day change <span className="opt">derived</span></dt><dd><Value value={a.derived.day_change} kind="currency" signed tone /></dd></div>
        <div><dt>Unrealized P/L <span className="opt">sum of broker positions</span></dt><dd><Value value={a.derived.unrealized_pl_total} kind="currency" signed tone /></dd></div>
        <div><dt>Cash share of equity</dt><dd><Value value={pct(a.derived.cash_share)} kind="percent" digits={1} /></dd></div>
        <div><dt>Largest position</dt><dd><Value value={pct(a.derived.largest_weight)} kind="percent" digits={1} /></dd></div>
        <div><dt>Best open position</dt><dd>{a.best ? <>{a.best.symbol} <Value value={pct(a.best.unrealized_plpc)} kind="percent" digits={2} signed tone /></> : '—'}</dd></div>
        <div><dt>Worst open position</dt><dd>{a.worst ? <>{a.worst.symbol} <Value value={pct(a.worst.unrealized_plpc)} kind="percent" digits={2} signed tone /></> : '—'}</dd></div>
        <div><dt>Realized P/L</dt><dd className="sys-null">not reported by these broker endpoints</dd></div>
        <div><dt>Recent orders</dt><dd>{Object.entries(a.order_activity).map(([s, n]) => `${n} ${s.replace(/_/g, ' ')}`).join(' · ') || 'none'}</dd></div>
      </dl>
    </Panel>
  )
}

/* ── positions ───────────────────────────────────────────────────────────── */

function Positions({ positions, onSell }: { positions: PaperPosition[]; onSell: (p: PaperPosition) => void }) {
  if (!positions.length) {
    return <EmptyLine label="Paper positions">No paper positions. Use <kbd className="sys-kbd">New paper order</kbd> above, or open one from a tracked security.</EmptyLine>
  }
  const values = positions.map((p) => Math.abs(money(p.market_value) ?? 0))
  const total = values.reduce((sum, v) => sum + v, 0)
  return (
    <Panel title="Paper positions" subtitle={`${positions.length} held · broker values`} flush>
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact paper-pos">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">Share of book</th>
              <th scope="col" className="num">Qty</th>
              <th scope="col" className="num">Avg entry</th>
              <th scope="col" className="num">Last</th>
              <th scope="col" className="num">Market value</th>
              <th scope="col" className="num">Cost basis</th>
              <th scope="col" className="num">Unrealized</th>
              <th scope="col" className="num">Unrealized %</th>
              <th scope="col"><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={p.symbol}>
                <td><CompanyIdentity symbol={p.symbol} size="sm" href={`/company/${encodeURIComponent(p.symbol)}`} /></td>
                <td>{total > 0 ? <span className="sys-num">{((values[i] / total) * 100).toFixed(1)}%</span> : <span className="sys-null">—</span>}</td>
                <td className="num"><Value value={money(p.qty)} kind="count" digits={money(p.qty) !== null && !Number.isInteger(money(p.qty)) ? 4 : 0} /></td>
                <td className="num"><Value value={money(p.avg_entry_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.current_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.market_value)} kind="currency" /></td>
                <td className="num"><Value value={money(p.cost_basis)} kind="currency" /></td>
                <td className="num"><Value value={money(p.unrealized_pl)} kind="currency" signed tone /></td>
                <td className="num">
                  {/* Alpaca reports this as a fraction; scaled once, here. */}
                  <Value value={money(p.unrealized_plpc) !== null ? (money(p.unrealized_plpc) as number) * 100 : null} kind="percent" digits={2} signed tone />
                </td>
                <td className="paper-acts">
                  <button type="button" className="sys-btn sys-btn--xs" onClick={() => onSell(p)}>Sell…</button>
                  <button type="button" className="sys-btn sys-btn--xs" onClick={() => void watchSymbol(p.symbol)}>Watch</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

/* ── orders ──────────────────────────────────────────────────────────────── */

function Orders({
  orders, filter, onFilter, onCancel, onDetail,
}: {
  orders: PaperOrder[]
  filter: 'all' | 'open' | 'closed'
  onFilter: (f: 'all' | 'open' | 'closed') => void
  onCancel: (o: PaperOrder) => void
  onDetail: (o: PaperOrder) => void
}) {
  const [confirming, setConfirming] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const sorted = useMemo(() => orders, [orders])
  return (
    <Panel
      title="Paper orders" subtitle={`${orders.length} shown · broker status`} flush
      actions={(
        <div className="sys-seg" role="group" aria-label="Order filter">
          {(['all', 'open', 'closed'] as const).map((f) => (
            <button key={f} type="button" className={`sys-btn${f === filter ? ' is-active' : ''}`} aria-pressed={f === filter} onClick={() => onFilter(f)}>{f}</button>
          ))}
        </div>
      )}
    >
      {!orders.length ? <p className="paper-empty">No {filter === 'all' ? '' : `${filter} `}paper orders.</p> : (
        <div className="sys-scroll-x">
          <table className="sys-table sys-table--compact">
            <thead>
              <tr>
                <th scope="col">Placed</th>
                <th scope="col">Symbol</th>
                <th scope="col">Side</th>
                <th scope="col">Type</th>
                <th scope="col" className="num">Qty / amount</th>
                <th scope="col" className="num">Filled</th>
                <th scope="col" className="num">Fill price</th>
                <th scope="col">Status</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((o) => (
                <tr key={o.id}>
                  <td className="sys-meta">{formatMoment(o.submitted_at ?? o.created_at)}</td>
                  <td>{o.symbol}</td>
                  <td>{o.side ? <span className="paper-side" data-side={o.side.toLowerCase()}>{o.side.toUpperCase()}</span> : '—'}</td>
                  <td className="sys-meta">{o.type}{o.limit_price ? ` @ ${o.limit_price}` : ''} · {o.time_in_force}</td>
                  <td className="num">{o.qty ?? (o.notional ? `$${o.notional}` : '—')}</td>
                  <td className="num">{o.filled_qty ?? '0'}</td>
                  {/* Absent until the broker reports a fill. */}
                  <td className="num"><Value value={money(o.filled_avg_price)} kind="currency" /></td>
                  <td><OrderStatus status={o.status} /></td>
                  <td className="paper-acts">
                    <button type="button" className="sys-btn sys-btn--xs" onClick={() => onDetail(o)}>Details</button>
                    {isOpenOrder(o.status) ? (
                      confirming === o.id ? (
                        <>
                          <button type="button" className="sys-btn sys-btn--xs" disabled={cancelling === o.id}
                            onClick={async () => { setCancelling(o.id); await onCancel(o); setCancelling(null); setConfirming(null) }}>
                            {cancelling === o.id ? 'cancelling…' : 'Confirm cancel'}
                          </button>
                          <button type="button" className="sys-btn sys-btn--xs" onClick={() => setConfirming(null)}>Keep</button>
                        </>
                      ) : <button type="button" className="sys-btn sys-btn--xs" onClick={() => setConfirming(o.id)}>Cancel…</button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

function OrderLifecycle({ order: o }: { order: PaperOrder }) {
  const steps: Array<[string, string | null | undefined]> = [
    ['Created', o.created_at], ['Submitted', o.submitted_at], ['Updated', o.updated_at], ['Filled', o.filled_at],
    ['Canceled', o.canceled_at], ['Expired', o.expired_at], ['Failed', o.failed_at],
  ]
  return (
    <div className="paper-life">
      <dl className="ticket__facts">
        <div><dt>Status</dt><dd><OrderStatus status={o.status} /></dd></div>
        <div><dt>Side</dt><dd>{o.side?.toUpperCase()}</dd></div>
        <div><dt>Type</dt><dd>{o.type}{o.limit_price ? ` @ ${o.limit_price}` : ''} · {o.time_in_force}</dd></div>
        <div><dt>Quantity</dt><dd>{o.qty ?? (o.notional ? `$${o.notional}` : '—')}</dd></div>
        <div><dt>Filled</dt><dd>{o.filled_qty ?? '0'}{o.filled_avg_price ? ` at ${o.filled_avg_price}` : ''}</dd></div>
        <div><dt>Broker order id</dt><dd className="ticket__id">{o.id}</dd></div>
        <div><dt>Client reference</dt><dd className="ticket__id">{o.client_order_id ?? '—'}</dd></div>
      </dl>
      <ol className="paper-life__steps">
        {steps.filter(([, at]) => at).map(([k, at]) => <li key={k}><span>{k}</span><span className="sys-meta">{formatMoment(String(at))}</span></li>)}
      </ol>
    </div>
  )
}

/**
 * The broker's own status word, mapped to this product's state vocabulary.
 * The word shown is always Alpaca's; only the colour is ours.
 */
function OrderStatus({ status }: { status?: string }) {
  if (!status) return <span className="sys-null">—</span>
  const s = status.toLowerCase()
  const state =
    s === 'filled' ? 'live'
      : ['canceled', 'cancelled', 'expired', 'rejected', 'suspended'].includes(s) ? 'blocked'
        : ['new', 'accepted', 'pending_new', 'partially_filled', 'held', 'pending_cancel'].includes(s) ? 'waking'
          : 'recorded'
  return <Status state={state} label={status.replace(/_/g, ' ').toUpperCase()} />
}
