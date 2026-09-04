'use client'

/**
 * A paper order, from intent to the broker's reply.
 *
 * Four states, and the reader cannot skip one: what they want, what it would
 * cost, a confirmation that names the environment, and whatever the broker
 * actually said. There is no arrangement of clicks that turns a quantity into
 * a submitted order in a single action, because the step this ticket exists
 * to protect is the one between deciding and doing.
 *
 * The preview is not decoration. It asks the broker whether the asset is
 * tradable and fractionable, prices the order against real buying power, and
 * returns every problem rather than the first — a ticket that reports one
 * error at a time is a ticket someone submits four times.
 *
 * The estimate is labelled as an estimate. It uses the last price this product
 * already holds, and a market order does not fill at the last price. Showing
 * that number without saying so is the difference between a preview and a
 * promise this cannot keep.
 *
 * And the thesis: optional, never generated. Someone who writes down why they
 * bought can be asked in three months whether they were right. Someone who
 * did not gets told no thesis was recorded — not a sentence assembled from
 * the fundamentals and presented as what they thought.
 */

import { useState } from 'react'

import { Prose, Status, Value } from '@/components/system'
import {
  placeOrder, previewOrder,
  type OrderIntent, type OrderPreview, type PaperOrder,
} from '@/lib/paper'
import { recordThesis } from '@/lib/thesis'

type Stage =
  | { at: 'intent' }
  | { at: 'previewing' }
  | { at: 'preview'; preview: OrderPreview }
  | { at: 'placing'; preview: OrderPreview }
  | { at: 'placed'; order: PaperOrder }
  | { at: 'failed'; reason: string }

export default function OrderTicket({
  symbol, researchState, onClose,
}: {
  symbol: string
  /** The research programme's state right now, snapshotted onto the thesis. */
  researchState?: string | null
  onClose: () => void
}) {
  const [side, setSide] = useState<'buy' | 'sell'>('buy')
  const [qty, setQty] = useState('10')
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [limitPrice, setLimitPrice] = useState('')
  const [thesis, setThesis] = useState('')
  const [stage, setStage] = useState<Stage>({ at: 'intent' })

  const intent = (): OrderIntent => ({
    symbol,
    qty: Number(qty),
    side,
    order_type: orderType,
    time_in_force: 'day',
    limit_price: orderType === 'limit' && limitPrice ? Number(limitPrice) : null,
  })

  const review = () => {
    setStage({ at: 'previewing' })
    previewOrder(intent())
      .then((preview) => setStage({ at: 'preview', preview }))
      .catch((e: Error) => setStage({ at: 'failed', reason: e.message }))
  }

  const place = (preview: OrderPreview) => {
    setStage({ at: 'placing', preview })
    placeOrder(intent())
      .then(({ order }) => {
        // The thesis is recorded against the broker's order id, and only when
        // the reader actually wrote one.
        const text = thesis.trim()
        if (text) {
          recordThesis({
            orderId: order.id,
            symbol,
            text,
            at: new Date().toISOString(),
            researchState: researchState ?? null,
          })
        }
        setStage({ at: 'placed', order })
      })
      .catch((e: Error) => setStage({ at: 'failed', reason: e.message }))
  }

  return (
    <section className="ticket" aria-label={`Paper order for ${symbol}`}>
      <header className="ticket__head">
        <h3 className="ticket__title">
          {side === 'buy' ? 'Buy' : 'Sell'} {symbol}
        </h3>
        <Status state="recorded" label="PAPER ORDER" />
        <button type="button" className="sys-btn sys-btn--micro ticket__close" onClick={onClose}>
          close
        </button>
      </header>

      {stage.at === 'placed' ? (
        <Placed order={stage.order} symbol={symbol} hadThesis={Boolean(thesis.trim())} />
      ) : stage.at === 'failed' ? (
        <div className="ticket__body">
          <Status state="unavailable" label="NOT PLACED" />
          <Prose size="tight">{stage.reason}</Prose>
          <div className="ticket__acts">
            <button type="button" className="sys-btn" onClick={() => setStage({ at: 'intent' })}>
              back to the ticket
            </button>
          </div>
        </div>
      ) : stage.at === 'preview' || stage.at === 'placing' ? (
        <Review
          preview={stage.preview}
          symbol={symbol}
          placing={stage.at === 'placing'}
          thesis={thesis.trim()}
          onBack={() => setStage({ at: 'intent' })}
          onPlace={() => place(stage.preview)}
        />
      ) : (
        <div className="ticket__body">
          <div className="ticket__fields">
            <label className="ticket__field">
              <span className="k">Side</span>
              <select
                className="sys-input" value={side}
                onChange={(e) => setSide(e.target.value as 'buy' | 'sell')}
              >
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>

            <label className="ticket__field">
              <span className="k">Quantity</span>
              <input
                className="sys-input" type="number" min="0" step="any"
                value={qty} onChange={(e) => setQty(e.target.value)}
                inputMode="decimal"
              />
            </label>

            <label className="ticket__field">
              <span className="k">Order type</span>
              <select
                className="sys-input" value={orderType}
                onChange={(e) => setOrderType(e.target.value as 'market' | 'limit')}
              >
                <option value="market">Market</option>
                <option value="limit">Limit</option>
              </select>
            </label>

            {orderType === 'limit' ? (
              <label className="ticket__field">
                <span className="k">Limit price</span>
                <input
                  className="sys-input" type="number" min="0" step="any"
                  value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)}
                  inputMode="decimal"
                />
              </label>
            ) : null}

            <label className="ticket__field ticket__field--wide">
              <span className="k">Thesis <span className="opt">optional</span></span>
              <textarea
                className="sys-input ticket__thesis" rows={2}
                placeholder="Why this trade? Recorded with the order so it can be reviewed later."
                value={thesis} onChange={(e) => setThesis(e.target.value)}
              />
            </label>
          </div>

          <p className="ticket__tif">
            Time in force is <strong>day</strong>. Orders reach Alpaca&apos;s paper
            environment and settle nothing.
          </p>

          <div className="ticket__acts">
            <button
              type="button" className="sys-btn sys-btn--primary"
              onClick={review}
              disabled={stage.at === 'previewing' || !qty || Number(qty) <= 0}
            >
              {stage.at === 'previewing' ? 'checking…' : 'review order'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

/* ── review ──────────────────────────────────────────────────────────────── */

function Review({
  preview, symbol, placing, thesis, onBack, onPlace,
}: {
  preview: OrderPreview
  symbol: string
  placing: boolean
  thesis: string
  onBack: () => void
  onPlace: () => void
}) {
  return (
    <div className="ticket__body">
      <div className="ticket__summary">
        <span className="ticket__verb">{preview.side.toUpperCase()}</span>
        <span className="ticket__qty">{preview.qty}</span>
        <span className="ticket__sym">{symbol}</span>
        <span className="ticket__meta">
          {preview.order_type} · {preview.time_in_force}
        </span>
      </div>

      <dl className="ticket__facts">
        <div><dt>Estimated value</dt><dd><Value value={preview.estimate.notional} kind="currency" /></dd></div>
        <div><dt>Last price</dt><dd><Value value={preview.estimate.last_price} kind="currency" /></dd></div>
        <div><dt>Paper buying power</dt><dd><Value value={preview.buying_power} kind="currency" /></dd></div>
      </dl>

      {/* Never dropped. The number above is an estimate and this says why. */}
      <p className="ticket__basis">
        {preview.estimate.basis}
        {preview.estimate.source ? ` · via ${preview.estimate.source}` : ''}
      </p>

      {preview.problems.length ? (
        <div className="ticket__problems">
          <Status state="blocked" label="CANNOT BE PLACED" />
          <ul>
            {preview.problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </div>
      ) : null}

      {thesis ? (
        <div className="ticket__thesis-note">
          <span className="k">Thesis recorded with this order</span>
          <p>{thesis}</p>
        </div>
      ) : (
        <p className="ticket__basis">
          No thesis attached. The order will record none rather than one
          assembled on your behalf.
        </p>
      )}

      <div className="ticket__acts">
        <button type="button" className="sys-btn" onClick={onBack} disabled={placing}>
          back
        </button>
        <button
          type="button" className="sys-btn sys-btn--primary"
          onClick={onPlace} disabled={!preview.ok || placing}
        >
          {placing ? 'placing…' : 'place paper order'}
        </button>
      </div>
    </div>
  )
}

/* ── result ──────────────────────────────────────────────────────────────── */

function Placed({ order, symbol, hadThesis }: { order: PaperOrder; symbol: string; hadThesis: boolean }) {
  return (
    <div className="ticket__body">
      <div className="ticket__summary">
        <span className="ticket__verb">{(order.side ?? '').toUpperCase()}</span>
        <span className="ticket__qty">{order.qty ?? '—'}</span>
        <span className="ticket__sym">{symbol}</span>
      </div>

      <dl className="ticket__facts">
        <div>
          <dt>Broker status</dt>
          {/* The broker's own word. An accepted order is not a filled one, and
              this does not upgrade it to filled because a market order
              probably filled. */}
          <dd>{(order.status ?? 'unknown').replace(/_/g, ' ').toUpperCase()}</dd>
        </div>
        <div><dt>Filled</dt><dd>{order.filled_qty ?? '0'} of {order.qty ?? '—'}</dd></div>
        <div>
          <dt>Fill price</dt>
          <dd>{order.filled_avg_price ? <Value value={Number(order.filled_avg_price)} kind="currency" /> : <span className="sys-null">not yet filled</span>}</dd>
        </div>
        <div><dt>Order id</dt><dd className="ticket__id">{order.id}</dd></div>
      </dl>

      <p className="ticket__basis">
        Placed in the paper account. {hadThesis
          ? 'Your thesis is recorded against this order and kept in this browser.'
          : 'No thesis was recorded for this order.'}
      </p>

      <div className="ticket__acts">
        <a className="sys-btn" href="/terminal/paper">open the paper account</a>
      </div>
    </div>
  )
}
