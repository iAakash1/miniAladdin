'use client'

/**
 * The environment this valuation sits in.
 *
 * Two things are joined here, both of which the request already paid for and
 * then discarded.
 *
 * **The rates** set the discount rate every multiple on this page implies.
 * Four series, not fourteen — a company page is not a macro dashboard, and
 * the full board already lives on Market. These are the ones that change
 * what a multiple *should* be.
 *
 * **The stress figures** gate the engine's verdict. They were fetched,
 * consumed by the scoring model and thrown away, which meant a reader could
 * be shown a dampened verdict with no way to see what dampened it. That is
 * the kind of opacity this product exists to avoid.
 *
 * ## Why every row carries its own date
 *
 * Macro series publish on different cadences: the policy rate monthly,
 * Treasury yields daily. A single "as of" for the block would be wrong for
 * most of it, and a monthly series read today is still last month's number.
 */

import type { MacroContext } from '@/lib/types'

export default function MacroContextPanel({ macro }: { macro: MacroContext }) {
  if (macro.rates.length === 0 && macro.stress.length === 0) return null

  return (
    <section className="panel panel--pad macro" aria-labelledby="macro-h">
      <div className="macro__head">
        <div>
          <h2 id="macro-h" className="h-panel">Macro environment</h2>
          <p className="macro__lede">{macro.note}</p>
        </div>
      </div>

      {macro.rates.length > 0 && (
        <div className="macro__rates">
          {macro.rates.map((r) => (
            <div key={r.series_id} className="macro__rate" title={r.why}>
              <span className="macro__rate-label">{r.label}</span>
              <span className="macro__rate-value num">
                {r.value.toFixed(2)}
                {r.unit === '%' && <span className="macro__rate-unit">%</span>}
              </span>
              <span className="macro__rate-foot">
                {r.change !== null && r.change !== 0 && (
                  <span className={`num macro__rate-chg macro__rate-chg--${
                    r.change > 0 ? 'up' : 'down'
                  }`}>
                    {r.change > 0 ? '+' : ''}{r.change.toFixed(2)}
                  </span>
                )}
                {/* The observation's own date. A monthly series read today is
                    still last month's number. */}
                <span className="num macro__rate-date">{r.as_of}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {macro.stress.length > 0 && (
        <div className="macro__stress">
          <h3 className="macro__stress-title">What gates the verdict</h3>
          <ul className="macro__stress-rows">
            {macro.stress.map((s) => (
              <li key={s.key} className="macro__stress-row">
                <span className="macro__stress-label">{s.label}</span>
                <span className="num macro__stress-value">{s.value.toFixed(3)}</span>
                <span className="macro__stress-note">{s.note}</span>
                {/* Vendor-supplied or computed here — a distinction the
                    reader is entitled to, not a footnote. */}
                <span className="macro__stress-src">{s.source}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
