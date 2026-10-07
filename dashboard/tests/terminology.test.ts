/* One name for one thing.

   The page that keeps a reader's saved reports and past runs is "Research log"
   in the navigation, in its own title, on the company header and in the
   daily-limit message. Three other places called it "the Vault", so a reader
   told to save something "in your Vault" had no screen of that name to open. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

const prose = (file: string) =>
  readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

test('the saved-research page is called the Research log everywhere a reader sees a name', () => {
  const offenders: string[] = []
  for (const file of walk(SRC)) {
    for (const m of prose(file).matchAll(/(?<![\w/.-])[Tt]he Vault\b|\bin your Vault\b|\bto Vault\b|>\s*Vault\s*</g)) {
      offenders.push(`${relative(SRC, file).split(sep).join('/')}: ${m[0]}`)
    }
  }
  assert.deepEqual(offenders, [])
})
