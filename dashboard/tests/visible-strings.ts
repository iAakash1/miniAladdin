/* The words a reader sees, and nothing else.

   String literals and JSX text from the dashboard source, found with the TypeScript compiler so that
   comments, identifiers, class names and import paths are excluded by construction rather than by a
   regular expression that guesses. Several guard tests read prose; this is the one place that decides
   what counts as prose. */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'

import ts from 'typescript'

export const SRC = join(__dirname, '..', 'src')

export interface VisibleString { file: string; line: number; text: string }

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (/\.tsx?$/.test(name)) out.push(full)
  }
  return out
}

/** Attributes whose value is a name for the code, not text for a reader. */
const CODE_ATTRIBUTES = /^(className|style|key|id|htmlFor|data-.*|role|type|href|src|d|viewBox|name)$/

export function visibleStrings(filter?: (relativePath: string) => boolean): VisibleString[] {
  const out: VisibleString[] = []
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split(sep).join('/')
    if (filter && !filter(rel)) continue
    const text = readFileSync(file, 'utf8')
    const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    const visit = (n: ts.Node) => {
      if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isJsxText(n)
        || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) {
        const parent = n.parent
        const code = ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent)
          || (ts.isJsxAttribute(parent) && CODE_ATTRIBUTES.test(parent.name.getText()))
          || (ts.isPropertyAssignment(parent) && parent.name === n)
        if (!code) {
          const value = (n as ts.StringLiteral).text ?? n.getText()
          out.push({ file: rel, line: sf.getLineAndCharacterOfPosition(n.getStart()).line + 1, text: value })
        }
      }
      ts.forEachChild(n, visit)
    }
    visit(sf)
  }
  return out
}
