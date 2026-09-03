'use client'

/**
 * The integrity gates standing between the research and the holdout.
 *
 * These checks already decided whether the holdout may be opened — the holdout
 * runner defers to them — and for a long time they were reachable only by
 * running a CLI. They are the most direct answer this product has to "can this
 * research be trusted", so they belong beside the promotion gates rather than
 * behind a command.
 *
 * They are a different question from the gates above them on this page, and the
 * page has to keep the two apart. Promotion gates ask whether a model has
 * earned production. These ask whether the study is clean enough for its
 * holdout to mean anything at all — a study that fails here cannot be rescued
 * by a better model, because the number it would produce would be measuring
 * contamination.
 *
 * Two things this panel must not imply:
 *
 *  - that clearing the gates opens anything. It does not; spending the holdout
 *    is an explicit human run under the contract.
 *  - that a fast preflight is the gate the runner requires. It omits the
 *    two-build contamination probe — the check that found the as-of join defect
 *    which voided EXP-002 — so the omission is stated rather than implied.
 */

import { useEffect, useState } from 'react'

import { Panel, Prose, StateBlock, Status } from '@/components/system'
import { quantFetch } from '@/lib/quantApi'

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

export default function HoldoutPreflight() {
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
      <Panel title="Holdout preflight" state="unavailable">
        <StateBlock state="unavailable" title="Unavailable — the integrity gates" detail={failed} />
      </Panel>
    )
  }
  if (!state) {
    return (
      <Panel title="Holdout preflight" state="waking">
        <StateBlock state="waking" title="Reading the integrity gates" />
      </Panel>
    )
  }
  if (!state.available) {
    return (
      <Panel title="Holdout preflight" state="unavailable" badge="NO STUDY" badgeTone="muted">
        <StateBlock state="unavailable" title="No study for the gates to read" detail={state.detail} />
      </Panel>
    )
  }

  const checks = state.checks ?? []
  const blocking = checks.filter((c) => !c.passed && c.blocking)
  const advisory = checks.filter((c) => !c.passed && !c.blocking)
  const passed = checks.filter((c) => c.passed)

  // Failures first, then advisories, then what passed. A reader scanning this
  // panel wants the reason it is blocked, and putting nine passes above one
  // failure buries the only line that changes what they do next.
  const ordered = [...blocking, ...advisory, ...passed]

  return (
    <Panel
      title="Holdout preflight"
      subtitle={state.experiment_id ?? undefined}
      state={blocking.length ? 'blocked' : 'recorded'}
      badge={blocking.length ? `${blocking.length} BLOCKING` : 'FAST GATES CLEAR'}
      badgeTone={blocking.length ? 'fail' : 'pass'}
      source={state.study_artifact}
      asOf={state.fingerprint ? `fingerprint ${state.fingerprint.slice(0, 12)}` : undefined}
    >
      <Prose>
        {state.summary}. Holdout window {state.holdout_start} → {state.holdout_end}.
      </Prose>

      <table className="sys-table sys-table--compact" style={{ marginTop: 'var(--d-3)' }}>
        <thead>
          <tr><th>Check</th><th style={{ width: '7rem' }}>Verdict</th><th>What it establishes</th></tr>
        </thead>
        <tbody>
          {ordered.map((gate) => (
            <tr key={gate.check}>
              <td className="sys-mono">{gate.check}</td>
              <td>
                <Status
                  state={gate.passed ? 'recorded' : gate.blocking ? 'blocked' : 'stale'}
                  label={gate.passed ? 'PASS' : gate.blocking ? 'BLOCKING' : 'ADVISORY'}
                />
              </td>
              <td><span className="sys-meta">{gate.detail}</span></td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* The omission is stated, not implied. A fast preflight is a read, not
          the gate the holdout runner requires. */}
      {state.contamination_probe && !state.contamination_probe.run ? (
        <div style={{ marginTop: 'var(--d-3)' }}>
          <StateBlock
            state="blocked"
            title="Not run here — the contamination probe"
            detail={state.contamination_probe.why}
          />
        </div>
      ) : null}

      {state.note ? <Prose size="tight" caution>{state.note}</Prose> : null}
    </Panel>
  )
}
