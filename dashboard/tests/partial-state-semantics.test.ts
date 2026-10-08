/* The screen keeps the backend's distinction between "nothing there" and
   "could not look".

   The backend now says, for the knowledge graph, the market snapshot and the
   news fan-out, whether a source answered with nothing or could not be asked.
   Each of those used to collapse in the interface: an unreachable ecosystem
   source rendered no panel at all, a failed graph request said "no connections
   recorded", a market snapshot of nothing drew a row of dashes beside an "as
   of" time, and a news outage said "no stories". These tests hold the line at
   the interface, where the collapse happened. */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { normalizeAnalysis } from '../src/lib/api'
import { sectionState, shortfall, type DashboardCoverage } from '../src/lib/dashboardInsights'
import { unavailableSources } from '../src/lib/knowledge'
import type { RawResearchResponse } from '../src/lib/types'

const SRC = join(__dirname, '..', 'src')
const read = (...p: string[]) => readFileSync(join(SRC, ...p), 'utf8')

// ── knowledge ────────────────────────────────────────────────────────────────

test('only a source that could not be asked is reported as down, in the reader\'s words', () => {
  assert.deepEqual(unavailableSources({ sources: { sec: 'ok', wikidata: 'unavailable', research: 'empty', openfigi: 'unavailable' } }),
    ['Wikidata', 'OpenFIGI'])
  assert.deepEqual(unavailableSources({ sources: { sec: 'empty', wikidata: 'empty' } }), [], 'a source with nothing to say is not down')
  assert.deepEqual(unavailableSources({}), [])
})

test('the ecosystem panel says so for a failed request and for an unavailable answer, not nothing', () => {
  const view = read('components', 'terminal', 'CompanyEcosystem.tsx')
  assert.match(view, /if \(!data \|\| data\.status === 'unavailable'\) \{\s*return \(/, 'a failed or unavailable lookup renders no explanation')
  assert.match(view, /did not answer, so nothing is shown for \{ticker\}/)
  assert.match(view, /This is not a finding that it has none/)
  assert.match(view, /state="warning" label="partial"/, 'a partial ecosystem is not flagged')
})

test('an ecosystem every source answered empty is still silent', () => {
  // The panel is optional: a complete answer with nothing in it is a finding
  // ("no relationships") shown by absence, which is the original design.
  const view = read('components', 'terminal', 'CompanyEcosystem.tsx')
  const afterNotice = view.slice(view.indexOf('const down = unavailableSources(data)'))
  assert.match(afterNotice, /data\.ecosystem\.length === 0[\s\S]*?return null/)
})

test('the graph explorer separates an unreadable graph from one with no connections', () => {
  const view = read('components', 'terminal', 'GraphExplorer.tsx')
  assert.match(view, /const unreadable = !loading && \(slice === null \|\| slice\.status === 'unavailable'\)/)
  const order = [view.indexOf(') : unreadable ? ('), view.indexOf(') : edges.length === 0 ? (')]
  assert.ok(order[0] > 0 && order[1] > order[0], 'the unreadable branch must come before the empty one')
  assert.match(view, /The graph could not be read/)
  assert.match(view, /setAttempt\(\(n\) => n \+ 1\)/, 'there is no way to try again')
  assert.doesNotMatch(view.slice(view.indexOf('unreadable ? ('), view.indexOf('edges.length === 0 ? (')), /No connections recorded/)
})

test('the graph workspace treats a failed request as failed, and names a company it could not look up', () => {
  const view = read('components', 'terminal', 'GraphWorkspace.tsx')
  assert.match(view, /if \(!res\.ok\) throw new Error/)
  assert.match(view, /failed \|\| data\?\.status === 'unavailable'/)
  assert.match(view, /could not be looked up, so the graph below leaves/)
  assert.doesNotMatch(view, /\.then\(\(res\) => \(res\.ok \? res\.json\(\) : null\)\)/, 'a failed response is still read as an empty graph')
})

// ── dashboard ────────────────────────────────────────────────────────────────

const coverage = (sectors: number, cards: number): Pick<{ coverage: DashboardCoverage }, 'coverage'> => ({
  coverage: {
    macro_cards: { available: cards, expected: 19 },
    sectors: { available: sectors, expected: 11 },
    indexes: { available: 5, expected: 5 },
    regime: true,
  },
})

test('a section claims "live" only when everything asked for arrived', () => {
  assert.equal(sectionState(coverage(11, 19), 'sectors'), 'live')
  assert.equal(sectionState(coverage(7, 19), 'sectors'), 'warning')
  assert.equal(sectionState(coverage(0, 19), 'sectors'), 'unavailable')
  assert.equal(sectionState(coverage(11, 11), 'macro_cards'), 'warning')
  assert.equal(sectionState({ coverage: undefined }, 'sectors'), 'live', 'an older backend reported whole sections')
})

test('a shortfall is stated as a count, and only when there is one', () => {
  assert.equal(shortfall(coverage(7, 19), 'sectors'), '7 of 11')
  assert.equal(shortfall(coverage(11, 19), 'sectors'), null)
  assert.equal(shortfall(coverage(0, 19), 'sectors'), null, 'nothing arrived: that is unavailable, not a shortfall')
})

test('the market workspace no longer hard-codes "live" on panels built from partial data', () => {
  const view = read('components', 'terminal', 'market', 'MarketWorkspace.tsx')
  for (const title of ['Breadth', 'Leadership', 'Macro']) {
    const panel = new RegExp(`<Panel[^>]*?title="${title}"[\\s\\S]*?>`).exec(view)?.[0] ?? ''
    assert.doesNotMatch(panel, /state="live"/, `${title} still claims "live" unconditionally`)
    assert.match(panel, /state=\{sectionState\(data, /)
  }
  assert.match(view, /data\.status === 'unavailable' \? 'unavailable' : data\.status === 'partial' \? 'warning' : 'live'/)
})

test('the home band treats an empty snapshot as unreadable, and says what was not reported', () => {
  const band = read('components', 'terminal', 'home', 'MarketBand.tsx')
  assert.match(band, /d\?\.status === 'unavailable' \? 'the market feeds did not answer'/)
  assert.match(band, /\$\{d\.status === 'partial' \? ' · partial' : ''\}/)
  assert.match(band, /not reported\)/)
})

// ── news ─────────────────────────────────────────────────────────────────────

const analysis = (sentiment: RawResearchResponse['sentiment']) => normalizeAnalysis({ ticker: 'AAPL', sentiment } as RawResearchResponse)

test('three reasons for an empty news list stay three', () => {
  assert.equal(analysis(null).newsStatus, 'not_requested', 'quick mode never asked for news')
  assert.equal(analysis({ headline_count: 0, status: 'no_headlines' }).newsStatus, 'no_headlines')
  assert.equal(analysis({ headline_count: 0, status: 'unavailable', sources_failed: ['gnews'] }).newsStatus, 'unavailable')
  assert.deepEqual(analysis({ headline_count: 0, status: 'unavailable', sources_failed: ['gnews'] }).newsSourcesFailed, ['gnews'])
})

test('an older backend\'s answers are read as they always were', () => {
  assert.equal(analysis({ headline_count: 0 }).newsStatus, 'no_headlines')
  assert.equal(analysis({ headline_count: 3 }).newsStatus, 'ok')
  assert.equal(analysis({ headline_count: 0, error: 'Sentiment sources unavailable' }).newsStatus, 'unavailable')
})

test('no headline means no sentiment score, rather than a score of zero', () => {
  const a = analysis({ headline_count: 0, status: 'no_headlines', average_score: null, dominant_label: null })
  assert.equal(a.sentimentScore, null)
  assert.equal(a.sentimentLabel, null)
})

test('the news panel gives each reason its own words', async () => {
  const News = (await import('../src/components/company/News')).default
  const render = (status: 'ok' | 'no_headlines' | 'unavailable' | 'not_requested', failed: string[] = []) =>
    renderToStaticMarkup(createElement(News, { headlines: [], stream: null, status, failed, isPro: false, onUpgrade: () => {} }))
  const outage = render('unavailable', ['gnews', 'tavily'])
  assert.match(outage, /News sources did not answer for this run/)
  assert.match(outage, /gnews, tavily could not be reached/)
  assert.match(outage, /This is not a finding that there is no news/)
  assert.match(render('not_requested'), /News was not requested for this run/)
  const quiet = render('no_headlines')
  assert.match(quiet, /No company headlines were returned for this run/)
  assert.doesNotMatch(quiet, /did not answer/)
  assert.notEqual(outage, quiet)
})

// ── a missing reading is never a plausible one ───────────────────────────────

test('the process-memory panel does not claim to be live without a memory measurement', () => {
  const board = read('components', 'terminal', 'system', 'SystemHealthBoard.tsx')
  assert.match(board, /state=\{!health\.process_memory \? 'unavailable'/)
})

test('a regime whose share was not reported does not read as a share of zero', () => {
  const regimes = read('components', 'terminal', 'models2', 'RegimePerformance.tsx')
  assert.doesNotMatch(regimes, /\?\? 0\) \* 100\)\.toFixed/, 'a missing share is printed as 0.0%')
  assert.match(regimes, /share not reported/)
})
