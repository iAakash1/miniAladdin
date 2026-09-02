/**
 * The analytical table.
 *
 * Sorting, filtering, column visibility, density and keyboard navigation, in
 * one component, because a research product lives in tables and every one of
 * them needs the same affordances. A page that reimplements sorting is a page
 * that sorts differently from the one beside it.
 *
 * Sorting is null-aware and null-last in both directions. An absent value is
 * not a small value, and letting it sort as one puts unmeasured rows at the top
 * of an ascending risk column — which reads as the safest holdings.
 */
'use client'

import { useMemo, useState, type ReactNode } from 'react'

export interface DataColumn<T> {
  key: string
  header: string
  /** Unit qualifier under the header. */
  unit?: string
  numeric?: boolean
  width?: string
  /** Sort key. Return null for "not recorded" — sorted last either way. */
  sort?: (row: T) => number | string | null
  /** Free-text search target for this column. */
  text?: (row: T) => string
  render: (row: T) => ReactNode
  /** Hidden by default; revealed through the column control. */
  optional?: boolean
}

type Direction = 'asc' | 'desc'

export function DataTable<T>({
  columns, rows, rowKey, density = 'compact', onSelect, selectedKey,
  filterPlaceholder = 'filter', empty, initialSort, toolbar,
}: {
  columns: DataColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  density?: 'compact' | 'normal' | 'relaxed'
  onSelect?: (row: T) => void
  selectedKey?: string
  filterPlaceholder?: string
  empty?: ReactNode
  initialSort?: { key: string; direction: Direction }
  toolbar?: ReactNode
}) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<{ key: string; direction: Direction } | null>(initialSort ?? null)
  const [hidden, setHidden] = useState<Set<string>>(
    () => new Set(columns.filter((c) => c.optional).map((c) => c.key)),
  )
  const [columnsOpen, setColumnsOpen] = useState(false)

  const visible = useMemo(() => columns.filter((c) => !hidden.has(c.key)), [columns, hidden])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) =>
      columns.some((c) => {
        const text = c.text?.(r)
        if (text) return text.toLowerCase().includes(q)
        const s = c.sort?.(r)
        return typeof s === 'string' && s.toLowerCase().includes(q)
      }),
    )
  }, [rows, columns, query])

  const sorted = useMemo(() => {
    if (!sort) return filtered
    const col = columns.find((c) => c.key === sort.key)
    if (!col?.sort) return filtered
    const dir = sort.direction === 'asc' ? 1 : -1
    return [...filtered].sort((a, b) => {
      const av = col.sort!(a)
      const bv = col.sort!(b)
      // Null last in both directions: an absent value is not a small one.
      if (av === null && bv === null) return 0
      if (av === null) return 1
      if (bv === null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [filtered, sort, columns])

  const toggleSort = (key: string) => {
    setSort((s) =>
      s?.key !== key
        ? { key, direction: 'desc' }
        : s.direction === 'desc'
          ? { key, direction: 'asc' }
          : null,
    )
  }

  const cls = `sys-table${density === 'compact' ? ' sys-table--compact' : density === 'relaxed' ? ' sys-table--relaxed' : ''}`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 'var(--d-2)',
        padding: 'var(--d-2) var(--d-3)', borderBottom: '1px solid var(--rule)',
        background: 'var(--p-sunken)', flexWrap: 'wrap',
      }}>
        <input
          className="sys-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={filterPlaceholder}
          aria-label="Filter rows"
          style={{ width: 150 }}
        />
        <span className="sys-meta">
          {sorted.length === rows.length ? `${rows.length} rows` : `${sorted.length} of ${rows.length}`}
        </span>
        {sort ? (
          <button className="sys-btn" onClick={() => setSort(null)}>clear sort</button>
        ) : null}
        {query ? (
          <button className="sys-btn" onClick={() => setQuery('')}>clear filter</button>
        ) : null}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--d-2)', alignItems: 'center', position: 'relative' }}>
          {toolbar}
          {columns.some((c) => c.optional) || columns.length > 4 ? (
            <button className="sys-btn" aria-expanded={columnsOpen} onClick={() => setColumnsOpen((v) => !v)}>
              columns
            </button>
          ) : null}
          {columnsOpen ? (
            <div style={{
              position: 'absolute', top: '100%', right: 0, zIndex: 20, marginTop: 4,
              background: 'var(--p-panel)', border: '1px solid var(--rule-strong)',
              padding: 'var(--d-2)', minWidth: 180, display: 'flex', flexDirection: 'column', gap: 2,
            }}>
              {columns.map((c) => (
                <label key={c.key} style={{ display: 'flex', gap: 'var(--d-2)', alignItems: 'center', fontSize: 'var(--t-meta)', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={!hidden.has(c.key)}
                    onChange={() => setHidden((h) => {
                      const next = new Set(h)
                      if (next.has(c.key)) next.delete(c.key)
                      else next.add(c.key)
                      return next
                    })}
                  />
                  {c.header}
                </label>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {sorted.length === 0 ? (
        <div style={{ padding: 'var(--d-5)', color: 'var(--ink-faint)', fontSize: 'var(--t-meta)', fontFamily: 'var(--font-mono)' }}>
          {empty ?? (query ? `No row matches “${query}”.` : 'No rows.')}
        </div>
      ) : (
        <div className="sys-scroll-x">
          <table className={cls}>
            <thead>
              <tr>
                {visible.map((c) => {
                  const active = sort?.key === c.key
                  return (
                    <th key={c.key} className={c.numeric ? 'num' : undefined} style={c.width ? { width: c.width } : undefined} scope="col"
                        aria-sort={active ? (sort!.direction === 'asc' ? 'ascending' : 'descending') : undefined}>
                      {c.sort ? (
                        <span
                          className="sys-th-sort sys-focusable"
                          role="button"
                          tabIndex={0}
                          data-sorted={active ? sort!.direction : undefined}
                          onClick={() => toggleSort(c.key)}
                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleSort(c.key) } }}
                        >
                          {c.header}
                          <span className="caret" aria-hidden>{active ? (sort!.direction === 'asc' ? '▲' : '▼') : '▾'}</span>
                        </span>
                      ) : c.header}
                      {c.unit ? <span className="unit">{c.unit}</span> : null}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, index) => {
                const key = rowKey(row)
                return (
                  <tr
                    key={key}
                    data-selected={selectedKey === key}
                    tabIndex={onSelect ? 0 : undefined}
                    style={onSelect ? { cursor: 'pointer' } : undefined}
                    onClick={onSelect ? () => onSelect(row) : undefined}
                    onKeyDown={(e) => {
                      if (!onSelect) return
                      if (e.key === 'Enter') { e.preventDefault(); onSelect(row) }
                      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                        e.preventDefault()
                        const delta = e.key === 'ArrowDown' ? 1 : -1
                        const next = (e.currentTarget.parentElement?.children[index + delta] as HTMLElement | undefined)
                        next?.focus()
                      }
                    }}
                  >
                    {visible.map((c) => (
                      <td key={c.key} className={c.numeric ? 'num' : undefined}>{c.render(row)}</td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
