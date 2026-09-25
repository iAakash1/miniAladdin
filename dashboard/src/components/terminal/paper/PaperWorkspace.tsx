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

import { useEffect, useState } from 'react'

import PaperGates from './PaperGates'
import CompanyIdentity from '@/components/visual/CompanyIdentity'

import { EmptyLine, Panel, StateBlock, Status, Value } from '@/components/system'
import {
  fetchPaperAccess, fetchPaperAccount, fetchPaperOrders, fetchPaperPositions, fetchPaperStatus,
  money, type PaperAccount, type PaperOrder, type PaperPosition, type PaperStatus,
} from '@/lib/paper'
import { ResourceError } from '@/lib/resource'

type WorkspaceState =
  | { at: 'loading' }
  | { at: 'unconfigured'; status: PaperStatus }
  | { at: 'signed-out'; detail: string }
  | { at: 'forbidden'; detail: string }
  | { at: 'unavailable'; detail: string }
  | {
      at: 'ready'
      account: PaperAccount
      positions: PaperPosition[]
      orders: PaperOrder[]
    }

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

        // Authorize once before touching Alpaca. This prevents account,
        // positions and orders from each rendering the same 401/403.
        try {
          await fetchPaperAccess()
        } catch (error) {
          if (!alive) return
          if (error instanceof ResourceError && error.status === 401) {
            setState({ at: 'signed-out', detail: 'Sign in to access the paper account.' })
            return
          }
          if (error instanceof ResourceError && error.status === 403) {
            setState({
              at: 'forbidden',
              detail: error.message,
            })
            return
          }
          throw error
        }

        const [account, positions, orders] = await Promise.all([
          fetchPaperAccount(), fetchPaperPositions(), fetchPaperOrders(),
        ])
        if (alive) {
          setState({
            at: 'ready',
            account: account.account,
            positions: positions.positions,
            orders: orders.orders,
          })
        }
      } catch (error) {
        if (alive) {
          const detail = error instanceof Error ? error.message : 'The broker did not answer.'
          setState({ at: 'unavailable', detail })
        }
      }
    }
    void load()
    return () => { alive = false }
  }, [])

  if (state.at === 'loading') {
    return <><Ribbon /><StateBlock state="waking" title="Reading the paper account" /></>
  }

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
          detail="The paper broker did not answer. Your watchlists, market data and research are unaffected."
        />
      </>
    )
  }

  if (state.at === 'unconfigured') {
    // Not a defect. A deployment without broker credentials is a deployment
    // that has not been given a paper account, which is the default state.
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
            Market data, research, rankings and watchlists all work without it.
          </p>
          {/* The operator allowlist is known only as set or unset here; whether
              this reader is on it is checked once an account exists. */}
          <PaperGates who={operatorsSet ? 'unknown' : 'closed'} where="closed" />
          <dl className="paper-closed__needs">
            <div><dt>Broker credentials</dt><dd>APCA_API_KEY_ID and APCA_API_SECRET_KEY, server-side only</dd></div>
            <div><dt>Operators</dt><dd>PAPER_TRADING_OWNERS — the Clerk user ids allowed to use the account</dd></div>
            <div><dt>Endpoint</dt><dd className="sys-mono">{state.status.endpoint ?? 'https://paper-api.alpaca.markets'}</dd></div>
          </dl>
        </section>
      </>
    )
  }

  return (
    <>
      <Ribbon detail="orders are placed by hand from a company workspace" />
      <AccountBand account={state.account} />
      <Positions positions={state.positions} />
      <Orders orders={state.orders} />
      <PaperGates who="open" where="open" />
    </>
  )
}

/* ── account ─────────────────────────────────────────────────────────────── */

function AccountBand({ account: a }: { account: PaperAccount }) {
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

function Positions({ positions }: { positions: PaperPosition[] }) {
  if (!positions.length) {
    return (
      <EmptyLine label="Paper positions">
        No paper positions. Open a security and use <kbd className="sys-kbd">paper trade</kbd> to
        place one — it costs nothing and settles nothing.
      </EmptyLine>
    )
  }

  // Shares of the book by the broker's own market values; nothing re-priced here.
  const values = positions.map((p) => Math.abs(money(p.market_value) ?? 0))
  const total = values.reduce((sum, v) => sum + v, 0)
  const maxPl = Math.max(0, ...positions.map((p) => Math.abs(money(p.unrealized_plpc) ?? 0)))

  return (
    <Panel title="Paper positions" subtitle={`${positions.length} held`} flush>
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
              <th scope="col" className="num">Unrealised</th>
              <th scope="col" className="num">Unrealised %</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={p.symbol}>
                <td>
                  <CompanyIdentity symbol={p.symbol} size="sm" href={`/company/${encodeURIComponent(p.symbol)}`} />
                </td>
                <td>
                  {total > 0 ? (
                    <span className="paper-share">
                      <span className="paper-share__bar" aria-hidden><span style={{ width: `${(values[i] / total) * 100}%` }} /></span>
                      <span className="sys-num">{((values[i] / total) * 100).toFixed(1)}%</span>
                    </span>
                  ) : <span className="sys-null">—</span>}
                </td>
                <td className="num"><Value value={money(p.qty)} kind="count" digits={0} /></td>
                <td className="num"><Value value={money(p.avg_entry_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.current_price)} kind="currency" /></td>
                <td className="num"><Value value={money(p.market_value)} kind="currency" /></td>
                <td className="num"><Value value={money(p.unrealized_pl)} kind="currency" signed tone /></td>
                <td className="num">
                  {/* Alpaca reports this as a fraction. Scaled once, here, at
                      the one place that knows it is a fraction. */}
                  <span className="paper-pl">
                    {money(p.unrealized_plpc) !== null && maxPl > 0 ? (
                      <span className="paper-pl__bar" aria-hidden>
                        <span
                          data-tone={(money(p.unrealized_plpc) as number) >= 0 ? 'pos' : 'neg'}
                          style={{ width: `${(Math.abs(money(p.unrealized_plpc) as number) / maxPl) * 100}%` }}
                        />
                      </span>
                    ) : null}
                    <Value
                      value={money(p.unrealized_plpc) !== null ? (money(p.unrealized_plpc) as number) * 100 : null}
                      kind="percent" digits={2} signed tone
                    />
                  </span>
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

function Orders({ orders }: { orders: PaperOrder[] }) {
  if (!orders.length) {
    return <EmptyLine label="Paper orders">No paper orders have been placed from this account.</EmptyLine>
  }

  return (
    <Panel title="Paper orders" subtitle={`${orders.length} most recent`} flush>
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
            {orders.map((o) => (
              <tr key={o.id}>
                <td className="sys-meta">{(o.submitted_at ?? o.created_at ?? '').slice(0, 19).replace('T', ' ')}</td>
                <td>
                  <CompanyIdentity symbol={o.symbol} size="sm" href={`/company/${encodeURIComponent(o.symbol)}`} />
                </td>
                <td>{o.side ? <span className="paper-side" data-side={o.side.toLowerCase()}>{o.side.toUpperCase()}</span> : '—'}</td>
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
