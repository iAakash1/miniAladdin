/* Table structure is a semantic contract, not a styling concern.

   The Evidence registry rendered nine cells per row against eight header
   cells: the row-actions column had a cell and no header, so the browser lined
   every value up under the header to its left. A reader saw mean IC under
   IC T-STAT and the t-statistic under NET SHARPE. Every figure was plausible,
   every one was labelled as a different statistic, and typecheck, lint, 1,715
   tests and a clean production build all passed with it in place.

   The defect was possible because headers and cells were decided in two
   places. These assert that they are decided in one. */
import { strict as assert } from 'node:assert'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const TABLE = readFileSync(join(ROOT, 'components/system/DataTable.tsx'), 'utf8')

test('headers and cells iterate the same column array', () => {
  // Both loops must walk `visible`. A header loop over one array and a cell
  // loop over another is the shape the Evidence bug had.
  const headerLoop = /<thead>[\s\S]*?\{visible\.map\(/.test(TABLE)
  const cellLoop = /<tbody>[\s\S]*?\{visible\.map\(/.test(TABLE)
  assert.ok(headerLoop, 'the header row does not derive from the visible columns')
  assert.ok(cellLoop, 'the body cells do not derive from the visible columns')
})

test('the row-actions column emits a header exactly when it emits cells', () => {
  // Both are gated on the same condition. If one is conditional and the other
  // is not, the table is one column out for every row.
  const th = TABLE.match(/\{actions\?\.length \? \(\s*<th\b/)
  const td = TABLE.match(/\{actions\?\.length \? \(\s*<td\b/)
  assert.ok(th, 'the actions column emits no header cell')
  assert.ok(td, 'the actions column emits no body cell')
})

test('the actions header carries a name for a screen reader', () => {
  // It must exist for alignment and say nothing to the eye — but a column with
  // no accessible name is a column a screen reader cannot announce.
  assert.match(TABLE, /<th className="sys-actions-col"[\s\S]{0,160}sys-sr-only/,
    'the actions header has no screen-reader label')
})

test('hiding a column removes its header and its cells together', () => {
  // Optional columns are filtered once into `visible`, which both loops read.
  assert.match(TABLE, /const visible\s*=/, 'there is no single visible-column derivation')
  assert.doesNotMatch(
    TABLE,
    /<thead>[\s\S]*?columns\.map\(/,
    'the header iterates all columns while the body iterates the visible ones',
  )
})

test('sortable headers announce their sort state', () => {
  assert.match(TABLE, /aria-sort=/, 'a sortable column does not expose aria-sort')
})

test('every hand-built table in the product is accounted for', () => {
  /* DataTable is safe by construction. A hand-written <table> is not, and the
     only reliable check on one is the rendered DOM — which is why the browser
     sweep exists and why this test does not pretend to replace it.

     What it can do is hold the count still. A new hand-built table is a
     deliberate act, and this failing is the prompt to either route it through
     DataTable or add it to the browser sweep. */
  const walk = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? walk(join(dir, e.name))
        : e.name.endsWith('.tsx') ? [join(dir, e.name)] : [])

  const files = walk(join(ROOT, 'components'))
  const handBuilt = files.filter((f) => /className="sys-table/.test(readFileSync(f, 'utf8')))

  /* Raised from 36 to 38 deliberately: the watchlist and the recent-securities
     list are fixed-column price tables with no sorting or column controls, and
     routing them through DataTable would add machinery neither needs. Both were
     checked in the rendered DOM — six headers against six cells, three against
     three — before this number moved. */
  assert.equal(
    handBuilt.length, 38,
    `hand-built tables changed from 38 to ${handBuilt.length}. Route the new one ` +
    'through DataTable, or check its alignment in the rendered DOM and update ' +
    'this count deliberately.',
  )
})
