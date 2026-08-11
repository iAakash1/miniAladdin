'use client'

/**
 * ConfirmButton — the one control in the product that destroys something.
 *
 * Five places let a user delete research they cannot get back: a vault run,
 * a saved report, an investigation, a watchlist ticker, a position. Every
 * one of them used to be a single unguarded click on a small ✕ sitting
 * directly beside "Open" and "Edit", and every one of them discarded the
 * result:
 *
 *     onClick={() => { void deleteHistory(id).then((ok) => ok && onDeleted()) }}
 *
 * So a failed delete did nothing at all — the row stayed, no message, and
 * the only reading available to the user was that the button is broken.
 *
 * ## Why arm-then-confirm rather than a modal
 *
 * A modal for deleting one table row is heavier than the action deserves,
 * moves focus, and covers the very row you are trying to identify. Arming
 * in place keeps the row visible, keeps focus on the control, and costs one
 * extra click. It disarms on blur, on Escape, and on a timer, so an armed
 * button left alone returns to rest instead of lying in wait.
 *
 * `window.confirm` was the other candidate and is worse: it blocks the main
 * thread, it cannot be styled, and on repeat use people click through it
 * without reading — which is the failure mode this exists to prevent.
 *
 * ## Honesty about the outcome
 *
 * `onConfirm` reports whether the deletion actually happened. `false` or a
 * throw leaves the row in place and says so inline. Nothing here pretends a
 * failed request succeeded.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** Long enough to read the confirm label and decide; short enough that a
 *  forgotten armed button is not still armed when you scroll back. */
const DISARM_MS = 4000

type Phase = 'rest' | 'armed' | 'working' | 'failed'

export default function ConfirmButton({
  children,
  confirmLabel = 'Confirm?',
  description,
  onConfirm,
  onDone,
  className = 'btn btn--ghost btn--xs',
}: {
  /** Resting content — usually '✕' or 'Delete'. */
  children: React.ReactNode
  /** Shown once armed. Should name the consequence: "Delete?", "Remove?". */
  confirmLabel?: string
  /** Full sentence for screen readers: "Delete AAPL run from Jul 28". */
  description: string
  /** Performs the deletion. `false` (or a throw) means it did not happen. */
  onConfirm: () => Promise<boolean | void> | boolean | void
  /** Called only after a confirmed success. */
  onDone?: () => void
  className?: string
}) {
  const [phase, setPhase] = useState<Phase>('rest')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      clearTimeout(timer.current)
    }
  }, [])

  const disarm = useCallback(() => {
    clearTimeout(timer.current)
    if (alive.current) setPhase('rest')
  }, [])

  const arm = useCallback(() => {
    setPhase('armed')
    clearTimeout(timer.current)
    timer.current = setTimeout(disarm, DISARM_MS)
  }, [disarm])

  async function run() {
    clearTimeout(timer.current)
    setPhase('working')
    try {
      const ok = await onConfirm()
      if (!alive.current) return
      // `void` means "the caller handles its own bookkeeping" and counts as
      // success; only an explicit `false` is a failure.
      if (ok === false) {
        setPhase('failed')
        return
      }
      // Deliberately no success phase: the row is about to disappear, and
      // setting state on a component that is unmounting is pointless noise.
      onDone?.()
    } catch {
      if (alive.current) setPhase('failed')
    }
  }

  if (phase === 'failed') {
    return (
      <span className="confirm confirm--failed" role="alert">
        <span className="confirm__msg">Couldn&apos;t delete</span>
        <button type="button" className={className} onClick={() => setPhase('armed')}>
          Retry
        </button>
      </span>
    )
  }

  const armed = phase === 'armed'
  const working = phase === 'working'

  return (
    <button
      type="button"
      className={`${className} confirm${armed ? ' is-armed' : ''}`}
      aria-label={armed ? `${description} — confirm` : description}
      disabled={working}
      onClick={() => (armed ? void run() : arm())}
      onBlur={armed ? disarm : undefined}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && armed) {
          event.stopPropagation()
          disarm()
        }
      }}
    >
      {working ? '…' : armed ? confirmLabel : children}
    </button>
  )
}
