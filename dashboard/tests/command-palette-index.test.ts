/* The command palette renders results in groups but selects them with one
   flat index into `shown`. If the two disagree the surface breaks quietly:
   the highlight and the thing Enter opens are different rows.

   That is exactly what happened. The index carried a trailing `+ 1`, so
   option ids ran 1..N while `active` ran 0..N-1:

     - `aria-activedescendant="palette-0"` pointed at no element at all
     - nothing was highlighted when the palette opened
     - one ArrowDown highlighted row 1 while Enter opened row 2
     - the last result could never be reached

   These assert the invariant that makes the listbox coherent: the indices
   this produces must be exactly 0..N-1 in render order. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { optionIndex } from '../src/components/terminal/CommandPalette'

const groupsOf = (...sizes: number[]) =>
  sizes.map((n) => ({ items: Array.from({ length: n }, (_, i) => i) }))

/** Every index the component would render, in the order it renders them. */
function walk(groups: Array<{ items: unknown[] }>): number[] {
  const seen: number[] = []
  groups.forEach((group, groupIndex) => {
    group.items.forEach((_, itemIndex) => {
      seen.push(optionIndex(groups, groupIndex, itemIndex))
    })
  })
  return seen
}

test('indices are zero-based and contiguous across every grouping', () => {
  for (const sizes of [[1], [3], [1, 1], [2, 3, 1], [5, 1, 4, 2], [1, 1, 1, 1, 1]]) {
    const groups = groupsOf(...sizes)
    const total = sizes.reduce((a, b) => a + b, 0)
    assert.deepEqual(
      walk(groups),
      Array.from({ length: total }, (_, i) => i),
      `grouping ${sizes.join('/')} did not produce 0..${total - 1}`,
    )
  }
})

test('the first option is index 0, so aria-activedescendant resolves on open', () => {
  // `active` starts at 0 and the input renders `palette-${active}`.
  assert.equal(optionIndex(groupsOf(4, 2), 0, 0), 0)
})

test('the last option is reachable by the arrow-key clamp', () => {
  // ArrowDown clamps at `shown.length - 1`; the final rendered index must
  // equal that, or the last result can never be highlighted.
  const sizes = [3, 4, 2]
  const groups = groupsOf(...sizes)
  const total = sizes.reduce((a, b) => a + b, 0)
  const indices = walk(groups)
  assert.equal(indices[indices.length - 1], total - 1)
})

test('indices never collide — two rows cannot share a highlight', () => {
  const indices = walk(groupsOf(2, 2, 2, 2))
  assert.equal(new Set(indices).size, indices.length)
})

test('an empty group does not shift the ones after it off by one', () => {
  assert.deepEqual(walk(groupsOf(2, 0, 3)), [0, 1, 2, 3, 4])
})
