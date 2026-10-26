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
 * The preview asks the broker whether the asset is tradable and fractionable,
 * prices the order against real buying power with a quote whose source, time
 * and freshness are shown, and returns every problem rather than the first.
 * It also issues the order's client reference: the confirmation sends that
 * reference, so pressing confirm twice — or a network retry — finds the first
 * order instead of placing a second, and an unconfirmed outcome is resolved by
 * asking the broker, never by sending again.
 *
 * A research verdict is context here, not a trigger. When the ticket opens
 * from research, the verdict is shown with its confidence and evidence grade,
 * and a weak or insufficient one says so in words.
 *
 * The thesis is optional and never generated.
 */

import { useEffect, useState } from 'react'

import { Prose, Status, Value } from '@/components/system'
import {
  placeOrder, previewOrder, reconcileOrder, ticketProblems,
  type OrderIntent, type OrderPreview, type PaperOrder, type QuoteFreshness,
} from '@/lib/paper'
import { formatMoment } from '@/lib/quantity'
import { fetchLatestResearch, signalCaution, type LatestResearch } from '@/lib/research-context'
import { recordThesis, thesisFor } from '@/lib/thesis'

type Stage =
  | { at: 'intent' }
  | { at: 'previewing' }
  | { at: 'preview'; preview: OrderPreview }
  | { at: 'placing'; preview: OrderPreview }
  | { at: 'placed'; order: PaperOrder; replayed: boolean; reconciledAfter: string | null }
  | { at: 'unknown'; clientOrderId: string; detail: string; checking: boolean }
  | { at: 'failed'; reason: string }

type Origin = NonNullable<OrderIntent['origin']>

const FRESHNESS_LABEL: Record<QuoteFreshness, string> = {
  live: 'live', delayed: 'delayed', end_of_day: 'last close', stale: 'stale', undated: 'undated', unavailable: 'unavailable',
}

export default function OrderTicket({
  symbol, researchState, onClose, origin = 'ticket', initialSide = 'buy', initialQty,
}: {
  symbol: string
  /** The research programme's state right now, snapshotted onto the thesis. */
  researchState?: string | null
  onClose: () => void
  origin?: Origin
  initialSide?: 'buy' | 'sell'
  initialQty?: number
}) {
  const [side, setSide] = useState<'buy' | 'sell'>(initialSide)
  const [sizing, setSizing] = useState<'shares' | 'dollars'>('shares')
  const [amount, setAmount] = useState(initialQty ? String(initialQty) : '1')
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [tif, setTif] = useState<'day' | 'gtc'>('day')
  const [limitPrice, setLimitPrice] = useState('')
  const [thesis, setThesis] = useState('')
  const [stage, setStage] = useState<Stage>({ at: 'intent' })
  const [research, setResearch] = useState<LatestResearch | null>(null)

  useEffect(() => {
    let alive = true
    void fetchLatestResearch([symbol]).then((m) => { if (alive) setResearch(m[symbol.toUpperCase()] ?? null) })
    return () => { alive = false }
  }, [symbol])

  const intent = (clientOrderId?: string): OrderIntent => {
    const n = Number(amount)
    return {
      symbol,
      side,
      qty: sizing === 'shares' ? n : null,
      notional: sizing === 'dollars' ? n : null,
      order_type: orderType,
      time_in_force: tif,
      limit_price: orderType === 'limit' && limitPrice ? Number(limitPrice) : null,
      client_order_id: clientOrderId ?? null,
      origin,
    }
  }
  const localProblems = ticketProblems(intent())

  const review = () => {
    setStage({ at: 'previewing' })
    previewOrder(intent())
      .then((preview) => setStage({ at: 'preview', preview }))
      .catch((e: Error) => setStage({ at: 'failed', reason: e.message }))
  }

  /* Only what the reader typed, and once per order. A replayed or reconciled
     confirmation keeps a thesis already recorded for the order, and records
     one only when the first reply was lost before it could be kept. */
  const keepThesis = (order: PaperOrder) => {
    const text = thesis.trim()
    if (text) {
      if (!thesisFor(order.id)) recordThesis({ orderId: order.id, symbol, text, at: new Date().toISOString(), researchState: researchState ?? null })
    }
  }

  const place = (preview: OrderPreview) => {
    setStage({ at: 'placing', preview })
    placeOrder(intent(preview.client_order_id))
      .then((result) => {
        if (result.kind === 'unknown') {
          setStage({ at: 'unknown', clientOrderId: result.clientOrderId, detail: result.detail, checking: false })
          return
        }
        keepThesis(result.order)
        setStage({ at: 'placed', order: result.order, replayed: result.replayed, reconciledAfter: result.reconciledAfter })
      })
      .catch((e: Error) => setStage({ at: 'failed', reason: e.message }))
  }

  const check = (clientOrderId: string, detail: string) => {
    setStage({ at: 'unknown', clientOrderId, detail, checking: true })
    reconcileOrder(clientOrderId)
      .then((r) => {
        if (r.found && r.order) {
          keepThesis(r.order)
          setStage({ at: 'placed', order: r.order, replayed: false, reconciledAfter: 'check' })
        }
        else setStage({ at: 'unknown', clientOrderId, checking: false, detail: 'The broker still has no order with this reference. It was not resent.' })
      })
      .catch((e: Error) => setStage({ at: 'unknown', clientOrderId, checking: false, detail: e.message }))
  }

  const caution = signalCaution(research)

  return (
    <section className="ticket" aria-label={`Paper order for ${symbol}`}>
      <header className="ticket__head">
        <h3 className="ticket__title">{side === 'buy' ? 'Buy' : 'Sell'} {symbol}</h3>
        <Status state="paper" label="paper order" />
        <button type="button" className="sys-btn sys-btn--micro ticket__close" onClick={onClose}>close</button>
      </header>

      {research?.verdict ? (
        <div className="ticket__research" data-caution={caution ? 'true' : undefined}>
          <span className="k">Your latest research</span>
          <span>
            {research.verdict} · confidence {research.confidence ?? '—'}/100 · evidence {research.evidence_grade?.toLowerCase() ?? 'not graded'}
          </span>
          <p>{caution ?? 'Research is context for your own decision. It is not a recommendation and never places an order.'}</p>
        </div>
      ) : null}

      {stage.at === 'placed' ? (
        <Placed order={stage.order} symbol={symbol} replayed={stage.replayed} reconciledAfter={stage.reconciledAfter} hadThesis={Boolean(thesis.trim())} />
      ) : stage.at === 'unknown' ? (
        <Unconfirmed clientOrderId={stage.clientOrderId} detail={stage.detail} checking={stage.checking} onCheck={() => check(stage.clientOrderId, stage.detail)} />
      ) : stage.at === 'failed' ? (
        <div className="ticket__body">
          <Status state="unavailable" label="NOT PLACED" />
          <Prose size="tight">{stage.reason}</Prose>
          <div className="ticket__acts">
            <button type="button" className="sys-btn" onClick={() => setStage({ at: 'intent' })}>back to the ticket</button>
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
              <select className="sys-input" value={side} onChange={(e) => setSide(e.target.value as 'buy' | 'sell')}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </label>

            <label className="ticket__field">
              <span className="k">Size by</span>
              <select
                className="sys-input" value={sizing}
                onChange={(e) => {
                  const next = e.target.value as 'shares' | 'dollars'
                  setSizing(next)
                  if (next === 'dollars') { setOrderType('market'); setTif('day') }
                }}
              >
                <option value="shares">Shares</option>
                <option value="dollars">Dollar amount</option>
              </select>
            </label>

            <label className="ticket__field">
              <span className="k">{sizing === 'shares' ? 'Quantity' : 'Amount (USD)'}</span>
              <input className="sys-input" type="number" min="0" step="any" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </label>

            <label className="ticket__field">
              <span className="k">Order type</span>
              <select className="sys-input" value={orderType} disabled={sizing === 'dollars'} onChange={(e) => setOrderType(e.target.value as 'market' | 'limit')}>
                <option value="market">Market</option>
                <option value="limit">Limit</option>
              </select>
            </label>

            {orderType === 'limit' ? (
              <label className="ticket__field">
                <span className="k">Limit price</span>
                <input className="sys-input" type="number" min="0" step="any" inputMode="decimal" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} />
              </label>
            ) : null}

            <label className="ticket__field">
              <span className="k">Time in force</span>
              <select className="sys-input" value={tif} disabled={sizing === 'dollars'} onChange={(e) => setTif(e.target.value as 'day' | 'gtc')}>
                <option value="day">Day</option>
                <option value="gtc">Good till canceled</option>
              </select>
            </label>

            <label className="ticket__field ticket__field--wide">
              <span className="k">Thesis <span className="opt">optional</span></span>
              <textarea
                className="sys-input ticket__thesis" rows={2}
                placeholder="Why this trade? Recorded with the order so it can be reviewed later."
                value={thesis} onChange={(e) => setThesis(e.target.value)}
              />
            </label>
          </div>

          {localProblems.length ? (
            <ul className="ticket__local" aria-live="polite">{localProblems.map((p) => <li key={p}>{p}</li>)}</ul>
          ) : null}

          <p className="ticket__tif">Orders reach Alpaca&apos;s paper environment and settle nothing. Nothing is sent until you confirm on the next step.</p>

          <div className="ticket__acts">
            <button type="button" className="sys-btn sys-btn--primary" onClick={review} disabled={stage.at === 'previewing' || localProblems.length > 0}>
              {stage.at === 'previewing' ? 'checking…' : 'review order'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

/* ── review ──────────────────────────────────────────────────────────────── */

export function Review({
  preview, symbol, placing, thesis, onBack, onPlace,
}: {
  preview: OrderPreview
  symbol: string
  placing: boolean
  thesis: string
  onBack: () => void
  onPlace: () => void
}) {
  const o = preview.order
  const q = preview.quote
  return (
    <div className="ticket__body">
      <div className="ticket__summary">
        <span className="ticket__verb">{o.side.toUpperCase()}</span>
        <span className="ticket__qty">{o.qty !== null ? o.qty : `$${o.notional}`}</span>
        <span className="ticket__sym">{symbol}</span>
        <span className="ticket__meta">
          {o.order_type}{o.limit_price ? ` @ ${o.limit_price}` : ''} · {o.time_in_force === 'gtc' ? 'good till canceled' : 'day'}
        </span>
      </div>

      <dl className="ticket__facts">
        <div><dt>Estimated value</dt><dd><Value value={preview.estimate.value} kind="currency" /></dd></div>
        {preview.estimate.qty !== null ? <div><dt>Estimated shares</dt><dd className="sys-num">{preview.estimate.qty.toFixed(4)}</dd></div> : null}
        <div>
          <dt>Last price</dt>
          <dd>
            <Value value={q.price} kind="currency" />{' '}
            <span className="ticket__fresh" data-fresh={q.freshness}>{FRESHNESS_LABEL[q.freshness]}</span>
          </dd>
        </div>
        <div><dt>Quote</dt><dd className="sys-meta">{q.source ?? 'no source'}{q.as_of ? ` · ${q.as_of.length === 10 ? `close of ${q.as_of}` : formatMoment(q.as_of)}` : ''}</dd></div>
        <div><dt>Paper buying power</dt><dd><Value value={preview.buying_power} kind="currency" /></dd></div>
        <div><dt>Market</dt><dd>{preview.market_open === null ? 'unknown' : preview.market_open ? 'open' : 'closed'}</dd></div>
      </dl>

      <p className="ticket__basis">{preview.estimate.basis}</p>

      {/* A weak research signal is qualified in the research note above, which stays in view. */}
      {preview.warnings.length ? (
        <ul className="ticket__warnings">
          {preview.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      ) : null}

      {preview.problems.length ? (
        <div className="ticket__problems">
          <Status state="blocked" label="CANNOT BE PLACED" />
          <ul>{preview.problems.map((p) => <li key={p}>{p}</li>)}</ul>
        </div>
      ) : null}

      {thesis ? (
        <div className="ticket__thesis-note"><span className="k">Thesis recorded with this order</span><p>{thesis}</p></div>
      ) : (
        <p className="ticket__basis">No thesis attached. The order will record none rather than one assembled on your behalf.</p>
      )}

      <p className="ticket__confirm" role="note">
        <span className="paper-ribbon__tag">Paper</span>
        This order is simulated and goes to the Alpaca Paper environment. No real money moves.
      </p>

      <div className="ticket__acts">
        <button type="button" className="sys-btn" onClick={onBack} disabled={placing}>back</button>
        <button type="button" className="sys-btn sys-btn--primary" onClick={onPlace} disabled={!preview.ok || placing}>
          {placing ? 'placing…' : 'Confirm paper order'}
        </button>
      </div>
    </div>
  )
}

/* ── unconfirmed ─────────────────────────────────────────────────────────── */

/** The broker's answer was lost. The only way forward is asking it, by reference. */
export function Unconfirmed({
  clientOrderId, detail, checking, onCheck,
}: { clientOrderId: string; detail: string; checking: boolean; onCheck: () => void }) {
  return (
    <div className="ticket__body">
      <Status state="warning" label="OUTCOME NOT CONFIRMED" />
      <Prose size="tight">{detail}</Prose>
      <p className="ticket__basis">Order reference <span className="ticket__id">{clientOrderId}</span>. Do not place it again until its status is known.</p>
      <div className="ticket__acts">
        <button type="button" className="sys-btn sys-btn--primary" disabled={checking} onClick={onCheck}>
          {checking ? 'checking…' : 'Check status with the broker'}
        </button>
      </div>
    </div>
  )
}

/* ── result ──────────────────────────────────────────────────────────────── */

export function Placed({
  order, symbol, replayed, reconciledAfter, hadThesis,
}: { order: PaperOrder; symbol: string; replayed: boolean; reconciledAfter: string | null; hadThesis: boolean }) {
  return (
    <div className="ticket__body">
      <div className="ticket__summary">
        <span className="ticket__verb">{(order.side ?? '').toUpperCase()}</span>
        <span className="ticket__qty">{order.qty ?? (order.notional ? `$${order.notional}` : '—')}</span>
        <span className="ticket__sym">{symbol}</span>
      </div>

      <dl className="ticket__facts">
        <div>
          <dt>Broker status</dt>
          {/* The broker's own word. An accepted order is not a filled one. */}
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
        {replayed
          ? 'This confirmation was already received; this is the order it created. Nothing was placed twice.'
          : reconciledAfter
            ? 'The broker did not answer the submission in time; this order was found by its reference, not sent again.'
            : 'Placed in the paper account.'}{' '}
        {hadThesis ? 'Your thesis is recorded against this order in this browser.' : ''}
      </p>

      <div className="ticket__acts">
        <a className="sys-btn" href="/terminal/paper">open the paper account</a>
      </div>
    </div>
  )
}
