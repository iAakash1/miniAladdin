/* A page about one security names its tab for that security.

   The company workspace is a client component, so it could not set a title,
   and every company a reader opened was a tab named after the whole product.
   Browser history, a tab strip and a screen reader's page announcement all
   told two companies apart by nothing. */

import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
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

import { safeDecode } from '../src/lib/page-title'
import { companyFromPath } from '../src/lib/context-commands'

test('a malformed escape in an address is text, not an exception', () => {
  assert.equal(safeDecode('%5EGSPC'), '^GSPC')
  assert.equal(safeDecode('%E0%A4%A'), '%E0%A4%A')
  assert.equal(safeDecode(undefined), '')
  assert.equal(companyFromPath('/company/aapl'), 'AAPL')
  assert.doesNotThrow(() => companyFromPath('/company/%E0%A4%A'))
})

test('no route segment is decoded with the throwing built-in', () => {
  const offenders: string[] = []
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name)
      if (statSync(full).isDirectory()) walk(full)
      else if (/\.tsx?$/.test(name) && !full.endsWith('page-title.ts') && /decodeURIComponent\(/.test(readFileSync(full, 'utf8'))) offenders.push(full.slice(full.indexOf('src/')))
    }
  }
  walk(join(__dirname, '..', 'src'))
  assert.deepEqual(offenders, [])
})
