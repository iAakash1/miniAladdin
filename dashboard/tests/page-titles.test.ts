/* Every page names itself.

   A tab title is the first thing a screen reader announces on navigation (WCAG 2.4.2) and the only
   label a browser history gives a page. The beginner and intermediate shells set one default title in
   their layout, so a page below them that said nothing was "Simple" whether it showed a comparison, a
   watchlist or a company; eight of them did. A page must carry its own title, or sit in a directory
   whose layout supplies one. Redirects render nothing and are exempt. */

import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const APP = join(__dirname, '..', 'src', 'app')

function pages(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) pages(full, out)
    else if (name === 'page.tsx') out.push(full)
  }
  return out
}

const NAMES_ITSELF = /export\s+(const\s+metadata\b|(async\s+)?function\s+generateMetadata\b)/
const REDIRECTS = /\b(permanentRedirect|redirect)\(/

test('every page that renders names itself, or its own directory layout does', () => {
  const unnamed: string[] = []
  for (const page of pages(APP)) {
    const source = readFileSync(page, 'utf8')
    if (REDIRECTS.test(source) || NAMES_ITSELF.test(source)) continue
    const layout = join(page, '..', 'layout.tsx')
    if (existsSync(layout) && NAMES_ITSELF.test(readFileSync(layout, 'utf8'))) continue
    unnamed.push(relative(APP, page).split(sep).join('/'))
  }
  assert.deepEqual(unnamed, [])
})
