/**
 * A shared cursor across every chart on a screen.
 *
 * A researcher looking at a drawdown in one chart wants to know what turnover,
 * cost and information coefficient were doing on the same date. With
 * independent cursors that means reading a date off one axis and hunting for it
 * on another, which is slow enough that nobody does it — so the comparison that
 * matters most never gets made.
 *
 * One cursor makes it free. Hovering any chart broadcasts the date; every chart
 * that has that date draws its crosshair there.
 *
 * The cursor is a date string, not an index. Charts here have different
 * lengths, different frequencies and different start points, and an index would
 * silently align the ninth observation of one series with the ninth of another.
 */
'use client'

import {
  createContext, useCallback, useContext, useMemo, useState, type ReactNode,
} from 'react'

interface CursorValue {
  /** The date under the pointer, or null. */
  at: string | null
  set: (at: string | null) => void
  /** True when some chart is driving the cursor. */
  active: boolean
}

const Ctx = createContext<CursorValue | null>(null)

export function ChartCursorProvider({ children }: { children: ReactNode }) {
  const [at, setAt] = useState<string | null>(null)
  const set = useCallback((next: string | null) => setAt(next), [])
  const value = useMemo(() => ({ at, set, active: at !== null }), [at, set])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useChartCursor(): CursorValue {
  // Outside a provider each chart keeps its own cursor, which is the correct
  // fallback: a lone chart has nothing to synchronise with.
  const ctx = useContext(Ctx)
  return ctx ?? { at: null, set: () => {}, active: false }
}
