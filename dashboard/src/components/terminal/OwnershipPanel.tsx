'use client'

/**
 * Ownership, short interest and sell-side positioning.
 *
 * Everything here answers "who is on the other side of this" rather than
 * "how did the business do", which is why it is a separate panel from the
 * ratios: a settlement-lagged short figure sitting next to a trailing margin
 * would be read as equally current, and it is not.
 *
 * All of it comes from a keyless source, so this panel is populated in every
 * environment — including local development, where every authenticated
 * vendor reports `not_configured`.
 *
 * ## The analyst block is not reduced to one number
 *
 * Each vendor polls a different set of analysts, so a median across vendors
 * would be a consensus of no actual group of people. Readings are shown per
 * vendor, and the target range is shown alongside the mean because the
 * spread between a $215 low and a $400 high is the part that tells you how
 * much disagreement the "consensus" is hiding.
 */

import type { AnalystBlock, OwnershipBlock } from '@/lib/types'

function pct(fraction: number | null, digits = 1): string {
  if (fraction === null || !Number.isFinite(fraction)) return '—'
  return `${(fraction * 100).toFixed(digits)}%`
}

function shares(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`
  return value.toLocaleString()
}

/** A share of a whole, drawn against 100%. Unlike the portfolio bars these
 *  genuinely are percentages of a fixed total, so a full-width scale is the
 *  honest one. */
function Share({ fraction, tone = 'accent' }: { fraction: number | null; tone?: string }) {
  if (fraction === null || !Number.isFinite(fraction)) return null
  return (
    <span className={`own-bar own-bar--${tone}`}>
      <span
        className="own-bar__fill"
        style={{ transform: `scaleX(${Math.min(1, Math.max(0, fraction))})` }}
      />
    </span>
  )
}

export default function OwnershipPanel({
  ownership, analyst,
}: {
  ownership: OwnershipBlock | null
  analyst: AnalystBlock | null
}) {
  if (!ownership && !analyst) return null

  return (
    <section className="panel panel--pad own" aria-labelledby="own-h">
      <div className="own__head">
        <div>
          <h2 id="own-h" className="h-panel">Ownership &amp; positioning</h2>
          <p className="own__lede">
            Who holds the shares, how many are sold short, and where the sell side has
            its targets. None of this is a scoring input — it is context for a position,
            not a signal.
          </p>
        </div>
      </div>

      <div className="own__grid">
        {ownership && (
          <div className="own__block">
            <h3 className="own__block-title">Holdings</h3>
            <dl className="own__rows">
              <div className="own__row">
                <dt>Institutions</dt>
                <dd><Share fraction={ownership.held_percent_institutions} /></dd>
                <dd className="num">{pct(ownership.held_percent_institutions)}</dd>
              </div>
              <div className="own__row">
                <dt>Insiders</dt>
                <dd><Share fraction={ownership.held_percent_insiders} tone="warn" /></dd>
                <dd className="num">{pct(ownership.held_percent_insiders, 2)}</dd>
              </div>
              <div className="own__row">
                <dt>Shares out</dt>
                <dd />
                <dd className="num">{shares(ownership.shares_outstanding)}</dd>
              </div>
              <div className="own__row">
                <dt>Free float</dt>
                <dd />
                <dd className="num">{shares(ownership.float_shares)}</dd>
              </div>
            </dl>
          </div>
        )}

        {ownership && ownership.shares_short !== null && (
          <div className="own__block">
            <h3 className="own__block-title">Short interest</h3>
            <dl className="own__rows">
              <div className="own__row">
                <dt>% of float</dt>
                <dd><Share fraction={ownership.short_percent_of_float} tone="neg" /></dd>
                <dd className="num">{pct(ownership.short_percent_of_float, 2)}</dd>
              </div>
              <div className="own__row">
                <dt>Shares short</dt>
                <dd />
                <dd className="num">{shares(ownership.shares_short)}</dd>
              </div>
              <div className="own__row">
                <dt>Days to cover</dt>
                <dd />
                <dd className="num">
                  {ownership.short_ratio !== null ? ownership.short_ratio.toFixed(2) : '—'}
                </dd>
              </div>
            </dl>
            {/* The date is not a footnote. Exchanges publish this twice a
                month, so a short figure read as current is wrong by up to
                two weeks of trading. */}
            {ownership.short_interest_date && (
              <p className="own__note">
                Settlement date {ownership.short_interest_date} — exchanges publish short
                interest twice monthly, so this lags the price above.
              </p>
            )}
          </div>
        )}

        {analyst && analyst.readings.length > 0 && (
          <div className="own__block">
            <h3 className="own__block-title">Sell-side targets</h3>
            {analyst.readings.map((r) => (
              <div key={r.source} className="own__analyst">
                <p className="own__metric">
                  <span className="num own__metric-value">
                    {r.target_mean !== null ? r.target_mean.toFixed(2) : '—'}
                  </span>
                  <span className="own__metric-unit">
                    mean target{r.analyst_count ? ` · ${r.analyst_count} analysts` : ''}
                  </span>
                </p>
                {/* The range is the informative part: a tight band and a
                    $185 spread are very different "consensus" figures. */}
                {r.target_low !== null && r.target_high !== null && (
                  <p className="own__range num">
                    {r.target_low.toFixed(0)} — {r.target_high.toFixed(0)}
                    <span className="u-note"> range</span>
                  </p>
                )}
                {r.recommendation && (
                  <p className="own__rec">
                    <span className="own__rec-label">{r.recommendation}</span>
                    {r.recommendation_mean !== null && (
                      <span className="u-note">
                        {' '}{r.recommendation_mean.toFixed(2)} on {r.source}&rsquo;s own scale
                      </span>
                    )}
                  </p>
                )}
                <p className="own__src">via {r.source}</p>
              </div>
            ))}
            {analyst.vendor_count > 1 && (
              <p className="own__note">
                Shown per vendor, not merged: each polls a different analyst set, so a
                figure averaged across them would be a consensus of no actual group.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
