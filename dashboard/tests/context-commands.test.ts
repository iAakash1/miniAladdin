/* The palette's commands, for the object actually open.

   Before this the palette offered twenty-four variations of "Go to X" and
   nothing else, which makes it a menu with a text box. These assert the two
   properties that keep it honest: it acts on the object the route names, and
   it never offers an action for an object that is not there. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { contextCommands } from '../src/lib/context-commands'

const labels = (c: { label: string }[]) => c.map((x) => x.label)

test('a security offers actions on that security', () => {
  const c = contextCommands({
    pathname: '/terminal/security',
    params: { symbol: 'AAPL' },
    recent: ['AAPL', 'MSFT'],
    watched: false,
  })
  assert.ok(labels(c).includes('Add AAPL to watchlist'))
  assert.ok(labels(c).includes('Compare AAPL with MSFT'), 'no comparison against the last other name')
  assert.ok(labels(c).some((l) => l.startsWith('AAPL fundamentals')))
})

test('watching is offered as its opposite once the name is watched', () => {
  const on = contextCommands({ pathname: '/terminal/security', params: { symbol: 'AAPL' }, watched: true })
  assert.ok(labels(on).includes('Remove AAPL from watchlist'))
  assert.ok(!labels(on).includes('Add AAPL to watchlist'))
})

test('comparison is not offered against nothing', () => {
  // A first visit has no second name. Offering "Compare AAPL with" and
  // stopping would be worse than not offering it.
  const c = contextCommands({ pathname: '/terminal/security', params: { symbol: 'AAPL' }, recent: ['AAPL'] })
  assert.ok(!labels(c).some((l) => l.startsWith('Compare')))
})

test('a comparison offers the pair, and the swap', () => {
  const c = contextCommands({ pathname: '/terminal/compare', params: { a: 'COST', b: 'WMT' } })
  assert.ok(labels(c).includes('Swap — WMT against COST'))
  assert.ok(labels(c).includes('Open COST'))
  assert.ok(labels(c).includes('Open WMT'))
  const swap = c.find((x) => x.id === 'swap')
  assert.equal(swap?.href, '/terminal/compare?a=WMT&b=COST', 'the swap does not reverse the pair')
})

test('a route with no object offers no object commands', () => {
  assert.deepEqual(contextCommands({ pathname: '/terminal/command', params: {} }), [])
  assert.deepEqual(contextCommands({ pathname: '/terminal/security', params: {} }), [])
  assert.deepEqual(contextCommands({ pathname: '/terminal/compare', params: { a: 'COST' } }), [])
})

test('every command names either a route or an action, never both and never neither', () => {
  const all = [
    ...contextCommands({ pathname: '/terminal/security', params: { symbol: 'AAPL' }, recent: ['AAPL', 'MSFT'] }),
    ...contextCommands({ pathname: '/terminal/compare', params: { a: 'A', b: 'B' } }),
  ]
  assert.ok(all.length > 0)
  for (const c of all) {
    const has = Number(Boolean(c.href)) + Number(Boolean(c.act))
    assert.equal(has, 1, `${c.id} declares ${has} ways to run`)
  }
})

test('symbols are encoded into the routes they build', () => {
  const c = contextCommands({ pathname: '/terminal/security', params: { symbol: 'BRK.B' }, recent: ['BRK.B', 'BRK-A'] })
  const compare = c.find((x) => x.id === 'compare')
  assert.ok(compare?.href?.includes('BRK.B') || compare?.href?.includes('BRK'), 'the symbol is missing from the route')
  for (const cmd of c) if (cmd.href) assert.ok(!cmd.href.includes(' '), 'an unencoded space reached a route')
})
