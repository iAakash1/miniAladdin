'use client'

/**
 * The paper account.
 *
 * Every figure on this screen was reported by the broker. Nothing is computed
 * here — not a fill, not an average price, not a profit derived from a quote
 * this product happens to hold. A terminal that quietly recomputes what an
 * account should be worth will one day disagree with the broker, and the
 * reader will have no way to tell which of the two is wrong.
 *
 * The word PAPER is not a badge in a corner. It is in the heading, in the
 * account line, on the positions, on the orders, and on every action that
 * could be mistaken for an instruction to a real broker. There is no
 * arrangement of this screen that leaves someone unsure which environment
 * they are in.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Panel, StateBlock, Status, Value } from '@/components/system'
import {
  fetchPaperAccount, fetchPaperOrders, fetchPaperPositions, fetchPaperStatus,
  money, type PaperAccount, type PaperOrder, type PaperPosition, type PaperStatus,
} from '@/lib/paper'

type Load<T> = { value: T } | { error: string }

export default function PaperWorkspace() {
  const [status, setStatus] = useState<Load<PaperStatus> | null>(null)
  const [account, setAccount] = useState<Load<PaperAccount> | null>(null)
  const [positions, setPositions] = useState<Load<PaperPosition[]> | null>(null)
  const [orders, setOrders] = useState<Load<PaperOrder[]> | null>(null)

  useEffect(() => {
    let alive = true
    fetchPaperStatus()
      .then((s) => {
        if (!alive) return
        setStatus({ value: s })
        // Nothing else is requested until the broker says it can answer. A
        // 503 per panel would report one configuration fact four times.
        if (!s.configured) return
        fetchPaperAccount()
          .then((d) => { if (alive) setAccount({ value: d.account }) })
          .catch((e: Error) => { if (alive) setAccount({ error: e.message }) })
        fetchPaperPositions()
          .then((d) => { if (alive) setPositions({ value: d.positions }) })
          .catch((e: Error) => { if (alive) setPositions({ error: e.message }) })
        fetchPaperOrders()
          .then((d) => { if (alive) setOrders({ value: d.orders }) })
          .catch((e: Error) => { if (alive) setOrders({ error: e.message }) })
      })
      .catch((e: Error) => { if (alive) setStatus({ error: e.message }) })
    return () => { alive = false }
  }, [])

  if (status === null) {
    return <StateBlock state="waking" title="Reading the paper account" />
  }

  if ('error' in status) {
    return (
      <StateBlock
        state="unavailable"
        title="Paper trading could not be reached"
        detail={`${status.error}. Your watchlist, market data and research are unaffected.`}
      />
    )
  }

  if (!status.value.configured) {
    return (
      <>
        <section className="paper__head">
          <h2 className="paper__title">Paper account</h2>
          <Status state="unavailable" label="NOT CONNECTED" />
        </section>
        <EmptyLine label="Paper trading">
          {status.value.reason ?? 'Alpaca paper credentials are not configured.'}{' '}
          Orders would be sent to <code>{status.value.endpoint}</code>, which is
          Alpaca&apos;s paper environment — this build cannot reach a live one.
          Market data, search and research are unaffected.
        </EmptyLine>
      </>
    )
  }

  return (
    <>
      <AccountBand account={account} />
      <Positions positions={positions} />
      <Orders orders={orders} />
    </>
  )
}

/* ── account ─────────────────────────────────────────────────────────────── */

function AccountBand({ account }: { account: Load<PaperAccount> | null }) {
  if (account === null) return <StateBlock state="waking" title="Reading the paper account" />
  if ('error' in account) {
    return (
      <StateBlock
        state="unavailable"
        title="The paper account could not be read"
        detail={`${account.error}. Nothing is shown in its place.`}
      />
    )
  }

  const a = account.value
  const equity = money(a.equity)
  const last = money(a.last_equity)
  /* The broker reports both today's equity and yesterday's close. The
     difference between two numbers it gave us is the one arithmetic this
     screen does, and only because the broker does not send it directly. */
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
        <div className="paper__big">
          <Value value={equity} kind="currency" />
        </div>
        <div className="paper__delta">
          <span className="k">since yesterday</span>
          <span className="v">
            <Value value={dayChange} kind="currency" signed tone />
            {dayPct !== null ? (
              <span className="paper__pct"><Value value={dayPct} kind="percent" digits={2} signed tone /></span>
            ) : null}
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

/* ── positions ───────────────────────────────────────────────────────────── */

function Positions({ positions }: { positions: Load<PaperPosition[]> | null }) {
  if (positions === null) return <StateBlock state="waking" title="Reading paper positions" />
  if ('error' in positions) {
    return (
      <StateBlock
        state="unavailable"
        title="Paper positions could not be read"
        detail={`${positions.error}. Nothing is shown in their place.`}
      />
    )
  }
  if (!positions.value.length) {
    return (
      <EmptyLine label="Paper positions">
        No paper positions. Open a security and use <kbd className="sys-kbd">paper trade</kbd> to
        place one — it costs nothing and settles nothing.
      </EmptyLine>
    )
  }

  return (
    <Panel title="Paper positions" subtitle={`${positions.value.length} held`} flush>
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact">
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col" className="num">Qty</th>
              <th scope="col" className="num">Avg entry</th>
              <th scope="col" className="num">Last</th>
              <th scope="col" className="num">Market value</th>
              <th scope="col" className="num">Unrealised</th>
              <th scope="col" className="num">Unrealised %</th>
            </tr>
          </thead>
          <tbody>
            {positions.value.map((p) => (
              <tr key={p.symbol}>
                <td>
                  <Link href={`/terminal/security?symbol=${encodeURIComponent(p.symbol)}`} className="wl__sym">
                    {p.symbol}
                  </Link>
                </td>
                <td className="num"><Value value={money(p.qty)} kind="count" digits={0} /></td>
                <td className="num"><Value value={money(p.avg_entry_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.current_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.market_value)} kind="currency" /></td>
                <td className="num"><Value value={money(p.unrealized_pl)} kind="currency" signed tone /></td>
                <td className="num">
                  {/* Alpaca reports this as a fraction. Scaled once, here, at
                      the one place that knows it is a fraction. */}
                  <Value
                    value={money(p.unrealized_plpc) !== null ? (money(p.unrealized_plpc) as number) * 100 : null}
                    kind="percent" digits={2} signed tone
                  />
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

function Orders({ orders }: { orders: Load<PaperOrder[]> | null }) {
  if (orders === null) return <StateBlock state="waking" title="Reading paper orders" />
  if ('error' in orders) {
    return (
      <StateBlock
        state="unavailable"
        title="Paper orders could not be read"
        detail={`${orders.error}. Nothing is shown in their place.`}
      />
    )
  }
  if (!orders.value.length) {
    return <EmptyLine label="Paper orders">No paper orders have been placed from this account.</EmptyLine>
  }

  return (
    <Panel title="Paper orders" subtitle={`${orders.value.length} most recent`} flush>
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact">
          <thead>
            <tr>
              <th scope="col">Placed</th>
              <th scope="col">Symbol</th>
              <th scope="col">Side</th>
              <th scope="col" className="num">Qty</th>
              <th scope="col" className="num">Filled</th>
              <th scope="col" className="num">Fill price</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {orders.value.map((o) => (
              <tr key={o.id}>
                <td className="sys-meta">{(o.submitted_at ?? o.created_at ?? '').slice(0, 19).replace('T', ' ')}</td>
                <td>
                  <Link href={`/terminal/security?symbol=${encodeURIComponent(o.symbol)}`} className="wl__sym">
                    {o.symbol}
                  </Link>
                </td>
                <td>{o.side ? o.side.toUpperCase() : '—'}</td>
                <td className="num"><Value value={money(o.qty)} kind="count" digits={0} /></td>
                <td className="num"><Value value={money(o.filled_qty)} kind="count" digits={0} /></td>
                <td className="num">
                  {/* Absent until the broker reports a fill. An unfilled order
                      has no fill price, and showing the last trade here would
                      be inventing one. */}
                  <Value value={money(o.filled_avg_price)} kind="currency" />
                </td>
                <td><OrderStatus status={o.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

/**
 * The broker's own status word, mapped to this product's state vocabulary.
 *
 * The word shown is always Alpaca's. Only the colour is ours, and it is
 * derived rather than assigned per status so a status nobody anticipated
 * still renders as something honest instead of disappearing.
 */
function OrderStatus({ status }: { status?: string }) {
  if (!status) return <span className="sys-null">—</span>
  const s = status.toLowerCase()
  const state =
    s === 'filled' ? 'live'
      : ['canceled', 'cancelled', 'expired', 'rejected', 'suspended'].includes(s) ? 'blocked'
        : ['new', 'accepted', 'pending_new', 'partially_filled', 'held'].includes(s) ? 'waking'
          : 'recorded'
  return <Status state={state} label={status.replace(/_/g, ' ').toUpperCase()} />
}
