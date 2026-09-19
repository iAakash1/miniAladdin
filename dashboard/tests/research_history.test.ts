import assert from 'node:assert/strict'
import { test } from 'node:test'

import { runStateLabel } from '../src/components/terminal/experiments/ResearchHistory'

test('a study that has not been run is never labelled complete', () => {
  assert.equal(runStateLabel('COMPLETE'), 'complete')
  assert.match(runStateLabel('PREPARED_NOT_RUN'), /not run/)
  assert.match(runStateLabel('PREREGISTERED_NOT_RUN'), /not run/)
})
