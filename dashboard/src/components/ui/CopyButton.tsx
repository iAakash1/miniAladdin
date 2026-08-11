'use client'

/**
 * CopyButton — copies a value and says so in place.
 *
 * Adapted from the Uiverse copy-button family, whose mechanism is a label
 * that *morphs* rather than a toast that appears: the control that performed
 * the action is the control that reports it, so feedback costs no layout and
 * needs no dismissal. The versions there swap an icon with a spring bounce
 * and a green flood; what survives here is the state machine and the width
 * reservation, not the bounce.
 *
 * Why this exists in a research terminal: tickers, factor names and figures
 * get pasted into notes, spreadsheets and messages constantly, and the
 * alternative is selecting monospace text inside a dense table by hand.
 *
 * The button never changes width between states — `idle` and `copied` labels
 * are stacked and the longer one sets the box — because a control that
 * resizes at the moment of clicking moves whatever sits next to it.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

type Phase = 'idle' | 'copied' | 'failed'

/** Long enough to read, short enough that the button is ready again by the
 *  time a second copy is wanted. */
const REVERT_MS = 1400

export default function CopyButton({
  value,
  label,
  title,
  className = 'btn btn--ghost btn--xs',
}: {
  /** The text placed on the clipboard. */
  value: string
  /** Resting label. Defaults to the value itself, which is the common case
   *  for a ticker: the button *is* the thing it copies. */
  label?: string
  /** Accessible description — "Copy ticker NVDA". */
  title: string
  className?: string
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = useCallback(async () => {
    clearTimeout(timer.current)
    try {
      // `navigator.clipboard` is unavailable on insecure origins and in some
      // embedded webviews. Reporting a failure the user can see beats a
      // button that silently does nothing.
      if (!navigator.clipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(value)
      setPhase('copied')
    } catch {
      setPhase('failed')
    }
    timer.current = setTimeout(() => setPhase('idle'), REVERT_MS)
  }, [value])

  const resting = label ?? value

  return (
    <button
      type="button"
      className={`${className} copyb`}
      aria-label={title}
      onClick={() => void copy()}
      data-phase={phase}
    >
      {/* Both labels are always in the DOM and overlaid, so the widest one
          fixes the width and the swap cannot reflow the row. `aria-live`
          announces the outcome without moving focus. */}
      <span className="copyb__stack" aria-hidden>
        <span className="copyb__face copyb__face--idle">{resting}</span>
        <span className="copyb__face copyb__face--done">
          {phase === 'failed' ? 'Press ⌘C' : 'Copied'}
        </span>
      </span>
      <span className="visually-hidden" role="status">
        {phase === 'copied' ? `${value} copied` : phase === 'failed' ? 'Copy unavailable' : ''}
      </span>
    </button>
  )
}
