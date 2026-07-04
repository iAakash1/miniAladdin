'use client'

import { useState } from 'react'
import { FACTOR_LABELS, diffSnapshots, useHistory } from '@/lib/history'
import { timeAgo } from '@/lib/format'

function verdictTone(verdict: string): string {
  return verdict.includes('Buy') ? 'badge--pos' : verdict.includes('Sell') ? 'badge--neg' : 'badge--warn'
}

/**
 * Phase 3: verdict history for the current ticker. Every change explains
 * WHY by diffing factor CONTRIBUTIONS between runs — not just scores.
 */
export default function VerdictTimeline({ ticker }: { ticker: string }) {
  const timeline = useHistory(ticker)
  const [expanded, setExpanded] = useState<string | null>(null)

  if (timeline.length < 2) return null // a timeline needs at least two points

  const entries = [...timeline].reverse() // newest first

  return (
    <section aria-label={`${ticker} verdict history`} className="panel" style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <h3 className="h-panel">Verdict timeline</h3>
        <span style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
          {timeline.length} runs stored in this browser
        </span>
      </div>

      <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {entries.map((entry, index) => {
          const older = entries[index + 1] ?? null
          const diff = older ? diffSnapshots(older, entry) : null
          const key = entry.ts
          const isOpen = expanded === key

          return (
            <li
              key={key}
              style={{
                padding: '12px 0',
                borderBottom: index < entries.length - 1 ? '1px solid var(--line)' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)', width: 110 }}>
                  {new Date(entry.ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  {' · '}
                  {timeAgo(entry.ts)}
                </span>
                <span className={`badge ${verdictTone(entry.verdict)}`} style={{ height: 19, fontSize: '0.625rem' }}>
                  {entry.verdict}
                </span>
                <span className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                  {entry.confidence}% conf
                </span>
                {diff?.verdictChanged && (
                  <span
                    className={`badge ${diff.direction === 'upgrade' ? 'badge--pos' : 'badge--neg'}`}
                    style={{ height: 19, fontSize: '0.625rem' }}
                  >
                    {diff.direction === 'upgrade' ? '▲' : '▼'} from {older!.verdict}
                  </span>
                )}
                {diff && (diff.verdictChanged || Math.abs(diff.confidenceDelta) >= 3) && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    style={{ height: 22, marginLeft: 'auto', fontSize: '0.6875rem' }}
                    aria-expanded={isOpen}
                    onClick={() => setExpanded(isOpen ? null : key)}
                  >
                    {isOpen ? 'Hide why' : 'Why?'}
                  </button>
                )}
              </div>

              {isOpen && diff && (
                <div className="fade-in" style={{ margin: '10px 0 2px 122px' }}>
                  <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {diff.topDrivers.map((driver) => (
                      <li key={driver.name} style={{ display: 'flex', gap: 10, fontSize: '0.8125rem', alignItems: 'baseline' }}>
                        <span
                          className="num"
                          style={{
                            width: 62,
                            textAlign: 'right',
                            color: driver.delta > 0 ? 'var(--pos)' : 'var(--neg)',
                            flexShrink: 0,
                          }}
                        >
                          {driver.delta > 0 ? '+' : ''}
                          {driver.delta.toFixed(3)}
                        </span>
                        <span style={{ color: 'var(--muted)' }}>
                          {FACTOR_LABELS[driver.name] ?? driver.name}
                          {' '}
                          <span style={{ color: 'var(--faint)' }}>
                            ({driver.delta > 0 ? 'strengthened' : 'weakened'}: {driver.before.toFixed(3)} → {driver.after.toFixed(3)})
                          </span>
                        </span>
                      </li>
                    ))}
                    {diff.gateDelta !== null && Math.abs(diff.gateDelta) >= 0.01 && (
                      <li style={{ fontSize: '0.8125rem', color: 'var(--muted)', paddingLeft: 72 }}>
                        Macro gate {diff.gateDelta > 0 ? 'eased' : 'tightened'} by {Math.abs(diff.gateDelta).toFixed(2)}
                        {' '}(SRM {older!.srm.toFixed(2)} → {entry.srm.toFixed(2)})
                      </li>
                    )}
                    {diff.regimesEntered.map((regime) => (
                      <li key={regime} style={{ fontSize: '0.8125rem', color: 'var(--warn)', paddingLeft: 72 }}>
                        Entered {regime.replace('_', ' ')} regime
                      </li>
                    ))}
                    {diff.regimesExited.map((regime) => (
                      <li key={regime} style={{ fontSize: '0.8125rem', color: 'var(--muted)', paddingLeft: 72 }}>
                        Exited {regime.replace('_', ' ')} regime
                      </li>
                    ))}
                    <li style={{ fontSize: '0.75rem', color: 'var(--faint)', paddingLeft: 72 }}>
                      Confidence {diff.confidenceDelta >= 0 ? '+' : ''}{diff.confidenceDelta}pp
                      {diff.scoreDelta !== null &&
                        ` · composite ${diff.scoreDelta >= 0 ? '+' : ''}${diff.scoreDelta.toFixed(3)}`}
                    </li>
                  </ul>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
