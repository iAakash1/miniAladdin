/**
 * Which navigation groups are folded away.
 *
 * Twenty-five destinations in six groups is a long rail, and most sessions use
 * one or two of those groups. Folding the rest is worth having. It is also the
 * kind of feature that quietly breaks navigation if the obvious version is
 * written, so three rules constrain it.
 *
 * **Folding never hides where you are.** A rail with no highlighted entry has
 * lost the one thing a rail is for. The first instinct was to force the group
 * holding the current page to stay open, but that makes its own heading a
 * control that visibly does nothing when clicked. So a folded group keeps its
 * active entry on screen and drops the rest: the click always does something,
 * and the answer to "where am I" survives every fold.
 *
 * **The narrow rail cannot fold at all.** Below 1025px the rail is a 46px glyph
 * column with every label hidden, so the group headings are not on screen and
 * the glyphs are the entire navigation. A fold control there would hide the
 * only way to move and offer no visible way to get it back.
 *
 * **Folding hides a link, never a destination.** The `g`-chords and the command
 * palette read the destination registry, not the DOM, so every route stays
 * reachable whatever the rail is showing.
 *
 * Both sources here are mutable state outside React — localStorage and a media
 * query — so both are read through `useSyncExternalStore` rather than into
 * state inside an effect. An effect means a first paint with the wrong value
 * and a second render correcting it, which for this feature is the whole rail
 * visibly unfolding on every navigation. The snapshots are memoised so their
 * identity changes only when the underlying value does, which is what the hook
 * requires to avoid an infinite loop.
 *
 * Which groups someone folded is a per-viewer convenience, not something
 * another device or another reader should inherit, so it lives in localStorage.
 * Every access is guarded: private windows, cleared site data and browsers set
 * to block storage all throw on read, and a rail that failed to render because
 * a preference could not be read would be far worse than the problem this
 * solves.
 */

'use client'

import { useCallback, useSyncExternalStore } from 'react'

import { DESTINATIONS } from '@/lib/destinations'

const STORAGE_KEY = 'omnisignal.rail.collapsed'

/** Below this the rail has no labels to fold. Matches the CSS breakpoint. */
const WIDE = '(min-width: 1025px)'

const NONE: readonly string[] = []

const listeners = new Set<() => void>()
/** Cached parse. Identity is stable until a write or another tab's change. */
let cached: readonly string[] | null = null

function notify(): void {
  for (const l of listeners) l()
}

function subscribeCollapsed(listener: () => void): () => void {
  listeners.add(listener)
  // Folding a group in one tab should move the other tab's rail too.
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === null) {
      cached = null
      notify()
    }
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

function collapsedSnapshot(): readonly string[] {
  if (cached !== null) return cached
  let value: readonly string[] = NONE
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      // Anything else under that key is a corrupted write or someone else's
      // data. An unreadable preference is no preference, not a failure.
      if (Array.isArray(parsed)) value = parsed.filter((v): v is string => typeof v === 'string')
    }
  } catch {
    value = NONE
  }
  cached = value
  return value
}

/** Nothing is folded on the server: it has no viewer to have a preference. */
function collapsedOnServer(): readonly string[] {
  return NONE
}

function subscribeWidth(listener: () => void): () => void {
  const query = window.matchMedia(WIDE)
  query.addEventListener('change', listener)
  return () => query.removeEventListener('change', listener)
}

function widthSnapshot(): boolean {
  return window.matchMedia(WIDE).matches
}

/** The server has no viewport. The wide rail is the layout it renders. */
function widthOnServer(): boolean {
  return true
}

function write(groups: readonly string[]): void {
  cached = groups
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(groups))
  } catch {
    /* The fold still applies for this session; it will not be remembered. */
  }
  notify()
}

/** The group a route belongs to, or null for a route outside the registry. */
export function groupOf(pathname: string): string | null {
  for (const section of DESTINATIONS) {
    for (const item of section.items) {
      if (pathname === item.href || pathname.startsWith(`${item.href}/`)) return section.group
    }
  }
  return null
}

export interface RailGroups {
  /** Whether a group shows all of its items. */
  isOpen: (group: string) => boolean
  /** Fold or unfold one group. */
  toggle: (group: string) => void
  /** Whether folding is offered at all at this width. */
  collapsible: boolean
  /** The group holding the current route, whose active entry survives a fold. */
  activeGroup: string | null
}

export function useRailGroups(pathname: string): RailGroups {
  const collapsed = useSyncExternalStore(
    subscribeCollapsed, collapsedSnapshot, collapsedOnServer,
  )
  const collapsible = useSyncExternalStore(subscribeWidth, widthSnapshot, widthOnServer)

  const isOpen = useCallback(
    (group: string) => (collapsible ? !collapsed.includes(group) : true),
    [collapsed, collapsible],
  )

  const toggle = useCallback((group: string) => {
    const current = collapsedSnapshot()
    write(
      current.includes(group)
        ? current.filter((g) => g !== group)
        : [...current, group],
    )
  }, [])

  return { isOpen, toggle, collapsible, activeGroup: groupOf(pathname) }
}
