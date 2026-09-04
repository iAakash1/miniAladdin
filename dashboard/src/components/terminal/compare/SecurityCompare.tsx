'use client'

/**
 * Two companies, side by side, with the arithmetic refused where it would lie.
 *
 * The comparison machinery already exists and already knows what may be
 * subtracted from what — same class, same scale, same basis. This gives it
 * securities to work on.
 *
 * The interesting cases are the ones it declines. A price-to-earnings multiple
 * and a margin are both dimensionless and both come back as plain numbers; the
 * difference between them means nothing. A trailing-twelve-month margin and a
 * five-year average describe different windows. The panel states which pairs
 * it will not difference and why, rather than showing a plausible number.
 *
 * Both symbols share the research cache, so a comparison of two names already
 * open costs nothing beyond what those pages already fetched.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { delta, deltaMoved } from '@/lib/semantics'
import type { Kind } from '@/lib/quantity'
import { fetchResearch } from '@/lib/research-cache'
import { useQuotes } from '@/lib/use-quotes'

interface Side {
  symbol: string
  name?: string | null
  ratios: Record<string, number | null | undefined>
  marketCap?: number | null
}

/** A row is one measurement, read the same way on both sides. */
interface Field {
  label: string
  key: string
  kind: Kind
  /** The window it describes. Two fields differing only in period are
   *  deliberately separate rows; they are not the same measurement. */
  period?: string
  group: string
  /** Where the metric's own direction does not match its role here. */
  direction?: 'higher-better' | 'lower-better'
  digits?: number
}

const FIELDS: Field[] = [
  { group: 'Valuation', label: 'Market cap', key: 'market_cap', kind: 'currency', digits: 0 },
  { group: 'Valuation', label: 'Price / earnings', key: 'pe_ratio', kind: 'multiple', direction: 'lower-better' },
  { group: 'Valuation', label: 'Price / sales', key: 'price_to_sales', kind: 'multiple', direction: 'lower-better' },
  { group: 'Valuation', label: 'Price / book', key: 'price_to_book', kind: 'multiple', direction: 'lower-better' },
  { group: 'Valuation', label: 'EV / EBITDA', key: 'ev_to_ebitda', kind: 'multiple', direction: 'lower-better' },

  { group: 'Profitability', label: 'Gross margin', key: 'gross_margin_ttm', kind: 'percent', period: 'TTM', direction: 'higher-better' },
  { group: 'Profitability', label: 'Operating margin', key: 'operating_margin_ttm', kind: 'percent', period: 'TTM', direction: 'higher-better' },
  { group: 'Profitability', label: 'Net margin', key: 'net_margin_ttm', kind: 'percent', period: 'TTM', direction: 'higher-better' },
  { group: 'Profitability', label: 'Net margin', key: 'net_margin_5y', kind: 'percent', period: '5-year average', direction: 'higher-better' },
  { group: 'Profitability', label: 'Return on equity', key: 'roe_ttm', kind: 'percent', period: 'TTM', direction: 'higher-better' },

  { group: 'Growth', label: 'Revenue growth', key: 'revenue_growth_ttm_yoy', kind: 'percent', period: 'TTM, year on year', direction: 'higher-better', digits: 2 },
  { group: 'Growth', label: 'Revenue growth', key: 'revenue_growth_3y', kind: 'percent', period: '3-year', direction: 'higher-better', digits: 2 },
  { group: 'Growth', label: 'EPS growth', key: 'eps_growth_ttm_yoy', kind: 'percent', period: 'TTM, year on year', direction: 'higher-better', digits: 2 },

  { group: 'Financial position', label: 'Current ratio', key: 'current_ratio', kind: 'multiple', direction: 'higher-better' },
  { group: 'Financial position', label: 'Debt / equity', key: 'debt_to_equity', kind: 'multiple', direction: 'lower-better' },
]

function useSide(symbol: string): { side: Side | null; error: string | null } {
  const [state, setState] = useState<{ for: string; side?: Side; error?: string } | null>(null)

  useEffect(() => {
    if (!symbol) return
    let alive = true
    fetchResearch(symbol)
      .then((d) => {
        if (!alive) return
        const profile = (d.profile ?? {}) as { name?: string; market_cap?: number }
        setState({
          for: symbol,
          side: {
            symbol,
            name: profile.name ?? null,
            marketCap: profile.market_cap ?? null,
            ratios: (d.ratios ?? {}) as Record<string, number | null>,
          },
        })
      })
      .catch((e: Error) => { if (alive) setState({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const current = state?.for === symbol ? state : null
  return { side: current?.side ?? null, error: current?.error ?? null }
}

export default function SecurityCompare({ a, b }: { a: string; b: string }) {
  const left = useSide(a)
  const right = useSide(b)
  const { quotes } = useQuotes([a, b].filter(Boolean))

  if (!a || !b) {
    return (
      <Panel title="Compare" state="unknown">
        <StateBlock
          state="unknown"
          title="Choose two securities"
          detail="Add ?a=AAPL&b=MSFT to compare, or open a security and compare from there."
        />
      </Panel>
    )
  }

  const value = (side: Side | null, f: Field): number | null => {
    if (!side) return null
    const raw = f.key === 'market_cap' ? side.marketCap : side.ratios[f.key]
    return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
  }

  const groups = [...new Set(FIELDS.map((f) => f.group))]

  return (
    <>
      <Panel
        title="Compare"
        subtitle={`${a} against ${b}`}
        state={left.error || right.error ? 'unavailable' : left.side && right.side ? 'live' : 'waking'}
      >
        <div className="cmp-heads">
          {[{ s: a, q: quotes[a], side: left.side }, { s: b, q: quotes[b], side: right.side }].map((x) => (
            <div key={x.s} className="cmp-head">
              <span className="cmp-head__sym">{x.s}</span>
              <span className="sys-meta">{x.side?.name ?? '—'}</span>
              <span className="cmp-head__px">
                <Value value={x.q?.price ?? null} kind="currency" />
                <Value value={x.q?.change_1d ?? null} kind="percent" digits={2} signed tone />
              </span>
            </div>
          ))}
        </div>

        {left.error || right.error ? (
          <StateBlock
            state="unavailable"
            title="One side could not be read"
            detail={`${left.error ?? right.error}. No comparison is shown against a missing side — a difference against an absent value is not a difference.`}
          />
        ) : !left.side || !right.side ? (
          <StateBlock state="waking" title="Reading both companies" detail="The vendor fan-out takes half a minute for each; they share a cache with their security pages." />
        ) : (
          groups.map((g) => (
            <section key={g} className="cmp-group">
              <h3 className="sys-label cmp-group__title">{g}</h3>
              {/* Headers and numeric cells do not wrap, so on a narrow
                  viewport the table is what scrolls — never the page. */}
              <div className="sys-scroll-x">
              <table className="sys-table sys-table--compact cmp">
                <thead>
                  <tr>
                    <th>Measure</th>
                    <th className="num">{a}</th>
                    <th className="num">{b}</th>
                    <th className="num">Difference</th>
                  </tr>
                </thead>
                <tbody>
                  {FIELDS.filter((f) => f.group === g).map((f) => {
                    const va = value(left.side, f)
                    const vb = value(right.side, f)
                    const d = delta(vb, va, { kind: f.kind }, { kind: f.kind })
                    // The field's role wins over the kind's default, the same
                    // rule the research comparison uses: a lower P/E is the
                    // better one, and a multiple has no inherent direction.
                    // Measured through deltaMoved, because a multiplicative
                    // delta is a ratio whose neutral point is 1, not 0.
                    const moved = deltaMoved(d)
                    const verdict = f.direction && moved !== null
                      ? ((f.direction === 'higher-better') === (moved > 0) ? 'better' : 'worse')
                      : d.interpretation

                    return (
                      <tr key={`${f.key}-${f.period ?? ''}`}>
                        <td className="cmp__k">
                          {f.label}
                          {f.period ? <span className="fund__period">{f.period}</span> : null}
                        </td>
                        <td className="num"><Value value={va} kind={f.kind} digits={f.digits} /></td>
                        <td className="num"><Value value={vb} kind={f.kind} digits={f.digits} /></td>
                        <td className="num">
                          {d.value === null ? (
                            <span className="sys-meta" title={d.reason}>
                              {va === null || vb === null ? 'one side missing' : 'not comparable'}
                            </span>
                          ) : (
                            <span
                              className={verdict === 'better' ? 'sys-pos' : verdict === 'worse' ? 'sys-neg' : ''}
                              title={f.direction ? `${verdict} for ${b}` : 'no declared direction: this difference is not an improvement'}
                            >
                              {d.formatted?.text ?? '—'}
                              {/* The difference's own unit: percentage points
                                  between two percentages, × between two
                                  multiples. Without it, +19.3 between margins
                                  of 48.6% and 67.9% reads as a percentage. */}
                              {d.unit ? <span className="unit">{d.unit}</span> : null}
                            </span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              </div>
            </section>
          ))
        )}
      </Panel>

      <Panel title="What is not compared here" state="recorded">
        <Prose>
          Only measurements of the same kind, on the same scale, over the same
          window are differenced. A price-to-earnings multiple and a margin are
          both plain numbers and the difference between them means nothing; a
          trailing-twelve-month margin and a five-year average describe
          different periods and appear as separate rows rather than as one.
        </Prose>
        <Prose size="tight">
          A difference against a value one side did not report is not shown as
          zero. <Status state="unavailable" label="one side missing" /> is the
          honest answer, and it is a different statement from the two being
          equal.
        </Prose>
      </Panel>
    </>
  )
}
