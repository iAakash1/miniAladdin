'use client'

/**
 * Filed financials, across securities, without pretending the years line up.
 *
 * This exists because of what the data actually contains. Asking the current
 * providers for the latest filed Revenue gives fiscal 2018 for Apple, fiscal
 * 2010 for Microsoft and fiscal 2026 for NVIDIA. Put those three numbers in a
 * row labelled "Revenue" and the table says NVIDIA earns twice what Microsoft
 * does — off by roughly a factor of four, from a source that is individually
 * correct in every cell.
 *
 * Even where coverage is good the years still differ, because fiscal years
 * do: Apple's ends in September, Microsoft's in June, NVIDIA's in January.
 * Net income comes back as FY2025 for one and FY2026 for the others, and
 * those are not the same twelve months.
 *
 * So the period is rendered in the cell, next to its number, always — not in
 * a column header, which would assert a shared year none of them has. Where
 * the years differ the row says so before the reader can draw a conclusion
 * from it. Nothing is aligned, interpolated, restated or filled forward.
 *
 * The comparability judgement is not made here. It comes from the same
 * `comparable()` the rest of the product uses, extended to understand
 * periods, so this surface cannot drift from the security page's idea of
 * what may be compared.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { comparable } from '@/lib/semantics'
import { format } from '@/lib/quantity'
import { fetchResearch } from '@/lib/research-cache'

interface Fact {
  fiscal_year?: number
  value?: number
  unit?: string
  form?: string
  filed?: string
}

/** The latest filed fact for one concept, for one security. */
interface Latest {
  value: number
  year: number
  unit?: string
  form?: string
  filed?: string
}

type Facts = Record<string, Latest | undefined>

const CONCEPTS: { group: string; items: string[] }[] = [
  { group: 'Operations', items: ['Revenue', 'Net income', 'R&D expense'] },
  { group: 'Position', items: ['Total assets', 'Total liabilities', 'Shareholders’ equity', 'Cash & equivalents', 'Long-term debt'] },
  { group: 'Returned to shareholders', items: ['Share repurchases', 'Dividends paid'] },
]

function latestOf(facts: Fact[] | undefined): Latest | undefined {
  if (!facts?.length) return undefined
  let best: Latest | undefined
  for (const f of facts) {
    if (typeof f.value !== 'number' || typeof f.fiscal_year !== 'number') continue
    if (!best || f.fiscal_year > best.year) {
      best = { value: f.value, year: f.fiscal_year, unit: f.unit, form: f.form, filed: f.filed }
    }
  }
  return best
}

type State =
  | { phase: 'reading' }
  | { phase: 'ready'; key: string; bySymbol: Record<string, Facts>; failed: string[] }

export default function FiledComparison({ symbols }: { symbols: string[] }) {
  const key = symbols.join(',')
  const [state, setState] = useState<State>({ phase: 'reading' })

  useEffect(() => {
    let alive = true
    Promise.all(symbols.map(async (s) => {
      try {
        const raw = await fetchResearch(s)
        const xbrl = (raw as { filings?: { xbrl?: Record<string, Fact[]> } }).filings?.xbrl ?? {}
        const out: Facts = {}
        for (const { items } of CONCEPTS) {
          for (const c of items) out[c] = latestOf(xbrl[c])
        }
        return { s, out, ok: true as const }
      } catch {
        return { s, out: {} as Facts, ok: false as const }
      }
    })).then((results) => {
      if (!alive) return
      const bySymbol: Record<string, Facts> = {}
      const failed: string[] = []
      for (const r of results) {
        bySymbol[r.s] = r.out
        if (!r.ok) failed.push(r.s)
      }
      setState({ phase: 'ready', key, bySymbol, failed })
    })
    return () => { alive = false }
  }, [key, symbols])

  if (state.phase === 'reading' || state.key !== key) {
    return <Panel title="Filed financials" state="waking"><StateBlock state="waking" title="Reading filings for each security" /></Panel>
  }

  const rows = CONCEPTS.map((g) => ({
    ...g,
    items: g.items.filter((c) => symbols.some((s) => state.bySymbol[s]?.[c])),
  })).filter((g) => g.items.length)

  if (!rows.length) {
    return (
      <EmptyLine label="Filed financials">
        No XBRL facts were returned for any of these securities. That is an
        absence in the filing data, not a statement that nothing was filed.
      </EmptyLine>
    )
  }

  return (
    <Panel
      title="Filed financials"
      subtitle="SEC XBRL · each security’s own latest filed year"
      flush
    >
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact fcmp">
          <thead>
            <tr>
              <th scope="col">Concept</th>
              {symbols.map((s) => <th scope="col" key={s} className="num">{s}</th>)}
            </tr>
          </thead>
          {rows.map((g) => (
            <tbody key={g.group}>
              <tr className="fin__group">
                <th scope="rowgroup" colSpan={symbols.length + 1}>{g.group}</th>
              </tr>
              {g.items.map((concept) => {
                const cells = symbols.map((s) => ({ s, f: state.bySymbol[s]?.[concept] }))
                const present = cells.filter((c) => c.f)
                const years = [...new Set(present.map((c) => c.f!.year))]

                /* The judgement comes from the shared engine, not from this
                   component, so the comparison page and the security page
                   cannot disagree about what may be compared. Two present
                   observations are enough to ask. */
                const caveat = present.length >= 2
                  ? comparable(
                    { kind: 'currency', period: `FY${present[0].f!.year}` },
                    { kind: 'currency', period: `FY${present[present.length - 1].f!.year}` },
                  ).caveat
                  : undefined

                const spread = years.length > 1
                  ? Math.max(...years) - Math.min(...years)
                  : 0

                return (
                  <tr key={concept} className={spread >= 3 ? 'fcmp__wide' : undefined}>
                    <td>
                      {concept}
                      {caveat ? (
                        <span
                          className={spread >= 3 ? 'fcmp__warn' : 'fcmp__note'}
                          title={caveat}
                        >
                          {years.length > 1
                            ? `${years.length} different fiscal years`
                            : caveat}
                        </span>
                      ) : null}
                    </td>
                    {cells.map(({ s, f }) => (
                      <td key={s} className="num">
                        {f ? (
                          <Inspectable refValue={{
                            label: `${s} · ${concept} · FY${f.year}`,
                            display: format(f.value, 'currency', { digits: 0 }).text,
                            unit: f.unit ?? undefined,
                            source: `SEC ${f.form ?? 'filing'}`,
                            asOf: `fiscal year ${f.year}`,
                            filedAt: f.filed,
                            method: 'latest filed XBRL fact for this concept — not restated, not aligned to any other security',
                            status: 'recorded',
                          }}>
                            <span className="fcmp__v"><Value value={f.value} kind="currency" digits={0} /></span>
                            {/* The period sits with its number, never in the
                                column header — a header would assert a shared
                                year that none of these securities has. */}
                            <span className="fcmp__fy">FY{f.year}</span>
                          </Inspectable>
                        ) : (
                          <span className="sys-null" title="no filed fact returned for this concept">—</span>
                        )}
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          ))}
        </table>
      </div>

      <Prose size="fine">
        Each figure is that security&apos;s own most recently filed value for the
        concept, on its own fiscal calendar — Apple&apos;s year ends in September,
        Microsoft&apos;s in June, NVIDIA&apos;s in January, so the same label rarely
        means the same twelve months. Rows where the filed years differ say so.
        Nothing here is aligned, restated, interpolated or carried forward, and
        a concept with no filed fact is an em dash rather than a zero.
      </Prose>

      {state.failed.length ? (
        <Prose size="fine">
          Filings could not be read for {state.failed.join(', ')}. Those columns
          are empty for that reason, not because nothing was filed.
        </Prose>
      ) : null}
    </Panel>
  )
}
