import { strict as assert } from 'node:assert'
import test from 'node:test'
import { fetchBars, fetchQuotes, quoteState } from '../src/lib/security'
import { quoteSnapshot, resetQuoteHub, subscribeQuotes } from '../src/lib/quote-hub'

const mock = (body: unknown) => {
  globalThis.fetch = async () => ({ ok: true, json: async () => body }) as Response
}

test('batch entry errors never become a quote', async () => {
  mock({ quotes: { AAPL: { error: 'no data' }, MSFT: { price: 406, source: 'vendor', stale: false } } })
  const quotes = await fetchQuotes(['AAPL', 'MSFT'])
  assert.equal(quotes.AAPL, undefined)
  assert.equal(quotes.MSFT.price, 406)
})

test('the shared hub also rejects per-symbol failures', async () => {
  resetQuoteHub()
  mock({ quotes: { AAPL: { error: 'no data' } } })
  const off = subscribeQuotes(['AAPL'], () => {})
  try {
    await new Promise((resolve) => setTimeout(resolve, 20))
    assert.equal(quoteSnapshot().quotes.AAPL, undefined)
  } finally { off(); resetQuoteHub() }
})

test('successful retrieval does not claim a daily close is live', () => {
  assert.equal(quoteState({ price: 100, stale: false, as_of: '2026-01-06', price_basis: 'daily close' }), 'unknown')
  assert.equal(quoteState({ price: 100, stale: true }), 'stale')
  assert.equal(quoteState(undefined), 'unavailable')
})

for (const status of ['unavailable', 'error']) {
  test(`chart ${status} is not a valid empty history`, async () => {
    mock({ prices: [], status, error: 'all vendors failed' })
    await assert.rejects(fetchBars('AAPL', '1mo'), /all vendors failed/)
  })
}

test('a provider-confirmed empty history remains a valid empty history', async () => {
  mock({ prices: [], status: 'empty', error: null })
  assert.deepEqual(await fetchBars('AAPL', '1mo'), [])
})

test('stale chart data keeps its stale warning', async () => {
  mock({ prices: [{ date: '2026-01-06', close: 100, volume: 0 }], status: 'stale', stale: true })
  await assert.rejects(fetchBars('AAPL', '1mo'), /stale/i)
})
