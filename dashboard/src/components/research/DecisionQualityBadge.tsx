'use client'

/**
 * How trustworthy the evidence is — never a probability of profit.
 *
 * The verdict answers "what does the evidence say"; this answers "how much
 * should you trust that the evidence says enough". A confident BUY built
 * from thin, stale evidence gives no sign of that from the verdict alone.
 * The grade and every reason shown here are exactly what
 * `src/services/decision_quality.py` computed for this response — nothing
 * here is re-derived, re-worded into a number, or estimated.
 *
 * Colour is never the only carrier: `data-grade` drives the tone, and the
 * word is what a reader who cannot distinguish the colours gets. This is a
 * badge, not one of the ten canonical research states — Decision Quality is
 * its own dimension, the same way SIMULATION and PAPER are badges rather
 * than forced onto a vocabulary built for freshness and availability.
 */

import type { DecisionQuality } from '@/lib/types'

/** Simple: grade and the one sentence. Nothing else — a reader here wants
 *  the answer, not the mechanism. */
export function DecisionQualityLine({ quality }: { quality: DecisionQuality | null }) {
  if (!quality) return null
  return (
    <div className="dq__line">
      <span className="sys-label">Decision quality</span>
      <span className="dq__grade" data-grade={quality.grade}>{quality.grade}</span>
      <p className="dq__summary">{quality.summary}</p>
    </div>
  )
}

/** Guided: the sentence plus the machine-readable reasons an INSUFFICIENT
 *  grade carries — the same vocabulary Explore's eligibility gate reports,
 *  not a second explanation invented for this panel. */
export function DecisionQualityDetail({ quality }: { quality: DecisionQuality | null }) {
  if (!quality) return null
  const readable: Record<string, string> = {
    not_common_equity: 'Not a common equity',
    insufficient_history: 'Not enough price history',
    no_valid_price: 'No valid current price',
    price_stale: 'Price is older than the freshness window',
    no_scorecard: 'The engine could not produce a scorecard',
    insufficient_data_completeness: 'Too little of the evidence set arrived',
    low_confidence: 'The engine itself reported low confidence',
    unresolved_evidence_conflict: 'Evidence conflict was not resolved',
  }
  return (
    <div className="dq__line">
      <span className="sys-label">Decision quality</span>
      <span className="dq__grade" data-grade={quality.grade}>{quality.grade}</span>
      <p className="dq__summary">{quality.summary}</p>
      {quality.reasons.length ? (
        <ul className="dq__reasons">
          {quality.reasons.map((reason) => (
            <li key={reason}>{readable[reason] ?? reason}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
