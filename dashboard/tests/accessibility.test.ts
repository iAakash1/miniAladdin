/* A source-level accessibility audit.

   **What this is not:** a rendered audit. No browser was opened in this
   session, so none of these rules were checked against a real accessibility
   tree, and the things only a rendered page can show — focus order in
   practice, contrast at the theme's actual computed colours, whether a live
   region actually announces — are unverified. Those checks are owed.

   What a source audit *can* do is hold the invariants that are decidable from
   the markup, and those are not the cosmetic ones. A <th> with no scope is a
   cell a screen reader cannot tie to its header; an icon button with no
   accessible name is a control it announces as "button"; a disclosure with no
   aria-expanded is a control whose state is invisible. Each of those is a
   reader who cannot use the surface, decided entirely by the source. */
import { strict as assert } from 'node:assert'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'

const ROOT = new URL('../src/', import.meta.url).pathname

const walk = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? walk(join(dir, e.name))
      : e.name.endsWith('.tsx') ? [join(dir, e.name)] : [])

const FILES = walk(join(ROOT, 'components'))

/** Comments discuss markup in prose. Strip them so a sentence about <th> is
 *  not reported as a <th>. */
const source = (f: string): string =>
  readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')

const rel = (f: string): string => f.replace(ROOT, '')

test('every table header declares its scope', () => {
  /* Without scope, a screen reader guesses which header a cell belongs to. In
     a wide financial table that guess is wrong often, and the reader is told a
     drawdown is a Sharpe. 149 headers were missing it. */
  const offenders: string[] = []
  for (const f of FILES) {
    for (const m of source(f).matchAll(/<th\b[^>]*>/g)) {
      if (!m[0].includes('scope=')) offenders.push(`${rel(f)}: ${m[0].slice(0, 70)}`)
    }
  }
  assert.deepEqual(offenders, [], `table headers without scope:\n  ${offenders.join('\n  ')}`)
})

test('no element carries a positive tabIndex', () => {
  /* A positive tabIndex jumps that element ahead of everything in the document
     order, so the tab sequence stops matching the visual one for every reader,
     not only assistive-technology users. 0 and -1 are fine. */
  const offenders: string[] = []
  for (const f of FILES) {
    for (const m of source(f).matchAll(/tabIndex=\{(\d+)\}/g)) {
      if (Number(m[1]) > 0) offenders.push(`${rel(f)}: tabIndex={${m[1]}}`)
    }
  }
  assert.deepEqual(offenders, [], `positive tabIndex:\n  ${offenders.join('\n  ')}`)
})

test('every image states its alternative text', () => {
  const offenders: string[] = []
  for (const f of FILES) {
    for (const m of source(f).matchAll(/<img\b[^>]*?\/?>/g)) {
      if (!m[0].includes('alt=')) offenders.push(`${rel(f)}: ${m[0].slice(0, 70)}`)
    }
  }
  assert.deepEqual(offenders, [], `images without alt:\n  ${offenders.join('\n  ')}`)
})

test('a button whose content is only a glyph carries an accessible name', () => {
  /* An icon-only control announces as "button" and nothing else. The name can
     come from aria-label, a title, or visually hidden text — what it cannot
     come from is a symbol the reader never receives. */
  const offenders: string[] = []
  // A button on one line whose children are a single non-alphanumeric run.
  const oneLine = /<button\b([^>]*)>\s*([^<>\n]{1,4})\s*<\/button>/g
  for (const f of FILES) {
    for (const m of oneLine.exec(source(f)) ? source(f).matchAll(oneLine) : []) {
      const attrs = m[1]
      const label = m[2].trim()
      if (/[a-z0-9]/i.test(label)) continue          // it has real text
      if (/aria-label=|aria-labelledby=|title=/.test(attrs)) continue
      offenders.push(`${rel(f)}: <button>${label}</button>`)
    }
  }
  assert.deepEqual(
    offenders, [],
    `icon-only buttons with no accessible name:\n  ${offenders.join('\n  ')}`,
  )
})

test('a control that folds a section announces whether it is open', () => {
  /* aria-expanded is the only way a reader learns that activating a control
     revealed something. Checked on the rail's group toggles, which are the
     disclosures this product added most recently. */
  const rail = readFileSync(join(ROOT, 'components/system/Workbench.tsx'), 'utf8')
  const toggle = rail.match(/<button[^>]*wb-group-toggle[\s\S]{0,300}?>/)
  assert.ok(toggle, 'the rail group toggle is no longer a button')
  assert.match(toggle[0], /aria-expanded=/, 'the group toggle does not announce its state')
  assert.match(toggle[0], /aria-controls=/, 'the group toggle does not say what it controls')
})

/** The attributes of the JSX tag starting at `start`, to its real end.

    A regex of the form `<input[^>]*>` looks right and is wrong: it stops at
    the first `>` character, and in this codebase that is almost always the
    arrow of an `onChange={(e) => ...}` handler rather than the end of the tag.
    Every attribute written after the first handler is invisible to it — which
    for these components is exactly where the aria-label lives.

    That produced eleven confident false reports on the first run. Scanning to
    a `>` at brace depth zero is what the check actually needs. */
function tagAttributes(src: string, start: number): string {
  let depth = 0
  for (let i = start; i < src.length; i += 1) {
    const ch = src[i]
    if (ch === '{') depth += 1
    else if (ch === '}') depth -= 1
    else if (ch === '>' && depth === 0) return src.slice(start, i)
  }
  return src.slice(start, start + 400)
}

test('every form control is associated with a label', () => {
  /* An input with no label is a field a screen reader announces as "edit
     text". The association can be a wrapping <label>, an htmlFor pairing, or
     an aria-label. A placeholder is not one — it disappears on typing, which
     is exactly when a reader needs to re-check what the field was. */
  const offenders: string[] = []
  for (const f of FILES) {
    const src = source(f)
    for (const m of src.matchAll(/<(input|select|textarea)\b/g)) {
      const attrs = tagAttributes(src, m.index + m[0].length)
      if (/type=["']hidden["']/.test(attrs)) continue
      if (/aria-label=|aria-labelledby=|id=/.test(attrs)) continue

      // Wrapped in a <label>? The nearest preceding label tag is an opening
      // one that has not been closed.
      const before = src.slice(0, m.index)
      const open = before.lastIndexOf('<label')
      const close = before.lastIndexOf('</label>')
      if (open !== -1 && open > close) continue

      offenders.push(`${rel(f)}: <${m[1]} ${attrs.replace(/\s+/g, ' ').trim().slice(0, 60)}>`)
    }
  }
  assert.deepEqual(offenders, [], `unlabelled form controls:\n  ${offenders.join('\n  ')}`)
})

test('wide content scrolls inside its own container, not the page', () => {
  /* A table wider than the viewport must scroll in its own box. Letting the
     body scroll sideways moves the whole layout under the reader, and on a
     phone it makes the navigation unreachable. */
  const css = readFileSync(join(ROOT, 'styles/system.css'), 'utf8')
  assert.match(css, /\.sys-scroll-x\s*\{[^}]*overflow-x:\s*auto/,
    'the horizontal scroll container no longer scrolls')

  const table = readFileSync(join(ROOT, 'components/system/index.tsx'), 'utf8')
  assert.match(table, /<div className="sys-scroll-x">\s*<table/,
    'the shared table is no longer wrapped in a scroll container')
})

test('the responsive rail keeps a way to navigate at every width', () => {
  /* The rule that makes the narrow rail safe: below the breakpoint the labels
     go and the glyphs stay. A stylesheet that hid the links themselves would
     leave a reader on a phone with no navigation at all. */
  const css = readFileSync(join(ROOT, 'styles/system.css'), 'utf8')
  const hidden = css.match(/\.wb-label, \.wb-key, \.wb-group-label \{ display: none/)
  assert.ok(hidden, 'the narrow rail no longer hides its labels')

  const index = css.indexOf(hidden[0])
  const block = css.slice(index, css.indexOf('}', css.indexOf('{', index)) + 400)
  assert.doesNotMatch(block, /\.wb-link \{ display: none/,
    'the narrow rail hides the links themselves, leaving no way to navigate')
  assert.doesNotMatch(block, /\.wb-glyph \{ display: none/,
    'the narrow rail hides the glyphs, which are its only remaining labels')
})
