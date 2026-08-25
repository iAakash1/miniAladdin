'use client'

/**
 * SEC filings — the primary source, not a vendor's reading of it.
 *
 * Every other fundamentals panel in this product shows a number a data
 * vendor extracted from a filing, relabelled and sometimes restated. This
 * shows the filing: the form, the date it was actually filed with the
 * regulator, and a link to the document. When a vendor's revenue disagrees
 * with the 10-K, the 10-K is not a fourth opinion to reconcile against — it
 * is the document the others are describing.
 *
 * EDGAR is keyless, so this is the one fundamentals-adjacent surface that is
 * available in every environment and never answers "not configured".
 *
 * Deliberately compact: a filings list is a recency and cadence signal, not
 * a reading surface. The counts by form say more at a glance than ten rows
 * do — a burst of Form 4s is insider activity, an 8-K is a material event.
 */

import { fmtDate } from '@/lib/format'
import type { FilingsBlock } from '@/lib/types'

/** Forms whose appearance is itself newsworthy get a tone; routine filings
 *  stay neutral so the exceptions are the ones that catch the eye. */
const FORM_TONE: Record<string, string> = {
  '8-K': 'warn',   // material event — something happened
  '4': 'accent',   // insider transaction
  'S-1': 'warn',   // registration
  'SC 13D': 'warn', // activist stake
}

function daysAgo(iso: string): number | null {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  return Math.floor((Date.now() - then) / 86_400_000)
}

export default function SecFilings({ block }: { block: FilingsBlock }) {
  if (!block.filings.length) return null

  const recency = block.latest ? daysAgo(block.latest.filed_at) : null

  return (
    <section className="panel panel--pad sec" aria-labelledby="sec-h">
      <div className="sec__head">
        <div>
          <h2 id="sec-h" className="h-panel">Regulatory filings</h2>
          <p className="sec__lede">
            Straight from {block.source}. These are the filed documents themselves — every
            other fundamentals figure on this page is a vendor&rsquo;s reading of one.
          </p>
        </div>
        {recency !== null && (
          <span className="sec__recency">
            last filed <strong className="num">{recency === 0 ? 'today' : `${recency}d ago`}</strong>
          </span>
        )}
      </div>

      {/* Form mix first: a burst of Form 4s is insider activity and an 8-K is
          a material event, and both read faster as counts than as rows. */}
      <div className="sec__forms">
        {Object.entries(block.by_form).map(([form, count]) => (
          <span key={form} className={`sec__form sec__form--${FORM_TONE[form] ?? 'neutral'}`}>
            <span className="mono">{form}</span>
            <span className="num sec__form-n">{count}</span>
          </span>
        ))}
      </div>

      {/* Figures the company later reported differently for the same period.
          Every ratio panel in this product shows the *current* record; this
          is the only place that can say the current record is not what was
          originally filed. Both filing dates are shown because the claim is
          checkable — a reader can open each document. */}
      {block.restatements && block.restatements.length > 0 && (
        <div className="sec__restate">
          <h3 className="sec__xbrl-title">Restated after first filing</h3>
          <ul className="sec__restates">
            {block.restatements.slice(0, 5).map((r) => (
              <li key={`${r.concept}-${r.period_end}`} className="sec__restate-row">
                <span className="sec__restate-name">{r.label}</span>
                <span className="num sec__restate-period">
                  {r.period_start ? `${r.period_start} → ${r.period_end}` : r.period_end}
                </span>
                <span className="num sec__restate-values">
                  {r.original_value.toLocaleString(undefined, { notation: 'compact' })}
                  {' → '}
                  {r.revised_value.toLocaleString(undefined, { notation: 'compact' })}
                </span>
                <span className={`num sec__restate-pct sec__restate-pct--${
                  r.change_pct > 0 ? 'pos' : 'neg'
                }`}>
                  {r.change_pct > 0 ? '+' : ''}{r.change_pct.toFixed(1)}%
                </span>
                <span className="sec__restate-filed">
                  filed {r.original_filed}, revised {r.revised_filed}
                </span>
              </li>
            ))}
          </ul>
          <p className="sec__xbrl-note">
            Compared within one concept and one exact period — a fiscal year is never
            measured against the fourth quarter that shares its end date, and a 10-Q
            figure superseded by a 10-K is ordinary year-end adjustment rather than a
            revision.
          </p>
        </div>
      )}

      {/* The company's own tagged figures, and the year-over-year change
          between consecutive fiscal years of the same concept. This is the
          only place in the product where a number traces to a specific
          document rather than to a vendor's extraction of one — so the form
          and filing date are shown, not hidden behind a tooltip. */}
      {block.xbrl_trend && block.xbrl_trend.length > 0 && (
        <div className="sec__xbrl">
          <h3 className="sec__xbrl-title">Reported year over year</h3>
          <ul className="sec__trends">
            {block.xbrl_trend.slice(0, 6).map((t) => (
              <li key={t.concept} className="sec__trend">
                <span className="sec__trend-name">{t.concept}</span>
                <span className="num sec__trend-years">
                  {t.prior_year}→{t.latest_year}
                </span>
                <span className={`num sec__trend-pct sec__trend-pct--${
                  t.change_pct > 0 ? 'pos' : t.change_pct < 0 ? 'neg' : 'flat'
                }`}>
                  {t.change_pct > 0 ? '+' : ''}{t.change_pct.toFixed(1)}%
                </span>
                <span className="sec__trend-src">
                  {t.form} · {t.filed}
                </span>
              </li>
            ))}
          </ul>
          <p className="sec__xbrl-note">
            Computed from consecutive fiscal years of the same tagged concept — never
            across different line items. A concept with one year of data shows no trend
            rather than a zero.
          </p>
        </div>
      )}

      <ul className="sec__list">
        {block.filings.slice(0, 8).map((filing) => (
          <li key={filing.accession} className="sec__row">
            <a href={filing.url} target="_blank" rel="noopener noreferrer" className="sec__link">
              <span className={`mono sec__row-form sec__form--${FORM_TONE[filing.form] ?? 'neutral'}`}>
                {filing.form}
              </span>
              <span className="sec__row-meaning">{filing.meaning}</span>
              <span className="num sec__row-date">{fmtDate(filing.filed_at)}</span>
              <span aria-hidden className="sec__row-out">↗</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
