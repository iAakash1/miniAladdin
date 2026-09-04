/* One quote per symbol, however many panels show it.

   The home screen had two panels asking for overlapping symbol sets — the
   watchlist wanting AAPL, MSFT, NVDA, TSLA and the recents list wanting MSFT,
   AAPL, NVDA — as two independent requests on independent timers. Two
   fan-outs across the vendor layer for one set of facts, and the same symbol
   able to hold two different prices on one screen because the requests landed
   at different moments.

   Both terminals we studied converge on the same answer: one fetch per topic,
   subscribers fan out free. */
import { strict as assert } from 'node:assert'
import test, { beforeEach } from 'node:test'

import {
  demandedSymbols, quoteSnapshot, resetQuoteHub, subscribeQuotes,
} from '../src/lib/quote-hub'

let requests: string[] = []

const stub = (impl?: () => Promise<unknown>) => {
  requests = []
  ;(globalThis as { fetch: unknown }).fetch = async (url: string) => {
    requests.push(decodeURIComponent(new URL(url, 'http://x').searchParams.get('symbols') ?? ''))
    if (impl) return impl()
    return { ok: true, json: async () => ({ quotes: { AAPL: { price: 1, stale: false } } }) }
  }
}

const settle = () => new Promise((r) => setTimeout(r, 10))

beforeEach(() => { resetQuoteHub(); stub() })

test('two panels wanting overlapping symbols produce one request', async () => {
  const offA = subscribeQuotes(['AAPL', 'MSFT', 'NVDA', 'TSLA'], () => {})
  const offB = subscribeQuotes(['MSFT', 'AAPL', 'NVDA'], () => {})
  await settle()

  // The second subscription adds no new symbol, so it rides the first request.
  assert.equal(requests.length, 1, `expected one request, got ${requests.length}: ${requests.join(' | ')}`)
  assert.equal(requests[0], 'AAPL,MSFT,NVDA,TSLA')
  offA(); offB()
})

test('a new symbol widens the request', async () => {
  const off = subscribeQuotes(['AAPL'], () => {})
  await settle()
  const off2 = subscribeQuotes(['GOOGL'], () => {})
  await settle()

  assert.equal(requests.length, 2)
  assert.equal(requests[1], 'AAPL,GOOGL', 'the second read did not union both panels')
  off(); off2()
})

test('demand is reference counted', async () => {
  const offA = subscribeQuotes(['AAPL', 'MSFT'], () => {})
  const offB = subscribeQuotes(['AAPL'], () => {})
  await settle()
  assert.deepEqual(demandedSymbols(), ['AAPL', 'MSFT'])

  // One panel leaving must not take a symbol the other still shows.
  offB()
  assert.deepEqual(demandedSymbols(), ['AAPL', 'MSFT'])
  offA()
  assert.deepEqual(demandedSymbols(), [])
})

test('symbols are normalised, so case cannot fork a request', async () => {
  const off = subscribeQuotes(['aapl', ' AAPL ', 'Aapl'], () => {})
  await settle()
  assert.deepEqual(demandedSymbols(), ['AAPL'])
  assert.equal(requests[0], 'AAPL')
  off()
})

test('every subscriber is notified once the read lands', async () => {
  let a = 0
  let b = 0
  const offA = subscribeQuotes(['AAPL'], () => { a += 1 })
  const offB = subscribeQuotes(['AAPL'], () => { b += 1 })
  await settle()
  assert.ok(a > 0 && b > 0, 'a subscriber was not notified')
  offA(); offB()
})

test('a failed refresh keeps the previous quotes and says they are not current', async () => {
  const off = subscribeQuotes(['AAPL'], () => {})
  await settle()
  assert.equal(quoteSnapshot().quotes.AAPL?.price, 1)

  stub(async () => ({ ok: false, status: 503 }))
  const off2 = subscribeQuotes(['MSFT'], () => {})
  await settle()

  const s = quoteSnapshot()
  // Blanking would empty a panel that showed a price a moment ago; keeping the
  // figures silently would present them as current. Both, with the error.
  assert.equal(s.quotes.AAPL?.price, 1, 'the previous quotes were discarded')
  assert.match(s.error ?? '', /503/, 'the failure is not reported')
  off(); off2()
})

test('a success clears a previous error', async () => {
  const off = subscribeQuotes(['AAPL'], () => {})
  await settle()
  stub(async () => ({ ok: false, status: 500 }))
  const off2 = subscribeQuotes(['MSFT'], () => {})
  await settle()
  assert.ok(quoteSnapshot().error)

  stub()
  const off3 = subscribeQuotes(['GOOGL'], () => {})
  await settle()
  assert.equal(quoteSnapshot().error, null, 'a recovered read left the error behind')
  off(); off2(); off3()
})

test('the last unsubscribe stops the refresh', async () => {
  const off = subscribeQuotes(['AAPL'], () => {})
  await settle()
  off()
  assert.deepEqual(demandedSymbols(), [])
})
