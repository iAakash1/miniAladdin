/**
 * The metric inspection system.
 *
 * A number on screen is the end of a long argument — a method, a unit, a
 * frequency, an annualisation, a source, a moment it was retrieved, and a set
 * of conditions under which it stops being true. Printing only the figure
 * throws all of that away and asks the reader to take it on trust.
 *
 * So any figure can declare what it is, and clicking it opens the rest. The
 * handbook is fetched once per session and shared, because the same twenty-odd
 * measures appear on every screen and refetching them per panel would be absurd.
 *
 * This is one system, mounted once at the shell. There is no second path for
 * inspecting a number.
 */
'use client'

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from 'react'

import { readResource } from '@/lib/resource'

export interface MetricRef {
  /** Handbook key, when the engine defines one. */
  measure?: string
  /** Display name. Falls back to the measure key. */
  label: string
  /** The rendered value, as text. Not re-formatted here. */
  display: string
  unit?: string
  /** Where this particular value came from, when known. */
  source?: string
  asOf?: string
  retrievedAt?: string
  /** How this instance was produced, when it differs from the handbook entry. */
  method?: string
  /** Research state of the value itself. */
  status?: string
  /** Additional context the caller wants carried into the inspector. */
  note?: string
}

export interface HandbookEntry {
  name: string
  unit: string
  annualisation: string
  inputs: string[]
  return_units_required: boolean
  minimum_observations: number
  purpose: string | null
  fails_when: string | null
}

interface MetricContextValue {
  inspect: (ref: MetricRef) => void
  close: () => void
  current: MetricRef | null
  entry: (measure?: string) => HandbookEntry | undefined
  /** Short definition for a hover, without opening anything. */
  summary: (measure?: string) => string | undefined
}

const Ctx = createContext<MetricContextValue | null>(null)

/** Shared across the session: the same measures appear on every screen. */
let cache: Map<string, HandbookEntry> | null = null
let inflight: Promise<Map<string, HandbookEntry>> | null = null

async function loadHandbook(): Promise<Map<string, HandbookEntry>> {
  if (cache) return cache
  if (inflight) return inflight
  inflight = (async () => {
    try {
      const d = await readResource<{ entries?: HandbookEntry[] }>('/api/quant/methodology', 'reference')
      cache = new Map((d.entries ?? []).map((e) => [e.name, e]))
    } catch {
      // A handbook that cannot be read must not stop a number rendering. The
      // inspector says the definition is unavailable rather than inventing one.
      cache = new Map()
    }
    inflight = null
    return cache
  })()
  return inflight
}

export function MetricProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<MetricRef | null>(null)
  const [book, setBook] = useState<Map<string, HandbookEntry> | null>(cache)

  useEffect(() => {
    let alive = true
    loadHandbook().then((m) => { if (alive) setBook(m) })
    return () => { alive = false }
  }, [])

  const inspect = useCallback((ref: MetricRef) => setCurrent(ref), [])
  const close = useCallback(() => setCurrent(null), [])
  const entry = useCallback((measure?: string) => (measure ? book?.get(measure) : undefined), [book])
  const summary = useCallback(
    (measure?: string) => (measure ? book?.get(measure)?.purpose ?? undefined : undefined),
    [book],
  )

  const value = useMemo(
    () => ({ inspect, close, current, entry, summary }),
    [inspect, close, current, entry, summary],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useMetrics(): MetricContextValue {
  const ctx = useContext(Ctx)
  if (ctx) return ctx
  // Outside a provider a metric is still a number; it simply cannot be opened.
  return {
    inspect: () => {},
    close: () => {},
    current: null,
    entry: () => undefined,
    summary: () => undefined,
  }
}
