/* The tracker, alerts, inbox and paper ticket, as a reader meets them.

   Each case is a claim the interface makes about the world: a stale quote is
   not drawn as a live one, a skipped evaluation is not a "checked, nothing
   happened", the bell's count is the server's, an order whose outcome was lost
   is resolved by asking the broker and never by placing it again, and a
   research verdict on a ticket is context, never an instruction. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { BellView } from '../src/components/shell/NotificationBell'
import { AlertRow } from '../src/components/terminal/alerts/AlertsWorkspace'
import { Placed, Review, Unconfirmed } from '../src/components/terminal/paper/OrderTicket'
import { TrackedRow } from '../src/components/terminal/tracker/TrackerWorkspace'
import { draftProblems, type InboxItem, type InboxState, type PriceAlert } from '../src/lib/alerts'
import { isOpenOrder, ticketProblems, type OrderIntent, type OrderPreview } from '../src/lib/paper'
import { signalCaution } from '../src/lib/research-context'
import { filterTracker, periodValue, sortTracker, type SortInput, type TrackerRow } from '../src/lib/tracker'
import { parseTags, type Watchlist } from '../src/lib/watchlists'

const SRC = join(__dirname, '..', 'src')
const html = (el: ReactElement) => renderToStaticMarkup(el)
const inTable = (row: ReactElement) => html(createElement('table', null, createElement('tbody', null, row)))
const noop = () => {}

/* ── tracker model ─────────────────────────────────────────────────────── */

function quote(symbol: string, over: Partial<TrackerRow> = {}): TrackerRow {
  return {
    symbol, price: 100, as_of: '2026-10-23T15:30:00Z', source: 'polygon', freshness: 'delayed',
    change: 1, change_pct: 1, quote_status: 'ok', performance: { '1W': 2, '1M': 5 }, ...over,
  }
}
const item = (ticker: string, position: number, row?: TrackerRow, alerts = 0, signalConfidence: number | null = null): SortInput =>
  ({ ticker, position, row, alerts, signalConfidence })

test('a period return comes from daily closes, and a window the history does not cover is blank', () => {
  const r = quote('A', { change_pct: 1.5, performance: { '1W': 2, '1M': null, '3M': Number.NaN } })
  assert.equal(periodValue(r, '1D'), 1.5, '1D is the quote\'s own change')
  assert.equal(periodValue(r, '1W'), 2)
  assert.equal(periodValue(r, '1M'), null)
  assert.equal(periodValue(r, '3M'), null, 'a non-finite value is not a return')
  assert.equal(periodValue(r, '1Y'), null)
  assert.equal(periodValue(undefined, '1D'), null)
})

test('a missing quote sorts last in either direction, so it never tops a gainers view', () => {
  const list = [
    item('MISS', 0, quote('MISS', { price: null, change_pct: null, quote_status: 'unavailable' })),
    item('UP', 1, quote('UP', { change_pct: 4 })),
    item('DOWN', 2, quote('DOWN', { change_pct: -3 })),
    item('NONE', 3),
  ]
  assert.deepEqual(sortTracker(list, 'change_pct', '1D', true).map((i) => i.ticker), ['UP', 'DOWN', 'MISS', 'NONE'])
  assert.deepEqual(sortTracker(list, 'change_pct', '1D', false).map((i) => i.ticker), ['DOWN', 'UP', 'MISS', 'NONE'])
})

test('manual order is the list\'s own order, and ties keep it', () => {
  const list = [item('C', 2), item('A', 0), item('B', 1)]
  assert.deepEqual(sortTracker(list, 'manual', '1M').map((i) => i.ticker), ['A', 'B', 'C'])
  assert.deepEqual(sortTracker(list, 'symbol', '1M', false).map((i) => i.ticker), ['A', 'B', 'C'], 'symbol order ignores direction')
  const tied = [item('X', 0, undefined, 1), item('Y', 1, undefined, 1), item('Z', 2, undefined, 2)]
  assert.deepEqual(sortTracker(tied, 'alerts', '1M').map((i) => i.ticker), ['Z', 'X', 'Y'])
})

test('period and signal sorts read the period and the research confidence', () => {
  const list = [
    item('A', 0, quote('A', { performance: { '1M': 3 } }), 0, 40),
    item('B', 1, quote('B', { performance: { '1M': 9 } }), 0, null),
    item('C', 2, quote('C', { performance: { '1M': -2 } }), 0, 80),
  ]
  assert.deepEqual(sortTracker(list, 'perf', '1M').map((i) => i.ticker), ['B', 'A', 'C'])
  assert.deepEqual(sortTracker(list, 'signal', '1M').map((i) => i.ticker), ['C', 'A', 'B'])
})

test('the filter matches symbol, note and tag, whatever the case', () => {
  const list = [item('NVDA', 0), item('MSFT', 1), item('AAPL', 2)]
  const notes = {
    NVDA: { note: 'Earnings Nov 19', tags: ['AI'] },
    MSFT: { note: null, tags: ['Core'] },
    AAPL: { note: null, tags: [] },
  }
  assert.deepEqual(filterTracker(list, 'nv', notes).map((i) => i.ticker), ['NVDA'])
  assert.deepEqual(filterTracker(list, 'earnings', notes).map((i) => i.ticker), ['NVDA'])
  assert.deepEqual(filterTracker(list, 'core', notes).map((i) => i.ticker), ['MSFT'], 'a capitalized tag still matches')
  assert.deepEqual(filterTracker(list, '  ', notes).length, 3)
})

/* ── tracker rows, rendered ────────────────────────────────────────────── */

const LIST: Watchlist = {
  id: 'w1', name: 'Core', tickers: ['NVDA'], createdAt: '2026-10-01T00:00:00Z',
  items: [{ ticker: 'NVDA', note: null, tags: [], position: 0, addedAt: '2026-10-01T00:00:00Z' }],
}
const row = (r: TrackerRow | undefined, research?: Parameters<typeof TrackedRow>[0]['research']) => inTable(createElement(TrackedRow, {
  list: LIST, lists: [LIST], ticker: 'NVDA', row: r, period: '1M', alerts: 0, research, manual: true, onAlert: noop,
}))

test('a stale quote is labelled stale, with its source and time', () => {
  const out = row(quote('NVDA', { freshness: 'stale', quote_status: 'stale' }))
  assert.match(out, /data-fresh="stale"[^>]*>stale</)
  assert.match(out, /polygon/)
  assert.doesNotMatch(out, /data-fresh="live"/)
})

test('a live quote says live, and only then', () => {
  assert.match(row(quote('NVDA', { freshness: 'live' })), /data-fresh="live"[^>]*>live</)
  assert.match(row(quote('NVDA', { freshness: 'end_of_day' })), />last close</)
})

test('without a quote the last close is shown as a close, never as a price', () => {
  const out = row(quote('NVDA', { price: null, freshness: undefined, quote_status: 'unavailable', last_close: 182.5, change: null, change_pct: null }))
  assert.match(out, /title="No current quote; this is the last daily close">close /)
  assert.doesNotMatch(out, /data-fresh=/)
})

test('a symbol no provider answers for says why, rather than showing a number', () => {
  const out = row(quote('NVDA', { price: null, freshness: undefined, quote_status: 'no_data', change: null, change_pct: null, last_close: null }))
  assert.match(out, /no provider has this symbol/)
  assert.match(row(quote('NVDA', { price: null, freshness: undefined, quote_status: 'unavailable', change: null, change_pct: null })), /providers unavailable/)
})

test('a weakly supported verdict is qualified on the row', () => {
  const out = row(quote('NVDA'), { ticker: 'NVDA', verdict: 'BUY', confidence: 42, evidence_grade: 'ACCEPTABLE' })
  assert.match(out, /BUY/)
  assert.match(out, /QUALIFIED/)
  const insufficient = row(quote('NVDA'), { ticker: 'NVDA', verdict: 'BUY', confidence: 90, evidence_grade: 'INSUFFICIENT' })
  assert.match(insufficient, /INSUFFICIENT EVIDENCE/)
})

test('the paper action opens a prefilled ticket and submits nothing', () => {
  const out = row(quote('NVDA'))
  assert.match(out, /href="\/terminal\/paper\?ticket=NVDA&amp;origin=watchlist"/)
})

/* ── alerts ────────────────────────────────────────────────────────────── */

test('an alert draft is checked the way the server checks it', () => {
  assert.deepEqual(draftProblems({ ticker: 'NVDA', kind: 'cross_above', threshold: 120 }), [])
  assert.ok(draftProblems({ ticker: 'NVDA', kind: 'cross_above', threshold: 0 }).length)
  assert.ok(draftProblems({ ticker: 'not a ticker', kind: 'cross_below', threshold: 5 }).length)
  assert.ok(draftProblems({ ticker: 'NVDA', kind: 'day_move', threshold: 150 }).length, 'a move above 100% is refused')
  assert.ok(draftProblems({ ticker: 'NVDA', kind: 'period_move', threshold: 5, period_days: 1 }).length)
  assert.deepEqual(draftProblems({ ticker: 'NVDA', kind: 'period_move', threshold: 5, period_days: 21 }), [])
  assert.ok(draftProblems({ ticker: 'NVDA', kind: 'range_exit', threshold: 120, threshold_high: 110 }).length, 'low must sit below high')
  assert.deepEqual(draftProblems({ ticker: 'NVDA', kind: 'new_filing' }), [])
})

function alert(over: Partial<PriceAlert> = {}): PriceAlert {
  return {
    id: 'a1', ticker: 'NVDA', kind: 'cross_above', threshold: 200, threshold_high: null, direction: null, period_days: null,
    form_types: [], status: 'active', repeat: false, armed: true, note: null, condition: 'NVDA crosses above $200.00',
    last_evaluated_at: null, last_observed_value: null, last_observed_at: null, last_source: null, last_result: null,
    last_triggered_at: null, created_at: '2026-10-20T00:00:00Z', ...over,
  }
}
const alertRow = (a: PriceAlert) => inTable(createElement(AlertRow, { a, act: noop }))

test('configured, evaluated, skipped and triggered read as four different things', () => {
  const configured = alertRow(alert())
  assert.match(configured, /waiting for the first evaluation/)
  assert.match(configured, /not yet evaluated/)

  const evaluated = alertRow(alert({ last_result: 'not crossed', last_evaluated_at: '2026-10-23T15:31:00Z', last_observed_value: 182.1, last_source: 'polygon' }))
  assert.match(evaluated, /not crossed/)
  assert.doesNotMatch(evaluated, /not yet evaluated/)
  assert.match(evaluated, /182\.1 · polygon/)

  // A skip is not an evaluation: it is marked, and "last checked" stays empty.
  const skipped = alertRow(alert({ last_result: 'skipped: quote is stale' }))
  assert.match(skipped, /class="alerts-skip">skipped: quote is stale/)
  assert.match(skipped, /not yet evaluated/)

  const triggered = alertRow(alert({ status: 'triggered', last_result: 'triggered', last_triggered_at: '2026-10-23T15:31:00Z', last_evaluated_at: '2026-10-23T15:31:00Z' }))
  assert.match(triggered, /TRIGGERED/)
  assert.match(triggered, />Re-arm</)

  const paused = alertRow(alert({ status: 'paused', last_result: 'not crossed' }))
  assert.match(paused, />paused</)
  assert.match(paused, />Resume</)
})

test('deleting an alert takes a second, explicit step', () => {
  const out = alertRow(alert())
  assert.match(out, />Delete…</)
  assert.doesNotMatch(out, />Delete alert</)
})

/* ── the bell ──────────────────────────────────────────────────────────── */

const note = (id: string, read: boolean): InboxItem => ({
  id, kind: 'alert', title: `NVDA crossed above $200.00 (${id})`, body: 'Observed $201.40 from polygon.', link: '/company/NVDA',
  read, createdAt: '2026-10-23T15:31:00Z', event: null,
})
const bell = (inbox: InboxState, open = true) =>
  html(createElement(BellView, { inbox, open, panelId: 'p', onToggle: noop, onOpen: noop, onClose: noop }))

test('the bell shows the server\'s unread count, and nothing when there is none', () => {
  const two = bell({ status: 'ready', unread: 2, notifications: [note('n1', false), note('n2', false), note('n3', true)] }, false)
  assert.match(two, /aria-label="Notifications, 2 unread"/)
  assert.match(two, /class="bell__count"[^>]*>2</)
  const none = bell({ status: 'ready', unread: 0, notifications: [note('n3', true)] }, false)
  assert.doesNotMatch(none, /bell__count/)
  assert.match(bell({ status: 'ready', unread: 250, notifications: [] }, false), />99\+</)
})

test('loading, empty and failed reads are each said, not shown as an empty inbox', () => {
  assert.match(bell({ status: 'loading', unread: 0, notifications: [] }), /Loading…/)
  assert.match(bell({ status: 'ready', unread: 0, notifications: [] }), /No notifications yet/)
  const failed = bell({ status: 'error', unread: 0, notifications: [] })
  assert.match(failed, /could not be read/)
  assert.doesNotMatch(failed, /No notifications yet/)
  const failedWithList = bell({ status: 'error', unread: 1, notifications: [note('n1', false)] })
  assert.match(failedWithList, /latest refresh failed/)
})

test('unread items are marked and every item can be opened', () => {
  const out = bell({ status: 'ready', unread: 1, notifications: [note('n1', false), note('n2', true)] })
  assert.equal((out.match(/class="inbox__dot"/g) ?? []).length, 1)
  assert.match(out, /data-read="true"/)
  assert.match(out, /Mark all read/)
  assert.match(out, /href="\/terminal\/alerts"/)
})

/* ── the paper ticket ──────────────────────────────────────────────────── */

const intent = (over: Partial<OrderIntent> = {}): OrderIntent =>
  ({ symbol: 'NVDA', side: 'buy', qty: 1, notional: null, order_type: 'market', time_in_force: 'day', ...over })

test('the ticket refuses what the broker would refuse, before a round trip', () => {
  assert.deepEqual(ticketProblems(intent()), [])
  assert.ok(ticketProblems(intent({ qty: 0 })).length)
  assert.ok(ticketProblems(intent({ qty: null, notional: null })).length, 'neither size given')
  assert.ok(ticketProblems(intent({ qty: 1, notional: 10 })).length, 'both sizes given')
  assert.ok(ticketProblems(intent({ qty: null, notional: 0.5 })).length, 'below the $1 minimum')
  assert.ok(ticketProblems(intent({ qty: 0.5, order_type: 'limit', limit_price: 10 })).length, 'fractional limit orders are refused')
  assert.ok(ticketProblems(intent({ order_type: 'limit', limit_price: null })).length)
  assert.deepEqual(ticketProblems(intent({ order_type: 'limit', limit_price: 101.5, time_in_force: 'gtc' })), [])
})

test('only a terminal broker status closes an order', () => {
  for (const s of ['new', 'accepted', 'partially_filled', 'pending_new', 'PENDING_CANCEL']) assert.equal(isOpenOrder(s), true, s)
  for (const s of ['filled', 'canceled', 'expired', 'rejected', 'FILLED']) assert.equal(isOpenOrder(s), false, s)
  assert.equal(isOpenOrder(null), false)
})

test('weak, insufficient or ungraded research is qualified in words; strong research is not', () => {
  assert.equal(signalCaution(null), null)
  assert.equal(signalCaution({ ticker: 'A', verdict: 'BUY', confidence: 80, evidence_grade: 'STRONG' }), null)
  assert.match(signalCaution({ ticker: 'A', verdict: 'BUY', confidence: 80, evidence_grade: 'INSUFFICIENT', evidence_reasons: ['NO_FILINGS'] }) ?? '', /insufficient evidence \(no filings\)/)
  assert.match(signalCaution({ ticker: 'A', verdict: 'SELL', confidence: 80, evidence_grade: 'WEAK' }) ?? '', /weak evidence/)
  assert.match(signalCaution({ ticker: 'A', verdict: 'BUY', confidence: 30, evidence_grade: 'ACCEPTABLE' }) ?? '', /low confidence \(30\/100\)/)
  assert.match(signalCaution({ ticker: 'A', verdict: 'BUY', confidence: 80, evidence_grade: null }) ?? '', /not graded/)
})

function preview(over: Partial<OrderPreview> = {}): OrderPreview {
  return {
    ok: true, problems: [], warnings: [],
    order: { symbol: 'NVDA', side: 'buy', order_type: 'market', time_in_force: 'day', qty: 2, notional: null, limit_price: null },
    client_order_id: 'omni-0123456789abcdef0123456789abcdef',
    quote: { price: 182.4, as_of: '2026-10-23T15:30:00Z', source: 'polygon', freshness: 'delayed' },
    estimate: { value: 364.8, qty: 2, basis: 'Estimated at the last quote; a market order fills at the market.' },
    buying_power: 100_000, market_open: true, asset: { tradable: true, fractionable: true, exchange: 'NASDAQ' },
    environment: 'paper', ...over,
  }
}
const review = (p: OrderPreview, placing = false) =>
  html(createElement(Review, { preview: p, symbol: 'NVDA', placing, thesis: '', onBack: noop, onPlace: noop }))

test('the review names the paper environment and the quote it priced against', () => {
  const out = review(preview())
  assert.match(out, /Alpaca Paper environment/)
  assert.match(out, /data-fresh="delayed"/)
  assert.match(out, /polygon · Oct 23, 15:30 UTC/)
  assert.match(out, />Confirm paper order</)
  assert.doesNotMatch(out, /<button[^>]*disabled=""[^>]*>Confirm paper order/)
})

test('a blocked order cannot be confirmed, and every problem is listed', () => {
  const out = review(preview({ ok: false, problems: ['NVDA is not tradable on Alpaca.', 'The estimated cost exceeds paper buying power.'] }))
  assert.match(out, /CANNOT BE PLACED/)
  assert.match(out, /not tradable/)
  assert.match(out, /exceeds paper buying power/)
  assert.match(out, /<button[^>]*disabled=""[^>]*>Confirm paper order/)
})

test('a stale quote is a warning on the review, not hidden', () => {
  const out = review(preview({ quote: { price: 182.4, as_of: '2026-10-20T20:00:00Z', source: 'polygon', freshness: 'stale' }, warnings: ['The quote is stale; the estimate may be far from the fill.'] }))
  assert.match(out, /data-fresh="stale"/)
  assert.match(out, /class="ticket__warnings"[^]*quote is stale/)
})

test('while placing, neither button can be pressed again', () => {
  const out = review(preview(), true)
  assert.match(out, /<button[^>]*disabled=""[^>]*>back</)
  assert.match(out, /<button[^>]*disabled=""[^>]*>placing…</)
})

test('an unconfirmed outcome offers a status check by reference, never a resend', () => {
  const out = html(createElement(Unconfirmed, { clientOrderId: 'omni-abc', detail: 'The broker did not answer in time.', checking: false, onCheck: noop }))
  assert.match(out, /OUTCOME NOT CONFIRMED/)
  assert.match(out, /omni-abc/)
  assert.match(out, /Check status with the broker/)
  assert.doesNotMatch(out, /Confirm paper order|place again|resubmit/i)
})

test('a placed order shows the broker\'s own status, and accepted is not filled', () => {
  const out = html(createElement(Placed, {
    order: { id: '3f1c', symbol: 'NVDA', side: 'buy', qty: '2', status: 'accepted', filled_qty: '0', filled_avg_price: null },
    symbol: 'NVDA', replayed: false, reconciledAfter: null, hadThesis: false,
  }))
  assert.match(out, /ACCEPTED/)
  assert.match(out, /not yet filled/)
  const replay = html(createElement(Placed, {
    order: { id: '3f1c', symbol: 'NVDA', side: 'buy', qty: '2', status: 'filled', filled_qty: '2', filled_avg_price: '182.40' },
    symbol: 'NVDA', replayed: true, reconciledAfter: null, hadThesis: false,
  }))
  assert.match(replay, /Nothing was placed twice/)
})

/* ── guarantees in the source ──────────────────────────────────────────── */

test('nothing in the browser can submit an order on its own or reach a broker directly', () => {
  const ticket = readFileSync(join(SRC, 'components', 'terminal', 'paper', 'OrderTicket.tsx'), 'utf8')
  const workspace = readFileSync(join(SRC, 'components', 'terminal', 'paper', 'PaperWorkspace.tsx'), 'utf8')
  const lib = readFileSync(join(SRC, 'lib', 'paper.ts'), 'utf8')
  // placeOrder is reached from one handler, behind the review's confirm button.
  assert.equal((ticket.match(/placeOrder\(/g) ?? []).length, 1)
  assert.doesNotMatch(workspace, /placeOrder\(/)
  // Every request the paper client makes goes to this site's own /api/paper
  // routes; the broker host and its credentials exist only on the server.
  const urls = [...lib.matchAll(/['`"](\/api\/[^'`"?$]*|https?:\/\/[^'`"\s]*)/g)].map((m) => m[1])
  assert.ok(urls.length >= 10, 'the paper client\'s routes were not found')
  assert.deepEqual(urls.filter((u) => !u.startsWith('/api/paper/')), [])
  for (const text of [ticket, lib]) assert.doesNotMatch(text, /alpaca\.markets|APCA_API_SECRET_KEY\s*[:=]/)
  assert.doesNotMatch(lib, /live[_-]?trading|LIVE_TRADING/i)
})

test('tags are cleaned the way the server stores them', () => {
  assert.deepEqual(parseTags('AI, Core , ai,  earnings!!, '), ['ai', 'core', 'earnings'])
  assert.deepEqual(parseTags('a,b,c,d,e,f,g,h,i,j'), ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'])
  assert.equal(parseTags('x'.repeat(40))[0].length, 24)
  assert.deepEqual(parseTags(' , ,'), [])
})

/* ── the company page ──────────────────────────────────────────────────── */

test('the company header offers an alert beside watch, and only when wired', async () => {
  const { default: CompanyHeader } = await import('../src/components/company/CompanyHeader')
  const props = {
    symbol: 'NVDA', name: 'NVIDIA', exchange: 'NASDAQ', sector: null, industry: null, quote: null, quoteError: null,
    historyId: null, onPaper: noop, paperAvailable: true,
  }
  assert.match(html(createElement(CompanyHeader, { ...props, onAlert: noop })), />Set alert</)
  assert.doesNotMatch(html(createElement(CompanyHeader, props)), />Set alert</)
})

test('from research, the alert and the ticket open prefilled and submit nothing', () => {
  const page = readFileSync(join(SRC, 'components', 'company', 'CompanyWorkspace.tsx'), 'utf8')
  assert.match(page, /<AlertEditor ticker=\{ticker\}/)
  assert.match(page, /<OrderTicket symbol=\{ticker\}[^>]*origin="research"/)
  assert.doesNotMatch(page, /placeOrder|previewOrder|createAlert/, 'the page itself never submits')
})
