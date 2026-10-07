'use client'

import { useEffect, useRef, type RefObject } from 'react'

/**
 * What a side panel owes the keyboard and the screen reader.
 *
 * The inspectors are non-modal dialogs: the page behind stays usable. They are
 * still dialogs, so opening one moves focus to it (a screen reader announces
 * its name, and Tab continues from inside it rather than from wherever the
 * click happened), and closing one returns focus to the control that opened
 * it. Before this they did neither, so a keyboard user opened an inspector and
 * had to tab through the rest of the page to find it.
 *
 * Escape closes the panel, unless a modal dialog is open above it. The palette
 * listens for Escape on `window` too; with both listening, one press closed the
 * palette and the inspector under it.
 */
export function useDrawerFocus<T extends HTMLElement>(
  active: boolean,
  onClose: () => void,
): RefObject<T | null> {
  const panel = useRef<T | null>(null)
  const close = useRef(onClose)
  useEffect(() => { close.current = onClose })

  useEffect(() => {
    if (!active) return undefined
    const opener = document.activeElement instanceof HTMLElement && document.activeElement !== document.body
      ? document.activeElement
      : null
    panel.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      if (document.querySelector('[aria-modal="true"]')) return
      close.current()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener?.isConnected) opener.focus()
    }
  }, [active])

  return panel
}
