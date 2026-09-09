import { strict as assert } from 'node:assert'
import test from 'node:test'
import { normalizeMacro } from '../src/lib/api'

test('macro observation dates survive both API shapes without becoming fetch dates', () => {
  const facts = { source: 'fred', fetched_at: '2026-09-09T00:00:00Z', observation_dates: { inflation_rate: '2026-07-01' }, status: 'STABLE' }
  for (const raw of [{ risk_multiplier: 1, stats: facts }, { risk_multiplier: 1, ...facts }]) {
    const value = normalizeMacro(raw)
    assert.equal(value.observationDates?.inflation_rate, '2026-07-01')
    assert.equal(value.observationDates?.fed_funds_rate, undefined)
    assert.equal(value.source, 'fred')
  }
})

test('stale macro absence is retained for display', () => {
  const value = normalizeMacro({ risk_multiplier: null, stats: { stale: true, status: 'UNAVAILABLE' } } as never)
  assert.equal(value.stale, true)
  assert.equal(value.srm, null)
  assert.equal(value.status, 'UNAVAILABLE')
})
