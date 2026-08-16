'use client'

import { useId, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

interface TooltipProps {
  /** Accessible name for the trigger, e.g. "Why Dollar Index matters". */
  label: string
  children: ReactNode
}

/**
 * Small "why this matters" info affordance — hover, focus, or click reveals
 * a short explanation anchored below the trigger. Closes on Escape, blur,
 * or mouse-leave. Shared by dashboard Cards and the breadth/section
 * headers now; the Validation phase will lean on this same primitive for
 * formula/interpretation panels, so it's kept generic (any content, not
 * just plain text).
 */
export default function Tooltip({ label, children }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Escape') setOpen(false)
  }

  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle' }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="info-trigger"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        onClick={() => setOpen((value) => !value)}
      >
        ⓘ
      </button>
      {/* No `fade-in` on the bubble any more. `.tooltip-bubble` now carries
          its own entrance — it unfolds from the trigger's corner rather than
          fading in place — and two `animation` declarations on one element
          do not compose: the later one simply wins, so the generic fade was
          silently replacing the specific one. (The comment sits above the
          conditional because a JSX comment cannot be the first child of
          `{cond && (…)}`.) */}
      {open && (
        <span role="tooltip" id={id} className="tooltip-bubble panel">
          {children}
        </span>
      )}
    </span>
  )
}
