'use client'

/**
 * Three form controls the product kept re-improvising: a boolean, an
 * n-of-many choice, and a continuous threshold. Each was previously a plain
 * checkbox, a row of buttons, or a bare `<input type="range">` with default
 * platform chrome — which is why filters looked like a settings dialog
 * rather than part of an instrument.
 *
 * All three adapt a real Uiverse mechanism, credited at each definition.
 * What is adapted is the *mechanism* — the thing that makes the interaction
 * legible — never the styling: colours, radii, type and spacing all resolve
 * to existing tokens, and every control keeps its native input underneath so
 * keyboard, form semantics and screen readers are unchanged.
 */

import { useId } from 'react'

/* ── Switch ───────────────────────────────────────────────────────────────
   Adapted from Uiverse `alexruix/silent-otter-72`. The original's insight is
   that a track and a knob alone tell you a switch *moved* but not what it
   now means, so a check glyph slides in from behind the knob as the state
   turns on (`right: 60% -> 20%`, opacity 0 -> 1) — position and symbol
   arrive together. Kept exactly that; dropped the 17px scale and the
   #222/#B0B0B0 palette for token sizing and `--accent`. */
export function Switch({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  /** Visible text beside the control. */
  label: string
  /** One short clause on what turning it on does. */
  hint?: string
}) {
  const id = useId()
  return (
    <span className="uswitch-row">
      {/* No `htmlFor` here on purpose. This label *contains* the input, so
          the association is already implicit — adding `for` as well makes
          the click activate the control twice (once via label forwarding,
          once via the real target), which toggles and immediately untoggles
          it. The switch looked inert: one click, no change. The separate
          text label below does carry `htmlFor`, since it is not a
          container. */}
      <label className="uswitch">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="uswitch__track">
          <svg className="uswitch__check" viewBox="0 0 32 32" aria-hidden>
            <path fill="none" d="m4 16.5 8 8 16-16" />
          </svg>
          <span className="uswitch__knob" />
        </span>
      </label>
      <label className="uswitch__label" htmlFor={id}>
        {label}
        {hint && <span className="uswitch__hint">{hint}</span>}
      </label>
    </span>
  )
}

/* ── Segmented control ────────────────────────────────────────────────────
   Adapted from Uiverse `zanina-yassine/curly-shrimp-52` and
   `ssweb_8300/sour-lionfish-41`. Both replace per-option backgrounds with a
   *single* indicator element that slides between positions, so the control
   reads as one selection moving rather than as several buttons independently
   lighting up — the state has continuity. The Uiverse versions hard-code the
   indicator offset per option in CSS (`left: calc(130px * 2 + 2px)`), which
   only works for a fixed option count; here the transform is computed from
   the index, so the same component serves a 2-option and a 5-option control.

   The existing `.seg` remains for controls whose options are not equal
   width; this is for the equal-width case where the slide is possible. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: ReadonlyArray<{ value: T; label: string; title?: string }>
  value: T
  onChange: (next: T) => void
  /** Accessible group name — "Rank by", "Time window". */
  label: string
}) {
  const index = Math.max(0, options.findIndex((option) => option.value === value))
  return (
    <span
      className="useg"
      role="radiogroup"
      aria-label={label}
      style={{ '--useg-count': options.length } as React.CSSProperties}
    >
      <span
        className="useg__indicator"
        aria-hidden
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          title={option.title}
          className="useg__opt"
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </span>
  )
}

/* ── Threshold slider ─────────────────────────────────────────────────────
   Adapted from Uiverse `Galahhad/happy-dodo-17`. A native range input paints
   no filled portion, so "how far along am I" has to be read off the thumb's
   position against the ends. The Uiverse trick is a zero-size thumb carrying
   an enormous one-sided box-shadow (`-200px 0 0 200px`) clipped by
   `overflow: hidden` on the track — the fill is the thumb's own shadow, so
   it tracks the value with no JavaScript and no second element. Kept; the
   thumb is given back a visible size so it stays grabbable, and the colours
   come from tokens. */
export function Threshold({
  value,
  min,
  max,
  step = 1,
  onChange,
  label,
  format,
}: {
  value: number
  min: number
  max: number
  step?: number
  onChange: (next: number) => void
  label: string
  /** Renders the current value. Defaults to the bare number. */
  format?: (value: number) => string
}) {
  const id = useId()
  return (
    <span className="uthresh">
      <label className="uthresh__label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        className="uthresh__input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <output className="uthresh__value num" htmlFor={id}>
        {format ? format(value) : value}
      </output>
    </span>
  )
}
