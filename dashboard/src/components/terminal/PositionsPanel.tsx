'use client'

import ActionMenu from '@/components/system/ActionMenu'
import CompanyMark from '@/components/ui/CompanyMark'
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
import { fmtPrice } from '@/lib/format'
import { format } from '@/lib/quantity'

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
  // Which field is wrong and why. A save that fails must say so: this form used
  // to return without a word on a zero share count or a failed request.
  const [problem, setProblem] = useState<{ field: 'ticker' | 'shares' | 'price' | 'save'; text: string } | null>(null)
  const [editing, setEditing] = useState<{ id: string; shares: string; price: string } | null>(null)
  // The position whose removal is awaiting a second, explicit press.
  const [removing, setRemoving] = useState<string | null>(null)

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
    if (!ticker.trim()) return setProblem({ field: 'ticker', text: 'Enter a ticker.' })
    if (!Number.isFinite(nShares) || nShares <= 0) return setProblem({ field: 'shares', text: 'Shares must be a number above zero.' })
    if (!Number.isFinite(nPrice) || nPrice < 0) return setProblem({ field: 'price', text: 'Average price must be zero or more.' })
    setProblem(null)
    setBusy(true)
    const created = await upsertPosition(ticker, nShares, nPrice)
    setBusy(false)
    if (!created) setProblem({ field: 'save', text: 'The position could not be saved. Check your connection and try again.' })
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
    <section aria-labelledby="positions-h" className="sys-panel pos">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 id="positions-h" className="sys-panel-title">Positions</h2>
          <span className="sys-panel-sub">
            {positions.length > 0
              ? `${positions.length} holding${positions.length === 1 ? '' : 's'} · cost basis ${fmtPrice(totalCost)}`
              : 'shares and average cost you record'}
          </span>
        </div>
        <span className="sys-meta">Synced to your account</span>
      </header>

      <form onSubmit={submit} className="pos-form" aria-label="Add a position">
        <label className="pos-form__field">
          <span className="pos-form__k">Ticker</span>
          <input
            id="pos-ticker"
            className="sys-input sys-input--block mono"
            placeholder="AAPL"
            maxLength={8}
            value={ticker}
            aria-invalid={problem?.field === 'ticker' || undefined}
            onChange={(e) => { setProblem(null); setTicker(e.target.value.toUpperCase().replace(/[^A-Z.^-]/g, '')) }}
          />
        </label>
        <label className="pos-form__field">
          <span className="pos-form__k">Shares</span>
          <input
            id="pos-shares"
            className="sys-input sys-input--block num"
            placeholder="10"
            inputMode="decimal"
            value={shares}
            aria-invalid={problem?.field === 'shares' || undefined}
            onChange={(e) => { setProblem(null); setShares(e.target.value.replace(/[^0-9.]/g, '')) }}
          />
        </label>
        <label className="pos-form__field">
          <span className="pos-form__k">Average price</span>
          <input
            id="pos-price"
            className="sys-input sys-input--block num"
            placeholder="0.00"
            inputMode="decimal"
            value={price}
            aria-invalid={problem?.field === 'price' || undefined}
            onChange={(e) => { setProblem(null); setPrice(e.target.value.replace(/[^0-9.]/g, '')) }}
          />
        </label>
        <button
          type="submit"
          className="sys-btn sys-btn--primary pos-form__submit"
          disabled={busy || !ticker.trim() || !shares || !price}
        >
          {busy ? 'Saving…' : 'Add position'}
        </button>
        {problem ? <p className="sys-meta sys-field-error pos-form__error" role="alert">{problem.text}</p> : null}
      </form>

      {status === 'loading' && <div className="pos-state"><Skeleton height={72} /></div>}

      {status === 'error' && (
        <div className="pos-state">
          <EmptyState
            title="Positions couldn't be loaded"
            description="The persistence service didn't respond — your holdings are safe on the server."
            action={
              <button type="button" className="sys-btn" onClick={reload}>
                Try again
              </button>
            }
          />
        </div>
      )}

      {/* A state the panel is in, said with what to do next — not a lone grey
          caption under a table that is not there. */}
      {status === 'ready' && positions.length === 0 && (
        <div className="pos-state emptyline">
          <span className="emptyline__k">No positions yet</span>
          <span className="emptyline__v">
            Record a holding above with its share count and average cost. Positions sync to your account,
            and Portfolio intelligence values them against current prices once there is one.
          </span>
        </div>
      )}

      {status === 'ready' && positions.length > 0 && (
        <div className="sys-scroll-x">
          <table className="sys-table pos-table">
            <caption className="visually-hidden">Recorded positions: shares, average price, cost basis and share of cost</caption>
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
                const confirming = removing === position.id
                return (
                  <tr key={position.id}>
                    <th scope="row" className="pos-sym">
                      <span className="pos-sym__line">
                        <CompanyMark ticker={position.ticker} size={18} />
                        <span className="pos-sym__t">{position.ticker}</span>
                      </span>
                    </th>
                    <td className="num pos-shares" data-label="Shares">
                      {isEditing ? (
                        <input
                          aria-label={`Shares of ${position.ticker}`}
                          className="sys-input num pos-edit"
                          value={editing.shares}
                          onChange={(e) =>
                            setEditing({ ...editing, shares: e.target.value.replace(/[^0-9.]/g, '') })
                          }
                        />
                      ) : (
                        // Exactly as held: 3.5 shares is not 3.5000, and is never 4.
                        format(position.shares, 'count', { digits: 6 }).text
                      )}
                    </td>
                    <td className="num pos-avg" data-label="Avg">
                      {isEditing ? (
                        <input
                          aria-label={`Average price of ${position.ticker}`}
                          className="sys-input num pos-edit"
                          value={editing.price}
                          onChange={(e) =>
                            setEditing({ ...editing, price: e.target.value.replace(/[^0-9.]/g, '') })
                          }
                        />
                      ) : (
                        fmtPrice(position.average_price)
                      )}
                    </td>
                    <td className="num pos-cost">
                      {fmtPrice(position.shares * position.average_price)}
                    </td>
                    <td className="pos-weight">
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
                    <td className="trk-acts pos-acts">
                      {isEditing ? (
                        <>
                          <button type="button" className="sys-btn sys-btn--xs sys-btn--primary" onClick={saveEdit}>
                            Save
                          </button>
                          <button type="button" className="sys-btn sys-btn--xs" onClick={() => setEditing(null)}>
                            Cancel
                          </button>
                        </>
                      ) : confirming ? (
                        <span className="trk-confirm" role="group" aria-label={`Remove ${position.ticker}?`}>
                          <button type="button" className="sys-btn sys-btn--xs sys-btn--danger" onClick={() => { setRemoving(null); void remove(position.id) }}>
                            Remove {position.ticker}
                          </button>
                          <button type="button" className="sys-btn sys-btn--xs" onClick={() => setRemoving(null)}>Keep</button>
                        </span>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="sys-btn sys-btn--xs"
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
                          <ActionMenu
                            label={`Actions for the ${position.ticker} position`}
                            items={[
                              { kind: 'link', label: `Open ${position.ticker}`, href: `/company/${encodeURIComponent(position.ticker)}` },
                              { kind: 'link', label: 'Paper order…', href: `/terminal/paper?ticket=${encodeURIComponent(position.ticker)}` },
                              { kind: 'separator' },
                              { label: 'Remove position…', onSelect: () => setRemoving(position.id), tone: 'danger' },
                            ]}
                          />
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
