/* The violation-report endpoint is public, so it is small and it does not trust its input.

   Browsers post a report without credentials, which is why it cannot sit behind
   sign-in. That makes it an unauthenticated write to the logs, so: one method,
   a size cap, a content-type check, a fixed set of fields, query strings
   stripped (a URL can carry a token), and no echo of what was sent. */

import assert from 'node:assert/strict'
import test from 'node:test'

import { POST } from '../src/app/api/csp-report/route'

const post = (body: BodyInit, type = 'application/csp-report') =>
  POST(new Request('http://localhost/api/csp-report', { method: 'POST', body, headers: { 'content-type': type } }))

async function logged(run: () => Promise<Response>): Promise<{ response: Response; lines: string[] }> {
  const lines: string[] = []
  const original = console.warn
  console.warn = (...args: unknown[]) => { lines.push(args.map(String).join(' ')) }
  try { return { response: await run(), lines } } finally { console.warn = original }
}

test('a legacy report is accepted, summarised and stripped of query strings', async () => {
  const { response, lines } = await logged(() => post(JSON.stringify({
    'csp-report': {
      'document-uri': 'https://app.example/terminal?session=SECRETTOKEN',
      'blocked-uri': 'https://evil.example/x.js?key=abc',
      'violated-directive': 'script-src-elem',
      'original-policy': "default-src 'self'; script-src 'nonce-LONG'",
      'unexpected-field': 'ignored',
    },
  })))
  assert.equal(response.status, 204)
  assert.equal(lines.length, 1)
  assert.match(lines[0], /csp-violation/)
  assert.doesNotMatch(lines[0], /SECRETTOKEN|key=abc|LONG|unexpected/)
  assert.match(lines[0], /https:\/\/evil\.example\/x\.js/)
  assert.match(lines[0], /script-src-elem/)
})

test('the Reporting API shape, an array of reports, is read too, and capped', async () => {
  const one = { type: 'csp-violation', body: { blockedURL: 'https://a.example/p?q=1', effectiveDirective: 'img-src' } }
  const { response, lines } = await logged(() => post(JSON.stringify(Array(9).fill(one)), 'application/reports+json'))
  assert.equal(response.status, 204)
  assert.equal(lines.length, 5, 'a single post may not write an unbounded number of log lines')
  assert.doesNotMatch(lines[0], /q=1/)
})

test('the wrong content type, an oversized body and a non-JSON body are refused without logging', async () => {
  const cases: Array<[string, () => Promise<Response>]> = [
    ['415', () => post('{}', 'text/plain')],
    ['413', () => post('x'.repeat(9000), 'application/json')],
    ['400', () => post('not json', 'application/json')],
  ]
  for (const [status, run] of cases) {
    const { response, lines } = await logged(run)
    assert.equal(String(response.status), status)
    assert.deepEqual(lines, [])
  }
})

test('only POST is exported', async () => {
  const route = await import('../src/app/api/csp-report/route')
  assert.deepEqual(Object.keys(route).filter((k) => /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/.test(k)), ['POST'])
})
