/* Tests for the pure verdict-history diff logic (Phase 3). */

import assert from 'node:assert/strict'
import test from 'node:test'
import { diffSnapshots, type AnalysisSnapshot } from '../src/lib/history'

function snap(overrides: Partial<AnalysisSnapshot>): AnalysisSnapshot {
  return {
    ts: '2026-07-01T00:00:00Z',
    verdict: 'Hold',
    rawVerdict: 'Hold',
    confidence: 70,
    riskLevel: 'MEDIUM',
    rawScore: 0.1,
    momentumScore: 0.2,
    fundamentalScore: 0.0,
    newsScore: null,
    macroGate: 1.0,
    srm: 1.0,
    regimes: [],
    factors: [
      { name: 'r21', family: 'momentum', contribution: 0.08 },
      { name: 'rsi_dev', family: 'momentum', contribution: 0.02 },
    ],
    price: 100,
    ...overrides,
  }
}

test('downgrade detected with factor-level drivers, sorted by |delta|', () => {
  const before = snap({ verdict: 'Buy', rawScore: 0.2 })
  const after = snap({
    ts: '2026-07-03T00:00:00Z',
    verdict: 'Sell',
    confidence: 55,
    rawScore: -0.18,
    factors: [
      { name: 'r21', family: 'momentum', contribution: -0.12 }, // big swing
      { name: 'rsi_dev', family: 'momentum', contribution: 0.01 },
      { name: 'sentiment', family: 'news', contribution: -0.05 }, // new factor
    ],
  })

  const diff = diffSnapshots(before, after)

  assert.equal(diff.verdictChanged, true)
  assert.equal(diff.direction, 'downgrade')
  assert.equal(diff.confidenceDelta, -15)
  assert.equal(diff.scoreDelta, -0.38)
  assert.equal(diff.topDrivers[0].name, 'r21') // largest |delta| first
  assert.equal(diff.topDrivers[0].delta, -0.2)
  const sentimentDriver = diff.topDrivers.find((d) => d.name === 'sentiment')
  assert.ok(sentimentDriver && sentimentDriver.before === 0 && sentimentDriver.after === -0.05)
})

test('upgrade direction and regime transitions', () => {
  const before = snap({ verdict: 'Hold', regimes: ['high_volatility'] })
  const after = snap({ verdict: 'Buy', regimes: ['earnings_window'] })

  const diff = diffSnapshots(before, after)

  assert.equal(diff.direction, 'upgrade')
  assert.deepEqual(diff.regimesEntered, ['earnings_window'])
  assert.deepEqual(diff.regimesExited, ['high_volatility'])
})

test('unchanged verdict yields no false drivers', () => {
  const before = snap({})
  const after = snap({ ts: '2026-07-02T00:00:00Z' })

  const diff = diffSnapshots(before, after)

  assert.equal(diff.verdictChanged, false)
  assert.equal(diff.direction, 'unchanged')
  assert.equal(diff.topDrivers.length, 0)
  assert.equal(diff.gateDelta, 0)
})

test('null scores handled without NaN', () => {
  const before = snap({ rawScore: null, macroGate: null })
  const after = snap({ rawScore: null, macroGate: null })
  const diff = diffSnapshots(before, after)
  assert.equal(diff.scoreDelta, null)
  assert.equal(diff.gateDelta, null)
})
