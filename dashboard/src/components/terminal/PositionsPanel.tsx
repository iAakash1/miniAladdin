'use client'

import { useEffect, useState } from 'react'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import {
  type Position,
  deletePosition,
  fetchPositions,
  patchPosition,
  upsertPosition,
} from '@/lib/persistence'
import { fmtNum } from '@/lib/format'

type Status = 'loading' | 'ready' | 'error'

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
    if (updated) setPositions((rows) => rows.map((r) => (r.id === updated.id ? updated : r)))
  }

  const remove = async (id: string) => {
    setPositions((rows) => rows.filter((r) => r.id !== id))
    if (!(await deletePosition(id))) reload()
  }

  const totalCost = positions.reduce((sum, p) => sum + p.shares * p.average_price, 0)

  return (
    <section aria-labelledby="positions-h" className="panel" style={{ padding: '18px 20px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <h3 id="positions-h" className="h-panel">Positions</h3>
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

      {status === 'ready' && positions.length === 0 && (
        <p style={{ fontSize: '0.8125rem', color: 'var(--faint)' }}>
          No positions yet. Add a holding above to track shares and average cost across devices.
        </p>
      )}

      {status === 'ready' && positions.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ minWidth: 560 }}>
            <thead>
              <tr>
                <th scope="col">Ticker</th>
                <th scope="col" style={{ textAlign: 'right' }}>Shares</th>
                <th scope="col" style={{ textAlign: 'right' }}>Avg price</th>
                <th scope="col" style={{ textAlign: 'right' }}>Cost basis</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => {
                const isEditing = editing?.id === position.id
                return (
                  <tr key={position.id}>
                    <td className="mono" style={{ fontWeight: 600 }}>{position.ticker}</td>
                    <td className="num" style={{ textAlign: 'right' }}>
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
                    <td className="num" style={{ textAlign: 'right' }}>
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
                    <td className="num" style={{ textAlign: 'right' }}>
                      ${fmtNum(position.shares * position.average_price, 2)}
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
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            aria-label={`Remove ${position.ticker} position`}
                            style={{ color: 'var(--faint)' }}
                            onClick={() => remove(position.id)}
                          >
                            ✕
                          </button>
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
