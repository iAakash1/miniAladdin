/* The loading UI's honesty rule, as a runnable property.

   ResearchLoader may never tell a user that a pipeline stage finished
   unless the backend said so. It may also not imply a stage has not started
   when the pipeline has visibly moved past it — the bug this covers showed
   "Fetching ✓ / Computing (untouched) / Fundamentals (running)" on the live
   company page, because everything between `completed` and `active` fell
   into the same `pending` bucket as stages that genuinely had not run. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { stageState } from '../src/components/ui/ResearchLoader'

const STAGES = 5

test('only stages the caller confirmed are ever marked done', () => {
  // The core honesty rule: exhaustively, `done` must imply `index < completed`,
  // no matter how far ahead the estimated `active` cursor has run.
  for (let completed = 0; completed <= STAGES; completed += 1) {
    for (let active = 0; active < STAGES; active += 1) {
      for (let index = 0; index < STAGES; index += 1) {
        if (stageState(index, completed, active) === 'done') {
          assert.ok(
            index < completed,
            `stage ${index} claimed done with completed=${completed}, active=${active}`,
          )
        }
      }
    }
  }
})

test('a stage the pipeline has passed never reads as not-yet-started', () => {
  for (let active = 1; active < STAGES; active += 1) {
    for (let index = 0; index < active; index += 1) {
      const state = stageState(index, 0, active)
      assert.notEqual(
        state,
        'pending',
        `stage ${index} read as pending while stage ${active} was active`,
      )
      assert.equal(state, 'passed')
    }
  }
})

test('never more than one stage is active, and none once all are confirmed', () => {
  // The caller guarantees `active >= completed` (it is either the reported
  // stage or `Math.max(estimate, completed)`), so that is the domain tested.
  for (let completed = 0; completed <= STAGES; completed += 1) {
    for (let active = completed; active < STAGES; active += 1) {
      const states = Array.from({ length: STAGES }, (_, i) => stageState(i, completed, active))
      const actives = states.filter((s) => s === 'active').length
      assert.ok(actives <= 1, `${actives} active stages at completed=${completed}, active=${active}`)
      // Nothing should still be pulsing once every stage is confirmed done —
      // a spinner next to a finished pipeline is its own small lie.
      assert.equal(
        actives,
        completed >= STAGES ? 0 : 1,
        `expected ${completed >= STAGES ? 'no' : 'one'} active stage at completed=${completed}, active=${active}`,
      )
    }
  }
})

test('states never go backwards as the pipeline advances', () => {
  // Reading down the list, a stage may only get less finished, never more.
  const rank: Record<string, number> = { done: 0, passed: 1, active: 2, pending: 3 }
  for (let completed = 0; completed <= STAGES; completed += 1) {
    for (let active = completed; active < STAGES; active += 1) {
      for (let index = 1; index < STAGES; index += 1) {
        const previous = rank[stageState(index - 1, completed, active)]
        const current = rank[stageState(index, completed, active)]
        assert.ok(
          current >= previous,
          `stage ${index} (${stageState(index, completed, active)}) is ahead of stage ${index - 1} ` +
          `(${stageState(index - 1, completed, active)}) at completed=${completed}, active=${active}`,
        )
      }
    }
  }
})

test('the reported-progress case marks everything before the running stage complete', () => {
  // When the backend reports both, e.g. Factor Lab: 2 stages done, 3rd running.
  assert.deepEqual(
    Array.from({ length: STAGES }, (_, i) => stageState(i, 2, 2)),
    ['done', 'done', 'active', 'pending', 'pending'],
  )
})
