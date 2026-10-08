/* A small CSS reader for the guard tests.

   The stylesheets are plain CSS with nested at-rules (@media, @supports,
   @layer). A regex over the text cannot tell whether a rule sits inside
   `@media (hover: hover)`, which is exactly what several guards need to know,
   so this walks the braces. It is not a complete CSS parser: it handles
   comments, strings, parentheses in values and nested at-rules, which is all
   these two files use. @keyframes are returned as one rule whose body is kept
   whole, because their inner selectors (`from`, `50%`) are not selectors. */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export interface CssRule {
  file: string
  line: number
  /** The enclosing at-rule preludes, outermost first. */
  context: string[]
  /** The selector, or the at-rule prelude for @font-face and friends. */
  selector: string
  decls: Array<[prop: string, value: string]>
  keyframes?: string
}

const SRC = join(__dirname, '..', 'src')
export const CSS_FILES = [
  join(SRC, 'styles', 'tokens.css'),
  join(SRC, 'styles', 'system.css'),
  join(SRC, 'app', 'globals.css'),
]

export function stripComments(text: string): string {
  // Newlines survive so line numbers still point at the source.
  return text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ''))
}

function blockEnd(text: string, open: number): number {
  let depth = 0
  let quote: string | null = null
  for (let i = open; i < text.length; i++) {
    const c = text[i]
    if (quote) {
      if (c === '\\') i++
      else if (c === quote) quote = null
    } else if (c === '"' || c === "'") quote = c
    else if (c === '{') depth++
    else if (c === '}' && --depth === 0) return i
  }
  return text.length
}

function declarations(body: string): Array<[string, string]> {
  const out: Array<[string, string]> = []
  let cur = ''
  let paren = 0
  let quote: string | null = null
  const flush = () => {
    const at = cur.indexOf(':')
    if (at > 0) out.push([cur.slice(0, at).trim().toLowerCase(), cur.slice(at + 1).replace(/\s+/g, ' ').trim()])
    cur = ''
  }
  for (const c of body) {
    if (quote) {
      cur += c
      if (c === quote) quote = null
      continue
    }
    if (c === '"' || c === "'") { quote = c; cur += c; continue }
    if (c === '(') paren++
    else if (c === ')') paren--
    if (c === ';' && paren === 0) flush()
    else cur += c
  }
  if (cur.trim()) flush()
  return out
}

const NESTING = new Set(['@media', '@supports', '@layer', '@container', '@scope', '@starting-style'])

export function parseCss(source: string, file = ''): CssRule[] {
  const text = stripComments(source)
  const rules: CssRule[] = []

  const walk = (lo: number, hi: number, context: string[]) => {
    let i = lo
    while (i < hi) {
      while (i < hi && /\s/.test(text[i])) i++
      if (i >= hi) break
      let j = i
      let quote: string | null = null
      let paren = 0
      for (; j < hi; j++) {
        const c = text[j]
        if (quote) {
          if (c === '\\') j++
          else if (c === quote) quote = null
        } else if (c === '"' || c === "'") quote = c
        else if (c === '(') paren++
        else if (c === ')') paren--
        else if (paren === 0 && (c === '{' || c === ';')) break
      }
      if (j >= hi) break
      const prelude = text.slice(i, j).replace(/\s+/g, ' ').trim()
      const line = text.slice(0, i).split('\n').length
      if (text[j] === ';') { i = j + 1; continue }
      const end = blockEnd(text, j)
      if (prelude.startsWith('@')) {
        const name = prelude.split(' ')[0]
        if (NESTING.has(name)) walk(j + 1, end, [...context, prelude])
        else if (name === '@keyframes' || name === '@-webkit-keyframes') {
          rules.push({ file, line, context, selector: prelude, decls: [], keyframes: text.slice(j + 1, end) })
        } else rules.push({ file, line, context, selector: prelude, decls: declarations(text.slice(j + 1, end)) })
      } else {
        rules.push({ file, line, context, selector: prelude, decls: declarations(text.slice(j + 1, end)) })
      }
      i = end + 1
    }
  }

  walk(0, text.length, [])
  return rules
}

export function loadAllCss(): CssRule[] {
  return CSS_FILES.flatMap((file) => parseCss(readFileSync(file, 'utf8'), file))
}

/** Every `@media` prelude in the stylesheets, with how many rules each wraps. */
export function mediaQueries(rules: CssRule[]): Map<string, number> {
  const out = new Map<string, number>()
  for (const rule of rules) {
    for (const c of rule.context) if (c.startsWith('@media')) out.set(c, (out.get(c) ?? 0) + 1)
  }
  return out
}
