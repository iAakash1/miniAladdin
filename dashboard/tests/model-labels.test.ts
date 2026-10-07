/* The models screens never imply a production model.

   The registry holds none: production, candidates and validated are all zero,
   and EXP-007's verdict is NO PRODUCTION CANDIDATE. The one hosted model is
   the EXP-006 research artifact, promotion-blocked. Its panel was titled
   "Deployed model", which a reader skimming the heading takes to mean the
   model that serves signals. It is a research model. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const read = (...p: string[]) => readFileSync(join(__dirname, '..', 'src', ...p), 'utf8')

test('the hosted model is titled as a research model, with promotion shown as blocked', () => {
  const panel = read('components', 'terminal', 'models2', 'DeployedModel.tsx')
  assert.match(panel, /title="Research model"/)
  assert.doesNotMatch(panel, /title="Deployed model"/)
  assert.match(panel, /state="experimental"/)
  assert.match(panel, /badge=\{`PROMOTION \$\{model\?\.promotion_status \?\? 'BLOCKED'\}`\}/)
  assert.match(panel, /badgeTone="fail"/)
})

test('no screen claims a production, live or deployed model outright', () => {
  const claims = /\b(?:production|live|deployed) model\b/i
  const files = [
    ['components', 'terminal', 'models2', 'DeployedModel.tsx'],
    ['components', 'terminal', 'models2', 'ModelLab.tsx'],
    ['components', 'terminal', 'models', 'EvidenceChain.tsx'],
    ['components', 'terminal', 'models', 'ValidationLadder.tsx'],
  ]
  for (const f of files) {
    const text = read(...f).replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
    assert.doesNotMatch(text, claims, `${f.join('/')} claims a ${text.match(claims)?.[0]}`)
  }
})
