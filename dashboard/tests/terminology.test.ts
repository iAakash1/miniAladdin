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

import { visibleStrings } from './visible-strings'

test('the saved-research page is never called a vault or a history in text a reader sees', () => {
  /* The heading of the page itself still said "Research Vault" under a navigation entry and a page
     title that said "Research log", and the stock page's panel offered "Open vault" and called the
     same record "Research history". Comments may name the old thing; the words on screen may not. */
  const offenders = visibleStrings()
    .flatMap(({ file, line, text }) => {
      const hit = /\bResearch Vault\b|\b[Oo]pen vault\b|\bVault section\b|\bresearch history\b/i.exec(text)
      return hit ? [`${file}:${line} "${hit[0]}"`] : []
    })
  assert.deepEqual(offenders, [])
})

test('the security and company workspaces do not use developer words with a reader', () => {
  /* "payload" and "endpoint" are how the code names a response and a route. A reader looking at a price
     or a provenance table is owed "response", "record" or "service". The research and admin workbenches
     are written for people who audit the pipeline and may use its vocabulary. */
  const OWN_WORDS = /^components\/(company|evidence|terminal\/security|system)\//
  const offenders = visibleStrings((p) => OWN_WORDS.test(p))
    .flatMap(({ file, line, text }) => {
      const hit = /\bpayloads?\b|\bendpoints?\b/i.exec(text)
      return hit ? [`${file}:${line} "${hit[0]}"`] : []
    })
  assert.deepEqual(offenders, [])
})

test('no text a reader sees names Render, the retired host', () => {
  /* A failure message told readers the backend was "asleep (Render free tier cold-starts)" and
     that Clerk answers signed-out API calls with a 404; production has been Cloud Run for a long
     time and a signed-out call is a 401. Advice about the wrong system is worse than no advice. */
  const offenders = visibleStrings()
    .flatMap(({ file, line, text }) => (/\bRender\b/.test(text) ? [`${file}:${line}`] : []))
  assert.deepEqual(offenders, [])
})
