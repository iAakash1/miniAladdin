/* The evidence chain.

   claim → observation → source → method → assumptions → failure conditions.

   The middle three were already in the inspector as "how it was produced".
   These pin the ends of the chain, which are the parts most products leave
   off — and the rule that there is exactly one inspector rather than a
   provenance panel per surface. */
import { strict as assert } from 'node:assert'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const CONTEXT = readFileSync(join(ROOT, 'components/system/MetricContext.tsx'), 'utf8')
const INSPECTOR = readFileSync(join(ROOT, 'components/system/MetricInspector.tsx'), 'utf8')
const FIN = readFileSync(join(ROOT, 'components/terminal/security/Financials.tsx'), 'utf8')
const PROFILE = readFileSync(join(ROOT, 'components/terminal/security/SecurityProfile.tsx'), 'utf8')

test('every stage of the chain exists on the reference', () => {
  for (const stage of ['claim?:', 'observation?:', 'assumptions?:', 'failsWhen?:',
    'source?:', 'method?:']) {
    assert.ok(CONTEXT.includes(stage), `MetricRef has no ${stage}`)
  }
})

test('the inspector renders claim and observation as distinct stages', () => {
  // They are different assertions. The claim is about a company; the
  // observation is about a record of one.
  assert.match(INSPECTOR, />Claim</)
  assert.match(INSPECTOR, />Observation</)
  assert.match(INSPECTOR, /current\.claim/)
  assert.match(INSPECTOR, /current\.observation/)
})

test('assumptions sit between method and failure', () => {
  const assumptions = INSPECTOR.indexOf('What had to be true')
  const failure = INSPECTOR.indexOf('What would make it wrong')
  assert.ok(assumptions > 0, 'assumptions are not rendered')
  assert.ok(failure > assumptions, 'failure conditions do not follow the assumptions')
})

test('a caller may supply failure conditions the handbook lacks', () => {
  // Most figures are not registered measures, and "no failure conditions are
  // recorded" is honest but useless when the caller knows what breaks it.
  assert.match(INSPECTOR, /current\.failsWhen/)
  // The handbook path must survive as the fallback.
  assert.match(INSPECTOR, /def\?\.fails_when/)
})

test('a filed fact states what it assumes and what would break it', () => {
  assert.match(FIN, /claim:/)
  assert.match(FIN, /observation:/)
  assert.match(FIN, /assumptions:/)
  assert.match(FIN, /failsWhen:/)
  // The two that actually matter for XBRL.
  assert.match(FIN, /restate/i, 'restatement is not named as a failure mode')
  assert.match(FIN, /coverage gap/i, 'sparse tagging is not named as a failure mode')
})

test('a merged profile field says the value is no single vendor’s number', () => {
  assert.match(PROFILE, /not any single vendor/i)
})

test('exactly one component renders the evidence chain', () => {
  /* Matching on filenames was wrong and this test caught it: `Inspector.tsx`
     is the *object* inspector — identity, neighbours, actions for a model or
     a dataset — which is a different thing from the *value* inspector. Two
     inspectors for two kinds of thing is correct.

     What must stay singular is the evidence chain itself. Two components
     rendering "what would make this wrong" is how a terminal ends up with two
     answers to one question, so this asserts on the behaviour rather than on
     the name. */
  const walk = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(join(dir, e.name))
        : e.name.endsWith('.tsx') ? [join(dir, e.name)] : [])

  const renderers = walk(join(ROOT, 'components')).filter((f) => {
    const src = readFileSync(f, 'utf8')
    return src.includes('What would make it wrong')
  })

  assert.equal(renderers.length, 1,
    `the evidence chain is rendered in ${renderers.length} places: ${renderers.join(', ')}`)
  assert.match(renderers[0], /MetricInspector\.tsx$/)
})
