'use client'

import { useEffect, useRef, type ReactNode } from 'react'

import Icon from '@/components/shell/Icon'

/**
 * A right-hand inspector that overlays the workspace instead of taking width
 * from it. Escape and the scrim close it; focus returns to whatever opened it.
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
  const opener = useRef<Element | null>(null)

  useEffect(() => {
    if (!open) return undefined
    opener.current = document.activeElement
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (opener.current instanceof HTMLElement) opener.current.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      <button type="button" className="drawer-scrim" aria-label="Close panel" tabIndex={-1} onClick={onClose} />
      <aside
        id={id}
        className="drawer"
        role="dialog"
        aria-modal="false"
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
