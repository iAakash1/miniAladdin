/* The factor lab must show what failed as easily as what worked.

   The old lab enforced this with a filter whose predicates were exact
   complements, so "significant" and "inconclusive" could not drift apart and
   "all" was the default. That component is gone; the property is not.

   The rebuilt workbench enforces it more strongly by not filtering at all.
   Every evaluated factor is in the table, significance is a first-class
   sortable column rather than a hidden predicate, and the reader narrows with
   the same generic control they use everywhere else.

   These assertions read the source, because the property is structural: it is
   about what the workspace refuses to hide, and that cannot be observed by
   calling a function that no longer exists. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const SOURCE = readFileSync(
  new URL('../src/components/terminal/factors2/FactorWorkbench.tsx', import.meta.url),
  'utf8',
)

test('significance is a column, not a filter', () => {
  // A sortable column shows both answers at once. A filter defaulting to one
  // of them is how a research tool becomes a marketing page.
  assert.match(SOURCE, /key:\s*'sig'/, 'the significance column is missing')
  assert.match(SOURCE, /sort:\s*\(f\)\s*=>\s*\(f\.significant/, 'significance is not sortable')
})

test('a factor that failed renders its own state, not an absence', () => {
  // Both branches render a Status. Rendering nothing for "not significant"
  // would make a failed factor look like an unmeasured one.
  assert.match(
    SOURCE,
    /f\.significant\s*\?\s*'candidate'\s*:\s*'blocked'/,
    'significance must map to a research state on both branches',
  )
  assert.match(SOURCE, /label=\{f\.significant\s*\?\s*'yes'\s*:\s*'no'\}/)
})

test('the table is handed every factor, unfiltered', () => {
  // The rows prop must be the full list. A predicate applied before the table
  // hides rows the reader never learns exist.
  assert.match(SOURCE, /rows=\{factors\}/, 'the factor table must receive the full population')
})

test('the counts state the population as well as the survivors', () => {
  // "12 significant" alone is a different claim from "12 of 40 significant".
  assert.match(SOURCE, /factors\.filter\(\(f\)\s*=>\s*f\.significant\)\.length/)
  assert.match(SOURCE, /label:\s*'Evaluated'|label:\s*'Factors'/)
})
