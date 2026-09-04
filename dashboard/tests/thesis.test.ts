/* The thesis, and the two things it must never do.

   A paper trade with no recorded reason is a ledger entry. A paper trade with
   the reason attached is the only part of this product that can answer, three
   months later, "what did I believe, and was I right". */
import { strict as assert } from 'node:assert'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname
const THESIS = readFileSync(join(ROOT, 'lib/thesis.ts'), 'utf8')
const TICKET = readFileSync(join(ROOT, 'components/terminal/paper/OrderTicket.tsx'), 'utf8')
const VIEW = readFileSync(join(ROOT, 'components/terminal/security/SecurityView.tsx'), 'utf8')

test('a thesis is never generated', () => {
  // A fabricated intent is worse than an absent one, because an absent one is
  // obviously absent.
  assert.match(THESIS, /[Nn]ever generated/)
  assert.match(TICKET, /No thesis attached|assembled on your behalf/)
  // Only what the reader typed is recorded.
  assert.match(TICKET, /const text = thesis\.trim\(\)/)
  assert.match(TICKET, /if \(text\)/, 'a thesis is recorded even when empty')
})

test('the research state on a thesis is read, never inferred', () => {
  // A recorded "blocked" that came from a failed request would be a claim
  // about research nobody made.
  assert.match(VIEW, /selection\/EXP-007/)
  assert.match(VIEW, /typeof passed !== 'boolean'/,
    'the verdict is derived from something other than the artifact’s own boolean')
  assert.match(VIEW, /no verdict read means no verdict recorded|Absent stays absent/)
})

test('the thesis snapshots the state at the time of the order', () => {
  // What the archive says in December is not what it said when the order was
  // placed, and a review that reads today's state reviews the wrong thing.
  assert.match(THESIS, /snapshot, not a link|is a snapshot/)
  assert.match(THESIS, /researchState\?:/)
})

test('a thesis is attached to the broker’s order id', () => {
  // Not to a symbol, and not to a local id — the order is the thing the
  // thesis is about, and the broker owns its identity.
  assert.match(TICKET, /orderId: order\.id/)
})

test('research context never reads as a recommendation', () => {
  // The archive's verdict travelling with a trade must not look like the
  // archive endorsing it.
  assert.match(VIEW, /no production candidate/i)
})

/* accepted is not filled, and submitted is not executed.

   These are different states and the difference is money. An interface that
   promotes one to the other is telling a reader they own something they do
   not. */
const PAPER = readFileSync(join(ROOT, 'components/terminal/paper/PaperWorkspace.tsx'), 'utf8')

test('the broker’s own status word is what is rendered', () => {
  // The label comes from the payload, reformatted for case only. Nothing
  // substitutes a word the broker did not use.
  assert.match(PAPER, /status\.replace\(\/_\/g, ' '\)\.toUpperCase\(\)/)
  assert.match(TICKET, /order\.status \?\? 'unknown'/)
})

test('accepted is never coloured as filled', () => {
  // The one mapping in the product is status → state colour. `filled` is the
  // only status that may read as live; accepted, new and pending_new are
  // in-flight and must not.
  const map = PAPER.slice(PAPER.indexOf('function OrderStatus'), PAPER.indexOf('function OrderStatus') + 700)
  assert.match(map, /s === 'filled' \? 'live'/)
  assert.match(map, /'accepted'/)
  // accepted must appear in the waking group, not the live branch.
  const liveBranch = map.slice(0, map.indexOf("'blocked'"))
  assert.doesNotMatch(liveBranch, /accepted/, 'accepted is grouped with filled')
})

test('no code substitutes one order state for another', () => {
  for (const src of [PAPER, TICKET]) {
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
    assert.doesNotMatch(code, /'FILLED'/, 'a hardcoded FILLED label exists')
    assert.doesNotMatch(code, /'EXECUTED'/, 'a hardcoded EXECUTED label exists')
  }
})

test('an unfilled order shows no fill price', () => {
  // Borrowing the last trade would invent an execution that did not happen.
  assert.match(TICKET, /not yet filled/)
  assert.match(TICKET, /order\.filled_avg_price \?/)
})
