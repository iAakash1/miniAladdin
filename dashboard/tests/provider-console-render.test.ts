/* The providers console, rendered.

   The model tests (provider-registry.test.ts) check the numbers; these render
   the real components with each state the backend can report, so a state that
   is classified right but drawn wrong — a stale vendor wearing a healthy chip,
   a declined call dropped from the count, a credential value in the detail
   panel — fails here. */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { Catalogue, Coverage, Detail, Summary, groupByDomain, windowText } from '../src/components/terminal/providers/ProviderConsole'
import type { ProviderRecord, Registry } from '../src/lib/providerRegistry'

const NOW = Date.now() / 1000

function record(id: string, state: string, over: Partial<ProviderRecord> = {}, health: Partial<ProviderRecord['health']> = {}): ProviderRecord {
  const called = !['IDLE', 'NOT_CONFIGURED', 'DISABLED'].includes(state)
  return {
    id, display_name: `Vendor ${id}`, domain: 'market_data', source_kind: 'commercial', endpoint: `api.${id}.test (HTTPS JSON)`,
    catalogued: true, groups: ['market'], capabilities: ['quote'], instances: 1,
    configuration: {
      credential_env: `${id.toUpperCase()}_API_KEY`, keyless: false, configured: state !== 'NOT_CONFIGURED',
      disabled: state === 'DISABLED', credential_state: state === 'AUTH_FAILURE' ? 'rejected' : called ? 'accepted' : 'unverified',
      optional_env: [],
    },
    policy: { requests_per_minute: 30, timeout_seconds: 6, max_retries: 2, cooldown_after_failures: 3, cooldown_seconds: 60 },
    health: {
      state, requests: called ? 5 : 0, failures: 0, success_pct: called ? 100 : null,
      avg_latency_ms: called ? 240 : null, max_latency_ms: called ? 600 : null, held_back_locally: 0,
      last_success_at: called ? NOW - 600 : null, last_failure_at: null, last_attempt_at: called ? NOW - 600 : null,
      last_failure_class: null, last_error: null, cooling_down: state === 'COOLDOWN', cooldown_remaining_seconds: 0,
      restricted_operations: [], window: { ok: called ? 5 : 0, failed: 0, declined: 0 }, ...health,
    },
    recent: [], terms: null, advisories: [], ...over,
  }
}

const capLabel = (k: string) => ({ quote: 'Real-time quote', filings: 'SEC filings' } as Record<string, string>)[k] ?? k

function registry(providers: ProviderRecord[]): Registry {
  return {
    generated_at: NOW, process_started_at: NOW - 3600, health_window_seconds: 21_600, adapter_version: 'abc1234', disabled: [],
    providers,
    capabilities: [
      { key: 'quote', label: 'Real-time quote', description: 'Latest price', reconciliation: 'median', fanout_limit: 3, implemented_by: providers.map((p) => p.id), eligible: providers.filter((p) => p.configuration.configured && !p.configuration.disabled).map((p) => p.id) },
      { key: 'filings', label: 'SEC filings', description: 'Filings index', reconciliation: 'primary', fanout_limit: null, implemented_by: ['sec'], eligible: [] },
    ],
  }
}

const table = (list: ProviderRecord[]) =>
  renderToStaticMarkup(createElement(Catalogue, { list, capLabel, onOpen: () => {}, openId: null }))

const rowOf = (html: string, id: string) => {
  const start = html.indexOf(`>${id}</span>`)
  assert.ok(start >= 0, `row for ${id} not rendered`)
  return html.slice(start, html.indexOf('</tr>', start))
}

const STATES: Array<[string, Partial<ProviderRecord['health']>, string]> = [
  ['HEALTHY', {}, 'Healthy'],
  ['IDLE', {}, 'Idle'],
  ['STALE', { window: { ok: 0, failed: 0, declined: 0 }, last_success_at: NOW - 9 * 3600 }, 'Stale'],
  ['NOT_CONFIGURED', {}, 'Not configured'],
  ['DISABLED', {}, 'Disabled'],
  ['AUTH_FAILURE', { last_failure_class: 'auth_failure', window: { ok: 0, failed: 1, declined: 0 } }, 'Credential rejected'],
  ['RATE_LIMITED', { last_failure_class: 'rate_limited', window: { ok: 2, failed: 1, declined: 0 } }, 'Rate limited'],
  ['DEGRADED', { failures: 1, window: { ok: 4, failed: 1, declined: 0 } }, 'Degraded'],
  ['UNAVAILABLE', { last_failure_class: 'parse_failure', window: { ok: 0, failed: 2, declined: 0 } }, 'Unavailable'],
  ['TIMEOUT', { last_failure_class: 'timeout' }, 'Timing out'],
  ['COOLDOWN', {}, 'Cooling down'],
  ['NOT_ENTITLED', { last_failure_class: 'not_entitled' }, 'Not entitled'],
]

test('every backend state renders with its own label, and only a healthy vendor reads healthy', () => {
  const list = STATES.map(([state, health]) => record(state.toLowerCase(), state, {}, health))
  const html = table(list)
  for (const [state, , label] of STATES) {
    assert.match(rowOf(html, state.toLowerCase()), new RegExp(`>${label}<`), `${state} → ${label}`)
  }
  assert.equal(html.match(/>Healthy</g)?.length, 1)
})

test('a vendor never called shows "never" and "not measured", not a zero latency', () => {
  const row = rowOf(table([record('quiet', 'IDLE')]), 'quiet')
  assert.match(row, />never</)
  assert.match(row, />not measured</)
  assert.doesNotMatch(row, /0 ms/)
})

test('declined calls are counted in the table, apart from failures', () => {
  assert.equal(windowText({ ok: 3, failed: 1, declined: 2 }), '3 ok · 1 failed · 2 declined')
  assert.equal(windowText({ ok: 0, failed: 0, declined: 1 }), '0 ok · 0 failed · 1 declined', 'declined alone is still shown')
  assert.equal(windowText({ ok: 0, failed: 0 }), '—')
  const row = rowOf(table([record('mixed', 'HEALTHY', {}, { window: { ok: 3, failed: 0, declined: 2 } })]), 'mixed')
  assert.match(row, /3 ok · 0 failed · 2 declined/)
})

test('providers are grouped by domain in catalog order, uncatalogued last', () => {
  const groups = groupByDomain([
    record('n', 'IDLE', { domain: 'news' }),
    record('x', 'IDLE', { domain: null, catalogued: false }),
    record('f', 'IDLE', { domain: 'filings' }),
    record('m', 'IDLE', { domain: 'market_data' }),
  ]).map((g) => g.domain)
  assert.deepEqual(groups, ['market_data', 'filings', 'news', null])
  const html = table([record('n', 'HEALTHY', { domain: 'news' }), record('m', 'IDLE', { domain: 'market_data' })])
  assert.ok(html.indexOf('Market data') < html.indexOf('News'))
  assert.match(html, /1 provider · 1 answered recently/)
  assert.match(html, /scope="rowgroup"/)
})

test('the summary names capabilities nothing can answer', () => {
  const html = renderToStaticMarkup(createElement(Summary, { reg: registry([record('a', 'HEALTHY'), record('b', 'NOT_CONFIGURED')]) }))
  assert.match(html, /1 capability has no eligible source:<\/strong> SEC filings/)
  assert.match(html, /Answered recently<\/dt><dd class="sys-num">1</)
  assert.match(html, /Configured<\/dt><dd class="sys-num">1</, 'a key that is not set is not counted as configured')
})

test('the detail panel names the credential variable, never a value, and explains each call', () => {
  const p = record('sec', 'DEGRADED', {
    capabilities: ['filings'],
    configuration: {
      credential_env: null, keyless: true, configured: true, disabled: false, credential_state: 'not_required',
      optional_env: [{ name: 'SEC_USER_AGENT', set: false }, { name: 'SEC_API', set: true }],
    },
    instances: 0,
    advisories: [{ kind: 'configuration', text: 'SEC_USER_AGENT is not set.' }],
    terms: { terms_status: 'reviewed', terms_url: 'https://www.sec.gov/x', notes: 'Ten requests a second.', attribution: null, terms_checked_on: '2026-10-24' },
    recent: [
      { at: NOW - 30, operation: 'get_filings', outcome: 'ok', latency_ms: 210, status_code: 200, attempt: 0, scope: 'vendor', request_id: 'rid-1234abcd' },
      { at: NOW - 60, operation: 'get_filings', outcome: 'empty', latency_ms: 90, status_code: 404, attempt: 0, scope: 'request', request_id: null },
      { at: NOW - 90, operation: 'get_xbrl_facts', outcome: 'upstream_failure', latency_ms: 6000, status_code: 503, attempt: 1, scope: 'vendor', request_id: null },
    ],
  }, { failures: 1, last_failure_class: 'upstream_failure', last_error: 'HTTP 503', window: { ok: 1, failed: 1, declined: 1 } })
  const html = renderToStaticMarkup(createElement(Detail, { p, reg: registry([p]), capLabel, onClose: () => {} }))
  assert.match(html, /role="dialog"/)
  assert.match(html, /SEC_USER_AGENT<\/code><\/dt><dd>not set/)
  assert.match(html, /SEC_API<\/code><\/dt><dd>set</)
  assert.match(html, /SEC_USER_AGENT is not set\./)
  assert.match(html, /Not loaded in this process yet/)
  assert.match(html, /answered: nothing matches/)
  assert.match(html, /about this input/)
  assert.match(html, /vendor error/)
  assert.match(html, /retry 1/)
  assert.match(html, /rid-1234abcd/)
  assert.match(html, /1 declined/)
  assert.match(html, /HTTP 503/, 'a degraded vendor shows its last error')
  assert.match(html, /rel="noopener noreferrer"/)
  assert.match(html, /Terms reviewed \(2026-10-24\)/)
  assert.doesNotMatch(html, /<input/, 'there is no credential form')
})

test('a healthy vendor does not show a stale error, and an unconfigured one says how to configure it', () => {
  const healthy = record('ok', 'HEALTHY', {}, { last_error: 'old error from yesterday' })
  const ok = renderToStaticMarkup(createElement(Detail, { p: healthy, reg: registry([healthy]), capLabel, onClose: () => {} }))
  assert.doesNotMatch(ok, /old error from yesterday/)
  const off = record('off', 'NOT_CONFIGURED')
  const html = renderToStaticMarkup(createElement(Detail, { p: off, reg: registry([off]), capLabel, onClose: () => {} }))
  assert.match(html, /set <code>OFF_API_KEY<\/code> on the backend service/)
  assert.match(html, /never called/)
})

test('coverage shows "none" for a capability with no eligible source', () => {
  const html = renderToStaticMarkup(createElement(Coverage, { reg: registry([record('a', 'HEALTHY')]), capLabel }))
  assert.match(html, /SEC filings[\s\S]*?<span class="pv-none">none<\/span>/)
})
