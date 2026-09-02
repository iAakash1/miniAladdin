'use client'

/**
 * `g`-prefixed navigation chords.
 *
 * Press `g`, then a letter. The pattern is standard in keyboard-driven tools
 * and it earns its place here for the reason it does there: a researcher moving
 * between market, factors and the quant register does it dozens of times, and a
 * chord costs one hand and no pointer.
 *
 * Every destination is a route that exists. There are no shortcuts to features
 * that do not, which is why this list is shorter than it could be.
 *
 * ## When it must not fire
 *
 * The hard part of a global key handler is knowing when to stay out of the way:
 *
 * - while typing in an input, textarea, select or contenteditable — otherwise
 *   `g` becomes unusable in the ticker box, which is the one control a user
 *   types into most;
 * - while a modifier is held, so browser and OS shortcuts are untouched;
 * - while a dialog or the palette is open, since those own the keyboard;
 * - after the chord times out, so a stray `g` does not arm a trap that
 *   hijacks an unrelated keystroke seconds later.
 */

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

/** How long `g` stays armed. Long enough to be deliberate, short enough that a
 *  forgotten press cannot capture a later keystroke. */
const CHORD_MS = 1500

export interface GotoTarget {
  key: string
  href: string
  label: string
}

/** The destinations, in the order the navigation presents them. */
export const GOTO_TARGETS: GotoTarget[] = [
  { key: 'm', href: '/terminal', label: 'Market' },
  { key: 'r', href: '/terminal/analyze', label: 'Research' },
  { key: 'f', href: '/terminal/factors', label: 'Factors' },
  { key: 'q', href: '/quant', label: 'Quant' },
  { key: 'd', href: '/terminal/models', label: 'Models' },
  { key: 'p', href: '/terminal/portfolio', label: 'Portfolio' },
  { key: 'w', href: '/terminal/sessions', label: 'Workspace' },
  { key: 'v', href: '/terminal/validation', label: 'Validation' },
]

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

export function useGotoShortcuts(): void {
  const router = useRouter()
  const armed = useRef<number | null>(null)

  useEffect(() => {
    const disarm = () => {
      if (armed.current !== null) {
        window.clearTimeout(armed.current)
        armed.current = null
      }
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isTyping(event.target)) return
      // A dialog or the palette owns the keyboard while it is open.
      if (document.querySelector('[role="dialog"], [aria-modal="true"]')) return

      const key = event.key.toLowerCase()

      if (armed.current !== null) {
        const target = GOTO_TARGETS.find((t) => t.key === key)
        disarm()
        if (target) {
          event.preventDefault()
          router.push(target.href)
        }
        return
      }

      if (key === 'g' && !event.shiftKey) {
        // Not prevented: `g` alone still does whatever it otherwise would.
        armed.current = window.setTimeout(disarm, CHORD_MS)
      }
    }

    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      disarm()
    }
  }, [router])
}
