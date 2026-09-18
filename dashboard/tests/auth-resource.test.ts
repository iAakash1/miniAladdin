import { strict as assert } from 'node:assert'
import test, { beforeEach } from 'node:test'

import { clearAuthResourceCache, readAuthResource } from '../src/lib/auth-resource'
import {
  cancelOrder,
  fetchPaperAccess,
  fetchPaperAccount,
  fetchPaperOrders,
  fetchPaperPositions,
  placeOrder,
  previewOrder,
} from '../src/lib/paper'
import { clearResourceCache } from '../src/lib/resource'

interface Call { url: string; method: string; authorization: string | null }
let sessionId = 'session-a'
let token = 'token-a'
let calls: Call[] = []

function installClerk(): void {
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      Clerk: {
        session: {
          get id() { return sessionId },
          getToken: async () => token,
        },
        user: { id: 'user-a' },
      },
    },
  })
}

function installFetch(): void {
  ;(globalThis as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const headers = new Headers(init.headers)
    calls.push({
      url,
      method: init.method ?? 'GET',
      authorization: headers.get('Authorization'),
    })
    const payload = url.endsWith('/access')
      ? { authenticated: true, authorized: true, environment: 'paper' }
      : url.endsWith('/account') ? { account: { equity: '100000' } }
        : url.endsWith('/positions') ? { positions: [] }
          : url.endsWith('/preview') ? {
              ok: true, problems: [], symbol: 'AAPL', qty: 1, side: 'buy',
              order_type: 'market', time_in_force: 'day',
              estimate: { last_price: 100, notional: 100, basis: 'test', source: null },
              buying_power: 100000,
              asset: { tradable: true, fractionable: true, exchange: 'NASDAQ' },
              environment: 'paper',
            }
            : init.method === 'DELETE' ? { cancelled: 'order-1' }
              : init.method === 'POST' ? { order: { id: 'order-1', symbol: 'AAPL' } }
                : { orders: [] }
    return { ok: true, status: 200, json: async () => payload }
  }
}

beforeEach(() => {
  sessionId = 'session-a'
  token = 'token-a'
  calls = []
  clearResourceCache()
  installClerk()
  installFetch()
})

test('authenticated reads retain single-flight and TTL behavior within one session', async () => {
  const answers = await Promise.all([
    readAuthResource('/api/paper/account', 'snapshot'),
    readAuthResource('/api/paper/account', 'snapshot'),
  ])
  assert.equal(calls.length, 1)
  assert.deepEqual(answers[0], answers[1])
  assert.equal(calls[0]?.authorization, 'Bearer token-a')
})

test('private cache entries cannot cross Clerk sessions', async () => {
  await readAuthResource('/api/paper/account', 'snapshot')
  sessionId = 'session-b'
  token = 'token-b'
  await readAuthResource('/api/paper/account', 'snapshot')

  assert.equal(calls.length, 2, 'the second Clerk session reused the first session cache')
  assert.deepEqual(calls.map((call) => call.authorization), ['Bearer token-a', 'Bearer token-b'])
})

test('all protected Paper reads and mutations carry the Clerk bearer token', async () => {
  const intent = {
    symbol: 'AAPL', qty: 1, side: 'buy' as const,
    order_type: 'market' as const, time_in_force: 'day' as const,
  }
  await fetchPaperAccess()
  await fetchPaperAccount()
  await fetchPaperPositions()
  await fetchPaperOrders()
  await previewOrder(intent)
  await placeOrder(intent)
  await cancelOrder('order-1')

  assert.deepEqual(
    calls.map((call) => [call.method, call.url]),
    [
      ['GET', '/api/paper/access'],
      ['GET', '/api/paper/account'],
      ['GET', '/api/paper/positions'],
      ['GET', '/api/paper/orders'],
      ['POST', '/api/paper/orders/preview'],
      ['POST', '/api/paper/orders'],
      ['DELETE', '/api/paper/orders/order-1'],
    ],
  )
  assert.ok(calls.every((call) => call.authorization === 'Bearer token-a'))
})

test('a mutation clears only the current private session cache', async () => {
  await fetchPaperAccount()
  await placeOrder({
    symbol: 'AAPL', qty: 1, side: 'buy', order_type: 'market', time_in_force: 'day',
  })
  await fetchPaperAccount()
  assert.equal(calls.filter((call) => call.url.endsWith('/account')).length, 2)

  clearAuthResourceCache()
})
