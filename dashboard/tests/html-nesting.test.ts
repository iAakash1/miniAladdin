/* The HTML a component renders is HTML a parser will keep as written.

   A `<p>` cannot contain a `<p>`, a `<div>` or a list: the parser closes the
   outer paragraph early, the server markup no longer matches what React
   rendered, and React discards the server HTML for that subtree and says so in
   the console. The technical-intelligence levels line put a tooltip whose body
   was a `<p>` inside a `<p>`. This walks every component's JSX for the pairs
   the parser rewrites. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

function tagEnd(text: string, from: number): number {
  let depth = 0
  let quote: string | null = null
  for (let i = from; i < text.length; i++) {
    const c = text[i]
    if (quote) { if (c === quote && text[i - 1] !== '\\') quote = null }
    else if (c === '"' || c === "'" || c === '`') quote = c
    else if (c === '{') depth++
    else if (c === '}') depth--
    else if (c === '>' && depth === 0 && text[i - 1] !== '=') return i + 1
  }
  return -1
}

/** Elements a `<p>` may not contain, because the parser would end the paragraph first. */
const NOT_IN_P = new Set(['div', 'ul', 'ol', 'dl', 'table', 'section', 'article', 'aside', 'header', 'footer', 'nav', 'main', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'blockquote', 'figure', 'fieldset', 'hr'])
const VOID = new Set(['img', 'input', 'br', 'hr', 'meta', 'link'])

test('no element is nested where an HTML parser would rewrite it', () => {
  const found: string[] = []
  for (const file of walk(SRC)) {
    // Comments and strings talk about tags; only code renders them.
    const text = readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, (c) => ' '.repeat(c.length)).replace(/(^|[^:])\/\/.*$/gm, (m, a) => a + ' '.repeat(m.length - a.length))
    const stack: Array<{ name: string }> = []
    for (const m of text.matchAll(/<\/?([a-z][a-z0-9]*)\b/g)) {
      const end = tagEnd(text, m.index!)
      if (end < 0) continue
      const tag = text.slice(m.index!, end)
      const name = m[1]
      if (tag.startsWith('</')) {
        const at = stack.map((s) => s.name).lastIndexOf(name)
        if (at >= 0) stack.length = at
        continue
      }
      const inside = stack.map((s) => s.name)
      const where = `${relative(SRC, file).split(sep).join('/')}:${text.slice(0, m.index!).split('\n').length}`
      if (inside.includes('p') && NOT_IN_P.has(name)) found.push(`${where} <${name}> inside <p>`)
      if (name === 'a' && inside.includes('a')) found.push(`${where} <a> inside <a>`)
      if ((name === 'button' || name === 'a') && inside.includes('button')) found.push(`${where} <${name}> inside <button>`)
      if (name === 'button' && inside.includes('a')) found.push(`${where} <button> inside <a>`)
      if (name === 'form' && inside.includes('form')) found.push(`${where} <form> inside <form>`)
      if (!tag.trimEnd().endsWith('/>') && !VOID.has(name)) stack.push({ name })
    }
  }
  assert.deepEqual(found, [])
})

test('a name given to a generic element comes with a role that can carry it', () => {
  // aria-label on a bare <div> or <span> is not announced: those elements have
  // no role to name. A group, an image or a status can.
  const generic = new Set(['div', 'span', 'p', 'strong', 'em', 'small', 'b', 'i', 'li', 'td', 'tr', 'th', 'g', 'text'])
  const found: string[] = []
  for (const file of walk(SRC)) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(/<([a-z][a-z0-9]*)\b(?=[\s/>])/g)) {
      if (!generic.has(m[1])) continue
      const end = tagEnd(text, m.index!)
      if (end < 0) continue
      const tag = text.slice(m.index!, end)
      if (/\baria-label(?:ledby)?=/.test(tag) && !/\brole=/.test(tag)) found.push(`${relative(SRC, file).split(sep).join('/')}:${text.slice(0, m.index!).split('\n').length} <${m[1]}>`)
    }
  }
  assert.deepEqual(found, [])
})
