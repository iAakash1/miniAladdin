'use client'

/**
 * Transient feedback, stacked.
 *
 * Adapted from the Uiverse notification family. Their mechanism is a card
 * that enters from an edge, holds, and leaves on a timer without ever
 * taking focus; the versions there arrive with coloured glows and icons,
 * and what is worth keeping is the lifecycle and the fact that it never
 * interrupts what you are doing.
 *
 * Why OmniSignal needs it: several actions currently succeed in complete
 * silence. Adding a ticker to a watchlist, removing one, and refreshing
 * quotes all mutate server state and say nothing — the row appears, or it
 * doesn't, and a failure is indistinguishable from a slow network.
 *
 * Deliberately not a modal and never focus-stealing: `role="status"` with
 * `aria-live="polite"` announces without hijacking the caret, which matters
 * because these fire while the user is typing the next ticker.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface Toast {
  id: number
  message: string
  tone: 'ok' | 'warn'
}

const HOLD_MS = 3200
/** Beyond three, the stack becomes a wall — older ones are dropped. */
const MAX_VISIBLE = 3

let seq = 0
const listeners = new Set<(t: Toast) => void>()

/** Announce something. Callable from anywhere, including outside React. */
export function notify(message: string, tone: Toast['tone'] = 'ok') {
  const toast: Toast = { id: (seq += 1), message, tone }
  listeners.forEach((listener) => listener(toast))
}

export default function Toasts() {
  const [items, setItems] = useState<Toast[]>([])
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) { clearTimeout(timer); timers.current.delete(id) }
  }, [])

  useEffect(() => {
    const onToast = (toast: Toast) => {
      setItems((current) => [...current, toast].slice(-MAX_VISIBLE))
      timers.current.set(toast.id, setTimeout(() => dismiss(toast.id), HOLD_MS))
    }
    listeners.add(onToast)
    const pending = timers.current
    return () => {
      listeners.delete(onToast)
      pending.forEach((timer) => clearTimeout(timer))
      pending.clear()
    }
  }, [dismiss])

  if (items.length === 0) return null

  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((toast) => (
        <div key={toast.id} className={`toast toast--${toast.tone}`}>
          <span className="toast__msg">{toast.message}</span>
          <button
            type="button"
            className="toast__x"
            aria-label="Dismiss notification"
            onClick={() => dismiss(toast.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
