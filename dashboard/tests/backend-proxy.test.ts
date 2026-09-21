import assert from 'node:assert/strict'
import test from 'node:test'

import { proxyBackend, resetBackendTokenForTests } from '../src/lib/backend-proxy'

test('public rollback mode proxies path/query and preserves application auth', async (t) => {
  const previousOrigin = process.env.BACKEND_ORIGIN
  const previousMode = process.env.BACKEND_AUTH_MODE
  const previousFetch = globalThis.fetch
  process.env.BACKEND_ORIGIN = 'https://rollback.example'
  process.env.BACKEND_AUTH_MODE = 'none'
  resetBackendTokenForTests()

  let target = ''
  let headers = new Headers()
  globalThis.fetch = (async (input, init) => {
    target = String(input)
    headers = new Headers(init?.headers)
    return new Response('{"ok":true}', {
      status: 200,
      headers: { 'Content-Type': 'application/json', Connection: 'keep-alive' },
    })
  }) as typeof fetch

  t.after(() => {
    globalThis.fetch = previousFetch
    if (previousOrigin === undefined) delete process.env.BACKEND_ORIGIN
    else process.env.BACKEND_ORIGIN = previousOrigin
    if (previousMode === undefined) delete process.env.BACKEND_AUTH_MODE
    else process.env.BACKEND_AUTH_MODE = previousMode
    resetBackendTokenForTests()
  })

  const response = await proxyBackend(new Request(
    'https://terminal.example/api/research/NVDA?mode=deep',
    { headers: {
      Authorization: 'Bearer clerk-session',
      'x-vercel-oidc-token': 'must-not-forward',
      'x-serverless-authorization': 'must-not-forward',
    } },
  ), ['research', 'NVDA'])

  assert.equal(target, 'https://rollback.example/api/research/NVDA?mode=deep')
  assert.equal(headers.get('Authorization'), 'Bearer clerk-session')
  assert.equal(headers.get('x-vercel-oidc-token'), null)
  assert.equal(headers.get('X-Serverless-Authorization'), null)
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('connection'), null)
})
