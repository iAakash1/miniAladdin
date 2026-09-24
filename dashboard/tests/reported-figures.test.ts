/* Vendor-reported statement figures, and the separations that make them safe.

   These figures were arriving on every research request and dying at the API
   boundary. The backend now groups them by concept, basis, period and unit
   together; this asserts the reader-side half — that the panel presents
   groups rather than pooling them, keeps vendor figures apart from filed
   ones, and never converts between bases to make two rows look comparable. */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const REP = readFileSync(ROOT + 'components/terminal/security/Reported.tsx', 'utf8')
const TABS = readFileSync(ROOT + 'components/company/tabs/Detail.tsx', 'utf8')
const FIN = readFileSync(ROOT + 'components/terminal/security/Financials.tsx', 'utf8')

const CODE = REP
  .replace(/\/\*[\s\S]*?\*\//g, ' ')
  .split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')

test('basis and period are columns, not decoration', () => {
  // The whole reason this is a table of groups. If either stops being a
  // column the reader sees three "Revenue" rows with no way to tell them
  // apart, which is worse than not showing them.
  for (const col of ['>Figure<', '>Basis<', '>Period<', '>Value<', '>Sources<']) {
    assert.ok(REP.includes(col), `the ${col} column is gone`)
  }
})

test('an unstated period is rendered as unstated, never as a blank', () => {
  // yfinance supplies no period at all. A blank cell reads as "no data";
  // the vendor did answer, it just did not say what span it covers.
  assert.match(CODE, /periodLabel/, 'periods are not passed through a labeller')
  assert.match(REP, /not stated/, 'an unstated period has no rendering')
  assert.match(REP, /rep__unstated/, 'an unstated period is styled the same as a value')
})

test('nothing converts between bases', () => {
  /* Dividing an absolute revenue by a share count to line it up with a
     per-share figure would manufacture a number no vendor reported. The
     panel must not contain that arithmetic. */
  assert.doesNotMatch(CODE, /shares_outstanding|sharesOutstanding/,
    'a share count reached the panel, which is the input a base conversion needs')
  assert.doesNotMatch(CODE, /value\s*[*/]\s*\w*[Ss]hares/, 'a per-share conversion appeared')
})

test('the conflict primitive is fed, not reimplemented', () => {
  // Part of the same rule that keeps one inspector rather than a provenance
  // panel per surface.
  assert.match(CODE, /conflict:\s*obs\.length > 1/,
    'vendor disagreement is not routed through the shared conflict field')
  assert.doesNotMatch(CODE, /useState<[^>]*[Dd]rawer|MetricInspector/,
    'the panel opens its own inspector')
})

test('agreement is never claimed for a single observation', () => {
  // `agrees` is null for a lone vendor. Rendering that as agreement would
  // turn one source into corroboration.
  assert.match(CODE, /obs\.length > 1 \?/, 'the source cell does not gate on observation count')
  assert.match(CODE, /agrees === false/, 'disagreement is not distinguished from absence')
})

test('filed facts and vendor figures stay in separate panels', () => {
  // One is what the company told the SEC; the other is a vendor's own
  // computation. In one grid a reader cannot say which a number is.
  const financials = TABS.slice(TABS.indexOf('export function FinancialsTab'), TABS.indexOf('export function TechnicalsTab'))
  assert.ok(/<Financials symbol/.test(financials) && /<Reported symbol/.test(financials),
    'the filed and the vendor-reported panels are not rendered separately')
  assert.match(FIN, /SEC XBRL/, 'the filed panel no longer names its source')
  assert.match(REP, /published, not filed|not filed ones/,
    'the vendor panel does not distinguish itself from the filed one')
  // And the vendor panel must not be reading filings.
  assert.doesNotMatch(CODE, /filings\?\.|\bxbrl\b/, 'the vendor panel reads filed facts')
})

test('the panel reads the grouped structure, not the dead fields map', () => {
  // `statements.fields` can only ever hold `eps`. Reading it would reproduce
  // the very gap this panel exists to close.
  assert.match(CODE, /statements\?[\s\S]{0,40}reported/,
    'the panel does not read the grouped `reported` structure')
  assert.doesNotMatch(CODE, /\.fields\b/, 'the panel reads the structurally-dead fields map')
})


/* ── every workspace section has a tab, and every tab a section ─────────── */

test('every company tab renders something and every rendered section has a tab', () => {
  /* The workspace's tab list is its map. A tab with no panel scrolls nowhere,
     and a panel with no tab is unreachable — the drift the old security
     page's index had. */
  const WS = readFileSync(ROOT + 'components/company/CompanyWorkspace.tsx', 'utf8')
  const tabs = new Set([...WS.matchAll(/\{ key: '([a-z]+)', label: /g)].map((m) => m[1]))
  const renders = new Set([...WS.matchAll(/tab === '([a-z]+)'/g)].map((m) => m[1]))
  const missing = [...tabs].filter((t) => !renders.has(t))
  const dangling = [...renders].filter((r) => !tabs.has(r))
  assert.ok(tabs.size >= 8, 'the workspace appears to have no tabs')
  assert.deepEqual(missing, [], `tabs with nothing rendered: ${missing.join(', ')}`)
  assert.deepEqual(dangling, [], `sections with no tab: ${dangling.join(', ')}`)
  assert.ok(tabs.has('financials'), 'the filed and vendor panels have no tab')
})
