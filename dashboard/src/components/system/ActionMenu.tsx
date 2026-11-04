'use client'

/**
 * A row's secondary actions behind one button.
 *
 * Tables of securities carry five or more actions per row; drawn as buttons
 * they stack into three lines and the numbers lose the row. This keeps the
 * row to one line and the actions one press away, without hiding any of them.
 *
 * It is a real menu: Enter, Space or ArrowDown opens it on the first item,
 * ArrowUp on the last; arrows, Home and End move; a letter jumps to the next
 * item that starts with it; Escape and Tab close it and focus returns to the
 * button. Disabled items are announced but skipped.
 *
 * Placement. The list is positioned against the viewport, so a table that
 * scrolls sideways does not clip it, and it closes when the page scrolls
 * rather than drifting away from its row. It opens below the button and
 * flips above it when the space below is short; it is held inside the
 * viewport on both sides. On a phone it is a sheet along the bottom edge,
 * with full-width items a thumb can hit.
 */

import Link from 'next/link'
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'

export type ActionItem =
  | { kind?: 'action'; label: string; onSelect: () => void; disabled?: boolean; tone?: 'danger' }
  | { kind: 'link'; label: string; href: string }
  | { kind: 'group'; label: string }
  | { kind: 'separator' }

/** Below this width the menu is a bottom sheet. Matches the card breakpoint. */
const SHEET_QUERY = '(max-width: 640px)'
const EDGE = 8
const GAP = 4

export default function ActionMenu({ label, items, size = 'sm' }: {
  label: string
  items: ActionItem[]
  /** `sm` sits beside the small row buttons; `md` beside a regular control. */
  size?: 'sm' | 'md'
}) {
  const [open, setOpen] = useState<null | { sheet: boolean; top: number; right: number }>(null)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const menuId = useId()

  const anchor = useCallback(() => {
    const r = button.current?.getBoundingClientRect()
    return r ? { top: r.bottom + GAP, right: Math.max(EDGE, window.innerWidth - r.right) } : { top: 0, right: EDGE }
  }, [])

  const close = useCallback((refocus: boolean) => {
    setOpen(null)
    if (refocus) button.current?.focus()
  }, [])

  const enabled = () =>
    Array.from(list.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') ?? [])

  const focusItem = (which: 'first' | 'last' | number) => {
    const nodes = enabled()
    if (!nodes.length) return
    const i = which === 'first' ? 0 : which === 'last' ? nodes.length - 1 : (which + nodes.length) % nodes.length
    nodes[i].focus()
  }

  const openAt = (which: 'first' | 'last') => {
    const sheet = window.matchMedia(SHEET_QUERY).matches
    setOpen({ sheet, ...anchor() })
    requestAnimationFrame(() => focusItem(which))
  }

  // Keep the list on screen. Measured after layout and applied to the node
  // directly: the list's own height decides whether it flips, and that is
  // only known once it has rendered.
  useLayoutEffect(() => {
    const node = list.current
    const trigger = button.current?.getBoundingClientRect()
    if (!open || open.sheet || !node || !trigger) return
    const box = node.getBoundingClientRect()
    if (box.bottom > window.innerHeight - EDGE) {
      const above = trigger.top - GAP - box.height
      node.style.top = `${Math.max(EDGE, above)}px`
    }
    if (box.left < EDGE) {
      node.style.right = 'auto'
      node.style.left = `${EDGE}px`
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node
      if (!list.current?.contains(t) && !button.current?.contains(t)) close(false)
    }
    const onScroll = (e: Event) => { if (!open.sheet && !list.current?.contains(e.target as Node)) close(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.preventDefault(); close(true) } }
    const onResize = () => close(false)
    window.addEventListener('pointerdown', onDown)
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('pointerdown', onDown)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onResize)
    }
  }, [open, close])

  const onListKey = (e: React.KeyboardEvent) => {
    const nodes = enabled()
    const at = nodes.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'ArrowDown') { e.preventDefault(); focusItem(at + 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusItem(at - 1) }
    else if (e.key === 'Home') { e.preventDefault(); focusItem('first') }
    else if (e.key === 'End') { e.preventDefault(); focusItem('last') }
    else if (e.key === 'Tab') close(false)
    else if (e.key.length === 1 && /\S/.test(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey) {
      // Type-ahead: the next enabled item, after the current one, whose
      // label starts with the letter pressed.
      const key = e.key.toLowerCase()
      const order = [...nodes.slice(at + 1), ...nodes.slice(0, at + 1)]
      order.find((n) => (n.textContent ?? '').trim().toLowerCase().startsWith(key))?.focus()
    }
  }

  return (
    <>
      <button
        ref={button} type="button"
        className={`sys-btn sys-btn--icon sys-menu__trigger${size === 'sm' ? ' sys-btn--xs' : ''}`}
        aria-label={label} aria-haspopup="menu" aria-expanded={open !== null} aria-controls={open ? menuId : undefined}
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
      {open ? (
        <>
          {open.sheet ? <div className="sys-menu__scrim" aria-hidden="true" /> : null}
          <div
            ref={list} id={menuId} role="menu" aria-label={label}
            className={`sys-menu${open.sheet ? ' sys-menu--sheet' : ''}`}
            style={open.sheet ? undefined : { top: open.top, right: open.right }}
            onKeyDown={onListKey}
          >
            {open.sheet ? <div className="sys-menu__title" aria-hidden="true">{label}</div> : null}
            {items.map((item, i) => {
              if (item.kind === 'separator') return <div key={`s${i}`} role="separator" className="sys-menu__sep" />
              if (item.kind === 'group') return <div key={`g${i}`} role="presentation" className="sys-menu__group">{item.label}</div>
              if (item.kind === 'link') {
                return (
                  <Link key={item.label} role="menuitem" tabIndex={-1} className="sys-menu__item" href={item.href} onClick={() => setOpen(null)}>
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
        </>
      ) : null}
    </>
  )
}
