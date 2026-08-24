'use client'

/**
 * Valuation, profitability, growth and leverage ratios.
 *
 * These arrived in a response the product was already making — one vendor
 * request returns 133 figures and the adapter was keeping seven. Nothing here
 * is computed by us; every number is the vendor's own, which matters because
 * a ratio is only meaningful when its numerator and denominator come from the
 * same period and the same definition.
 *
 * ## Why the period is in every label
 *
 * A trailing-twelve-month margin and a five-year average margin are different
 * measurements. Labelling both "net margin" would make them look
 * interchangeable, and the moment they look interchangeable somebody averages
 * them. So the period is part of the label, not a footnote.
 *
 * ## Why this is single-vendor and not reconciled
 *
 * Ratios are a *family*: this vendor's P/E, margins and returns are all
 * computed against the same denominators. Taking P/E from one vendor and
 * margin from another produces a set that is internally inconsistent even
 * though every individual figure is correct. The vendor is named instead.
 */

import type { RatiosBlock } from '@/lib/types'

type Row = { label: string; value: number | undefined; unit: '%' | 'x' | '' }

function group(title: string, rows: Row[]) {
  return { title, rows: rows.filter((r) => typeof r.value === 'number' && Number.isFinite(r.value)) }
}

function format(value: number, unit: Row['unit']): string {
  if (unit === '%') return `${value.toFixed(1)}%`
  if (unit === 'x') return `${value.toFixed(2)}×`
  return value.toFixed(2)
}

export default function RatioPanel({ ratios }: { ratios: RatiosBlock }) {
  const groups = [
    group('Valuation', [
      { label: 'P/E (TTM)', value: ratios.pe_ratio, unit: 'x' },
      { label: 'P/S (TTM)', value: ratios.price_to_sales, unit: 'x' },
      { label: 'P/B', value: ratios.price_to_book, unit: 'x' },
      { label: 'EV/EBITDA (TTM)', value: ratios.ev_to_ebitda, unit: 'x' },
      { label: 'EV/Revenue (TTM)', value: ratios.ev_to_revenue, unit: 'x' },
    ]),
    group('Profitability', [
      { label: 'Gross margin (TTM)', value: ratios.gross_margin_ttm, unit: '%' },
      { label: 'Operating margin (TTM)', value: ratios.operating_margin_ttm, unit: '%' },
      { label: 'Net margin (TTM)', value: ratios.net_margin_ttm, unit: '%' },
      { label: 'Net margin (5y avg)', value: ratios.net_margin_5y, unit: '%' },
      { label: 'ROE (TTM)', value: ratios.roe_ttm, unit: '%' },
      { label: 'ROA (TTM)', value: ratios.roa_ttm, unit: '%' },
      { label: 'ROI (TTM)', value: ratios.roi_ttm, unit: '%' },
    ]),
    group('Growth', [
      { label: 'Revenue growth (TTM y/y)', value: ratios.revenue_growth_ttm_yoy, unit: '%' },
      { label: 'Revenue growth (3y)', value: ratios.revenue_growth_3y, unit: '%' },
      { label: 'EPS growth (TTM y/y)', value: ratios.eps_growth_ttm_yoy, unit: '%' },
      { label: 'EPS growth (3y)', value: ratios.eps_growth_3y, unit: '%' },
    ]),
    group('Balance sheet', [
      { label: 'Current ratio', value: ratios.current_ratio, unit: '' },
      { label: 'Quick ratio', value: ratios.quick_ratio, unit: '' },
      { label: 'Debt / equity', value: ratios.debt_to_equity, unit: '' },
      { label: 'LT debt / equity', value: ratios.long_term_debt_to_equity, unit: '' },
      { label: 'Payout ratio (TTM)', value: ratios.payout_ratio_ttm, unit: '%' },
      { label: 'Dividend yield', value: ratios.dividend_yield, unit: '%' },
    ]),
  ].filter((g) => g.rows.length > 0)

  if (groups.length === 0) return null

  return (
    <section className="panel panel--pad ratios" aria-labelledby="ratios-h">
      <div className="ratios__head">
        <div>
          <h2 id="ratios-h" className="h-panel">Ratios</h2>
          <p className="ratios__lede">
            Reported by the vendor, not computed here. Each period is part of the label:
            a trailing figure and a multi-year average are different measurements.
          </p>
        </div>
        {ratios.source && (
          <span className="ratios__src">
            all from <strong>{ratios.source}</strong>
          </span>
        )}
      </div>

      <div className="ratios__grid">
        {groups.map((g) => (
          <div key={g.title} className="ratios__group">
            <h3 className="ratios__group-title">{g.title}</h3>
            <dl className="ratios__rows">
              {g.rows.map((r) => (
                <div key={r.label} className="ratios__row">
                  <dt>{r.label}</dt>
                  <dd className="num">{format(r.value as number, r.unit)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  )
}
