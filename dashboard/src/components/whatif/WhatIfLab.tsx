'use client'

/**
 * What-If Lab — the same engine, one input moved.
 *
 * Every scenario here re-runs the real scoring engine with one perturbed
 * argument. There is no second model estimating what the verdict "would"
 * become, which is the only reason the sensitivities shown can be trusted: a
 * simulator that approximates production teaches a reader a relationship the
 * model does not have.
 *
 * Two presentation rules follow from that and are not cosmetic:
 *
 *   1. Everything is labelled SIMULATION. Nothing here is stored, nothing here
 *      changes the security's real signal, and a number that looks like a
 *      verdict must never be mistaken for one.
 *   2. A scenario that could not move anything says so, in words. The honest
 *      outcomes include "this lever had nothing to move" and "the macro gate
 *      only subtracts" — and a reader who sees two identical numbers with no
 *      explanation concludes the tool is broken rather than learning how the
 *      model works.
 */

import { useEffect, useState } from 'react'

import {
  AvailabilityNote,
  type AvailabilityPayload,
  isAvailable,
} from '@/components/system/Availability'
import { EmptyLine, Panel, Prose, StateBlock, signed } from '@/components/system'

interface Scenario {
  key: string
  label: string
  lever: string
  change: number
}

interface FamilyChange {
  current: number | null
  simulated: number | null
}

interface Simulation extends AvailabilityPayload {
  simulation?: boolean
  scenario?: string
  label?: string
  current_signal?: string | null
  current_confidence?: number | null
  current_risk?: number | null
  current_score?: number | null
  simulated_signal?: string | null
  simulated_confidence?: number | null
  simulated_risk?: number | null
  simulated_score?: number | null
  signal_changed?: boolean
  family_changes?: Record<string, FamilyChange>
  note?: string | null
}

const FAMILY_LABEL: Record<string, string> = {
  momentum: 'Momentum',
  fundamental: 'Valuation',
  quality: 'Quality',
  news: 'News',
  reversal: 'Reversal',
}

/** `??` not `||`: a score of exactly 0 is a measurement, not a missing value. */
const num = (v: number | null | undefined): string =>
  v === null || v === undefined ? '—' : String(v)

export default function WhatIfLab({ ticker }: { ticker: string }) {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [result, setResult] = useState<Simulation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const res = await fetch('/api/what-if/scenarios')
        if (!res.ok) return
        const body = (await res.json()) as { scenarios: Scenario[] }
        if (live) setScenarios(body.scenarios ?? [])
      } catch {
        /* Without scenarios the panel shows its empty line; nothing to report. */
      }
    })()
    return () => {
      live = false
    }
  }, [])

  // The ticker changing invalidates the result, not the scenario list. Leaving
  // a stale simulation on screen under a new security's heading would attribute
  // one security's sensitivity to another.
  useEffect(() => {
    setResult(null)
    setActive(null)
    setError(null)
  }, [ticker])

  async function run(scenario: string) {
    setBusy(true)
    setError(null)
    setResult(null)
    setActive(scenario)
    try {
      const res = await fetch('/api/what-if', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, scenario }),
      })
      if (!res.ok) {
        setError(`This scenario could not be simulated (${res.status}).`)
      } else {
        setResult((await res.json()) as Simulation)
      }
    } catch {
      setError('OmniSignal could not be reached.')
    } finally {
      setBusy(false)
    }
  }

  const moved = Object.entries(result?.family_changes ?? {})
  const unchanged =
    result &&
    isAvailable(result) &&
    result.current_score !== null &&
    result.current_score === result.simulated_score

  return (
    <Panel
      title="What-If Lab"
      subtitle="simulation only — nothing here is saved"
      badge="SIMULATION"
      badgeTone="warn"
    >
      <Prose>
        Each scenario re-runs the scoring engine for {ticker} with one input
        changed, and shows what the engine returns. It does not change {ticker}
        &rsquo;s real signal, and nothing on this panel is stored.
      </Prose>

      {scenarios.length ? (
        <div className="ask__chips" role="group" aria-label="Scenarios">
          {scenarios.map((s) => (
            <button
              key={s.key}
              type="button"
              className="ask__chip"
              disabled={busy}
              aria-pressed={active === s.key}
              onClick={() => void run(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      ) : null}

      {busy ? (
        <StateBlock state="waking" title="Re-scoring" detail="the same engine, one input moved" />
      ) : null}
      {error ? <StateBlock state="unavailable" title="Not simulated" detail={error} /> : null}

      {result && !isAvailable(result) ? <AvailabilityNote payload={result} /> : null}

      {result && isAvailable(result) ? (
        <div className="whatif__result">
          <table className="sys-table sys-table--compact whatif__table">
            <caption className="visually-hidden">
              {result.label} — current compared with simulated
            </caption>
            <thead>
              <tr>
                {/* The corner cell labels the row headers below it. It reads as
                    blank, and a screen reader still announces what the column
                    contains rather than an empty cell. */}
                <th scope="col"><span className="sys-sr-only">Measure</span></th>
                <th scope="col" className="num">Current</th>
                <th scope="col" className="num">Simulated</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Signal</th>
                <td className="num">{result.current_signal ?? '—'}</td>
                <td className="num" data-changed={result.signal_changed ? 'true' : undefined}>
                  {result.simulated_signal ?? '—'}
                </td>
              </tr>
              <tr>
                <th scope="row">Score</th>
                <td className="num">{signed(result.current_score)}</td>
                <td className="num">{signed(result.simulated_score)}</td>
              </tr>
              <tr>
                <th scope="row">Confidence</th>
                <td className="num">{num(result.current_confidence)}</td>
                <td className="num">{num(result.simulated_confidence)}</td>
              </tr>
              <tr>
                <th scope="row">Risk</th>
                <td className="num">{num(result.current_risk)}</td>
                <td className="num">{num(result.simulated_risk)}</td>
              </tr>
            </tbody>
          </table>

          <p className="whatif__verdict">
            {result.signal_changed
              ? `Under this scenario the signal would read ${result.simulated_signal} instead of ${result.current_signal}. It is a simulation, not a forecast.`
              : unchanged
                ? 'The signal does not move under this scenario.'
                : 'The signal category does not change, though the underlying score does.'}
          </p>

          {result.note ? <p className="ask__meta">{result.note}</p> : null}

          {moved.length ? (
            <p className="ask__meta">
              Where it landed:{' '}
              {moved
                .map(
                  ([name, change]) =>
                    `${FAMILY_LABEL[name] ?? name} ${signed(change.current, 2)} → ${signed(change.simulated, 2)}`,
                )
                .join(' · ')}
              .
            </p>
          ) : (
            <p className="ask__meta">No factor family moved under this scenario.</p>
          )}

          <p className="ask__meta">
            SIMULATION — {ticker}&rsquo;s stored signal, ranking and any saved
            analysis are unchanged.
          </p>
        </div>
      ) : null}

      {!busy && !result && !error ? (
        <EmptyLine label="What-if">
          Pick a scenario to see how the engine responds.
        </EmptyLine>
      ) : null}
    </Panel>
  )
}
