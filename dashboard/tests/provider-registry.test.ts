/* The providers console's model of /api/providers/registry.

   Every count on the page comes from these functions, so they are where a
   wrong claim would start: a configured vendor counted as answering, a failed
   read shown as an empty registry, a filter that hides a failing vendor, a
   secret that reaches the page. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { classifyVendor } from '../src/lib/providerHealth'
import {
  NO_FILTERS, ago, classify, filterProviders, filtersActive, healthFingerprint, outcomeLabel,
  parseRegistry, providerFactText, summarizeRegistry, type ProviderRecord, type Registry,
} from '../src/lib/providerRegistry'

function provider(id: string, over: Partial<ProviderRecord> = {}, health: Partial<ProviderRecord['health']> = {}): ProviderRecord {
  return {
    id, display_name: id.toUpperCase(), domain: 'market_data', source_kind: 'commercial', endpoint: `api.${id}.test`,
    catalogued: true, groups: ['market'], capabilities: ['quote'], instances: 1,
    configuration: { credential_env: `${id.toUpperCase()}_KEY`, keyless: false, configured: true, disabled: false, credential_state: 'accepted', optional_env: [] },
    policy: { requests_per_minute: 30, timeout_seconds: 6, max_retries: 2, cooldown_after_failures: 3, cooldown_seconds: 60 },
    health: {
      state: 'HEALTHY', requests: 4, failures: 0, success_pct: 100, avg_latency_ms: 120, max_latency_ms: 300,
      held_back_locally: 0, last_success_at: 1_700_000_000, last_failure_at: null, last_attempt_at: 1_700_000_000,
      last_failure_class: null, last_error: null, cooling_down: false, cooldown_remaining_seconds: 0,
      restricted_operations: [], window: { ok: 4, failed: 0 }, ...health,
    },
    recent: [], terms: null, advisories: [], ...over,
  }
}

function registry(providers: ProviderRecord[]): Registry {
  return {
    generated_at: 1_700_000_100, process_started_at: 1_699_990_000, health_window_seconds: 21_600,
    adapter_version: 'abc123', disabled: [], providers,
    capabilities: [
      { key: 'quote', label: 'Real-time quote', description: '', reconciliation: 'median', fanout_limit: 3, implemented_by: providers.map((p) => p.id), eligible: providers.filter((p) => p.configuration.configured).map((p) => p.id) },
      { key: 'filings', label: 'SEC filings', description: '', reconciliation: 'primary', fanout_limit: null, implemented_by: ['sec'], eligible: [] },
    ],
  }
}

test('a reply that is not a registry is unreadable, never an empty registry', () => {
  assert.equal(parseRegistry(null), null)
  assert.equal(parseRegistry({ providers: [] }), null, 'missing capabilities and window')
  assert.equal(parseRegistry('<html>proxy error</html>'), null)
  const ok = parseRegistry(registry([provider('a')]))
  assert.ok(ok && ok.providers.length === 1)
})

test('a malformed provider record is dropped, not rendered half-empty', () => {
  const raw = { ...registry([provider('a')]), providers: [provider('a'), { id: 'b' }, null] }
  assert.deepEqual(parseRegistry(raw)?.providers.map((p) => p.id), ['a'])
})

test('the record is classified by the same rules as every other vendor state', () => {
  const p = provider('a', {}, { state: 'AUTH_FAILURE', last_failure_class: 'auth_failure' })
  assert.deepEqual(classify(p), classifyVendor({ vendor: 'a', configured: true, health_state: 'AUTH_FAILURE', requests: 4, success_pct: 100, failures: 0, rate_limited: 0, last_failure_class: 'auth_failure' }))
})

test('stale and disabled are their own states, neither healthy nor failing', () => {
  const stale = classify(provider('a', {}, { state: 'STALE' }))
  assert.equal(stale.state, 'STALE')
  assert.notEqual(stale.tone, 'pos')
  assert.notEqual(stale.tone, 'neg')
  const off = classify(provider('b', { configuration: { ...provider('b').configuration, disabled: true } }, { state: 'DISABLED' }))
  assert.equal(off.state, 'DISABLED')
  assert.match(off.note ?? '', /PROVIDER_DISABLED/)
})

test('configured is counted apart from answering, and uncovered capabilities are named', () => {
  const reg = registry([
    provider('live'),
    provider('quiet', {}, { state: 'IDLE', requests: 0, window: { ok: 0, failed: 0 }, last_success_at: null }),
    provider('broken', {}, { state: 'UNAVAILABLE', window: { ok: 0, failed: 3 } }),
    provider('nokey', { configuration: { ...provider('n').configuration, configured: false, credential_state: 'not_configured' } }, { state: 'NOT_CONFIGURED', requests: 0, window: { ok: 0, failed: 0 } }),
  ])
  const s = summarizeRegistry(reg)
  assert.equal(s.registered, 4)
  assert.equal(s.configured, 3)
  assert.equal(s.answeringNow, 1, 'only an answer in the window counts')
  assert.equal(s.failing, 1)
  assert.equal(s.staleOrIdle, 1)
  assert.equal(s.notConfigured, 1)
  assert.deepEqual(s.uncovered.map((c) => c.key), ['filings'])
})

test('filters combine, search the name, id, host and capability, and can be cleared', () => {
  const list = [
    provider('sec', { domain: 'filings', capabilities: ['filings'] }),
    provider('fred', { domain: 'macro', capabilities: ['macro_context'] }, { state: 'UNAVAILABLE', window: { ok: 0, failed: 2 } }),
    provider('polygon'),
  ]
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, query: 'macro_con' }).map((p) => p.id), ['fred'])
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, query: 'api.polygon' }).map((p) => p.id), ['polygon'])
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, state: 'failing' }).map((p) => p.id), ['fred'])
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, state: 'no_recent_success' }).map((p) => p.id), ['fred'])
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, domain: 'filings', capability: 'filings' }).map((p) => p.id), ['sec'])
  assert.deepEqual(filterProviders(list, { ...NO_FILTERS, domain: 'filings', state: 'failing' }), [])
  assert.equal(filtersActive(NO_FILTERS), false)
  assert.equal(filtersActive({ ...NO_FILTERS, query: ' x ' }), true)
})

test('a refresh can tell "unchanged" from "updated"', () => {
  const a = registry([provider('a')])
  const same = { ...a, generated_at: a.generated_at + 30 }
  const moved = registry([provider('a', {}, { requests: 5 })])
  assert.equal(healthFingerprint(a), healthFingerprint(same), 'a later read of the same state is unchanged')
  assert.notEqual(healthFingerprint(a), healthFingerprint(moved))
})

test('recent-call outcomes are worded for a reader, and an empty answer is not a failure', () => {
  assert.equal(outcomeLabel('empty'), 'answered: nothing matches')
  assert.equal(outcomeLabel('auth_failure'), 'credential rejected')
  assert.equal(ago(null), null)
  assert.equal(ago(1000, 1000 + 7200), '2h ago')
})

test('the console reads the registry endpoint, and never a credential value', () => {
  const source = readFileSync(join(__dirname, '..', 'src', 'components', 'terminal', 'providers', 'ProviderConsole.tsx'), 'utf8')
  assert.match(source, /fetch\('\/api\/providers\/registry'/)
  assert.doesNotMatch(source, /process\.env/, 'the page reads no environment, public or not')
  assert.doesNotMatch(source, /VENDOR_LABEL|const \w+ = \{\s*polygon:/, 'vendor names come from the backend catalog')
  assert.doesNotMatch(source, /<input[^>]*(api[_-]?key|secret|token)/i, 'there is no credential form')
})

test('a record without its window counters, or a capability without its lists, is dropped rather than crashing the page', () => {
  const broken = provider('b')
  const noWindow = { ...broken, health: { ...broken.health, window: undefined } }
  const raw = {
    ...registry([provider('a')]),
    providers: [provider('a'), noWindow],
    capabilities: [...registry([provider('a')]).capabilities, { key: 'x', label: 'X' }],
  }
  const parsed = parseRegistry(raw)
  assert.deepEqual(parsed?.providers.map((p) => p.id), ['a'])
  assert.ok(parsed && !parsed.capabilities.some((c) => c.key === 'x'))
  assert.doesNotThrow(() => summarizeRegistry(parsed!))
})

test('the status bar counts every registered adapter, the same population as the providers page', () => {
  // The footer once summed vendors per capability family (27) while the page
  // counted registered adapters (30): adapters outside every family vanished.
  const reg = registry([
    provider('a'),
    provider('b', { groups: [], capabilities: [] }),
    provider('c', { configuration: { ...provider('c').configuration, disabled: true } }, { state: 'DISABLED' }),
    provider('d', { configuration: { ...provider('d').configuration, configured: false, credential_state: 'not_configured' } }, { state: 'NOT_CONFIGURED', requests: 0, window: { ok: 0, failed: 0 } }),
  ])
  const s = summarizeRegistry(reg)
  assert.equal(s.registered, reg.providers.length)
  assert.equal(providerFactText(s), `${s.configured} of ${s.registered} configured`)
  assert.equal(providerFactText(s), '2 of 4 configured', 'disabled and unconfigured adapters are not configured')
})

test('the status bar reads the providers page\'s endpoint and summary, not a second implementation', () => {
  const src = readFileSync(join(__dirname, '../src/components/shell/StatusBar.tsx'), 'utf8')
  assert.match(src, /'\/api\/providers\/registry'/)
  assert.match(src, /summarizeRegistry\(/)
  assert.doesNotMatch(src, /\/api\/providers\/health/)
  const page = readFileSync(join(__dirname, '../src/components/terminal/providers/ProviderConsole.tsx'), 'utf8')
  assert.match(page, /summarizeRegistry\(/)
})

test('failing and constrained adapters are named in the status line', () => {
  const s = summarizeRegistry(registry([
    provider('a', {}, { state: 'UNAVAILABLE', window: { ok: 0, failed: 3 } }),
    provider('b', {}, { state: 'RATE_LIMITED' }),
    provider('c'),
  ]))
  assert.equal(providerFactText(s), '3 of 3 configured · 1 failing · 1 constrained')
})
