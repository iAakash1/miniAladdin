'use client'

import CompanyMark from '@/components/ui/CompanyMark'
import ConfirmButton from '@/components/ui/ConfirmButton'
import { useEffect, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { AllocBar } from '@/components/ui/DataMarks'
import {
  type Position,
  deletePosition,
  fetchPositions,
  patchPosition,
  upsertPosition,
} from '@/lib/persistence'
import { fmtNum } from '@/lib/format'

type Status = 'loading' | 'ready' | 'error'

/** Broadcast that the book changed.
 *
 *  Portfolio Intelligence is a sibling of this panel, not a child, and it
 *  values the same holdings server-side. Without a signal it kept showing the
 *  valuation of the previous book after an add or a delete — the table said
 *  four positions and the summary said three.
 *
 *  A window event rather than lifted state or a store: the two panels share
 *  no data, only a *fact* ("the book changed"), and the product already uses
 *  this exact pattern for the command palette. Adding a state container to
 *  carry one boolean edge would be the larger change. */
export const POSITIONS_CHANGED = 'omni-positions-changed'

function announceChange() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(POSITIONS_CHANGED))
}

/**
 * Portfolio positions — cloud-persisted holdings (ticker, shares, average
 * cost). Deliberately simple: an add form, a table, inline edit on the two
 * numeric fields. Cost basis is the only derived figure shown; live P&L
 * belongs to the watchlist quotes above.
 */
export default function PositionsPanel() {
  const [positions, setPositions] = useState<Position[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [ticker, setTicker] = useState('')
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<{ id: string; shares: string; price: string } | null>(null)

  const reload = () => {
    // Microtask keeps the setState out of the synchronous effect body
    // (house rule: react-hooks/set-state-in-effect).
    queueMicrotask(() => setStatus('loading'))
    fetchPositions()
      .then((rows) => {
        setPositions(rows)
        setStatus('ready')
      })
      .catch(() => setStatus('error'))
  }

  useEffect(reload, [])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    const nShares = Number(shares)
    const nPrice = Number(price)
    if (!ticker.trim() || !Number.isFinite(nShares) || nShares <= 0 || !Number.isFinite(nPrice) || nPrice < 0) return
    setBusy(true)
    const created = await upsertPosition(ticker, nShares, nPrice)
    setBusy(false)
    if (created) {
      setTicker('')
      setShares('')
      setPrice('')
      reload()
      announceChange()
    }
  }

  const saveEdit = async () => {
    if (!editing) return
    const nShares = Number(editing.shares)
    const nPrice = Number(editing.price)
    const fields: { shares?: number; average_price?: number } = {}
    if (Number.isFinite(nShares) && nShares > 0) fields.shares = nShares
    if (Number.isFinite(nPrice) && nPrice >= 0) fields.average_price = nPrice
    const updated = await patchPosition(editing.id, fields)
    setEditing(null)
    if (updated) {
      setPositions((rows) => rows.map((r) => (r.id === updated.id ? updated : r)))
      announceChange()
    }
  }

  const remove = async (id: string) => {
    setPositions((rows) => rows.filter((r) => r.id !== id))
    if (!(await deletePosition(id))) reload()
    announceChange()
  }

  const totalCost = positions.reduce((sum, p) => sum + p.shares * p.average_price, 0)
  // The biggest weight sets the scale for every bar in the column, so the
  // bars compare holdings against each other rather than against a 100%
  // ceiling no single position in a real book ever approaches.
  const largestWeight = positions.reduce(
    (top, p) => Math.max(top, (p.shares * p.average_price * 100) / (totalCost || 1)),
    0,
  )

  return (
    <section aria-labelledby="positions-h" className="panel panel--pad">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <h2 id="positions-h" className="h-panel">Positions</h2>
        {positions.length > 0 && (
          <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
            {positions.length} · cost basis ${fmtNum(totalCost, 2)}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: '0.6875rem', color: 'var(--faint)' }}>
          Synced to your account
        </span>
      </div>

      <form onSubmit={submit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
        <label htmlFor="pos-ticker" className="visually-hidden">Ticker</label>
        <input
          id="pos-ticker"
          className="input mono"
          style={{ maxWidth: 120, height: 32, fontSize: '0.8125rem', letterSpacing: '0.06em' }}
          placeholder="Ticker"
          maxLength={8}
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z.^-]/g, ''))}
        />
        <label htmlFor="pos-shares" className="visually-hidden">Shares</label>
        <input
          id="pos-shares"
          className="input num"
          style={{ maxWidth: 110, height: 32, fontSize: '0.8125rem' }}
          placeholder="Shares"
          inputMode="decimal"
          value={shares}
          onChange={(e) => setShares(e.target.value.replace(/[^0-9.]/g, ''))}
        />
        <label htmlFor="pos-price" className="visually-hidden">Average price</label>
        <input
          id="pos-price"
          className="input num"
          style={{ maxWidth: 130, height: 32, fontSize: '0.8125rem' }}
          placeholder="Avg price"
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value.replace(/[^0-9.]/g, ''))}
        />
        <button
          type="submit"
          className="btn btn--secondary btn--sm"
          disabled={busy || !ticker.trim() || !shares || !price}
        >
          {busy ? 'Saving…' : 'Add position'}
        </button>
      </form>

      {status === 'loading' && <Skeleton height={72} />}

      {status === 'error' && (
        <EmptyState
          title="Positions couldn't be loaded"
          description="The persistence service didn't respond — your holdings are safe on the server."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={reload}>
              Try again
            </button>
          }
        />
      )}

      {/* Was a lone grey sentence, which reads as a caption on a panel that
          lost its table rather than as a state the panel is in. */}
      {status === 'ready' && positions.length === 0 && (
        <EmptyState
          title="No positions yet"
          description="Add a holding above to track shares and average cost. Positions sync to your account, so they follow you across devices."
        />
      )}

      {status === 'ready' && positions.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col" className="num">Shares</th>
                <th scope="col" className="num">Avg price</th>
                <th scope="col" className="num">Cost basis</th>
                {/* "Cost weight", not "Weight": Portfolio Intelligence below
                    shows weights of *current market value*, and two columns
                    on one page both labelled "Weight" and disagreeing is
                    worse than either label alone. This table is the record of
                    what was paid; that panel is the valuation. */}
                <th scope="col" title="Share of total cost basis">Cost weight</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const isEditing = editing?.id === position.id
                return (
                  <tr key={position.id}>
                    <td className="mono" style={{ fontWeight: 600 }}>
                      <span className="u-row" style={{ gap: 7, flexWrap: 'nowrap' }}>
                        <CompanyMark ticker={position.ticker} size={18} />
                        {position.ticker}
                      </span>
                    </td>
                    <td className="num">
                      {isEditing ? (
                        <input
                          aria-label={`Shares of ${position.ticker}`}
                          className="input num"
                          style={{ width: 90, height: 26, fontSize: '0.8125rem', textAlign: 'right' }}
                          value={editing.shares}
                          onChange={(e) =>
                            setEditing({ ...editing, shares: e.target.value.replace(/[^0-9.]/g, '') })
                          }
                        />
                      ) : (
                        fmtNum(position.shares, position.shares % 1 === 0 ? 0 : 4)
                      )}
                    </td>
                    <td className="num">
                      {isEditing ? (
                        <input
                          aria-label={`Average price of ${position.ticker}`}
                          className="input num"
                          style={{ width: 100, height: 26, fontSize: '0.8125rem', textAlign: 'right' }}
                          value={editing.price}
                          onChange={(e) =>
                            setEditing({ ...editing, price: e.target.value.replace(/[^0-9.]/g, '') })
                          }
                        />
                      ) : (
                        `$${fmtNum(position.average_price, 2)}`
                      )}
                    </td>
                    <td className="num">
                      ${fmtNum(position.shares * position.average_price, 2)}
                    </td>
                    <td>
                      {/* Share of *cost basis*, computed from the figures in
                          this table and nothing else — deliberately not the
                          market-value weight shown in Portfolio Intelligence,
                          which needs a live quote this table does not fetch.
                          Scaled to the largest holding rather than to 100%,
                          so a diversified book still produces bars that can
                          be compared instead of eight stubs in the first
                          tenth of the track. */}
                      <AllocBar
                        value={(position.shares * position.average_price * 100) / (totalCost || 1)}
                        max={largestWeight}
                      />
                    </td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {isEditing ? (
                        <>
                          <button type="button" className="btn btn--ghost btn--xs" onClick={saveEdit}>
                            Save
                          </button>
                          <button type="button" className="btn btn--ghost btn--xs" onClick={() => setEditing(null)}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            onClick={() =>
                              setEditing({
                                id: position.id,
                                shares: String(position.shares),
                                price: String(position.average_price),
                              })
                            }
                          >
                            Edit
                          </button>
                          <ConfirmButton
                            description={`Remove ${position.ticker} position`}
                            confirmLabel="Remove?"
                            onConfirm={() => remove(position.id)}
                          >
                            ✕
                          </ConfirmButton>
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
