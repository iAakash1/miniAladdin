/**
 * Building the palette's render list.
 *
 * The palette paints section headers and selectable rows in one column, but
 * the keyboard cursor is a single flat index. If the painted order and the
 * index ever disagree the surface breaks quietly: the highlighted row and the
 * row Enter opens are different rows.
 *
 * That is not hypothetical. An earlier palette counted rows during render with
 * a trailing `+ 1`, so option ids ran 1..N while the cursor ran 0..N-1 —
 * nothing was highlighted on open, one arrow press highlighted one row while
 * Enter opened the next, and the last result could never be reached at all.
 *
 * Assigning the index while building the list makes the two the same thing by
 * construction. This lives outside the component so the property can be
 * asserted rather than assumed.
 */

export type PaletteRow<C, O> =
  | { type: 'header'; key: string; label: string }
  | { type: 'command'; key: string; index: number; value: C }
  | { type: 'object'; key: string; index: number; value: O }

export interface RowInput<C, O> {
  commands: C[]
  commandKey: (c: C) => string
  /** Object groups in the order they should paint. */
  groups: { key: string; label: string; items: O[] }[]
  objectKey: (o: O) => string
  /** Shown only when the query is empty. */
  pinned?: { label: string; keyPrefix: string; items: O[] }
  recent?: { label: string; keyPrefix: string; items: O[] }
  showSuggestions: boolean
}

export function buildRows<C, O>(input: RowInput<C, O>): PaletteRow<C, O>[] {
  const out: PaletteRow<C, O>[] = []
  let index = 0

  const section = (label: string, headerKey: string, items: O[], prefix: string) => {
    if (!items.length) return
    out.push({ type: 'header', key: headerKey, label })
    for (const o of items) {
      out.push({ type: 'object', key: `${prefix}${input.objectKey(o)}`, index, value: o })
      index += 1
    }
  }

  if (input.commands.length) {
    out.push({ type: 'header', key: 'h:commands', label: 'Commands' })
    for (const c of input.commands) {
      out.push({ type: 'command', key: `c:${input.commandKey(c)}`, index, value: c })
      index += 1
    }
  }

  for (const g of input.groups) section(g.label, `h:${g.key}`, g.items, 'o:')

  if (input.showSuggestions) {
    if (input.pinned) section(input.pinned.label, 'h:pinned', input.pinned.items, input.pinned.keyPrefix)
    if (input.recent) section(input.recent.label, 'h:recent', input.recent.items, input.recent.keyPrefix)
  }

  return out
}

/** The rows a cursor can land on, in paint order. */
export function selectableRows<C, O>(
  rows: PaletteRow<C, O>[],
): Extract<PaletteRow<C, O>, { index: number }>[] {
  return rows.filter((r): r is Extract<PaletteRow<C, O>, { index: number }> => r.type !== 'header')
}
