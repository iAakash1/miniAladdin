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

  /**
   * Which vendors supplied this particular field.
   *
   * Distinct from `source`, which names where the value came from as a single
   * string. The research engine merges several vendors per field and records
   * who contributed to each; a reader deciding whether to trust a headcount is
   * better served by "polygon and yfinance" than by "the research payload".
   */
  providers?: string[]

  /**
   * Vendors that disagree about this field, and by how much.
   *
   * The merge engine already detects these and the interface has been
   * discarding them: Apple's employee count is reported as 166,000 by one
   * vendor and 150,000 by another, and the profile rendered their midpoint as
   * a single confident 158,000. A disputed number presented as settled is the
   * most dangerous kind of number this product can show, because nothing
   * about it looks wrong.
   */
  conflict?: {
    observations: { provider: string; value: number | string | null }[]
    spreadPct?: number | null
  }

  /**
   * When the source document was filed, for a figure that comes from one.
   *
   * Distinct from `retrievedAt`, which is when this product fetched it. A
   * 10-K fact carried both and only the fetch had a label — so a 2018 filing
   * date rendered under the word "Retrieved", which says this product read it
   * in 2018. It did not; the company filed it then.
   */
  filedAt?: string

  /**
   * What the terminal is asserting by showing this number.
   *
   * The first link of the chain, and the one most products skip. A figure on
   * screen is a claim — "Apple's market capitalisation is 4.73 trillion
   * dollars" — and the rest of the chain exists to say how much weight it
   * carries. Where this is absent the inspector says the claim was not
   * recorded rather than inventing one from the label.
   */
  claim?: string

  /**
   * What was actually observed, as distinct from what is being claimed.
   *
   * These differ more often than they look like they should. The claim is
   * "revenue was 215.64 billion dollars"; the observation is "one XBRL fact
   * tagged Revenues in a 10-K for fiscal 2018". The claim is about a company;
   * the observation is about a document.
   */
  observation?: string

  /**
   * What had to be true for the claim to follow from the observation.
   *
   * The step that turns a number into a judgement, and the one worth reading
   * before trusting it — that the provider's field means what its name says,
   * that the period matches the one requested, that no later filing
   * supersedes it.
   */
  assumptions?: string[]

  /**
   * When this should not be trusted, for figures the handbook does not cover.
   *
   * The handbook carries `fails_when` for registered measures. Most numbers
   * on screen are not registered measures, and "no failure conditions are
   * recorded" is honest but unhelpful when the caller knows perfectly well
   * what would break the figure.
   */
  failsWhen?: string[]

  /**
   * How long a value of this kind may be reused before it is re-read. Names
   * the policy, not the age — "this is a snapshot, good for a minute" rather
   * than "this is 41 seconds old".
   */
  freshness?: string
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
