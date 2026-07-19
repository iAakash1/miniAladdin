/* ============================================================
   Research sessions — investigations that survive.

   One store, one serialization, one autosave path. The workspace never
   writes session state directly; it calls `updateWorkspace`, which
   debounces and persists in the background. Users are never asked to
   save.
   ============================================================ */

import { authFetch } from './persistence'

export interface WorkspaceState {
  schema_version: number
  symbols: string[]
  center: string | null
  selected: string | null
  pinned: string[]
  hidden: string[]
  expanded: string[]
  collections: Array<{ name: string; entity_ids: string[] }>
  bookmarks: Array<{ label: string; route: string; kind: string }>
  filters: { node_types: string; edge_types: string; min_confidence: number; hops: number }
  camera: { zoom: number; x: number; y: number }
  panels: { inspector: boolean; timeline: boolean; notebook: boolean }
  search: string
  snapshots: Array<{ id: string; label: string; at: string; state: Partial<WorkspaceState> }>
  activity: Array<{ at: string; action: string; detail: string }>
}

export interface SessionSummary {
  id: string
  title: string
  description: string | null
  tags: string[]
  status: 'active' | 'archived'
  color: string | null
  icon: string | null
  created_at: string
  updated_at: string
  last_opened_at: string
}

export interface SessionNote {
  id: string
  session_id: string
  body: string
  refs: Array<{ type: string; id: string; label?: string }>
  tags: string[]
  pinned: boolean
  created_at: string
  updated_at: string
}

export interface ResearchSession extends SessionSummary {
  workspace_state: WorkspaceState
  notes: SessionNote[]
}

export function emptyWorkspaceState(): WorkspaceState {
  return {
    schema_version: 1,
    symbols: [], center: null, selected: null,
    pinned: [], hidden: [], expanded: [],
    collections: [], bookmarks: [],
    filters: { node_types: '', edge_types: '', min_confidence: 0, hops: 2 },
    camera: { zoom: 1, x: 0, y: 0 },
    panels: { inspector: true, timeline: true, notebook: true },
    search: '',
    snapshots: [], activity: [],
  }
}

/* ---------- API ---------- */

export async function listSessions(status?: string): Promise<SessionSummary[]> {
  const res = await authFetch(`/api/sessions${status ? `?status=${status}` : ''}`)
  if (!res.ok) return []
  return ((await res.json()) as { sessions: SessionSummary[] }).sessions
}

export async function createSession(
  title: string, description?: string, tags?: string[], workspace_state?: WorkspaceState,
): Promise<SessionSummary | null> {
  const res = await authFetch('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ title, description, tags: tags ?? [], workspace_state }),
  })
  return res.ok ? ((await res.json()) as SessionSummary) : null
}

export async function openSession(id: string): Promise<ResearchSession | null> {
  const res = await authFetch(`/api/sessions/${encodeURIComponent(id)}`)
  return res.ok ? ((await res.json()) as ResearchSession) : null
}

export async function deleteSession(id: string): Promise<boolean> {
  const res = await authFetch(`/api/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
  return res.ok
}

export async function addNote(
  sessionId: string, body: string, refs: SessionNote['refs'] = [], tags: string[] = [],
): Promise<SessionNote | null> {
  const res = await authFetch(`/api/sessions/${encodeURIComponent(sessionId)}/notes`, {
    method: 'POST',
    body: JSON.stringify({ body, refs, tags }),
  })
  return res.ok ? ((await res.json()) as SessionNote) : null
}

export async function deleteNote(noteId: string): Promise<boolean> {
  const res = await authFetch(`/api/notes/${encodeURIComponent(noteId)}`, { method: 'DELETE' })
  return res.ok
}

export async function searchSessions(term: string): Promise<{ sessions: SessionSummary[]; notes: SessionNote[] }> {
  const res = await authFetch(`/api/sessions/search?q=${encodeURIComponent(term)}`)
  if (!res.ok) return { sessions: [], notes: [] }
  return (await res.json()) as { sessions: SessionSummary[]; notes: SessionNote[] }
}

/* ---------- autosave ----------
   One debounced writer for the whole app. Rapid workspace mutations
   (panning, selecting, filtering) collapse into a single write, and the
   most recent state always wins — a slow request can never overwrite a
   newer one, because each save reads the latest pending state. */

const SAVE_DEBOUNCE_MS = 1200

let pendingState: WorkspaceState | null = null
let pendingSessionId: string | null = null
let timer: ReturnType<typeof setTimeout> | null = null
let inFlight = false
const listeners = new Set<(saving: boolean) => void>()

function emit(saving: boolean) {
  listeners.forEach((listener) => listener(saving))
}

export function onSaveStateChange(listener: (saving: boolean) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function flush(): Promise<void> {
  if (inFlight || !pendingSessionId || !pendingState) return
  const sessionId = pendingSessionId
  const state = pendingState
  pendingState = null
  inFlight = true
  emit(true)
  try {
    await authFetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ workspace_state: state }),
    })
  } catch {
    // Losing one autosave is acceptable; the next mutation retries. Never
    // interrupt research with a save error.
  } finally {
    inFlight = false
    emit(false)
    // A mutation that arrived mid-flight is written immediately after.
    if (pendingState) void flush()
  }
}

/** Queue a workspace-state save. Debounced; safe to call on every change. */
export function updateWorkspace(sessionId: string, state: WorkspaceState): void {
  pendingSessionId = sessionId
  pendingState = state
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => void flush(), SAVE_DEBOUNCE_MS)
}

/** Write immediately — for navigation away or explicit checkpoints. */
export async function flushWorkspace(): Promise<void> {
  if (timer) clearTimeout(timer)
  await flush()
}

/** Append an activity entry, bounded, newest last. */
export function recordActivity(
  state: WorkspaceState, action: string, detail: string,
): WorkspaceState {
  return {
    ...state,
    activity: [...state.activity, { at: new Date().toISOString(), action, detail }].slice(-200),
  }
}

/** Capture the current view as a restorable snapshot. */
export function captureSnapshot(state: WorkspaceState, label: string): WorkspaceState {
  const snapshot = {
    id: `snap_${Date.now().toString(36)}`,
    label: label.trim().slice(0, 80) || 'Snapshot',
    at: new Date().toISOString(),
    state: {
      symbols: state.symbols, selected: state.selected, pinned: state.pinned,
      hidden: state.hidden, filters: state.filters, camera: state.camera,
    },
  }
  return recordActivity(
    { ...state, snapshots: [...state.snapshots, snapshot].slice(-40) },
    'snapshot',
    snapshot.label,
  )
}
