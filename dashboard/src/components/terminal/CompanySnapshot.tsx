'use client'

/**
 * Company snapshot — who the company is, from the profile the research call
 * already fetched.
 *
 * Every field here arrived in the same vendor response the market cap came
 * from and was being discarded: the business description, the domain, the
 * headcount, the CEO, the IPO date. The product was paying for a request and
 * using six of its fields.
 *
 * Fields render only when a vendor supplied them. A company with no recorded
 * headcount shows no headcount row rather than a dash — the absence of a row
 * is quieter than a row full of em-dashes, and the reader is not asked to
 * scan placeholders.
 */

import CompanyMedia from '@/components/terminal/CompanyMedia'
import SourceBadge from '@/components/ui/SourceBadge'
import type { CompanyProfile } from '@/lib/types'

function compactMoney(value: number | null, currency: string): string | null {
  if (value === null || !Number.isFinite(value)) return null
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency', currency, notation: 'compact', maximumFractionDigits: 2,
    }).format(value)
  } catch {
    return null
  }
}

export default function CompanySnapshot({ profile }: { profile: CompanyProfile }) {
  const rows: Array<[string, string]> = []
  const cap = compactMoney(profile.market_cap, profile.currency || 'USD')
  if (cap) rows.push(['Market cap', cap])
  if (profile.employees) rows.push(['Employees', profile.employees.toLocaleString()])
  if (profile.beta !== null && Number.isFinite(profile.beta)) rows.push(['Beta', profile.beta.toFixed(2)])
  if (profile.ipo_date) rows.push(['Listed', profile.ipo_date])
  if (profile.exchange) rows.push(['Exchange', profile.exchange])
  if (profile.country) rows.push(['Country', profile.country])
  if (profile.ceo) rows.push(['CEO', profile.ceo])

  // Nothing worth a panel: no description and no facts.
  if (!profile.description && rows.length === 0) return null

  return (
    <section className="panel panel--pad csnap" aria-labelledby="csnap-h">
      <div className="csnap__head">
        <h2 id="csnap-h" className="h-panel">Company</h2>
        {/* No single vendor carries a complete profile, so this is a union.
            Saying how many contributed is the difference between "a company
            description" and "a company description three sources agree on". */}
        {profile.providers && profile.providers.length > 0 && (
          <span className="csnap__srcs" title={profile.providers.join(', ')}>
            <span className="num">{profile.providers.length}</span> sources
          </span>
        )}
        {profile.domain && (
          <a
            className="csnap__domain"
            href={profile.website || `https://${profile.domain}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <SourceBadge name={profile.name} url={`https://${profile.domain}`} />
            <span aria-hidden>↗</span>
          </a>
        )}
      </div>

      {profile.description && (
        <p className="csnap__desc">{profile.description}</p>
      )}

      {/* Loaded separately and after the fact — imagery never sits on the
          critical path of a price. Renders nothing when nothing resolves. */}
      <CompanyMedia
        ticker={profile.symbol}
        sector={profile.sector}
        industry={profile.industry}
        name={profile.name}
      />

      {/* Disagreement is shown, never smoothed into an average. Two vendors
          reporting different headcounts are reporting different headcounts. */}
      {profile.conflicts && profile.conflicts.length > 0 && (
        <ul className="csnap__conflicts">
          {profile.conflicts.map((c) => (
            <li key={c.field} className="csnap__conflict">
              <span className="csnap__conflict-field">{c.field.replace(/_/g, ' ')}</span>
              {c.observations.map((o) => (
                <span key={o.provider} className="csnap__conflict-obs">
                  {o.provider} <span className="num">{o.value.toLocaleString()}</span>
                </span>
              ))}
              <span className="u-note">{c.spread_pct.toFixed(1)}% apart — not averaged</span>
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <dl className="csnap__facts">
          {rows.map(([label, value]) => (
            <div key={label} className="csnap__fact">
              <dt>{label}</dt>
              <dd className={label === 'CEO' || label === 'Exchange' ? undefined : 'num'}>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
