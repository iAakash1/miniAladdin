/**
 * The panel that opens when a number is clicked.
 *
 * Three sections in a fixed order: what this value is, how it was produced, and
 * what would make it wrong. The third is last because it is the one a reader
 * needs after they have decided the number matters, and first because it is the
 * one nobody writes — so it gets the strongest treatment on the page rather
 * than a footnote.
 */
'use client'

import { useEffect } from 'react'
import Link from 'next/link'

import { Status, type ResearchState } from './index'
import { useMetrics } from './MetricContext'

const STATUS_MAP: Record<string, ResearchState> = {
  live: 'live', recorded: 'recorded', stale: 'stale', waking: 'waking',
  unavailable: 'unavailable', unknown: 'unknown',
}

const UNIT_LABEL: Record<string, string> = {
  return: 'a return, in the series’ own units',
  return_magnitude: 'a magnitude — reported positive, so no consumer renders a double negative',
  annualised_volatility: 'an annualised volatility',
  ratio: 'a ratio — dimensionless, so a percent sign would be wrong',
  other: 'unclassified',
}

const ANN_LABEL: Record<string, string> = {
  none: 'none — reported per period as measured',
  sqrt_periods_per_year: 'scaled by the square root of periods per year, as dispersion is',
  periods_per_year: 'scaled linearly by periods per year, as a mean is',
  geometric_compounded: 'compounded geometrically, as a growth rate is',
}

export default function MetricInspector() {
  const { current, close, entry } = useMetrics()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [close])

  if (!current) return null
  const def = entry(current.measure)

  return (
    <aside className="sys-drawer" role="dialog" aria-modal="false" aria-label={`${current.label} inspector`}>
      <header className="sys-drawer-head">
        <span className="pal-badge" aria-hidden>ƒ</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="sys-label">{current.label}</div>
          <div className="sys-metric__value" style={{ fontSize: 'var(--t-title)', marginTop: 2 }}>
            {current.display}
            {current.unit ? <em className="sys-metric__unit">{current.unit}</em> : null}
          </div>
        </div>
        {current.status ? <Status state={STATUS_MAP[current.status] ?? 'unknown'} /> : null}
        <button className="sys-btn" onClick={close} aria-label="Close">esc</button>
      </header>

      <div className="sys-drawer-body">
        <section>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>What this is</div>
          {def?.purpose ? (
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink)' }}>
              {def.purpose}
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              {current.measure
                ? 'The handbook has no entry for this measure. No definition is shown in place of one.'
                : 'This figure is not one of the engine’s registered measures, so it has no handbook entry.'}
            </p>
          )}
        </section>

        {current.conflict?.observations?.length ? (
          <section className="prov-conflict">
            <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>
              Vendors disagree
            </div>
            <p className="prov-conflict__lede">
              The value above is what the merge produced. These are the figures
              it was produced from, and they do not agree.
            </p>
            <table className="sys-table sys-table--compact">
              <thead>
                <tr><th scope="col">Vendor</th><th scope="col" className="num">Reported</th></tr>
              </thead>
              <tbody>
                {current.conflict.observations.map((o) => (
                  <tr key={o.provider}>
                    <td>{o.provider}</td>
                    <td className="num">
                      {typeof o.value === 'number' ? o.value.toLocaleString() : (o.value ?? '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {typeof current.conflict.spreadPct === 'number' ? (
              <p className="prov-conflict__spread">
                Widest disagreement: {current.conflict.spreadPct.toFixed(1)}% of the
                larger figure.
              </p>
            ) : null}
          </section>
        ) : null}

        <section>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>How it was produced</div>
          <table className="sys-table sys-table--compact">
            <tbody>
              {def ? (
                <>
                  <tr>
                    <td style={{ width: '38%', color: 'var(--ink-muted)' }}>Unit</td>
                    <td style={{ whiteSpace: 'normal' }}>{UNIT_LABEL[def.unit] ?? def.unit}</td>
                  </tr>
                  <tr>
                    <td style={{ color: 'var(--ink-muted)' }}>Annualisation</td>
                    <td style={{ whiteSpace: 'normal' }}>{ANN_LABEL[def.annualisation] ?? def.annualisation}</td>
                  </tr>
                  <tr>
                    <td style={{ color: 'var(--ink-muted)' }}>Computed from</td>
                    <td style={{ whiteSpace: 'normal' }}>{def.inputs.join(', ') || '—'}</td>
                  </tr>
                  <tr>
                    <td style={{ color: 'var(--ink-muted)' }}>Needs return units</td>
                    <td>{def.return_units_required ? 'yes — it is suppressed on a rank series' : 'no'}</td>
                  </tr>
                  <tr>
                    <td style={{ color: 'var(--ink-muted)' }}>Minimum observations</td>
                    <td className="num" style={{ textAlign: 'left' }}>{def.minimum_observations}</td>
                  </tr>
                </>
              ) : null}
              {current.method ? (
                <tr>
                  <td style={{ color: 'var(--ink-muted)' }}>This instance</td>
                  <td style={{ whiteSpace: 'normal', fontSize: 'var(--t-meta)' }}>{current.method}</td>
                </tr>
              ) : null}
              {current.source ? (
                <tr>
                  <td style={{ color: 'var(--ink-muted)' }}>Source</td>
                  <td style={{ whiteSpace: 'normal', wordBreak: 'break-all', fontSize: 'var(--t-micro)' }}>{current.source}</td>
                </tr>
              ) : null}
              {current.asOf ? (
                <tr><td style={{ color: 'var(--ink-muted)' }}>As of</td><td className="num" style={{ textAlign: 'left' }}>{current.asOf}</td></tr>
              ) : null}
              {current.providers?.length ? (
                <tr>
                  <td style={{ color: 'var(--ink-muted)' }}>Vendors</td>
                  <td style={{ whiteSpace: 'normal', fontSize: 'var(--t-meta)' }}>
                    {current.providers.join(', ')}
                  </td>
                </tr>
              ) : null}
              {current.freshness ? (
                <tr>
                  <td style={{ color: 'var(--ink-muted)' }}>Freshness</td>
                  <td style={{ whiteSpace: 'normal', fontSize: 'var(--t-meta)' }}>{current.freshness}</td>
                </tr>
              ) : null}
              {current.filedAt ? (
                <tr>
                  <td style={{ color: 'var(--ink-muted)' }}>Filed</td>
                  <td className="num" style={{ textAlign: 'left' }}>{current.filedAt.slice(0, 10)}</td>
                </tr>
              ) : null}
              {current.retrievedAt ? (
                <tr><td style={{ color: 'var(--ink-muted)' }}>Retrieved</td><td className="num" style={{ textAlign: 'left' }}>{current.retrievedAt.slice(0, 19)}</td></tr>
              ) : null}
            </tbody>
          </table>
        </section>

        {/* The section nobody writes, given the strongest treatment on the page. */}
        <section>
          <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>What would make it wrong</div>
          {def?.fails_when ? (
            <p
              style={{
                margin: 0, padding: 'var(--d-3)',
                borderLeft: '2px solid var(--s-blocked)',
                background: 'var(--p-sunken)',
                fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink)',
              }}
            >
              {def.fails_when}
            </p>
          ) : (
            <p style={{ margin: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-muted)', lineHeight: 'var(--lh-body)' }}>
              No failure conditions are recorded for this figure. That is an absence
              in the handbook, not a claim that none exist.
            </p>
          )}
        </section>

        {current.note ? (
          <section>
            <div className="sys-label" style={{ marginBottom: 'var(--d-2)' }}>In this context</div>
            <p style={{ margin: 0, fontSize: 'var(--t-body)', lineHeight: 'var(--lh-body)', color: 'var(--ink-muted)' }}>
              {current.note}
            </p>
          </section>
        ) : null}

        {current.measure ? (
          <section>
            <Link
              href={`/terminal/handbook?measure=${encodeURIComponent(current.measure)}`}
              className="sys-btn"
              style={{ textDecoration: 'none' }}
              onClick={close}
            >
              Open in the handbook
            </Link>
          </section>
        ) : null}
      </div>
    </aside>
  )
}
