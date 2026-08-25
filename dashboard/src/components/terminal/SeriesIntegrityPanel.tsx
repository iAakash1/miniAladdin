'use client'

import type { SeriesIntegrity } from '@/lib/types'

/**
 * Cross-vendor agreement on the price history.
 *
 * The consensus strip above already answers "do vendors agree on the price
 * now". This answers the question a chart cannot: *is the history we drew
 * the same history everyone else has?* One vendor's series is an assertion —
 * there is nothing in it that could reveal it was wrong.
 *
 * Two findings are rendered deliberately differently, because they are not
 * the same severity and do not have the same fix:
 *
 *   an **adjustment mismatch** is a vendor whose closes sit at a stable
 *   multiple of everyone else's — almost always a raw series among adjusted
 *   ones. It is systematic, it silently corrupts every technical reading
 *   taken from it, and it gets the loud treatment.
 *
 *   a **divergence** is a handful of sessions where closes differ. Usually a
 *   different venue or close time. Worth showing, not worth alarming about,
 *   so it stays a quiet row.
 *
 * Nothing here rewrites the series. A ratio is named, never corrected —
 * guessing at an adjustment is how a chart becomes confidently wrong.
 */
export default function SeriesIntegrityPanel({ integrity }: { integrity: SeriesIntegrity | null }) {
  // Below two vendors there is no comparison to report. Rendering an empty
  // panel would imply a check ran and passed.
  if (!integrity || integrity.providers.length < 2) return null

  const { agreement_pct, shared_sessions, providers, adjustment_mismatch } = integrity
  const clean = adjustment_mismatch.length === 0 && integrity.conflict_count === 0
  const gaps = Object.entries(integrity.session_gaps ?? {})

  return (
    <section aria-label="Price history agreement" className="panel panel--pad">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
        <h3 className="h-panel">History agreement</h3>
        <span className="u-note">
          {providers.length} vendors · {shared_sessions} shared sessions
        </span>
      </div>

      <div className="sint">
        <span className="sint__stat">
          <strong
            className="num"
            style={{ color: clean ? 'var(--pos)' : agreement_pct >= 95 ? 'var(--text)' : 'var(--warn)' }}
          >
            {agreement_pct.toFixed(1)}%
          </strong>
          <span className="u-note"> of closes agree within {integrity.tolerance_pct}%</span>
        </span>
        {integrity.conflict_count > 0 && (
          <span className="sint__stat">
            <strong className="num">{integrity.conflict_count}</strong>
            <span className="u-note"> sessions diverge · worst {integrity.max_divergence_pct.toFixed(2)}%</span>
          </span>
        )}
        {gaps.length > 0 && (
          <span className="sint__stat" title="Sessions missing relative to the union of all vendors">
            <span className="u-note">gaps: </span>
            {gaps.map(([p, n]) => `${p} −${n}`).join(', ')}
          </span>
        )}
      </div>

      {/* The finding that matters. Given its own block, its own colour and a
          plain-language consequence, because "ratio 4.0012" means nothing to
          a reader who does not already know what it implies. */}
      {adjustment_mismatch.map((m) => (
        <div key={m.provider} className="sint__mismatch">
          <div className="sint__mismatch-head">
            <span className="badge badge--neg" style={{ height: 20 }}>adjustment mismatch</span>
            <strong>{m.provider}</strong>
            <span className="num">×{m.ratio}</span>
            {m.likely_split && <span className="u-note">consistent with a {m.likely_split} split</span>}
          </div>
          <p className="sint__mismatch-body">
            {m.provider}&rsquo;s closes sit at a stable {m.ratio}× the other vendors&rsquo; across{' '}
            <span className="num">{m.sessions}</span> sessions
            {' '}({(m.stability * 100).toFixed(1)}% stable) — the signature of an unadjusted series
            rather than a bad print. Its history is <strong>not</strong> used for the chart or any
            technical reading; this vendor is reported, not corrected.
          </p>
        </div>
      ))}

      {integrity.conflicts.length > 0 && (
        <div style={{ overflowX: 'auto', marginTop: 12 }}>
          <table className="sint__table">
            <thead>
              <tr>
                <th>Session</th>
                <th style={{ textAlign: 'right' }}>Spread</th>
                <th>Readings</th>
              </tr>
            </thead>
            <tbody>
              {integrity.conflicts.map((c) => (
                <tr key={c.date}>
                  <td className="num">{c.date}</td>
                  <td className="num" style={{ textAlign: 'right', color: 'var(--warn)' }}>
                    {c.divergence_pct.toFixed(2)}%
                  </td>
                  <td className="num u-note">
                    {Object.entries(c.readings).map(([p, v]) => `${p} ${v}`).join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {clean && (
        <p className="u-note" style={{ marginTop: 8 }}>
          Every vendor that holds this history reports the same adjusted closes.
        </p>
      )}
    </section>
  )
}
