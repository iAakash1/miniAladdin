/* Tests for normalizeAi — the raw-snake_case → typed-camelCase mapping for
   the Groq/GPT-OSS-120B explanation block (Explainability Phase 3 addition:
   bull_case / bear_case / things_to_watch). */

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
    bull_case: 'Momentum and quality factors both point higher.',
    bear_case: 'Macro regime is elevated and could cap further gains.',
    key_catalysts: ['Momentum +0.41'],
    key_risks: ['Macro -0.08'],
    things_to_watch: ['SRM crossing back below 1.0'],
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

test('normalizeAi defaults the new v3 fields when the backend omits them (fallback path)', () => {
  const result = normalizeAi(rawAi({ bull_case: undefined, bear_case: undefined, things_to_watch: undefined }))
  assert.ok(result)
  assert.equal(result!.bullCase, '')
  assert.equal(result!.bearCase, '')
  assert.deepEqual(result!.thingsToWatch, [])
})

test('normalizeAi returns null when there is no executive summary (fast mode / ai: null)', () => {
  assert.equal(normalizeAi(null), null)
  assert.equal(normalizeAi({ executive_summary: '' }), null)
})
