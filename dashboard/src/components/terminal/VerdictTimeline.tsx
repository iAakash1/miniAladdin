'use client'

import { useState } from 'react'
import { FACTOR_LABELS, diffSnapshots, useHistory } from '@/lib/history'
import { fmtDate, timeAgo } from '@/lib/format'

/** A track of every stored run, oldest to newest.
 *
 *  Adapted from the Uiverse stepper/range family, whose mechanism is a rail
 *  with discrete markers and one indicator that moves between them. The
 *  timeline below is a list you scroll; this is the same data as a shape —
 *  ten runs at a glance, with the verdict encoded in each marker, so a
 *  flip-flopping ticker is visible before reading a single row.
 *
 *  Left-to-right is oldest-to-newest, the opposite of the list beneath it,
 *  because a timeline that ran backwards would be the surprising choice.
 *  Arrow keys walk it; picking a marker opens that run's diff in the list.
 */
function RunScrubber({
  entries, picked, onPick,
}: {
  entries: Array<{ ts: string; verdict: string; confidence: number }>
  picked: string | null
  onPick: (ts: string | null) => void
}) {
  if (entries.length < 3) return null    // a track of two is just two buttons
  const oldestFirst = [...entries].reverse()

  return (
    <div className="scrub-wrap">
    {/* Endpoints labelled, so the row of markers reads as a timeline rather
        than as decoration, and the picked run names itself. */}
    <div className="scrub-wrap__ends u-note">
      <span>{fmtDate(oldestFirst[0].ts)}</span>
      <span className="scrub-wrap__picked">
        {picked
          ? (() => {
              const entry = oldestFirst.find((e) => e.ts === picked)
              return entry ? `${fmtDate(entry.ts)} · ${entry.verdict} · ${entry.confidence}%` : 'Pick a run'
            })()
          : `${oldestFirst.length} runs · click or use ←/→`}
      </span>
      <span>{fmtDate(oldestFirst[oldestFirst.length - 1].ts)}</span>
    </div>
    <div
      className="scrub"
      role="listbox"
      aria-label="Stored runs, oldest first"
      tabIndex={0}
      onKeyDown={(event) => {
        const at = oldestFirst.findIndex((e) => e.ts === picked)
        const go = (to: number) => {
          const next = oldestFirst[Math.max(0, Math.min(oldestFirst.length - 1, to))]
          if (next) { event.preventDefault(); onPick(next.ts) }
        }
        if (event.key === 'ArrowRight') go(at < 0 ? 0 : at + 1)
        if (event.key === 'ArrowLeft') go(at < 0 ? oldestFirst.length - 1 : at - 1)
        if (event.key === 'Home') go(0)
        if (event.key === 'End') go(oldestFirst.length - 1)
        if (event.key === 'Escape') onPick(null)
      }}
    >
      <span className="scrub__rail" aria-hidden />
      {oldestFirst.map((entry) => (
        <button
          key={entry.ts}
          type="button"
          role="option"
          aria-selected={picked === entry.ts}
          className={`scrub__pip scrub__pip--${verdictKind(entry.verdict)}${picked === entry.ts ? ' is-picked' : ''}`}
          title={`${fmtDate(entry.ts)} · ${entry.verdict} · ${entry.confidence}%`}
          aria-label={`Run of ${fmtDate(entry.ts)}, ${entry.verdict}, ${entry.confidence} percent confidence`}
          onClick={() => onPick(picked === entry.ts ? null : entry.ts)}
        />
      ))}
    </div>
    </div>
  )
}

/** Verdict reduced to the three states a marker can carry. */
function verdictKind(verdict: string): 'pos' | 'neg' | 'hold' {
  return verdict.includes('Buy') ? 'pos' : verdict.includes('Sell') ? 'neg' : 'hold'
}

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
    <section aria-label={`${ticker} verdict history`} className="panel panel--pad">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
        <h3 className="h-panel">Verdict timeline</h3>
        <span className="u-meta">
          {timeline.length} runs stored in this browser
        </span>
      </div>

      <RunScrubber entries={entries} onPick={setExpanded} picked={expanded} />

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
                  {fmtDate(entry.ts)}
                  {' · '}
                  {timeAgo(entry.ts)}
                </span>
                <span className={`badge ${verdictTone(entry.verdict)}`} style={{ height: 19, fontSize: '0.625rem' }}>
                  {entry.verdict}
                </span>
 <span className="num u-note" >
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
