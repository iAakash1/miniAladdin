/**
 * Building the palette's render list.
 *
 * The palette paints section headers and selectable rows in one column while
 * the keyboard cursor is a single flat index. Assigning the index while the
 * list is built makes the painted order and the cursor order the same thing
 * by construction — the highlighted row is always the row Enter opens.
 */

export type PaletteRow<T> =
  | { type: 'header'; key: string; label: string; note?: string }
  | { type: 'item'; key: string; index: number; value: T }

export interface PaletteSection<T> {
  key: string
  label: string
  /** A qualifier shown beside the section label. */
  note?: string
  items: T[]
  itemKey: (item: T) => string
}

/** Sections in paint order. Empty sections produce no header. */
export function buildRows<T>(sections: PaletteSection<T>[]): PaletteRow<T>[] {
  const out: PaletteRow<T>[] = []
  let index = 0
  for (const section of sections) {
    if (!section.items.length) continue
    out.push({ type: 'header', key: `h:${section.key}`, label: section.label, note: section.note })
    for (const item of section.items) {
      out.push({ type: 'item', key: `${section.key}:${section.itemKey(item)}`, index, value: item })
      index += 1
    }
  }
  return out
}

/** The rows a cursor can land on, in paint order. */
export function selectableRows<T>(rows: PaletteRow<T>[]): Extract<PaletteRow<T>, { index: number }>[] {
  return rows.filter((r): r is Extract<PaletteRow<T>, { index: number }> => r.type !== 'header')
}
