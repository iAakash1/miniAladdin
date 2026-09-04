/* One research request per symbol, however many panels want it.

   /api/research/:ticker fans out across every configured vendor and takes
   between twenty-five and sixty-five seconds. Three panels on the security
   page need parts of it, and three independent fetches would mean three
   fan-outs, three sets of rate limit spent, and three arrival times for facts
   about one company. */
import { strict as assert } from 'node:assert'
import test, { beforeEach } from 'node:test'

import { clearResearchCache, fetchResearch, researchCacheSize } from '../src/lib/research-cache'

let calls: string[] = []

const stubFetch = (impl?: (url: string) => Promise<unknown>) => {
  calls = []
  ;(globalThis as { fetch: unknown }).fetch = async (url: string) => {
    calls.push(url)
    if (impl) return impl(url)
    return { ok: true, json: async () => ({ profile: { name: 'stub' } }) }
  }
}

beforeEach(() => { clearResearchCache(); stubFetch() })

test('concurrent callers share one request', async () => {
  const [a, b, c] = await Promise.all([
    fetchResearch('AAPL'), fetchResearch('AAPL'), fetchResearch('AAPL'),
  ])
  assert.equal(calls.length, 1, 'three panels produced more than one fan-out')
  assert.deepEqual(a, b)
  assert.deepEqual(b, c)
})

test('a returning visitor does not pay the minute again', async () => {
  await fetchResearch('AAPL')
  await fetchResearch('AAPL')
  assert.equal(calls.length, 1)
})

test('symbols are cached apart, and normalised', async () => {
  await fetchResearch('AAPL')
  await fetchResearch('MSFT')
  await fetchResearch('aapl')
  assert.equal(calls.length, 2, 'a lowercase symbol started a second request for the same company')
  assert.equal(researchCacheSize(), 2)
})

test('a failure is not cached', async () => {
  // A transient vendor outage must not persist for the cache lifetime. The
  // next panel to ask should get a fresh attempt.
  let attempt = 0
  stubFetch(async () => {
    attempt += 1
    if (attempt === 1) return { ok: false, status: 503 }
    return { ok: true, json: async () => ({ profile: { name: 'recovered' } }) }
  })

  await assert.rejects(fetchResearch('AAPL'), /503/)
  assert.equal(researchCacheSize(), 0, 'the failed attempt was retained')

  const ok = await fetchResearch('AAPL')
  assert.deepEqual(ok, { profile: { name: 'recovered' } })
  assert.equal(calls.length, 2)
})

test('the cache stays small', async () => {
  for (const s of ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']) {
    await fetchResearch(s)
  }
  assert.ok(researchCacheSize() <= 8, `cache grew to ${researchCacheSize()}; this is a browsing session, not a database`)
})
