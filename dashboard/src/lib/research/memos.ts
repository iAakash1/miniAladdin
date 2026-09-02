/**
 * Analyst memos.
 *
 * Stored in the browser, because there is no memo backend and inventing one
 * that pretends to be shared storage would be worse than a local notebook that
 * says it is local. Everything here is written by the person reading the
 * product — nothing is generated, and no conclusion is inferred from data.
 *
 * A memo's value is its references. A note saying "momentum looks strong" is an
 * opinion; the same note attached to the factor, the experiment and the gate it
 * rests on is a reviewable claim, and the references are what let a later
 * reader check whether the evidence still says what it said.
 */

import { useSyncExternalStore } from 'react'

import type { ResearchObject } from './objects'

const MEMO_KEY = 'ma.research.memos.v1'

export interface Memo {
  id: string
  title: string
  thesis: string
  evidence: string
  risks: string
  conclusion: string
  /** Objects this memo is about. The point of the format. */
  references: ResearchObject[]
  createdAt: number
  updatedAt: number
  status: 'draft' | 'open' | 'resolved'
}

const listeners = new Set<() => void>()
let snapshot: Memo[] | null = null
const EMPTY: Memo[] = []

function notify(): void {
  for (const l of listeners) l()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  const onStorage = (e: StorageEvent) => {
    if (e.key === MEMO_KEY) { snapshot = null; notify() }
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

function read(): Memo[] {
  if (snapshot) return snapshot
  let value: Memo[] = EMPTY
  try {
    const raw = window.localStorage.getItem(MEMO_KEY)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (Array.isArray(parsed)) value = parsed as Memo[]
    }
  } catch {
    value = EMPTY
  }
  snapshot = value
  return value
}

function write(next: Memo[]): void {
  snapshot = next
  try {
    window.localStorage.setItem(MEMO_KEY, JSON.stringify(next))
  } catch {
    /* storage unavailable; the memo lives for this session only */
  }
  notify()
}

export function useMemos(): Memo[] {
  return useSyncExternalStore(subscribe, read, () => EMPTY)
}

export function memos(): Memo[] {
  if (typeof window === 'undefined') return EMPTY
  return read()
}

export function createMemo(partial: Partial<Memo> = {}): Memo {
  const now = Date.now()
  const memo: Memo = {
    id: `memo-${now}`,
    title: partial.title ?? 'Untitled memo',
    thesis: partial.thesis ?? '',
    evidence: partial.evidence ?? '',
    risks: partial.risks ?? '',
    conclusion: partial.conclusion ?? '',
    references: partial.references ?? [],
    status: partial.status ?? 'draft',
    createdAt: now,
    updatedAt: now,
  }
  write([memo, ...memos()])
  return memo
}

export function updateMemo(id: string, patch: Partial<Memo>): void {
  write(memos().map((m) => (m.id === id ? { ...m, ...patch, updatedAt: Date.now() } : m)))
}

export function deleteMemo(id: string): void {
  write(memos().filter((m) => m.id !== id))
}

export function addReference(id: string, object: ResearchObject): void {
  const current = memos().find((m) => m.id === id)
  if (!current) return
  const exists = current.references.some((r) => r.kind === object.kind && r.id === object.id)
  if (exists) return
  updateMemo(id, { references: [...current.references, object] })
}

export function removeReference(id: string, object: ResearchObject): void {
  const current = memos().find((m) => m.id === id)
  if (!current) return
  updateMemo(id, {
    references: current.references.filter((r) => !(r.kind === object.kind && r.id === object.id)),
  })
}
