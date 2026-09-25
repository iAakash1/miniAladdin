import assert from 'node:assert/strict'
import test, { type TestContext } from 'node:test'

import {
  proxyBackend,
  resetBackendTokenForTests,
  setBackendIdTokenForTests,
} from '../src/lib/backend-proxy'

type FetchHandler = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

function arrange(t: TestContext, handler: FetchHandler, mode = 'none'): void {
  const previousOrigin = process.env.BACKEND_ORIGIN
  const previousMode = process.env.BACKEND_AUTH_MODE
  const previousFetch = globalThis.fetch
  process.env.BACKEND_ORIGIN = 'https://backend.example'
  process.env.BACKEND_AUTH_MODE = mode
  resetBackendTokenForTests()
  globalThis.fetch = handler as typeof fetch
  t.after(() => {
    globalThis.fetch = previousFetch
    if (previousOrigin === undefined) delete process.env.BACKEND_ORIGIN
    else process.env.BACKEND_ORIGIN = previousOrigin
    if (previousMode === undefined) delete process.env.BACKEND_AUTH_MODE
    else process.env.BACKEND_AUTH_MODE = previousMode
    resetBackendTokenForTests()
  })
}

function request(headers?: HeadersInit): Request {
  return new Request('https://terminal.example/api/research/NVDA?mode=deep', { headers })
}

test('rollback mode preserves path, query, Clerk auth, JSON body and safe headers', async (t) => {
  let target = ''
  let outbound = new Headers()
  arrange(t, async (input, init) => {
    target = String(input)
    outbound = new Headers(init?.headers)
    return new Response('{"ok":true}', {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-Id': 'request-1',
        Connection: 'keep-alive, x-internal-hop',
        'X-Internal-Hop': 'remove-me',
      },
    })
  })

  const response = await proxyBackend(request({
    Authorization: 'Bearer clerk-session',
    'x-vercel-oidc-token': 'must-not-forward',
    'x-serverless-authorization': 'must-not-forward',
  }), ['research', 'NVDA'])

  assert.equal(target, 'https://backend.example/api/research/NVDA?mode=deep')
  assert.equal(outbound.get('Authorization'), 'Bearer clerk-session')
  assert.equal(outbound.get('x-vercel-oidc-token'), null)
  assert.equal(outbound.get('X-Serverless-Authorization'), null)
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('content-type'), 'application/json')
  assert.equal(response.headers.get('x-request-id'), 'request-1')
  assert.equal(response.headers.get('connection'), null)
  assert.equal(response.headers.get('x-internal-hop'), null)
  assert.deepEqual(await response.json(), { ok: true })
})

test('4xx and 5xx JSON bodies survive with their exact status', async (t) => {
  let status = 422
  arrange(t, async () => Response.json({ error: `status-${status}` }, { status }))

  const clientError = await proxyBackend(request(), ['research', 'NVDA'])
  assert.equal(clientError.status, 422)
  assert.deepEqual(await clientError.json(), { error: 'status-422' })

  status = 503
  const serverError = await proxyBackend(request(), ['research', 'NVDA'])
  assert.equal(serverError.status, 503)
  assert.deepEqual(await serverError.json(), { error: 'status-503' })
})

test('empty no-body statuses are reconstructed without an invalid body', async (t) => {
  arrange(t, async () => new Response(null, { status: 204, headers: { 'Content-Length': '0' } }))
  const response = await proxyBackend(request(), ['health'])
  assert.equal(response.status, 204)
  assert.equal(response.headers.get('content-length'), null)
  assert.equal(await response.text(), '')
})

test('large but bounded JSON is preserved byte-for-byte', async (t) => {
  const value = { rows: Array.from({ length: 20_000 }, (_, index) => ({ index, label: `row-${index}` })) }
  const encoded = JSON.stringify(value)
  arrange(t, async () => new Response(encoded, { headers: { 'Content-Type': 'application/json' } }))
  const response = await proxyBackend(request(), ['quant', 'model-lab'])
  assert.equal((await response.text()).length, encoded.length)
})

test('responses above the explicit proxy bound are rejected', async (t) => {
  const oversized = 'x'.repeat(8 * 1024 * 1024 + 1)
  arrange(t, async () => new Response(oversized, { headers: { 'Content-Type': 'text/plain' } }))
  await assert.rejects(proxyBackend(request(), ['oversized']), /exceeded the proxy size limit/)
})

test('decoded Render-style bodies drop stale compression and length metadata', async (t) => {
  arrange(t, async () => new Response('{"source":"render"}', {
    headers: {
      'Content-Type': 'application/json',
      'Content-Encoding': 'br',
      'Content-Length': '999',
      'Transfer-Encoding': 'chunked',
    },
  }))
  const response = await proxyBackend(request(), ['macro'])
  assert.deepEqual(await response.json(), { source: 'render' })
  assert.equal(response.headers.get('content-encoding'), null)
  assert.equal(response.headers.get('content-length'), null)
  assert.equal(response.headers.get('transfer-encoding'), null)
})

test('private Cloud Run mode uses infrastructure auth without replacing Clerk auth', async (t) => {
  let outbound = new Headers()
  arrange(t, async (_input, init) => {
    outbound = new Headers(init?.headers)
    return Response.json({ source: 'cloud-run' }, {
      headers: {
        Authorization: 'must-not-reach-browser',
        'X-Serverless-Authorization': 'must-not-reach-browser',
      },
    })
  }, 'google_oidc')
  setBackendIdTokenForTests('google-id-token')

  const response = await proxyBackend(request({
    Authorization: 'Bearer clerk-session',
    'X-Serverless-Authorization': 'attacker-value',
  }), ['health'])
  assert.equal(outbound.get('Authorization'), 'Bearer clerk-session')
  assert.equal(outbound.get('X-Serverless-Authorization'), 'Bearer google-id-token')
  assert.equal(response.headers.get('authorization'), null)
  assert.equal(response.headers.get('x-serverless-authorization'), null)
  assert.deepEqual(await response.json(), { source: 'cloud-run' })
})

test('malformed or non-JSON upstream content passes through without reinterpretation', async (t) => {
  arrange(t, async () => new Response('<upstream failure', {
    status: 502, headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  }))
  const response = await proxyBackend(request(), ['research', 'NVDA'])
  assert.equal(response.status, 502)
  assert.match(response.headers.get('content-type') || '', /^text\/plain/)
  assert.equal(await response.text(), '<upstream failure')
})

test('timeout and backend network failures reject for the route boundary to map to 503', async (t) => {
  let sawSignal = false
  arrange(t, async (_input, init) => {
    sawSignal = init?.signal instanceof AbortSignal
    throw new DOMException('timed out', 'TimeoutError')
  })
  await assert.rejects(proxyBackend(request(), ['health']), { name: 'TimeoutError' })
  assert.equal(sawSignal, true)

  globalThis.fetch = (async () => { throw new TypeError('backend unavailable') }) as typeof fetch
  await assert.rejects(proxyBackend(request(), ['health']), /backend unavailable/)
})

test('missing backend configuration fails without attempting a request', async (t) => {
  arrange(t, async () => { throw new Error('fetch must not run') })
  delete process.env.BACKEND_ORIGIN
  await assert.rejects(proxyBackend(request(), ['health']), /Missing server configuration: BACKEND_ORIGIN/)
})

test('the route boundary maps missing configuration to a sanitized 503', async (t) => {
  arrange(t, async () => { throw new Error('fetch must not run') })
  delete process.env.BACKEND_ORIGIN
  const previousError = console.error
  console.error = () => undefined
  t.after(() => { console.error = previousError })
  const { GET } = await import('../src/app/api/[...path]/route')
  const response = await GET(request(), { params: Promise.resolve({ path: ['health'] }) })
  assert.equal(response.status, 503)
  assert.deepEqual(await response.json(), {
    status: 'unavailable', error: 'Backend proxy is not configured.',
  })
})

test('a Cloud Run capacity refusal is retried until an instance answers', async (t) => {
  // Cloud Run writes this 429 itself: no instance took the request, so it
  // never reached the application and carries no X-Request-Id.
  const bodies: string[] = []
  let calls = 0
  arrange(t, async (_input, init) => {
    calls += 1
    bodies.push(new TextDecoder().decode(init?.body as ArrayBuffer))
    if (calls < 3) return new Response('Rate exceeded.', { status: 429 })
    return Response.json({ ok: true }, { headers: { 'X-Request-Id': 'served' } })
  })

  const response = await proxyBackend(new Request('https://terminal.example/api/research/NVDA/narrative', {
    method: 'POST',
    body: '{"snapshot_id":"abc","depth":"beginner"}',
  }), ['research', 'NVDA', 'narrative'])

  assert.equal(calls, 3)
  assert.equal(response.status, 200)
  assert.deepEqual(await response.json(), { ok: true })
  assert.deepEqual(bodies, Array(3).fill('{"snapshot_id":"abc","depth":"beginner"}'))
})

test('a 429 the application wrote is returned, not repeated', async (t) => {
  let calls = 0
  arrange(t, async () => {
    calls += 1
    return Response.json({ detail: 'slow down' }, { status: 429, headers: { 'X-Request-Id': 'app' } })
  })

  const response = await proxyBackend(request(), ['research', 'NVDA'])
  assert.equal(calls, 1)
  assert.equal(response.status, 429)
  assert.deepEqual(await response.json(), { detail: 'slow down' })
})
