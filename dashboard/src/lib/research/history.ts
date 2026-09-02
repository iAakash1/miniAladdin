/**
 * Recently viewed and pinned research objects, as an external store.
 *
 * Kept in localStorage because it is a per-viewer convenience and nothing else
 * depends on it. Every read and write is guarded: a private window, cleared
 * site data or a browser configured to block storage all throw on access, and
 * the product must render correctly with no stored value rather than break.
 *
 * Exposed through `useSyncExternalStore` rather than read into state inside an
 * effect. localStorage is a mutable source outside React, and reading it in an
 * effect means a first paint with the wrong value followed by a second render —
 * visible as recents appearing a frame late on every navigation. The snapshots
 * below are memoised so their identity only changes when the data does, which
 * is what the hook requires to avoid an infinite loop.
 */

import { useSyncExternalStore } from 'react'

import { objectKey, type ResearchObject } from './objects'

const RECENT_KEY = 'ma.research.recent.v1'
const PINNED_KEY = 'ma.research.pinned.v1'
const VIEWS_KEY = 'ma.research.views.v1'
const RECENT_LIMIT = 24

export interface SavedView {
  id: string
  label: string
  href: string
  createdAt: number
}

const listeners = new Set<() => void>()
/** Cached parses, keyed by storage key. Identity is stable until a write. */
const snapshots = new Map<string, unknown>()
const EMPTY: never[] = []

function notify(): void {
  for (const l of listeners) l()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  // Another tab writing the same key must move this one too.
  const onStorage = (e: StorageEvent) => {
    if (e.key && snapshots.has(e.key)) {
      snapshots.delete(e.key)
      notify()
    }
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

function snapshot<T>(key: string): T[] {
  if (snapshots.has(key)) return snapshots.get(key) as T[]
  let value: T[] = EMPTY
  try {
    const raw = window.localStorage.getItem(key)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (Array.isArray(parsed)) value = parsed as T[]
    }
  } catch {
    value = EMPTY
  }
  snapshots.set(key, value)
  return value
}

function serverSnapshot<T>(): T[] {
  return EMPTY
}

function write(key: string, value: unknown[]): void {
  snapshots.set(key, value)
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable; the value still applies for this session */
  }
  notify()
}

/* ── reads ──────────────────────────────────────────────────────────────── */

export function useRecentObjects(): ResearchObject[] {
  return useSyncExternalStore(
    subscribe,
    () => snapshot<ResearchObject>(RECENT_KEY),
    serverSnapshot<ResearchObject>,
  )
}

export function usePinnedObjects(): ResearchObject[] {
  return useSyncExternalStore(
    subscribe,
    () => snapshot<ResearchObject>(PINNED_KEY),
    serverSnapshot<ResearchObject>,
  )
}

export function useSavedViews(): SavedView[] {
  return useSyncExternalStore(
    subscribe,
    () => snapshot<SavedView>(VIEWS_KEY),
    serverSnapshot<SavedView>,
  )
}

/** Non-hook reads, for event handlers and one-shot checks. */
export function recentObjects(): ResearchObject[] {
  if (typeof window === 'undefined') return EMPTY
  return snapshot<ResearchObject>(RECENT_KEY)
}

export function pinnedObjects(): ResearchObject[] {
  if (typeof window === 'undefined') return EMPTY
  return snapshot<ResearchObject>(PINNED_KEY)
}

export function savedViews(): SavedView[] {
  if (typeof window === 'undefined') return EMPTY
  return snapshot<SavedView>(VIEWS_KEY)
}

export function isPinned(obj: ResearchObject): boolean {
  const key = objectKey(obj)
  return pinnedObjects().some((o) => objectKey(o) === key)
}

/* ── writes ─────────────────────────────────────────────────────────────── */

export function recordVisit(obj: ResearchObject): void {
  if (typeof window === 'undefined') return
  const key = objectKey(obj)
  const current = recentObjects()
  // A repeat visit to the head is not a change; writing it would notify every
  // subscriber on each render of the same object.
  if (current.length && objectKey(current[0]) === key) return
  write(RECENT_KEY, [obj, ...current.filter((o) => objectKey(o) !== key)].slice(0, RECENT_LIMIT))
}

export function clearRecent(): void {
  write(RECENT_KEY, [])
}

export function togglePin(obj: ResearchObject): void {
  const key = objectKey(obj)
  const current = pinnedObjects()
  const exists = current.some((o) => objectKey(o) === key)
  write(PINNED_KEY, exists ? current.filter((o) => objectKey(o) !== key) : [obj, ...current])
}

export function saveView(label: string, href: string): void {
  const view: SavedView = { id: `${Date.now()}`, label, href, createdAt: Date.now() }
  write(VIEWS_KEY, [view, ...savedViews().filter((v) => v.href !== href)].slice(0, 30))
}

export function removeView(id: string): void {
  write(VIEWS_KEY, savedViews().filter((v) => v.id !== id))
}
