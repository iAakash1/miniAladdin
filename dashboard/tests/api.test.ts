/* Tests for normalizeAi — the raw-snake_case → typed-camelCase mapping for
   the Groq/GPT-OSS-120B explanation block, including the full research-report
   fields (investment thesis, verdict rationale, per-family factor impacts). */

import assert from 'node:assert/strict'
import test from 'node:test'
import { normalizeAi } from '../src/lib/api'
import type { RawAiAnalysis } from '../src/lib/types'

function rawAi(overrides: Partial<RawAiAnalysis> = {}): RawAiAnalysis {
  return {
    recommendation: 'BUY',
    confidence: 72,
    risk: 'MEDIUM',
    executive_summary: 'Buy at 72% confidence on strong momentum.',
    investment_thesis: 'Momentum and quality both support the thesis at an elevated but manageable macro regime.',
    verdict_rationale: 'Momentum and quality outweigh a mildly elevated macro drag.',
    bull_case: 'Momentum and quality factors both point higher.',
    bear_case: 'Macro regime is elevated and could cap further gains.',
    momentum_impact: 'Momentum contributed +0.410, the single largest driver.',
    quality_impact: 'Quality contributed +0.190 on stable profitability.',
    value_impact: 'Value contributed +0.050 on a modest earnings yield.',
    pead_impact: 'Post-earnings drift contributed +0.020.',
    top_positive_narrative: 'Momentum and quality are the biggest positive drivers.',
    top_negative_narrative: 'The macro regime is the main drag.',
    key_catalysts: ['Momentum +0.41'],
    key_risks: ['Macro -0.08'],
    things_to_watch: ['SRM crossing back below 1.0'],
    conclusion: 'Buy reflects strong momentum and quality outweighing a mild macro drag.',
    factor_impacts: {
      momentum: { contribution: 0.41, factors: [{ name: 'r12_1', contribution: 0.41 }] },
      quality: { contribution: 0.19, factors: [{ name: 'gross_profitability', contribution: 0.19 }] },
      value: { contribution: 0.05, factors: [] },
      pead: { contribution: 0.02, factors: [] },
      news: { contribution: 0.06, factors: [] },
    },
    generated: true,
    model: 'openai/gpt-oss-120b',
    ...overrides,
  }
}

test('normalizeAi maps bull_case/bear_case/things_to_watch through to camelCase', () => {
  const result = normalizeAi(rawAi())
  assert.ok(result)
  assert.equal(result!.bullCase, 'Momentum and quality factors both point higher.')
  assert.equal(result!.bearCase, 'Macro regime is elevated and could cap further gains.')
  assert.deepEqual(result!.thingsToWatch, ['SRM crossing back below 1.0'])
})

test('normalizeAi defaults narrative fields when the backend omits them (fallback path)', () => {
  const result = normalizeAi(rawAi({
    bull_case: undefined, bear_case: undefined, things_to_watch: undefined,
    investment_thesis: undefined, verdict_rationale: undefined, conclusion: undefined,
    momentum_impact: undefined, quality_impact: undefined, value_impact: undefined, pead_impact: undefined,
  }))
  assert.ok(result)
  assert.equal(result!.bullCase, '')
  assert.equal(result!.bearCase, '')
  assert.deepEqual(result!.thingsToWatch, [])
  assert.equal(result!.investmentThesis, '')
  assert.equal(result!.verdictRationale, '')
  assert.equal(result!.conclusion, '')
  assert.equal(result!.momentumImpact, '')
})

test('normalizeAi maps factor_impacts subtotals through to camelCase, per bucket', () => {
  const result = normalizeAi(rawAi())
  assert.ok(result)
  assert.equal(result!.factorImpacts.momentum.contribution, 0.41)
  assert.deepEqual(result!.factorImpacts.momentum.factors, [{ name: 'r12_1', contribution: 0.41 }])
  assert.equal(result!.factorImpacts.quality.contribution, 0.19)
})

test('normalizeAi defaults factor_impacts to empty buckets when absent (fallback path)', () => {
  const result = normalizeAi(rawAi({ factor_impacts: undefined }))
  assert.ok(result)
  assert.equal(result!.factorImpacts.momentum.contribution, 0)
  assert.deepEqual(result!.factorImpacts.momentum.factors, [])
  assert.equal(result!.factorImpacts.news.contribution, 0)
})

test('normalizeAi returns null when there is no executive summary (fast mode / ai: null)', () => {
  assert.equal(normalizeAi(null), null)
  assert.equal(normalizeAi({ executive_summary: '' }), null)
})
