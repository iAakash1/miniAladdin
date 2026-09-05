'use client'

/**
 * What the company filed, by fiscal year.
 *
 * These are XBRL facts from SEC filings — primary source, not a vendor's
 * interpretation of one. Each carries the concept, the fiscal year, the unit,
 * the form it came from and the date it was filed, and every one of those
 * travels with the number to the screen.
 *
 * The design is driven by a hazard found in the data itself: coverage is
 * uneven, and a sheet that printed "Revenue" from one year beside "Net
 * income" from another would show figures years apart as though they
 * described the same business.
 *
 * So the fiscal year is not a caption here. It is the column. A concept
 * appears in the year it was filed for and nowhere else, a year with no fact
 * is an em dash rather than a carried-forward value, and a row whose most
 * recent filing is old says how old before it says anything else.
 *
 * Much of that unevenness turned out to be ours rather than the filers'.
 * Apple's revenue series was a single fact from 2018 and Microsoft's a single
 * fact from 2010, because several XBRL tags map to one label and the adapter
 * kept whichever it met first — Apple tagged `Revenues` once, in 2018, and
 * used the contract-with-customer tag for every year since. And the fiscal
 * year came from EDGAR's `fy`, which is the *filing's* year rather than the
 * fact's period: a 10-K carries a comparative balance sheet, so Apple's
 * FY2025 filing supplies assets for both 2025-09-27 and 2024-09-28 with
 * `fy: 2025` on both, and the column labelled FY2025 held 2024's balance
 * sheet. Facts are now keyed by the period they describe, which is why the
 * reconciliation warning below has stopped firing for these names — it was
 * reporting a real inconsistency with a cause upstream of the filings.
 *
 * The period end travels with each fact and is shown in the inspector, so
 * the label FY2025 can always be checked against the date it stands for.
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
  /** The period the fact describes — the authority the year label is derived from. */
  period_end?: string
  period_start?: string
  value?: number
  unit?: string
  form?: string
  filed?: string
  /** Which XBRL tag this series came from. Filers change tags between years. */
  concept_tag?: string
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

  /* Assets = Liabilities + Equity is an identity. It holds exactly in any
     filed balance sheet, or the filing would not have been accepted. Running
     it over these facts fails, and by margins that are not rounding — 51% of
     assets for one security in one year.

     What that means is that the three concepts for a labelled fiscal year are
     not drawn from one reconciled context: different periods, different XBRL
     contexts, or a concept mapped to a tag that does not mean what its label
     says. It does not make any single fact wrong, and it does make arithmetic
     across them invalid.

     So the check runs in front of the reader rather than in a document. A
     panel that quietly displays facts failing an accounting identity is
     inviting exactly the cross-concept arithmetic the identity just proved
     unsafe. */
  const balance = years.map((y) => {
    const a = xbrl['Total assets']?.find((f) => f.fiscal_year === y)?.value
    const l = xbrl['Total liabilities']?.find((f) => f.fiscal_year === y)?.value
    const e = xbrl['Shareholders’ equity']?.find((f) => f.fiscal_year === y)?.value
    if (typeof a !== 'number' || typeof l !== 'number' || typeof e !== 'number' || !a) return null
    const gap = a - (l + e)
    return { year: y, gap, pct: Math.abs(gap) / a * 100 }
  }).filter((b): b is { year: number; gap: number; pct: number } => b !== null)

  // A tenth of a per cent is presentation rounding in a filing. Anything
  // above that is a reconciliation problem.
  const unbalanced = balance.filter((b) => b.pct > 0.1)

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
                                asOf: f.period_end
                                  ? `period ending ${f.period_end}`
                                  : `fiscal year ${y}`,
                                // When the company filed it — not when this
                                // product fetched it.
                                filedAt: f.filed,
                                claim: `${concept} for fiscal ${y} was ${format(f.value, 'currency', { digits: 0 }).text}.`,
                                observation: `One XBRL fact${f.concept_tag ? `, tagged \`${f.concept_tag}\`,` : ''} in a ${f.form ?? 'filing'} covering ${f.period_start && f.period_end ? `${f.period_start} to ${f.period_end}` : f.period_end ? `the period ending ${f.period_end}` : `fiscal ${y}`}, filed ${f.filed ?? 'on an unrecorded date'}.`,
                                assumptions: [
                                  'The concept in the filing means what its label says — XBRL tags are chosen by the filer, not by a standard body.',
                                  `No later filing restates fiscal ${y}. Restatements are filed as new facts and this shows the value as originally tagged.`,
                                  `The fiscal year label is the calendar year of the period end${f.period_end ? ` (${f.period_end})` : ''}, not a calendar year of trading.`,
                                  ...(f.concept_tag
                                    ? [`Every year in this row uses the tag \`${f.concept_tag}\` — a series is never assembled from two tags, because the definition would change partway down the column.`]
                                    : []),
                                ],
                                failsWhen: [
                                  'The company restated the period after filing, in which case a later fact supersedes this one.',
                                  'The concept is sparsely tagged — several concepts here have coverage gaps of years, so the latest available fact may be far from current.',
                                ],
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

      {unbalanced.length ? (
        <div className="fin__identity">
          <div className="sys-label">These facts do not reconcile</div>
          <p>
            Assets should equal liabilities plus equity in every filed balance
            sheet. Across {unbalanced.length === 1 ? 'one year' : `${unbalanced.length} years`} here they do not
            {unbalanced.length ? `, by up to ${Math.max(...unbalanced.map((b) => b.pct)).toFixed(1)}% of assets` : ''}.
          </p>
          <ul>
            {unbalanced.slice(0, 3).map((b) => (
              <li key={b.year}>
                FY{b.year}: assets less liabilities and equity leaves{' '}
                <Value value={b.gap} kind="currency" digits={0} signed /> — {b.pct.toFixed(1)}% of assets
              </li>
            ))}
          </ul>
          <p>
            Each figure above is a real filed fact. Together they are not a
            reconciled statement, which means the concepts for one labelled
            year are not all drawn from the same context. Read them
            individually; do not compute across them.
          </p>
        </div>
      ) : null}

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
