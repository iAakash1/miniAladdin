/* Provider states as the providers page shows them.

   The distinctions are the point: configured is not proven healthy, a local
   limiter is not an upstream 429, a refused credential is not a plan
   boundary, and one endpoint outside the plan is not the vendor failing. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { classifyVendor, type VendorSnapshot } from '../src/lib/providerHealth'

const snap = (over: Partial<VendorSnapshot>): VendorSnapshot => ({
  vendor: 'v', configured: true, requests: 10, success_pct: 100, failures: 0, rate_limited: 0, ...over,
})

test('configured but never called is idle, not healthy', () => {
  assert.equal(classifyVendor(snap({ requests: 0, health_state: 'IDLE' })).state, 'IDLE')
})

test('no credential is not configured, never failing', () => {
  const h = classifyVendor(snap({ configured: false, health_state: 'NOT_CONFIGURED' }))
  assert.equal(h.state, 'NOT_CONFIGURED')
  assert.equal(h.tone, 'muted')
})

test('a local limiter is not described as the vendor throttling', () => {
  const local = classifyVendor(snap({ health_state: 'RATE_LIMITED', last_failure_class: 'local_limiter' }))
  const upstream = classifyVendor(snap({ health_state: 'RATE_LIMITED', last_failure_class: 'rate_limited' }))
  assert.match(local.note ?? '', /local rate limit/)
  assert.match(upstream.note ?? '', /vendor is throttling/)
})

test('a refused credential and a plan boundary are different states', () => {
  assert.equal(classifyVendor(snap({ health_state: 'AUTH_FAILURE' })).state, 'AUTH_FAILURE')
  assert.equal(classifyVendor(snap({ health_state: 'NOT_ENTITLED' })).state, 'NOT_ENTITLED')
})

test('one endpoint outside the plan names it instead of counting failures', () => {
  const h = classifyVendor(snap({ health_state: 'DEGRADED', failures: 3, restricted_operations: ['options'] }))
  assert.equal(h.state, 'DEGRADED')
  assert.match(h.note ?? '', /Plan excludes options/)
  const plain = classifyVendor(snap({ health_state: 'DEGRADED', failures: 3 }))
  assert.match(plain.note ?? '', /3 of 10 requests failed/)
})

/* The production NewsAPI key is refused with `apiKeyInvalid`. The backend pauses
   a vendor after rejecting its credential, so `cooling_down` is true for exactly
   these vendors — and the cooldown branch ran first, labelling a wrong key
   "Cooling down: paused after repeated failures". That reads as transient for a
   fault only the key's owner can fix. */
test('a refused credential is not described as a transient cooldown', () => {
  const h = classifyVendor(snap({
    health_state: 'AUTH_FAILURE', cooling_down: true, cooldown_remaining_seconds: 840,
    last_failure_class: 'auth_failure', failures: 1, success_pct: 0,
  }))
  assert.equal(h.state, 'AUTH_FAILURE')
  assert.equal(h.tone, 'neg')
  assert.equal(h.label, 'Credential rejected')
  assert.match(h.note ?? '', /rejected the credential/)
  assert.match(h.note ?? '', /14 min/)
})

test('an older backend that only reports the cooldown still shows the rejection', () => {
  const h = classifyVendor(snap({ cooling_down: true, last_failure_class: 'auth_failure' }))
  assert.equal(h.state, 'AUTH_FAILURE')
})

test('an ordinary cooldown after transient failures is still a cooldown', () => {
  const h = classifyVendor(snap({
    health_state: 'COOLDOWN', cooling_down: true, cooldown_remaining_seconds: 40, last_failure_class: 'upstream_failure',
  }))
  assert.equal(h.state, 'COOLDOWN')
  assert.equal(h.tone, 'warn')
})

test('a credential that was refused and later accepted is not shown as rejected', () => {
  assert.notEqual(classifyVendor(snap({ health_state: 'HEALTHY', last_failure_class: 'auth_failure' })).state, 'AUTH_FAILURE')
})
