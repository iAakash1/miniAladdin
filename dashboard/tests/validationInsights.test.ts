/* Tests for the pure Validation-page derivations: overallHealth (the
   "can I trust this model" headline) and failureModes (deterministic
   threshold flags). Every threshold mirrors metricGlossary.ts. */

import assert from 'node:assert/strict'
import test from 'node:test'
import { failureModes, overallHealth } from '../src/lib/validationInsights'

test('overallHealth reports Insufficient data below 20 samples', () => {
  const result = overallHealth({ ic: 0.1, hitRate: 60, sharpe: 1.2, samples: 10 })
  assert.equal(result.label, 'Insufficient data')
})

test('overallHealth reports Positive when IC, hit rate and Sharpe all clear their bars', () => {
  const result = overallHealth({ ic: 0.08, hitRate: 58, sharpe: 1.3, samples: 100 })
  assert.equal(result.label, 'Positive')
  assert.equal(result.tone, 'pos')
})

test('overallHealth reports Weak when IC is negative and Sharpe is negative', () => {
  const result = overallHealth({ ic: -0.05, hitRate: 45, sharpe: -0.3, samples: 100 })
  assert.equal(result.label, 'Weak')
  assert.equal(result.tone, 'neg')
})

test('overallHealth reports Mixed for a middling but not alarming read', () => {
  const result = overallHealth({ ic: 0.02, hitRate: 52, sharpe: 0.4, samples: 100 })
  assert.equal(result.label, 'Mixed')
})

test('failureModes flags PSI above 0.25 as distribution drift', () => {
  const flags = failureModes({
    psi: 0.31,
    factorDiagnostics: {},
    confusionMatrix: { long: { up: 5, down: 2 }, flat: { up: 1, down: 1 }, short: { up: 1, down: 5 } },
    scoreDistribution: [{ bin: '-0.1', count: 40 }, { bin: '+0.1', count: 40 }],
  })
  assert.ok(flags.some((f) => f.includes('Distribution drift')))
})

test('failureModes flags a score distribution stuck in the extreme tails, using real +/-.1f bin labels', () => {
  const flags = failureModes({
    psi: 0.02,
    factorDiagnostics: {},
    confusionMatrix: { long: { up: 0, down: 0 }, flat: { up: 0, down: 0 }, short: { up: 0, down: 0 } },
    scoreDistribution: [
      { bin: '-0.6', count: 30 }, { bin: '-0.5', count: 20 },
      { bin: '+0.0', count: 2 }, { bin: '+0.1', count: 1 },
      { bin: '+0.5', count: 20 }, { bin: '+0.6', count: 30 },
    ],
  })
  assert.ok(flags.some((f) => f.includes('extreme tails')))
})

test('failureModes does not flag tails when most mass sits within +/-0.2 of zero, using real bin labels', () => {
  const flags = failureModes({
    psi: 0.02,
    factorDiagnostics: {},
    confusionMatrix: { long: { up: 0, down: 0 }, flat: { up: 0, down: 0 }, short: { up: 0, down: 0 } },
    scoreDistribution: [
      { bin: '-0.6', count: 2 }, { bin: '-0.1', count: 20 },
      { bin: '+0.0', count: 30 }, { bin: '+0.1', count: 20 }, { bin: '+0.6', count: 2 },
    ],
  })
  assert.ok(!flags.some((f) => f.includes('extreme tails')))
})

test('failureModes flags factors with sign stability below 0.5 (min 12 samples)', () => {
  const flags = failureModes({
    psi: 0.05,
    factorDiagnostics: {
      r12_1: { ic: 0.1, sign_stability: 0.8, samples: 30 },
      pead: { ic: 0.02, sign_stability: 0.3, samples: 20 },
      tiny_sample: { ic: 0.5, sign_stability: 0.1, samples: 5 }, // below sample floor, ignored
    },
    confusionMatrix: { long: { up: 3, down: 1 }, flat: { up: 0, down: 0 }, short: { up: 1, down: 3 } },
    scoreDistribution: [{ bin: '0', count: 50 }],
  })
  assert.equal(flags.length, 1)
  assert.ok(flags[0].includes('pead'))
  assert.ok(!flags[0].includes('tiny_sample'))
})

test('failureModes flags long calls that realize down more often than up', () => {
  const flags = failureModes({
    psi: null,
    factorDiagnostics: {},
    confusionMatrix: { long: { up: 2, down: 8 }, flat: { up: 0, down: 0 }, short: { up: 0, down: 0 } },
    scoreDistribution: [{ bin: '0', count: 50 }],
  })
  assert.ok(flags.some((f) => f.includes('Long calls')))
})

test('failureModes returns no flags for a clean bill of health', () => {
  const flags = failureModes({
    psi: 0.02,
    factorDiagnostics: { r12_1: { ic: 0.1, sign_stability: 0.8, samples: 40 } },
    confusionMatrix: { long: { up: 8, down: 2 }, flat: { up: 1, down: 1 }, short: { up: 2, down: 8 } },
    scoreDistribution: [{ bin: '-0.15', count: 20 }, { bin: '0', count: 40 }, { bin: '0.15', count: 20 }],
  })
  assert.deepEqual(flags, [])
})
