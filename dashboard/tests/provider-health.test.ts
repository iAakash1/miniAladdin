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
