'use client'

/**
 * What the company filed, by fiscal year.
 *
 * These are XBRL facts from SEC filings — primary source, not a vendor's
 * interpretation of one. Each carries the concept, the fiscal year, the unit,
 * the form it came from and the date it was filed, and every one of those
 * travels with the number to the screen.
 *
 * The design is driven by a single hazard found in the data itself. Coverage
 * is uneven: Apple has six years of net income, total assets and shareholders'
 * equity, but exactly one Revenue fact — from fiscal 2018 — and one Dividends
 * paid fact from 2017. A sheet that printed "Revenue $215.64B" next to
 * "Net income $96.99B" would be showing figures seven years apart as though
 * they described the same business, and nothing on screen would say so.
 *
 * So the fiscal year is not a caption here. It is the column. A concept
 * appears in the year it was filed for and nowhere else, a year with no fact
 * is an em dash rather than a carried-forward value, and a row whose most
 * recent filing is old says how old before it says anything else.
 *
 * Nothing is derived. There are no margins, no growth rates and no ratios in
 * this table — those belong to the ratio surface above, which is computed from
 * a different source on a different basis. Mixing a filed fact with a derived
 * one in a single grid is how a reader ends up unable to say which is which.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'
import { format } from '@/lib/quantity'

interface Fact {
  fiscal_year?: number
  value?: number
  unit?: string
  form?: string
  filed?: string
}

type Xbrl = Record<string, Fact[]>

/* The statement each concept belongs to. Concepts the engine does not return
   simply do not appear — this is a map for grouping, never a list of rows to
   render whether or not there is data behind them. */
const GROUPS: { title: string; note: string; concepts: string[] }[] = [
  {
    title: 'Operations',
    note: 'What the business earned and what it spent to earn it.',
    concepts: ['Revenue', 'Net income', 'R&D expense'],
  },
  {
    title: 'Position',
    note: 'What it owns and owes at the fiscal year end.',
    concepts: ['Total assets', 'Total liabilities', 'Shareholders’ equity', 'Cash & equivalents', 'Long-term debt'],
  },
  {
    title: 'Returned to shareholders',
    note: 'Cash paid out, as filed.',
    concepts: ['Share repurchases', 'Dividends paid'],
  },
]

type Answer = { for: string; xbrl: Xbrl } | { for: string; error: string }

export default function Financials({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = raw as { filings?: { xbrl?: Xbrl } }
        setAnswer({ for: symbol, xbrl: d.filings?.xbrl ?? {} })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  if (!settled) return <Panel title="Filed financials" state="waking"><StateBlock state="waking" title="Reading filings" /></Panel>

  if ('error' in settled) {
    return (
      <Panel title="Filed financials" state="unavailable">
        <StateBlock
          state="unavailable"
          title="Filings could not be read"
          detail={`${settled.error}. Nothing is shown in their place.`}
        />
      </Panel>
    )
  }

  const xbrl = settled.xbrl
  const present = Object.entries(xbrl).filter(([, facts]) => facts?.length)
  if (!present.length) {
    return (
      <EmptyLine label="Filed financials">
        No XBRL facts were returned for this security. That is an absence in
        the filing data, not a statement that the company filed nothing.
      </EmptyLine>
    )
  }

  /* The years actually filed, newest first. Built from the facts rather than
     from a range, so a year nobody filed never becomes a column of dashes. */
  const years = [...new Set(
    present.flatMap(([, facts]) => facts.map((f) => f.fiscal_year).filter((y): y is number => typeof y === 'number')),
  )].sort((a, b) => b - a)

  const latestYear = years[0]

  return (
    <Panel
      title="Filed financials"
      subtitle={`SEC XBRL · fiscal ${years[years.length - 1]}–${latestYear}`}
      flush
    >
      <div className="sys-scroll-x">
        <table className="sys-table sys-table--compact fin">
          <thead>
            <tr>
              <th scope="col">Concept</th>
              {years.map((y) => (
                <th scope="col" key={y} className="num">FY{y}</th>
              ))}
            </tr>
          </thead>
          {GROUPS.map((g) => {
            const rows = g.concepts.filter((c) => xbrl[c]?.length)
            if (!rows.length) return null
            return (
              <tbody key={g.title}>
                <tr className="fin__group">
                  <th scope="rowgroup" colSpan={years.length + 1}>
                    {g.title}
                    <span className="fin__note">{g.note}</span>
                  </th>
                </tr>
                {rows.map((concept) => {
                  const facts = xbrl[concept]
                  const byYear = new Map(facts.map((f) => [f.fiscal_year, f]))
                  const newest = Math.max(...facts.map((f) => f.fiscal_year ?? -Infinity))
                  /* A concept whose most recent filing is behind the others is
                     the trap this table exists to make visible. Apple's only
                     Revenue fact is from 2018; printed beside a 2025 net
                     income it would read as the same year's business. */
                  const behind = typeof latestYear === 'number' && newest < latestYear

                  return (
                    <tr key={concept}>
                      <td>
                        {concept}
                        {behind ? (
                          <span className="fin__behind" title={`The most recent filed value for this concept is fiscal ${newest}. Later years were not returned.`}>
                            latest FY{newest}
                          </span>
                        ) : null}
                      </td>
                      {years.map((y) => {
                        const f = byYear.get(y)
                        if (!f || typeof f.value !== 'number') {
                          // No fact for this year. Never the previous year's
                          // number, and never a zero.
                          return <td key={y} className="num"><span className="sys-null">—</span></td>
                        }
                        return (
                          <td key={y} className="num">
                            <Inspectable
                              refValue={{
                                label: `${concept} · FY${y}`,
                                // The figure as this table renders it. Showing
                                // 215639000000 where the cell reads 215.64B
                                // makes the drawer look like a different number.
                                display: format(f.value, 'currency', { digits: 0 }).text,
                                unit: f.unit ?? undefined,
                                source: `SEC ${f.form ?? 'filing'}`,
                                asOf: `fiscal year ${y}`,
                                // When the company filed it — not when this
                                // product fetched it.
                                filedAt: f.filed,
                                method: 'XBRL fact as filed — not restated, not derived',
                                freshness: 'a filed fact does not go stale; it is superseded by a later filing',
                                status: 'recorded',
                              }}
                            >
                              <Value value={f.value} kind="currency" digits={0} />
                            </Inspectable>
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            )
          })}
        </table>
      </div>

      <Prose size="fine">
        Facts as filed with the SEC, by the company&apos;s own fiscal year — not
        calendar years, and not trailing twelve months. A blank cell is a year
        this concept was not returned for, never a carried-forward value. These
        are filed figures only: margins, growth and ratios are computed
        elsewhere from a different source and are deliberately not mixed in here.
      </Prose>
    </Panel>
  )
}
