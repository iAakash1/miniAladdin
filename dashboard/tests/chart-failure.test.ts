/* A chart that could not be fetched is not an empty chart.

   `fetchChart` returned `{ prices: [] }` for any non-OK response, and
   `normalizeChartSeries` reads "no prices, no status" as `empty`: "No sessions
   returned for AAPL". A 502 from a cold backend therefore told a reader the
   security had never traded. The route already distinguishes ok, stale, empty
   and unavailable in a 200 body; the client has to keep that distinction, and a
   response that is not a 200 must not borrow the vocabulary of one. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { ApiError, fetchChart, normalizeChartSeries } from '../src/lib/api'

const realFetch = globalThis.fetch
const answer = (status: number, body: unknown) => {
  globalThis.fetch = (async () => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })) as typeof fetch
}
test.afterEach(() => { globalThis.fetch = realFetch })

for (const status of [401, 404, 422, 500, 502, 503, 504]) {
  test(`HTTP ${status} from the chart route is a failure, not an empty history`, async () => {
    answer(status, { detail: 'nope' })
    await assert.rejects(fetchChart('AAPL', '1y'), (error: unknown) => error instanceof ApiError && error.status === status)
  })
}

test('the route\'s own outcomes arrive in a 200 and keep their names', async () => {
  for (const outcome of ['unavailable', 'empty', 'error', 'stale'] as const) {
    answer(200, { ticker: 'AAPL', period: '1y', prices: [], status: outcome, error: outcome === 'empty' ? null : 'down' })
    const raw = await fetchChart('AAPL', '1y')
    assert.equal(normalizeChartSeries(raw).status, outcome)
  }
})

test('only a body that says nothing at all reads as empty', () => {
  assert.equal(normalizeChartSeries({ prices: [] }).status, 'empty')
  assert.equal(normalizeChartSeries({ prices: [{ date: '2026-10-01', close: 1 }] }).status, 'ok')
})

test('the hook reports a failed request as an error with a reason, never as empty', () => {
  const hook = readFileSync(join(__dirname, '..', 'src', 'components', 'company', 'useCompany.ts'), 'utf8')
  const chartHook = hook.slice(hook.indexOf('export function usePriceSeries'))
  const failure = /\.catch\(\(e: unknown\) => \{[\s\S]*?\}\)\s*return \(\) =>/.exec(chartHook)?.[0] ?? ''
  assert.match(failure, /status: 'error'/)
  assert.doesNotMatch(failure, /status: 'empty'/)
  assert.match(failure, /did not answer/)
})
