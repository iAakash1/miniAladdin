'use client'

/**
 * What the business looks like, grouped so it can be read.
 *
 * The provider layer has carried a rich ratio surface for a long time —
 * margins, returns, leverage, growth, valuation multiples — and none of it
 * reached the interface. The vendor returns a hundred and thirty figures per
 * request; the schema keeps twenty-eight of them with their periods written
 * into the field names, and the security page showed none.
 *
 * Two things this panel is built around.
 *
 * **Period is part of the measurement.** A trailing-twelve-month margin and a
 * five-year average margin are different numbers about different things, and a
 * table that called both "net margin" would invite a reader to compare them.
 * Every row here carries its period, because the payload does.
 *
 * **Two scale conventions live in one response.** The ratio surface sends
 * percentages already scaled — a 48.65 gross margin means 48.65%. Ownership
 * sends fractions — 0.66373 institutional means 66.4%. Formatting both with
 * one kind would be wrong by a factor of a hundred in one direction or the
 * other, so each field states which it is and the shared number system does
 * the rest. Nothing here multiplies silently.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Value } from '@/components/system'
import type { Kind } from '@/lib/quantity'
import { fetchResearch } from '@/lib/research-cache'

interface Ratios {
  pe_ratio?: number | null
  forward_pe?: number | null
  eps?: number | null
  beta?: number | null
  week_52_high?: number | null
  week_52_low?: number | null
  dividend_yield?: number | null
  price_to_sales?: number | null
  price_to_book?: number | null
  ev_to_ebitda?: number | null
  ev_to_revenue?: number | null
  gross_margin_ttm?: number | null
  operating_margin_ttm?: number | null
  net_margin_ttm?: number | null
  net_margin_5y?: number | null
  roe_ttm?: number | null
  roa_ttm?: number | null
  roi_ttm?: number | null
  revenue_growth_ttm_yoy?: number | null
  revenue_growth_3y?: number | null
  eps_growth_ttm_yoy?: number | null
  eps_growth_3y?: number | null
  current_ratio?: number | null
  quick_ratio?: number | null
  debt_to_equity?: number | null
  long_term_debt_to_equity?: number | null
  payout_ratio_ttm?: number | null
  source?: string
}

interface Ownership {
  shares_outstanding?: number | null
  float_shares?: number | null
  held_percent_insiders?: number | null
  held_percent_institutions?: number | null
  shares_short?: number | null
  short_percent_of_float?: number | null
  short_ratio?: number | null
  short_interest_date?: string | null
  source?: string
}

interface Payload {
  ratios?: Ratios
  ownership?: Ownership
  profile?: { market_cap?: number | null; currency?: string | null }
}

/** One row: what it is, its period, and how to read the number. */
interface Row {
  label: string
  value: number | null | undefined
  kind: Kind
  /** The window the figure describes. Absent only where there isn't one. */
  period?: string
  digits?: number
  title?: string
}

interface Group { title: string; note?: string; rows: Row[] }

export default function Fundamentals2({ symbol }: { symbol: string }) {
  const [settled, setSettled] = useState<{ for: string; d?: Payload; error?: string } | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      // The cache returns the whole response; this panel reads one part of
      // it. The narrowing is here, at the boundary, rather than inside the
      // shared fetch — which has no business knowing who wants what.
      .then((d) => { if (alive) setSettled({ for: symbol, d: d as unknown as Payload }) })
      .catch((e: Error) => { if (alive) setSettled({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const current = settled?.for === symbol ? settled : null

  if (current === null) {
    return (
      <Panel title="Fundamentals" state="waking">
        <StateBlock
          state="waking"
          title="Reading the ratio surface"
          detail="The vendor fan-out takes half a minute. Price and history above did not wait for it."
        />
      </Panel>
    )
  }
  if (current.error) {
    return (
      <Panel title="Fundamentals" state="unavailable">
        <StateBlock
          state="unavailable"
          title="No fundamentals were returned"
          detail={`${current.error}. Nothing is shown in their place, and the market data above is unaffected.`}
        />
      </Panel>
    )
  }

  const r = current.d?.ratios ?? {}
  const o = current.d?.ownership ?? {}
  const cap = current.d?.profile?.market_cap ?? null

  /* Kinds, per field, from the convention the payload actually uses.
     `percent` never multiplies; `share` renders a fraction. The two live side
     by side in this response and must not be confused. */
  const groups: Group[] = [
    {
      title: 'Valuation',
      note: 'Multiples are bare ratios. A price-to-earnings of 37 is 37 times, not 37 per cent.',
      rows: [
        { label: 'Market cap', value: cap, kind: 'currency', digits: 0 },
        { label: 'Price / earnings', value: r.pe_ratio, kind: 'multiple' },
        { label: 'Forward P/E', value: r.forward_pe, kind: 'multiple' },
        { label: 'Price / sales', value: r.price_to_sales, kind: 'multiple' },
        { label: 'Price / book', value: r.price_to_book, kind: 'multiple' },
        { label: 'EV / EBITDA', value: r.ev_to_ebitda, kind: 'multiple' },
        { label: 'EV / revenue', value: r.ev_to_revenue, kind: 'multiple' },
        { label: 'Earnings per share', value: r.eps, kind: 'currency', period: 'TTM' },
      ],
    },
    {
      title: 'Profitability',
      rows: [
        { label: 'Gross margin', value: r.gross_margin_ttm, kind: 'percent', period: 'TTM' },
        { label: 'Operating margin', value: r.operating_margin_ttm, kind: 'percent', period: 'TTM' },
        { label: 'Net margin', value: r.net_margin_ttm, kind: 'percent', period: 'TTM' },
        { label: 'Net margin', value: r.net_margin_5y, kind: 'percent', period: '5-year average',
          title: 'A different measurement from the trailing figure above, not a revision of it' },
        { label: 'Return on equity', value: r.roe_ttm, kind: 'percent', period: 'TTM' },
        { label: 'Return on assets', value: r.roa_ttm, kind: 'percent', period: 'TTM' },
        { label: 'Return on investment', value: r.roi_ttm, kind: 'percent', period: 'TTM' },
      ],
    },
    {
      title: 'Growth',
      note: 'Year-on-year and multi-year figures answer different questions; a business can grow this year and not over three.',
      rows: [
        { label: 'Revenue growth', value: r.revenue_growth_ttm_yoy, kind: 'percent', period: 'TTM, year on year', digits: 2 },
        { label: 'Revenue growth', value: r.revenue_growth_3y, kind: 'percent', period: '3-year', digits: 2 },
        { label: 'EPS growth', value: r.eps_growth_ttm_yoy, kind: 'percent', period: 'TTM, year on year', digits: 2 },
        { label: 'EPS growth', value: r.eps_growth_3y, kind: 'percent', period: '3-year', digits: 2 },
      ],
    },
    {
      title: 'Financial position',
      rows: [
        { label: 'Current ratio', value: r.current_ratio, kind: 'multiple' },
        { label: 'Quick ratio', value: r.quick_ratio, kind: 'multiple' },
        { label: 'Debt / equity', value: r.debt_to_equity, kind: 'multiple' },
        { label: 'Long-term debt / equity', value: r.long_term_debt_to_equity, kind: 'multiple' },
        // `ratio` is signed, and a signed beta implies a direction it does
        // not have — 1.09 is not "up 1.09". A multiple reads it correctly.
        { label: 'Beta', value: r.beta, kind: 'multiple', title: 'Against the vendor’s own benchmark, which it does not name' },
      ],
    },
    {
      title: 'Shareholder return',
      rows: [
        { label: 'Dividend yield', value: r.dividend_yield, kind: 'percent', digits: 2 },
        { label: 'Payout ratio', value: r.payout_ratio_ttm, kind: 'percent', period: 'TTM' },
      ],
    },
    {
      title: 'Ownership',
      // The one place in this payload where percentages arrive as fractions.
      note: 'These arrive as fractions and are rendered as shares of one, not as the percentages above.',
      rows: [
        { label: 'Shares outstanding', value: o.shares_outstanding, kind: 'count' },
        { label: 'Float', value: o.float_shares, kind: 'count' },
        { label: 'Held by institutions', value: o.held_percent_institutions, kind: 'share' },
        { label: 'Held by insiders', value: o.held_percent_insiders, kind: 'share' },
        { label: 'Shares short', value: o.shares_short, kind: 'count' },
        { label: 'Short interest of float', value: o.short_percent_of_float, kind: 'share' },
        { label: 'Days to cover', value: o.short_ratio, kind: 'multiple' },
      ],
    },
  ]

  // Only groups with something in them. An empty group is a heading that
  // implies coverage the vendor did not supply.
  const present = groups
    .map((g) => ({ ...g, rows: g.rows.filter((x) => typeof x.value === 'number' && Number.isFinite(x.value)) }))
    .filter((g) => g.rows.length)

  if (!present.length) {
    return (
      <Panel title="Fundamentals" state="unavailable">
        <StateBlock
          state="unavailable"
          title={`No fundamental figures were returned for ${symbol}`}
          detail="The vendors answered without a ratio surface for this symbol. Nothing is shown in its place."
        />
      </Panel>
    )
  }

  return (
    <Panel
      title="Fundamentals"
      subtitle={r.source ? `via ${r.source}` : undefined}
      state="live"
      source={[r.source, o.source].filter(Boolean).join(', ') || undefined}
    >
      <div className="fund-groups">
        {present.map((g) => (
          <section key={`${g.title}-${g.rows[0]?.label}`} className="fund-group">
            <h3 className="sys-label fund-group__title">{g.title}</h3>
            <table className="sys-table sys-table--compact fund">
              <tbody>
                {g.rows.map((row) => (
                  <tr key={`${row.label}-${row.period ?? ''}`}>
                    <td className="fund__k" title={row.title}>
                      {row.label}
                      {row.period ? <span className="fund__period">{row.period}</span> : null}
                    </td>
                    <td className="num">
                      <Value value={row.value} kind={row.kind} digits={row.digits} title={row.title} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {g.note ? <Prose size="fine">{g.note}</Prose> : null}
          </section>
        ))}
      </div>

      {o.short_interest_date ? (
        <Prose size="fine">
          Short interest is as of {o.short_interest_date}. Exchanges publish it
          twice a month, so it is the least current figure on this page and is
          dated for that reason.
        </Prose>
      ) : null}
    </Panel>
  )
}
