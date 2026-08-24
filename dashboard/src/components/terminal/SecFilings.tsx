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
