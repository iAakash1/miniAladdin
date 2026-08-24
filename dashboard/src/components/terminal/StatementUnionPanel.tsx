'use client'

/**
 * Reported statement figures, as a union across every entitled vendor.
 *
 * This is the panel the fundamentals fan-out exists for. No single vendor
 * here carries every line: one has revenue and net income, another free cash
 * flow, a third EBITDA. Taking the "best" vendor would discard whichever
 * lines only the others hold — which is the loss the fabric was built to
 * prevent.
 *
 * ## Nothing here is averaged
 *
 * Where two vendors report the same line, **both values are shown**. They are
 * not averaged, because two vendors reporting different revenue are usually
 * reporting different fiscal periods or different definitions (GAAP vs
 * adjusted, restated vs original), and the mean of those is a number no
 * company ever filed. A disagreement is rendered as a disagreement.
 *
 * The reporting period is shown once, at the top, and comes from the newest
 * statement any vendor holds — mixing periods across vendors is exactly the
 * error the header guards against.
 */

import type { StatementUnion } from '@/lib/types'

/** Statement lines in reading order, with the labels a filing would use. */
const LINES: Array<[string, string]> = [
  ['revenue', 'Revenue'],
  ['gross_profit', 'Gross profit'],
  ['operating_income', 'Operating income'],
  ['ebitda', 'EBITDA'],
  ['net_income', 'Net income'],
  ['eps', 'EPS'],
  ['operating_cash_flow', 'Operating cash flow'],
  ['free_cash_flow', 'Free cash flow'],
  ['cash', 'Cash & equivalents'],
  ['debt', 'Total debt'],
  ['total_assets', 'Total assets'],
  ['total_liabilities', 'Total liabilities'],
  ['equity', 'Shareholder equity'],
  ['shares_diluted', 'Diluted shares'],
]

/** Large figures in the units a filing uses. EPS and share counts are not
 *  money and must not carry a currency symbol. */
function money(value: number, line: string): string {
  if (line === 'eps') return value.toFixed(2)
  const abs = Math.abs(value)
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`
  return value.toLocaleString()
}

export default function StatementUnionPanel({ statements }: { statements: StatementUnion }) {
  const rows = LINES.map(([key, label]) => ({ key, label, entry: statements.fields[key] }))
    .filter((r) => r.entry !== undefined)

  if (rows.length === 0) return null

  return (
    <section className="panel panel--pad stmt" aria-labelledby="stmt-h">
      <div className="stmt__head">
        <div>
          <h2 id="stmt-h" className="h-panel">Reported statements</h2>
          <p className="stmt__lede">
            A union across {statements.providers.length} vendor
            {statements.providers.length === 1 ? '' : 's'} — no single one carries every
            line. Where two disagree both values are shown; they are never averaged,
            because different vendors report different periods and definitions.
          </p>
        </div>
        <div className="stmt__meta">
          {statements.period && <span className="num stmt__period">{statements.period}</span>}
          <span className="stmt__vendors">{statements.providers.join(' · ')}</span>
        </div>
      </div>

      <dl className="stmt__rows">
        {rows.map(({ key, label, entry }) => (
          <div key={key} className={`stmt__row${entry.agrees ? '' : ' stmt__row--conflict'}`}>
            <dt className="stmt__label">{label}</dt>
            <dd className="stmt__value num">{money(entry.value, key)}</dd>
            <dd className="stmt__src">
              {/* When vendors disagree the individual readings replace the
                  provider list — the reader needs to see who said what, not
                  just that there was a disagreement. */}
              {entry.agrees ? (
                entry.providers.join(', ')
              ) : (
                <span className="stmt__obs">
                  {(entry.observations ?? []).map((o) => (
                    <span key={o.provider} className="stmt__ob">
                      {o.provider} <span className="num">{money(o.value, key)}</span>
                    </span>
                  ))}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>

      {statements.conflicts.length > 0 && (
        <p className="stmt__note">
          {statements.conflicts.length} line
          {statements.conflicts.length === 1 ? '' : 's'} disputed between vendors. The value
          shown is the median of the readings; every reading is listed beside it so the
          disagreement is visible rather than resolved away.
        </p>
      )}
    </section>
  )
}
