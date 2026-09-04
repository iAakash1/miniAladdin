/* One request per resource, however many components want it.

   Six components read the model registry; two read the market dashboard,
   which takes twenty seconds to build. Before this layer each called `fetch`
   directly, so opening a workspace issued the same request several times and
   held several copies of the answer, arriving at several moments. */
import { strict as assert } from 'node:assert'
import test, { beforeEach } from 'node:test'

import { clearResourceCache, readResource, resourceCacheSize } from '../src/lib/resource'

let calls: string[] = []

const stubFetch = (impl?: (url: string) => Promise<unknown>) => {
  calls = []
  ;(globalThis as { fetch: unknown }).fetch = async (url: string) => {
    calls.push(url)
    if (impl) return impl(url)
    return { ok: true, json: async () => ({ leaderboard: [] }) }
  }
}

beforeEach(() => { clearResourceCache(); stubFetch() })

test('the six registry readers issue one request', async () => {
  const answers = await Promise.all(
    Array.from({ length: 6 }, () => readResource('/api/ml/registry', 'artifact')),
  )
  assert.equal(calls.length, 1, 'six components produced more than one request')
  for (const a of answers) assert.deepEqual(a, answers[0])
})

test('the second workspace to open does not pay the twenty seconds again', async () => {
  await readResource('/api/dashboard', 'snapshot')
  await readResource('/api/dashboard', 'snapshot')
  assert.equal(calls.length, 1)
})

test('different resources are not confused for each other', async () => {
  await readResource('/api/ml/registry', 'artifact')
  await readResource('/api/dashboard', 'snapshot')
  assert.equal(calls.length, 2)
})

test('a failure is not cached', async () => {
  let attempt = 0
  stubFetch(async () => {
    attempt += 1
    if (attempt === 1) throw new Error('vendor down')
    return { ok: true, json: async () => ({ leaderboard: [] }) }
  })

  await assert.rejects(readResource('/api/ml/registry', 'artifact'))
  /* The outage ended. A cached rejection would keep reporting it for the
     policy's full five minutes after the vendor came back. */
  await readResource('/api/ml/registry', 'artifact')
  assert.equal(calls.length, 2)
})

test('an HTTP error is a rejection, not a cached body', async () => {
  stubFetch(async () => ({ ok: false, status: 503, json: async () => ({}) }))
  await assert.rejects(readResource('/api/ml/registry', 'artifact'))
  assert.equal(resourceCacheSize(), 0)
})

test('the cache does not grow without bound', async () => {
  for (let i = 0; i < 40; i += 1) {
    await readResource(`/api/quant/experiments/EXP-${i}`, 'artifact')
  }
  assert.ok(resourceCacheSize() <= 24, `cache held ${resourceCacheSize()} entries`)
})

test("a live policy caches nothing — the quote hub owns liveness", async () => {
  await readResource('/api/quotes?symbols=AAPL', 'live')
  await readResource('/api/quotes?symbols=AAPL', 'live')
  assert.equal(calls.length, 2, 'a price was served from cache')
})
