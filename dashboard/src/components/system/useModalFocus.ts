'use client'

import { useEffect, useRef, type RefObject } from 'react'

/**
 * What a modal dialog owes the keyboard and the screen reader.
 *
 * `aria-modal="true"` tells assistive technology that everything behind the
 * dialog is inert, so the dialog has to keep that promise: focus moves into it
 * when it opens, Tab and Shift+Tab stay inside it, and closing it returns focus
 * to the control that opened it. A sheet that declared itself modal and did none
 * of that left the keyboard on the page underneath it.
 *
 * (Non-modal side panels use `useDrawerFocus`; `ui/Dialog` carries the same
 * behaviour for its own markup.)
 */

export const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Where Tab should go next, or null to let the browser move focus normally.
 *
 * Pure so the wrap-around rule can be tested without a DOM: `items` are the
 * dialog's focusable controls in order, `active` is what has focus now.
 */
export function trapTarget<T>(items: readonly T[], active: T | null, shift: boolean, panel: T): T | null {
  if (items.length === 0) return panel
  const first = items[0]
  const last = items[items.length - 1]
  if (shift && (active === first || active === panel || active === null)) return last
  if (!shift && active === last) return first
  return null
}

export function useModalFocus<T extends HTMLElement>(open: boolean): RefObject<T | null> {
  const panel = useRef<T | null>(null)

  useEffect(() => {
    if (!open) return undefined
    const opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null
    const controls = () => Array.from(panel.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])
    ;(controls()[0] ?? panel.current)?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !panel.current) return
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null
      const target = trapTarget(controls(), active, e.shiftKey, panel.current)
      if (target) { e.preventDefault(); target.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (opener?.isConnected) opener.focus()
    }
  }, [open])

  return panel
}
