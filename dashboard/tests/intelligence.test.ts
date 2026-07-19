/* Intelligence OS core: ranking, grouping, registry composition. */
import { strict as assert } from 'node:assert'
import test from 'node:test'
import { fuzzyIncludes, groupByType, rankEntities, type Entity } from '../src/lib/intelligence/entities'
import { _resetForTests, queryIntelligence, registerProvider } from '../src/lib/intelligence/registry'

const company = (t: string, name: string): Entity => ({
  id: `company:${t}`, type: 'company', title: t, subtitle: name,
  route: `/company/${t}`, keywords: [t.toLowerCase(), ...name.toLowerCase().split(' ')],
})
const route = (id: string, title: string, keywords: string[]): Entity => ({
  id: `route:${id}`, type: 'route', title, route: `/${id}`, keywords,
})

test('exact ticker outranks everything', () => {
  const ranked = rankEntities('nvda', [company('NVDA', 'Nvidia Corp'), route('vault', 'Research Vault', ['nvda-adjacent'])])
  assert.equal(ranked[0].entity.id, 'company:NVDA')
})

test('empty query returns nothing (recents are the empty state)', () => {
  assert.equal(rankEntities('', [company('NVDA', 'Nvidia')]).length, 0)
})

test('keyword and fuzzy matches rank below prefix matches', () => {
  const entities = [
    route('validation', 'Validation', ['backtest']),
    route('vault', 'Vault', ['history']),
  ]
  const ranked = rankEntities('va', entities)
  assert.equal(ranked.length, 2)
  const backtest = rankEntities('backtest', entities)
  assert.equal(backtest[0].entity.id, 'route:validation')
})

test('recency boosts ties deterministically', () => {
  const a = company('AAPL', 'Apple')
  const b = company('AAPD', 'Apple Short ETF')
  const without = rankEntities('aap', [a, b])
  const withRecent = rankEntities('aap', [a, b], ['company:AAPD'])
  assert.equal(without[0].entity.id, 'company:AAPD') // alphabetical tiebreak
  assert.equal(withRecent[0].entity.id, 'company:AAPD')
  const recentOther = rankEntities('aap', [a, b], ['company:AAPL'])
  assert.equal(recentOther[0].entity.id, 'company:AAPL')
})

test('fuzzy subsequence', () => {
  assert.equal(fuzzyIncludes('research vault', 'rvl'), true)
  assert.equal(fuzzyIncludes('research vault', 'zzz'), false)
})

test('grouping follows type order and preserves rank inside groups', () => {
  const scored = rankEntities('a', [route('analyze', 'Analyze', []), company('AAPL', 'Apple')])
  const groups = groupByType(scored)
  assert.equal(groups[0].type, 'company')
  assert.equal(groups[1].type, 'route')
})

test('registry: sync tier answers immediately, async merges once, stale queries dropped', async () => {
  _resetForTests()
  registerProvider({ id: 's', tier: 'sync', entities: () => [route('analyze', 'Analyze', [])] })
  let release!: (v: Entity[]) => void
  registerProvider({
    id: 'a', tier: 'async',
    entities: () => new Promise<Entity[]>((resolve) => { release = resolve }),
  })
  const calls: Array<{ n: number; settled: boolean }> = []
  queryIntelligence('anal', [], ({ scored, settled }) => calls.push({ n: scored.length, settled }))
  assert.deepEqual(calls, [{ n: 1, settled: false }])
  release([company('ANET', 'Arista analog')])
  await new Promise((r) => setTimeout(r, 0))
  assert.equal(calls.length, 2)
  assert.equal(calls[1].settled, true)
  assert.equal(calls[1].n, 2)
})

/* ── search as reasoning: intent parser ── */
import { parseIntent } from '../src/lib/intelligence/reasoning'

test('compare intent: tickers extracted, stopwords ignored', () => {
  assert.deepEqual(parseIntent('compare NVDA and AMD'), { kind: 'compare', a: 'NVDA', b: 'AMD' })
  assert.deepEqual(parseIntent('nvda vs amd'), { kind: 'compare', a: 'NVDA', b: 'AMD' })
  assert.deepEqual(parseIntent('compare between MSFT and AAPL'), { kind: 'compare', a: 'MSFT', b: 'AAPL' })
})

test('changed intent: single ticker, various phrasings', () => {
  assert.deepEqual(parseIntent('what changed for NVDA'), { kind: 'changed', ticker: 'NVDA' })
  assert.deepEqual(parseIntent("what's changed since earnings TSLA"), { kind: 'changed', ticker: 'TSLA' })
  assert.deepEqual(parseIntent('AAPL what moved'), { kind: 'changed', ticker: 'AAPL' })
})

test('no intent: plain retrieval queries pass through', () => {
  assert.equal(parseIntent('nvidia'), null)
  assert.equal(parseIntent('NVDA'), null)
  assert.equal(parseIntent('compare apples to oranges'), null) // no tickers
  assert.equal(parseIntent(''), null)
})

test('answer entities rank first regardless of title text', () => {
  const answer: Entity = {
    id: 'answer:x', type: 'answer', title: 'Compare NVDA vs AMD',
    route: '/terminal/vault?compare=a,b', keywords: [],
  }
  const ranked = rankEntities('compare nvda and amd', [answer, company('NVDA', 'Nvidia')])
  assert.equal(ranked[0].entity.type, 'answer')
})
