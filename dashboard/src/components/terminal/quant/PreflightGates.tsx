'use client'

/**
 * The integrity gates standing between the research and the holdout.
 *
 * These nine checks already decided whether the holdout may be opened — the
 * holdout runner defers to them — and they were reachable only by running a
 * CLI. They are the most direct answer this product has to "can this research
 * be trusted", and no surface showed them.
 *
 * Two things this panel must not imply:
 *
 * - that clearing the gates opens anything. It does not; spending the holdout
 *   is an explicit human run under the contract.
 * - that a fast preflight is the gate the runner requires. It omits the
 *   two-build contamination probe, which is the check that found the as-of join
 *   defect that voided EXP-002, so the omission is stated rather than implied.
 */

import { useEffect, useState } from 'react'
import { quantFetch } from '@/lib/quantApi'
import { Panel, StateBlock } from '@/components/system'

interface Gate {
  check: string
  passed: boolean
  blocking: boolean
  detail: string
}

interface Preflight {
  available: boolean
  detail?: string
  experiment_id?: string | null
  study_artifact?: string
  fast_gates_clear?: boolean
  valid_for_run?: boolean
  contamination_probe?: { run: boolean; why: string; command: string }
  holdout_start?: string | null
  holdout_end?: string | null
  fingerprint?: string | null
  checks?: Gate[]
  blocking_failures?: string[]
  advisories?: string[]
  summary?: string
  note?: string
}

export default function PreflightGates() {
  const [state, setState] = useState<Preflight | null>(null)
  const [failed, setFailed] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    quantFetch<Preflight>('/api/quant/preflight')
      .then((r) => {
        if (!live) return
        if (r.ok) setState(r.data)
        else setFailed(`${r.message} ${r.remedy}`)
      })
      .catch(() => { if (live) setFailed('The request never reached a server.') })
    return () => { live = false }
  }, [])

  if (failed) {
    return (
      <Panel title="Holdout preflight" badge="UNAVAILABLE" badgeTone="warn">
        <StateBlock state="unavailable" title="Unavailable — the integrity gates" detail={failed} />
      </Panel>
    )
  }
  if (!state) {
    return (
      <Panel title="Holdout preflight">
        <StateBlock state="waking" title="Reading the integrity gates" />
      </Panel>
    )
  }
  if (!state.available) {
    return (
      <Panel title="Holdout preflight" badge="NO STUDY" badgeTone="muted">
        <StateBlock state="unavailable" title="No data for a study to gate" detail={state.detail} />
      </Panel>
    )
  }

  const checks = state.checks ?? []
  const blocking = checks.filter((c) => !c.passed && c.blocking)
  const advisory = checks.filter((c) => !c.passed && !c.blocking)
  const passed = checks.filter((c) => c.passed)

  return (
    <Panel
      title="Holdout preflight"
      subtitle={state.experiment_id ?? undefined}
      badge={blocking.length ? `${blocking.length} BLOCKING` : 'FAST GATES CLEAR'}
      badgeTone={blocking.length ? 'fail' : 'pass'}
      source={state.study_artifact}
      asOf={state.fingerprint ? `fingerprint ${state.fingerprint.slice(0, 12)}` : undefined}
    >
      <p className="body-copy u-note" style={{ marginTop: 0 }}>
        {state.summary}. Holdout window {state.holdout_start} → {state.holdout_end}.
      </p>

      <div className="qs-gates">
        {[...blocking, ...advisory, ...passed].map((gate) => (
          <div
            key={gate.check}
            className={`qs-gate qs-gate--${gate.passed ? 'pass' : gate.blocking ? 'fail' : 'warn'}`}
          >
            <div className="qs-gate__head">
              <span className="qs-gate__name">{gate.check}</span>
              <span
                className={`tp-status tp-status--${
                  gate.passed ? 'pass' : gate.blocking ? 'fail' : 'warn'
                }`}
              >
                {gate.passed ? 'PASS' : gate.blocking ? 'BLOCKING' : 'ADVISORY'}
              </span>
            </div>
            <p className="qs-gate__purpose u-note">{gate.detail}</p>
          </div>
        ))}
      </div>

      {/* The omission is stated, not implied. A fast preflight is a read, not
          the gate the holdout runner requires. */}
      {state.contamination_probe && !state.contamination_probe.run ? (
        <StateBlock state="blocked" title="Locked — the contamination probe" detail={state.contamination_probe.why} />
      ) : null}

      <p className="body-copy u-note">{state.note}</p>
    </Panel>
  )
}
