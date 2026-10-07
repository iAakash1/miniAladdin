/* A page about one security names its tab for that security.

   The company workspace is a client component, so it could not set a title,
   and every company a reader opened was a tab named after the whole product.
   Browser history, a tab strip and a screen reader's page announcement all
   told two companies apart by nothing. */

import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { securityTitle, symbolFromSegment } from '../src/lib/page-title'

test('a route segment is read as a symbol, upper-cased and decoded', () => {
  assert.equal(symbolFromSegment('aapl'), 'AAPL')
  assert.equal(symbolFromSegment('BRK.B'), 'BRK.B')
  assert.equal(symbolFromSegment('brk-b'), 'BRK-B')
  assert.equal(symbolFromSegment('%5EGSPC'), '^GSPC')
})

test('something that is not a symbol is not made into a title', () => {
  assert.equal(symbolFromSegment(undefined), null)
  assert.equal(symbolFromSegment(''), null)
  assert.equal(symbolFromSegment('<script>'), null)
  assert.equal(symbolFromSegment('TOOLONGSYMBOL1'), null)
  assert.equal(symbolFromSegment('%E0%A4%A'), null, 'a malformed escape must not throw')
})

test('the title names the symbol and what the page is', () => {
  assert.equal(securityTitle('msft', 'research', 'Company research'), 'MSFT research')
  assert.equal(securityTitle('???', 'research', 'Company research'), 'Company research')
})

test('the company, evidence and agent pages each set one', () => {
  const root = join(__dirname, '..', 'src', 'app')
  for (const file of ['company/[ticker]/layout.tsx', 'evidence/[ticker]/layout.tsx', 'terminal/agents/[ticker]/page.tsx']) {
    const full = join(root, file)
    assert.ok(existsSync(full), `${file} is missing`)
    const text = readFileSync(full, 'utf8')
    assert.match(text, /export async function generateMetadata/, `${file} sets no title`)
    assert.match(text, /securityTitle\(/)
  }
})
