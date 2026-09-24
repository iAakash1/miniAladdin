/* The palette's commands, for the object actually open.

   These assert the properties that keep it honest: it acts on the object the
   route names, and it never offers an action for an object that is not there. */
import { strict as assert } from 'node:assert'
import test from 'node:test'

import { companyFromPath, companyHref, contextCommands } from '../src/lib/context-commands'

const labels = (c: { label: string }[]) => c.map((x) => x.label)

test('a company workspace offers actions on that company', () => {
  const c = contextCommands({
    pathname: '/company/AAPL',
    params: {},
    recent: ['AAPL', 'MSFT'],
    watched: false,
  })
  assert.ok(labels(c).includes('Add AAPL to watchlist'))
  assert.ok(labels(c).includes('Compare AAPL with MSFT'), 'no comparison against the last other name')
  assert.ok(labels(c).some((l) => l.startsWith('AAPL evidence')))
  assert.equal(c.find((x) => x.id === 'evidence')?.href, '/company/AAPL?tab=evidence')
})

test('watching is offered as its opposite once the name is watched', () => {
  const on = contextCommands({ pathname: '/company/AAPL', params: {}, watched: true })
  assert.ok(labels(on).includes('Remove AAPL from watchlists'))
  assert.ok(!labels(on).includes('Add AAPL to watchlist'))
})

test('comparison is not offered against nothing', () => {
  const c = contextCommands({ pathname: '/company/AAPL', params: {}, recent: ['AAPL'] })
  assert.ok(!labels(c).some((l) => l.startsWith('Compare')))
})

test('a comparison offers the pair, and the swap', () => {
  const c = contextCommands({ pathname: '/terminal/compare', params: { a: 'COST', b: 'WMT' } })
  assert.ok(labels(c).includes('Swap — WMT against COST'))
  assert.equal(c.find((x) => x.id === 'open-a')?.href, '/company/COST')
  assert.equal(c.find((x) => x.id === 'swap')?.href, '/terminal/compare?a=WMT&b=COST')
})

test('a route with no object offers no object commands', () => {
  assert.deepEqual(contextCommands({ pathname: '/terminal/command', params: {} }), [])
  assert.deepEqual(contextCommands({ pathname: '/terminal/compare', params: { a: 'COST' } }), [])
})

test('every command names either a route or an action, never both and never neither', () => {
  const all = [
    ...contextCommands({ pathname: '/company/AAPL', params: {}, recent: ['AAPL', 'MSFT'] }),
    ...contextCommands({ pathname: '/terminal/compare', params: { a: 'A', b: 'B' } }),
  ]
  assert.ok(all.length > 0)
  for (const c of all) {
    const has = Number(Boolean(c.href)) + Number(Boolean(c.act))
    assert.equal(has, 1, `${c.id} declares ${has} ways to run`)
  }
})

test('symbols are encoded into the routes they build', () => {
  const c = contextCommands({ pathname: '/company/BRK.B', params: {}, recent: ['BRK.B', 'BRK A'] })
  for (const cmd of c) if (cmd.href) assert.ok(!cmd.href.includes(' '), 'an unencoded space reached a route')
  assert.equal(companyHref('BRK A'), '/company/BRK%20A')
})

test('the paper command is labelled as paper and opens the company ticket', () => {
  const paper = contextCommands({ pathname: '/company/AAPL', params: {} }).find((x) => x.id === 'paper')
  assert.ok(paper, 'no paper command on a company')
  assert.match(paper?.label ?? '', /paper/i)
  assert.match(paper?.note ?? '', /no real money/i)
  assert.equal(paper?.href, '/company/AAPL?paper=1')
})

test('company routes resolve to their symbol', () => {
  assert.equal(companyFromPath('/company/aapl'), 'AAPL')
  assert.equal(companyFromPath('/company/BRK.B'), 'BRK.B')
  assert.equal(companyFromPath('/terminal/command'), null)
})
