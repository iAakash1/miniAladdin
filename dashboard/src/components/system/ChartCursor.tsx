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
 *
 * Focus is the second half of the same idea, along the other axis. A chart of
 * six models beside a table of six models are two views of one set of things,
 * and the reader should not have to match a colour swatch to a row by eye.
 * Pointing at either lifts the same model out of both. Focus is keyed by name
 * rather than position, for the same reason the cursor is keyed by date.
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
  /** The name of the series or object under the pointer, or null. */
  focus: string | null
  setFocus: (name: string | null) => void
}

const Ctx = createContext<CursorValue | null>(null)

export function ChartCursorProvider({ children }: { children: ReactNode }) {
  const [at, setAt] = useState<string | null>(null)
  const [focus, setFocusState] = useState<string | null>(null)
  const set = useCallback((next: string | null) => setAt(next), [])
  const setFocus = useCallback((next: string | null) => setFocusState(next), [])
  const value = useMemo(
    () => ({ at, set, active: at !== null, focus, setFocus }),
    [at, set, focus, setFocus],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useChartCursor(): CursorValue {
  // Outside a provider each chart keeps its own cursor, which is the correct
  // fallback: a lone chart has nothing to synchronise with.
  const ctx = useContext(Ctx)
  return ctx ?? { at: null, set: () => {}, active: false, focus: null, setFocus: () => {} }
}
