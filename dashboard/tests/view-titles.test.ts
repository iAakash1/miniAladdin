/* A page is called what the way in called it.

   The rail, the palette and the workspace tabs all read one registry of names. A page that then
   opened under a different name (the "Path explorer" entry opened a page headed "Explore") makes the
   reader wonder whether they arrived. The tab title and the heading must each be a name the registry
   gives that page: the view's label, or the destination's own when the page is the one it opens on. */

import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

import { ALL_VIEWS } from '../src/lib/destinations'

const APP = join(__dirname, '..', 'src', 'app')

test('every registered view opens under its own name', () => {
  const differs: string[] = []
  for (const view of ALL_VIEWS) {
    const file = join(APP, view.href, 'page.tsx')
    if (!existsSync(file)) continue
    const source = readFileSync(file, 'utf8')
    if (/\bredirect\(/.test(source)) continue
    const names = new Set([view.label.toLowerCase()])
    if (view.href === view.destination.href) names.add(view.destination.label.toLowerCase())
    const title = /export const metadata[^=]*=\s*\{[^}]*?\btitle:\s*'([^']+)'/.exec(source)?.[1]
    const heading = /<Workbench[^>]*?\btitle="([^"]+)"/.exec(source)?.[1]
    for (const [kind, name] of [['title', title], ['heading', heading]] as const) {
      if (name !== undefined && !names.has(name.toLowerCase())) {
        differs.push(`${view.href}: ${kind} "${name}" but the way in says ${[...names].map((n) => `"${n}"`).join(' or ')}`)
      }
    }
  }
  assert.deepEqual(differs, [])
})
