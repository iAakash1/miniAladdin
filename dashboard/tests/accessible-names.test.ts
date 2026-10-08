/* Every control and every named region has a name a screen reader can say.

   Built on the TypeScript compiler's own parse of each component rather than on
   regular expressions over JSX, so a conditional `role={x ? 'button' : undefined}`
   or an icon inside a labelled button is read as the compiler reads it. It audits
   the native controls (button, link, input, select, textarea, image, svg, dialog)
   and every ARIA role that cannot name itself (dialog, tabpanel, img, application,
   combobox, listbox, region, search ...), and it flags a click handler on an
   element that has neither a role nor a way to focus it.

   What it deliberately cannot see: a name supplied by a component's props
   (`<Button label=...>`), which is skipped, and what the name *says*. A control
   named "button" or "icon" is caught by the second test, which lists names too
   generic to be a name. */

import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import test from 'node:test'

import * as ts from 'typescript'

const SRC = join(__dirname, '..', 'src')

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.tsx')) out.push(full)
  }
  return out
}

type AttrValue = ts.Expression | string | true
function attributes(node: ts.JsxOpeningLikeElement): Map<string, AttrValue> {
  const out = new Map<string, AttrValue>()
  for (const prop of node.attributes.properties) {
    if (!ts.isJsxAttribute(prop)) { out.set('...spread', true); continue }
    const name = prop.name.getText()
    let value: AttrValue = true
    if (prop.initializer) {
      if (ts.isStringLiteral(prop.initializer)) value = prop.initializer.text
      else if (ts.isJsxExpression(prop.initializer) && prop.initializer.expression) value = prop.initializer.expression
    }
    out.set(name, value)
  }
  return out
}
const hasAny = (a: Map<string, AttrValue>, ...names: string[]) => names.some((n) => a.has(n))
const nonEmpty = (v: AttrValue | undefined) => typeof v === 'string' ? v.trim().length > 0 : v !== undefined && v !== true

/** The role, whether written as a string or as `cond ? 'role' : undefined`. */
function roleOf(a: Map<string, AttrValue>): string | null {
  const v = a.get('role')
  if (typeof v === 'string') return v
  if (v && v !== true) {
    const literal = (v as ts.Expression).getText().match(/'([a-z]+)'/)
    if (literal) return literal[1]
  }
  return null
}

const DECORATIVE_COMPONENTS = /^(Icon|Glyph|Svg|CompanyMark|EntityMark|Skeleton)/

/** Whether an element's content provides a name: text, a dynamic expression, or a labelled child. */
function hasContentName(node: ts.JsxElement): boolean {
  for (const child of node.children) {
    if (ts.isJsxText(child) && child.text.trim()) return true
    if (ts.isJsxExpression(child) && child.expression) return true
    if (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) {
      const opening = ts.isJsxElement(child) ? child.openingElement : child
      const a = attributes(opening)
      if (hasAny(a, 'aria-label', 'aria-labelledby', 'alt')) return true
      const tag = opening.tagName.getText()
      if (ts.isJsxElement(child)) {
        if (/^[a-z]/.test(tag) && tag !== 'svg' && tag !== 'img' && hasContentName(child)) return true
        if (/^[A-Z]/.test(tag) && !DECORATIVE_COMPONENTS.test(tag) && hasContentName(child)) return true
      } else if (/^[A-Z]/.test(tag) && !DECORATIVE_COMPONENTS.test(tag) && opening.attributes.properties.length) {
        return true // a component that may render text from its props
      }
    }
  }
  return false
}

interface Finding { file: string; line: number; what: string }

const NAMED_ROLES = new Set(['dialog', 'alertdialog', 'tabpanel', 'img', 'figure', 'application', 'combobox', 'listbox', 'tablist', 'progressbar', 'meter', 'slider', 'search', 'region', 'form', 'radiogroup', 'menu', 'menubar', 'grid', 'tree', 'treegrid', 'toolbar'])
const NAMES_FROM_CONTENT = new Set(['tab', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'option', 'checkbox', 'radio', 'switch', 'button', 'link', 'treeitem'])
const GENERIC = /^(button|icon|click|menu|link|image|img|svg|close|x|ok|go|btn|untitled|label|text|here)$/i

function audit(): { missing: Finding[]; generic: Finding[]; checked: number } {
  const missing: Finding[] = []
  const generic: Finding[] = []
  let checked = 0

  for (const file of walk(SRC)) {
    const sf = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const rel = relative(SRC, file).split(sep).join('/')
    const labelTargets = new Set<string>()
    let dynamicLabel = false

    const gather = (node: ts.Node) => {
      if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
        const opening = ts.isJsxElement(node) ? node.openingElement : node
        if (opening.tagName.getText() === 'label') {
          const target = attributes(opening).get('htmlFor')
          if (typeof target === 'string') labelTargets.add(target)
          else if (target) dynamicLabel = true
        }
      }
      ts.forEachChild(node, gather)
    }
    gather(sf)

    const visit = (node: ts.Node, insideLabel: boolean, hidden: boolean) => {
      let inLabel = insideLabel
      let isHidden = hidden
      if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
        const opening = ts.isJsxElement(node) ? node.openingElement : node
        const tag = opening.tagName.getText()
        const a = attributes(opening)
        const role = roleOf(a)
        const line = sf.getLineAndCharacterOfPosition(node.getStart()).line + 1
        const spread = a.has('...spread')
        if (a.get('aria-hidden') === true || a.get('aria-hidden') === 'true') isHidden = true
        if (tag === 'label') inLabel = true
        const flag = (what: string) => missing.push({ file: rel, line, what })
        const named = hasAny(a, 'aria-label', 'aria-labelledby') || nonEmpty(a.get('title')) || spread
        const label = a.get('aria-label')
        if (typeof label === 'string' && GENERIC.test(label.trim())) generic.push({ file: rel, line, what: `aria-label="${label}"` })

        if (!isHidden) {
          checked++
          const element = ts.isJsxElement(node) ? node : null
          if (tag === 'button' && !spread && !hasAny(a, 'aria-label', 'aria-labelledby')) {
            if (!element || !hasContentName(element)) flag(nonEmpty(a.get('title')) ? '<button> named only by its title' : '<button> with no accessible name')
          }
          if ((tag === 'a' || tag === 'Link') && !spread && !hasAny(a, 'aria-label', 'aria-labelledby')) {
            if (!element || !hasContentName(element)) flag(`<${tag}> with no accessible name`)
          }
          if ((tag === 'input' || tag === 'select' || tag === 'textarea') && !spread) {
            const type = typeof a.get('type') === 'string' ? (a.get('type') as string) : 'text'
            if (!['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) {
              const id = a.get('id')
              const labelled = hasAny(a, 'aria-label', 'aria-labelledby') || inLabel || nonEmpty(a.get('title'))
                || (typeof id === 'string' && labelTargets.has(id)) || (id !== undefined && typeof id !== 'string' && dynamicLabel)
              if (!labelled) flag(`<${tag} type=${type}> with no label`)
            }
          }
          // An svg is named by a <title> child, written outright or behind a condition.
          const titledSvg = tag === 'svg' && ts.isJsxElement(node) && /<title\b/.test(node.getText())
          if (role && NAMED_ROLES.has(role) && !named && !titledSvg) flag(`role="${role}" with no accessible name`)
          if (role && NAMES_FROM_CONTENT.has(role) && !named && (!element || !hasContentName(element))) flag(`role="${role}" with no text or label`)
          if (tag === 'svg' && !role && !hasAny(a, 'aria-hidden', 'aria-label', 'aria-labelledby') && !spread) {
            const titled = ts.isJsxElement(node) && node.children.some((c) => ts.isJsxElement(c) && c.openingElement.tagName.getText() === 'title')
            if (!titled) flag('<svg> neither hidden nor named')
          }
          if (tag === 'dialog' && !named) flag('<dialog> with no accessible name')
          if (tag === 'img' && !a.has('alt') && !spread) flag('<img> with no alt')
          if (a.has('onClick') && /^(div|span|li|td|p|section|article|svg|g|circle|rect|path|header|footer)$/.test(tag) && !role && !spread) {
            flag(`<${tag}> with onClick but no role`)
          }
          // A container with a role (a menu that only stops propagation, say) has
          // already said what it is; the unreachable-click rule is for bare elements.
          if (a.has('onClick') && /^(div|span|li|tr)$/.test(tag) && !role && !a.has('tabIndex') && !spread && !hasAny(a, 'aria-hidden')) {
            flag(`<${tag}> with onClick that keyboard focus cannot reach`)
          }
        }
      }
      ts.forEachChild(node, (child) => visit(child, inLabel, isHidden))
    }
    visit(sf, false, false)
  }
  return { missing, generic, checked }
}

const RESULT = audit()
const show = (items: Finding[]) => items.map((f) => `${f.file}:${f.line} ${f.what}`)

test('the audit really looked: it parsed hundreds of components and thousands of elements', () => {
  assert.ok(walk(SRC).length > 250, 'fewer components than expected were found')
  assert.ok(RESULT.checked > 5000, `only ${RESULT.checked} elements were inspected`)
})

test('every interactive control and named region has an accessible name', () => {
  assert.deepEqual(show(RESULT.missing), [])
})

test('no accessible name is a placeholder such as "button" or "icon"', () => {
  assert.deepEqual(show(RESULT.generic), [])
})
