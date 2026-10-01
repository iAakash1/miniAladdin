'use client'

import { useEffect, useRef, type ReactNode } from 'react'

import Icon from '@/components/shell/Icon'

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * A right-hand inspector that overlays the workspace instead of taking width
 * from it. Escape and the scrim close it; Tab stays inside it while it is
 * open, because the scrim makes everything behind it unreachable by pointer
 * and focus should agree; focus returns to whatever opened it.
 */
export default function Drawer({
  id, open, onClose, title, meta, children, width,
}: {
  id?: string
  open: boolean
  onClose: () => void
  title: string
  meta?: ReactNode
  children: ReactNode
  width?: number
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const opener = useRef<Element | null>(null)
  // Callers pass an inline closure. Keyed on it, this effect re-ran on every
  // parent render and pulled focus back to the close button mid-typing.
  const closeLatest = useRef(onClose)
  useEffect(() => { closeLatest.current = onClose }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    opener.current = document.activeElement
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { closeLatest.current(); return }
      if (e.key !== 'Tab' || !panelRef.current) return
      const items = [...panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      const inside = panelRef.current.contains(document.activeElement)
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener.current instanceof HTMLElement) opener.current.focus()
    }
  }, [open])

  if (!open) return null

  return (
    <>
      <button type="button" className="drawer-scrim" aria-label="Close panel" tabIndex={-1} onClick={onClose} />
      <aside
        ref={panelRef}
        id={id}
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={width ? { width: `min(${width}px, 100vw)` } : undefined}
      >
        <header className="drawer__head">
          <div className="drawer__title">
            <h2>{title}</h2>
            {meta ? <div className="drawer__meta">{meta}</div> : null}
          </div>
          <button ref={closeRef} type="button" className="sys-btn sys-btn--icon" onClick={onClose} aria-label="Close panel">
            <Icon name="close" size={14} />
          </button>
        </header>
        <div className="drawer__body">{children}</div>
      </aside>
    </>
  )
}
