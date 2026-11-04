'use client'

/**
 * A row's secondary actions behind one button.
 *
 * Tables of securities carry five or more actions per row; drawn as buttons
 * they stack into three lines and the numbers lose the row. This keeps the
 * row to one line and the actions one press away, without hiding any of them.
 *
 * It is a real menu: Enter, Space or ArrowDown opens it on the first item,
 * ArrowUp on the last; arrows, Home and End move; Escape and Tab close it and
 * focus returns to the button. The list is positioned against the viewport,
 * so a table that scrolls sideways does not clip it, and it closes when the
 * page scrolls rather than drifting away from its row.
 */

import Link from 'next/link'
import { useCallback, useEffect, useId, useRef, useState } from 'react'

export type ActionItem =
  | { kind?: 'action'; label: string; onSelect: () => void; disabled?: boolean; tone?: 'danger' }
  | { kind: 'link'; label: string; href: string }
  | { kind: 'group'; label: string }
  | { kind: 'separator' }

export default function ActionMenu({ label, items }: { label: string; items: ActionItem[] }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; right: number } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const menuId = useId()

  const place = useCallback(() => {
    const r = button.current?.getBoundingClientRect()
    if (r) setPos({ top: r.bottom + 4, right: Math.max(8, window.innerWidth - r.right) })
  }, [])

  const close = useCallback((refocus: boolean) => {
    setOpen(false)
    if (refocus) button.current?.focus()
  }, [])

  const focusItem = (which: 'first' | 'last' | number) => {
    const nodes = Array.from(list.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? [])
    if (!nodes.length) return
    const i = which === 'first' ? 0 : which === 'last' ? nodes.length - 1 : (which + nodes.length) % nodes.length
    nodes[i].focus()
  }

  const openAt = (which: 'first' | 'last') => {
    place()
    setOpen(true)
    requestAnimationFrame(() => focusItem(which))
  }

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!list.current?.contains(t) && !button.current?.contains(t)) close(false)
    }
    const onScroll = (e: Event) => { if (!list.current?.contains(e.target as Node)) close(false) }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', place)
    }
  }, [open, close, place])

  const onListKey = (e: React.KeyboardEvent) => {
    const nodes = Array.from(list.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? [])
    const at = nodes.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'ArrowDown') { e.preventDefault(); focusItem(at + 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusItem(at - 1) }
    else if (e.key === 'Home') { e.preventDefault(); focusItem('first') }
    else if (e.key === 'End') { e.preventDefault(); focusItem('last') }
    else if (e.key === 'Escape') { e.preventDefault(); close(true) }
    else if (e.key === 'Tab') close(false)
  }

  return (
    <>
      <button
        ref={button} type="button" className="sys-btn sys-btn--icon sys-menu__trigger"
        aria-label={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
        onClick={() => (open ? close(false) : openAt('first'))}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); openAt('first') }
          else if (e.key === 'ArrowUp') { e.preventDefault(); openAt('last') }
        }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
          <circle cx="3.5" cy="8" r="1.25" fill="currentColor" />
          <circle cx="8" cy="8" r="1.25" fill="currentColor" />
          <circle cx="12.5" cy="8" r="1.25" fill="currentColor" />
        </svg>
      </button>
      {open && pos ? (
        <div
          ref={list} id={menuId} role="menu" aria-label={label} className="sys-menu"
          style={{ top: pos.top, right: pos.right }} onKeyDown={onListKey}
        >
          {items.map((item, i) => {
            if (item.kind === 'separator') return <div key={`s${i}`} role="separator" className="sys-menu__sep" />
            if (item.kind === 'group') return <div key={`g${i}`} role="presentation" className="sys-menu__group">{item.label}</div>
            if (item.kind === 'link') {
              return (
                <Link key={item.label} role="menuitem" tabIndex={-1} className="sys-menu__item" href={item.href} onClick={() => setOpen(false)}>
                  {item.label}
                </Link>
              )
            }
            return (
              <button
                key={item.label} type="button" role="menuitem" tabIndex={-1}
                className="sys-menu__item" data-tone={item.tone}
                aria-disabled={item.disabled || undefined}
                onClick={() => { if (item.disabled) return; close(true); item.onSelect() }}
              >
                {item.label}
              </button>
            )
          })}
        </div>
      ) : null}
    </>
  )
}
