'use client'

/**
 * The three facts that are true of the whole product, read live.
 *
 * Whether anything is armed in production, whether the holdout is still sealed,
 * and how large the registry is. They are global — the same on every workspace
 * — so twelve pages were each stating them as static text in their own rail.
 *
 * Static was wrong twice over. It repeated one fact twelve times, so changing
 * it meant changing it twelve times or having the workspaces disagree. And it
 * asserted live state the page could not see: with the backend down, every one
 * of those workspaces still announced HOLDOUT SEALED and REGISTRY 103 ENTRIES
 * while the panels above them correctly reported that nothing could be read.
 *
 * A rail that keeps saying "sealed" when the app cannot reach the thing that
 * would tell it is the most dangerous kind of stale: it is the reassuring half
 * of the screen, it is always in view, and it is the last thing a reader would
 * think to doubt.
 */

import { useEffect, useRef, useState } from 'react'

import { Status } from '@/components/system'
import type { ResearchState } from '@/components/system'
import { failed, observed, staleNote, type Observed } from '@/lib/observation'

interface Status {
  deployment_status?: string
  registry_available?: boolean
  total_entries?: number | null
  production?: number | null
  firewall?: { contract_state?: 'ARMED' | 'NOT_ARMED' | 'UNKNOWN' }
  holdout?: { touched?: boolean }
}

type Fact = { label: string; state: ResearchState; detail: string }

export default function SystemRail() {
  const [reading, setReading] = useState(true)
  const [obs, setObs] = useState<Observed<Status> | null>(null)
  // The last success survives a failure so the rail can say what it last saw.
  // Held in a ref as well as state because the failure handler needs the
  // previous value without re-running on every change of it.
  const last = useRef<Observed<Status> | null>(null)

  useEffect(() => {
    let alive = true
    const read = () => {
      fetch('/api/quant/status')
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`the status request returned ${r.status}`))))
        .then((d: Status) => {
          if (!alive) return
          const next = observed(d)
          last.current = next
          setObs(next)
          setReading(false)
        })
        .catch((e: Error) => {
          if (!alive) return
          setObs(failed(last.current, e.message))
          setReading(false)
        })
    }
    read()
    // Re-read periodically so a recovered backend returns the rail to a
    // current reading rather than leaving a remembered one on screen for the
    // rest of the session.
    const timer = window.setInterval(read, 30_000)
    return () => { alive = false; window.clearInterval(timer) }
  }, [])

  const facts: Fact[] = (() => {
    if (reading || obs === null) {
      return [
        { label: 'Production', state: 'waking', detail: 'reading' },
        { label: 'Holdout', state: 'waking', detail: 'reading' },
        { label: 'Registry', state: 'waking', detail: 'reading' },
      ]
    }
    if (obs.state === 'unavailable') {
      // Nothing was ever read. Not "none armed", not "sealed", not a count.
      return [
        { label: 'Production', state: 'unavailable', detail: 'cannot be read' },
        { label: 'Holdout', state: 'unavailable', detail: 'cannot be read' },
        { label: 'Registry', state: 'unavailable', detail: 'cannot be read' },
      ]
    }

    if (obs.state === 'last-observed' && obs.value !== null) {
      // A remembered reading, labelled as one. It carries the time it was read
      // — not the time the request failed — and every entry says "last seen",
      // so a stale figure cannot be mistaken for a live one.
      const p = obs.value.production
      const t = obs.value.holdout?.touched
      const n = obs.value.total_entries
      const note = (render: string) => staleNote(obs, () => render) ?? 'last seen'
      return [
        { label: 'Production', state: 'stale', detail: note(p ? `${p} armed` : 'none armed') },
        { label: 'Holdout', state: 'stale', detail: note(t ? 'spent' : 'sealed') },
        { label: 'Registry', state: 'stale', detail: note(n === null || n === undefined ? 'unread' : `${n} entries`) },
      ]
    }

    const d = obs.value as Status
    const production = d.production
    const armed = d.firewall?.contract_state
    const touched = d.holdout?.touched
    const entries = d.registry_available === false ? null : d.total_entries

    return [
      {
        label: 'Production',
        state: production === null || production === undefined ? 'unavailable'
          : production > 0 ? 'production' : 'unavailable',
        detail: production === null || production === undefined ? 'not reported'
          : production > 0 ? `${production} armed` : 'none armed',
      },
      {
        // Untouched is sealed. Unknown is not sealed — it is unknown, and the
        // three-valued contract state exists so the two are never merged.
        label: 'Holdout',
        state: touched === undefined && armed === 'UNKNOWN' ? 'unavailable'
          : touched ? 'unavailable' : 'blocked',
        detail: touched === undefined && armed === 'UNKNOWN' ? 'state not reported'
          : touched ? 'spent' : 'sealed',
      },
      {
        label: 'Registry',
        state: entries === null || entries === undefined ? 'unavailable' : 'recorded',
        detail: entries === null || entries === undefined
          ? 'could not be read'
          : `${entries} ${entries === 1 ? 'entry' : 'entries'}`,
      },
    ]
  })()

  return (
    <>
      {facts.map((f) => (
        <div className="wb-status-item" key={f.label} title={f.detail}>
          <span className="sys-label wb-status-key">{f.label}</span>
          <Status state={f.state} label={f.detail} />
        </div>
      ))}
    </>
  )
}
