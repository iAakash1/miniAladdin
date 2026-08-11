/* `/api/research/{ticker}` is not a read — the backend records every call to
   the user's history. Issuing it twice writes two rows.

   It *was* being issued twice per page visit (measured in the browser, two
   GETs 1 ms apart): React StrictMode mounts/unmounts/remounts in dev, and the
   company page's once-per-ticker guard frees itself on an undelivered
   teardown so the remount can fetch — otherwise the report never loads at
   all. Correct for the loader, but the second mount started a real second
   request, which is what filled the Vault with pairs of identical rows and
   spent a second ~10 s vendor pipeline per visit.

   These pin the coalescing window that fixes it. Note what is deliberately
   NOT tested: that a later call reuses an earlier result. This is not a
   cache — two visits a minute apart must still produce two analyses. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { coalesce } from '../src/lib/api'

const defer = <T>() => {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

test('concurrent callers on the same key share one execution', async () => {
  const registry = new Map<string, Promise<string>>()
  const gate = defer<string>()
  let runs = 0
  const work = () => { runs += 1; return gate.promise }

  const a = coalesce(registry, 'KO:false', work)
  const b = coalesce(registry, 'KO:false', work)
  const c = coalesce(registry, 'KO:false', work)

  gate.resolve('analysis')
  assert.deepEqual(await Promise.all([a, b, c]), ['analysis', 'analysis', 'analysis'])
  assert.equal(runs, 1, `expected one request, got ${runs}`)
})

test('different keys never share — a different ticker is a different request', async () => {
  const registry = new Map<string, Promise<string>>()
  let runs = 0
  const work = (name: string) => async () => { runs += 1; return name }

  await Promise.all([
    coalesce(registry, 'KO:false', work('KO')),
    coalesce(registry, 'PEP:false', work('PEP')),
    // `fast` is part of the key: a quick scan is a different analysis.
    coalesce(registry, 'KO:true', work('KO-fast')),
  ])
  assert.equal(runs, 3)
})

test('the window closes when the request settles — this is not a cache', async () => {
  const registry = new Map<string, Promise<number>>()
  let runs = 0
  const work = async () => { runs += 1; return runs }

  assert.equal(await coalesce(registry, 'KO:false', work), 1)
  assert.equal(await coalesce(registry, 'KO:false', work), 2, 'a later visit must run a new analysis')
  assert.equal(registry.size, 0, 'registry leaked an entry')
})

test('a failure is shared by everyone waiting, and clears the window', async () => {
  const registry = new Map<string, Promise<string>>()
  const gate = defer<string>()
  let runs = 0
  const failing = () => { runs += 1; return gate.promise }

  const a = coalesce(registry, 'KO:false', failing)
  const b = coalesce(registry, 'KO:false', failing)
  gate.reject(new Error('vendor down'))

  await assert.rejects(a, /vendor down/)
  await assert.rejects(b, /vendor down/)
  assert.equal(runs, 1)
  // A failed attempt must not wedge the key — retrying has to be possible.
  assert.equal(registry.size, 0)
  assert.equal(await coalesce(registry, 'KO:false', async () => 'recovered'), 'recovered')
})

test('a synchronous throw in the work function still clears the window', async () => {
  const registry = new Map<string, Promise<string>>()
  await assert.rejects(
    coalesce(registry, 'KO:false', () => { throw new Error('boom') }),
    /boom/,
  )
  assert.equal(registry.size, 0, 'a throwing request left the key wedged forever')
})
