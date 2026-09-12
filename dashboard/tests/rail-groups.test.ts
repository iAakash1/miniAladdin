/* Folding the navigation is the kind of feature that breaks navigation.

   The rules that keep it safe are not visual, so they are asserted here rather
   than trusted to a screenshot: a fold must never cost a reader the answer to
   "where am I", a fold must never be offered where the rail has no labels to
   fold, and a fold must never make a destination unreachable. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { groupOf } from '../src/lib/rail-groups'
import { ALL_DESTINATIONS, DESTINATIONS, GOTO } from '../src/lib/destinations'

test('every destination resolves to the group that contains it', () => {
  for (const section of DESTINATIONS) {
    for (const item of section.items) {
      assert.equal(
        groupOf(item.href), section.group,
        `${item.href} does not resolve to ${section.group}`,
      )
    }
  }
})

test('a sub-route resolves to its destination group', () => {
  // /terminal/security/AAPL is still Securities, and the rail must still show
  // the reader which group they are in when they are one level down.
  assert.equal(groupOf('/terminal/security/AAPL'), groupOf('/terminal/security'))
  assert.equal(groupOf('/terminal/experiments/EXP-007'), groupOf('/terminal/experiments'))
})

test('a route outside the registry belongs to no group', () => {
  // Not a crash and not a wrong highlight — no group is the honest answer.
  assert.equal(groupOf('/terminal/nowhere'), null)
  assert.equal(groupOf('/'), null)
})

test('folding cannot make a destination unreachable', () => {
  /* The chord map is derived from the registry, not from what the rail is
     rendering, so a folded group hides a link and never a destination. This
     asserts the property the fold depends on: every destination in every group
     has a chord, and every chord resolves to a real destination. */
  for (const d of ALL_DESTINATIONS) {
    assert.equal(GOTO[d.key], d.href, `chord g ${d.key} does not reach ${d.href}`)
  }
  assert.equal(
    Object.keys(GOTO).length, ALL_DESTINATIONS.length,
    'the chord map and the destination list are different sizes',
  )
})

test('a folded group still renders the entry the reader is on', () => {
  /* The filter the rail applies when a group is folded, asserted directly: on
     any route inside a group, folding that group leaves exactly the current
     entry — not zero entries, which would lose the reader, and not all of
     them, which would mean the fold did nothing. */
  const shownWhenFolded = (pathname: string, group: string) =>
    (DESTINATIONS.find((s) => s.group === group)?.items ?? []).filter(
      (i) => pathname === i.href || pathname.startsWith(`${i.href}/`),
    )

  for (const section of DESTINATIONS) {
    for (const item of section.items) {
      const shown = shownWhenFolded(item.href, section.group)
      assert.equal(shown.length, 1, `folding ${section.group} on ${item.href} shows ${shown.length} entries`)
      assert.equal(shown[0].href, item.href)
    }
    // And on a route outside the group, folding it shows nothing at all.
    assert.equal(shownWhenFolded('/terminal/nowhere', section.group).length, 0)
  }
})

test('the fold breakpoint matches the stylesheet that hides the labels', () => {
  /* Below 1025px the rail is a glyph column with no labels. If these two
     numbers disagree, one of two things happens: a fold control appears with
     no heading to sit in, or the rail keeps six headings it has no room for. */
  const hook = readFileSync(new URL('../src/lib/rail-groups.ts', import.meta.url).pathname, 'utf8')
  const css = readFileSync(new URL('../src/styles/system.css', import.meta.url).pathname, 'utf8')

  const inHook = hook.match(/\(min-width:\s*(\d+)px\)/)
  assert.ok(inHook, 'the hook declares no width at which folding is offered')

  // The media block that *contains* the rule, found by scanning back from it.
  // A forward regex here matched an earlier @media and read 900px off a block
  // three rules away, which is the kind of wrong answer a test can give with
  // complete confidence.
  const rule = css.indexOf('.wb-label, .wb-key, .wb-group-label { display: none')
  assert.notEqual(rule, -1, 'the stylesheet no longer hides the rail labels')
  const preceding = [...css.slice(0, rule).matchAll(/@media \(max-width: (\d+)px\)/g)]
  assert.ok(preceding.length, 'the label rule is not inside a max-width media query')
  const breakpoint = Number(preceding[preceding.length - 1][1])

  assert.equal(
    Number(inHook[1]), breakpoint + 1,
    `the hook folds above ${inHook[1]}px while the labels vanish at ${breakpoint}px`,
  )
})


test('the snapshot is memoised, which useSyncExternalStore requires', () => {
  /* A getSnapshot that parses JSON on every call returns a new array every
     time, React sees the store as perpetually changed, and the component
     re-renders forever. The symptom is a frozen tab, not a failing test, so
     the cache is asserted here at source.

     Checked by reading the module rather than by driving React: this test
     environment has no DOM, and the property — that a parsed value is stored
     and returned on the next call — is visible in the code. */
  const src = readFileSync(new URL('../src/lib/rail-groups.ts', import.meta.url).pathname, 'utf8')

  assert.match(src, /if \(cached !== null\) return cached/,
    'the snapshot does not return a cached value')
  assert.match(src, /cached = value/, 'the snapshot never populates the cache')
  assert.match(src, /cached = null/, 'nothing ever invalidates the cache')

  // A write must update the cache before notifying, or subscribers read the
  // value the write replaced.
  const writeBody = src.slice(src.indexOf('function write('), src.indexOf('/** The group a route'))
  const setsCache = writeBody.indexOf('cached = groups')
  const notifies = writeBody.indexOf('notify()')
  assert.ok(setsCache !== -1 && notifies !== -1, 'write does not both cache and notify')
  assert.ok(setsCache < notifies, 'write notifies before updating the cache')
})

test('the server snapshot folds nothing', () => {
  /* The server has no viewer and no preference. If it guessed, the first client
     paint would disagree with the markup and React would discard it — the rail
     visibly unfolding on every navigation, which is the bug this module avoids
     by not reading storage in an effect. */
  const src = readFileSync(new URL('../src/lib/rail-groups.ts', import.meta.url).pathname, 'utf8')
  assert.match(src, /function collapsedOnServer\(\): readonly string\[\] \{\s*return NONE/)
  assert.match(src, /function widthOnServer\(\): boolean \{\s*return true/)
})
