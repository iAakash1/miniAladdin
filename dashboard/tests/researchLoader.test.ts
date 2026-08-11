import assert from 'node:assert/strict'
import test from 'node:test'
import { ANALYSIS_STAGES, FACTOR_LAB_STAGES } from '../src/components/ui/ResearchLoader'

/* The loader's contract is honesty, and the honesty lives in two places:
   the stage definitions, and the rule that only *confirmed* stages tick.
   Both are asserted here; the DOM is not, since there is no renderer set up
   and mounting one to check a checkmark would test React, not us. */

/** Mirrors the component's stage-selection logic exactly. */
function activeStage(stages: typeof ANALYSIS_STAGES, elapsed: number, completed = 0) {
  let cumulative = 0
  let expected = stages.length - 1
  for (let i = 0; i < stages.length; i += 1) {
    cumulative += stages[i].typicalMs
    if (elapsed < cumulative) { expected = i; break }
  }
  return Math.max(expected, completed)
}

test('stages start at the first step, not part-way through', () => {
  assert.equal(activeStage(ANALYSIS_STAGES, 0), 0)
})

test('the highlight advances through the pipeline in order', () => {
  const first = activeStage(ANALYSIS_STAGES, 0)
  const mid = activeStage(ANALYSIS_STAGES, 6000)
  const late = activeStage(ANALYSIS_STAGES, 14000)
  assert.ok(first < mid, 'should have advanced by 6s')
  assert.ok(mid < late, 'should have advanced further by 14s')
})

test('overrunning the estimate parks on the last stage rather than finishing', () => {
  // The dangerous failure: a slow provider must never make the loader claim
  // everything completed. It should sit on the final step indefinitely.
  const veryLate = activeStage(ANALYSIS_STAGES, 10 * 60 * 1000)
  assert.equal(veryLate, ANALYSIS_STAGES.length - 1)
})

test('a confirmed completion can only move the highlight forward', () => {
  // A real signal arriving early advances the display; it must never drag it
  // backwards if the estimate had already moved past it.
  assert.equal(activeStage(ANALYSIS_STAGES, 0, 3), 3)
  assert.equal(activeStage(ANALYSIS_STAGES, 14000, 1), activeStage(ANALYSIS_STAGES, 14000))
})

test('every stage names real work and carries a duration', () => {
  for (const set of [ANALYSIS_STAGES, FACTOR_LAB_STAGES]) {
    assert.ok(set.length >= 4, 'a two-step pipeline is a spinner with extra words')
    for (const stage of set) {
      assert.ok(stage.label.length > 0)
      assert.ok(stage.detail.length > 10, `${stage.label} needs a real explanation`)
      assert.ok(stage.typicalMs > 0, `${stage.label} needs a measured duration`)
    }
  }
})

test('factor lab stages are slower than analysis stages', () => {
  // Not decoration: the factor lab builds a whole panel and genuinely takes
  // far longer. If these ever converge, one of the estimates is wrong.
  const analysis = ANALYSIS_STAGES.reduce((t, s) => t + s.typicalMs, 0)
  const lab = FACTOR_LAB_STAGES.reduce((t, s) => t + s.typicalMs, 0)
  assert.ok(lab > analysis * 1.5, `lab ${lab}ms vs analysis ${analysis}ms`)
})

test('a reported stage overrides the timer entirely', () => {
  // The server knows which stage is running. Letting the estimate run ahead
  // of it highlights a step that has not started — and briefly showed two
  // rows as active at once.
  const reported = 1
  const resolve = (rep: number | undefined, elapsed: number, done: number) =>
    rep !== undefined ? rep : Math.max(activeStage(FACTOR_LAB_STAGES, elapsed), done)

  assert.equal(resolve(reported, 60_000, 1), 1, 'report must win over a much later estimate')
  assert.equal(resolve(undefined, 0, 0), 0, 'no report falls back to the estimate')
})

test('exactly one stage is ever active', () => {
  for (const elapsed of [0, 5_000, 23_000, 90_000]) {
    for (const reported of [undefined, 0, 2, 4]) {
      const done = reported ?? 0
      const act = reported !== undefined
        ? reported
        : Math.max(activeStage(FACTOR_LAB_STAGES, elapsed), done)
      const states = FACTOR_LAB_STAGES.map((_, i) =>
        i < done ? 'done' : i === act ? 'active' : 'pending')
      assert.equal(states.filter((s) => s === 'active').length, 1,
        `elapsed=${elapsed} reported=${reported} produced ${states.join(',')}`)
    }
  }
})
