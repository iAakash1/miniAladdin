'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'

import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { timeAgo } from '@/lib/format'
import {
  createSession,
  deleteSession,
  listSessions,
  searchSessions,
  type SessionNote,
  type SessionSummary,
} from '@/lib/sessions'

/**
 * Investigations — every research session, newest-opened first. A session
 * is the complete state of an investigation: the graph you were reading,
 * what you pinned, and everything you wrote down. Opening one restores it
 * exactly.
 */
export default function SessionsView() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [title, setTitle] = useState('')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<{ sessions: SessionSummary[]; notes: SessionNote[] } | null>(null)

  const refresh = () => {
    listSessions()
      .then(setSessions)
      .catch(() => setFailed(true))
  }
  useEffect(refresh, [])

  useEffect(() => {
    if (!query.trim()) {
      setHits(null)
      return
    }
    const timer = setTimeout(() => {
      searchSessions(query).then(setHits).catch(() => setHits(null))
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const start = async () => {
    const created = await createSession(title.trim() || 'New investigation')
    if (created) {
      setTitle('')
      refresh()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Investigations</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          Each investigation remembers the graph you were reading, what you pinned, and everything
          you wrote. Leave for a week and open it again exactly where you stopped — nothing to save.
        </p>
      </div>

      {/* Workspace is a hub: the surfaces that left the tab bar are one
          click from here, and one ⌘K keystroke from anywhere. */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {[
          ['/terminal/graph', 'Knowledge graph', 'Entities and how they connect'],
          ['/terminal/vault', 'Research Vault', 'Every analysis you have run'],
          ['/terminal/validation', 'Validation', 'How well the model performs'],
          ['/terminal/methodology', 'Methodology', 'How the engine works'],
        ].map(([href, label, description]) => (
          <Link key={href} href={href} className="panel"
                style={{ padding: '10px 14px', textDecoration: 'none', flex: '1 1 200px' }}>
            <span style={{ display: 'block', fontSize: '0.8125rem', fontWeight: 600 }}>{label}</span>
            <span style={{ display: 'block', fontSize: '0.6875rem', color: 'var(--faint)' }}>{description}</span>
          </Link>
        ))}
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label htmlFor="new-session" className="visually-hidden">New investigation title</label>
        <input id="new-session" className="input" value={title} placeholder="New investigation…"
               style={{ maxWidth: 260, height: 32, fontSize: '0.8125rem' }}
               onChange={(e) => setTitle(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter') void start() }} />
        <button type="button" className="btn btn--secondary btn--sm" onClick={() => void start()}>
          Start
        </button>
        <label htmlFor="session-search" className="visually-hidden">Search investigations and notes</label>
        <input id="session-search" className="input" type="search" value={query}
               placeholder="Search notes and investigations…"
               style={{ maxWidth: 280, height: 32, fontSize: '0.8125rem', marginLeft: 'auto' }}
               onChange={(e) => setQuery(e.target.value)} />
      </div>

      {hits && (
        <section aria-label="Search results" className="panel" style={{ padding: '14px 18px' }}>
          <p className="label" style={{ fontSize: '0.625rem', marginBottom: 8 }}>
            {hits.sessions.length + hits.notes.length} match{hits.sessions.length + hits.notes.length === 1 ? '' : 'es'}
          </p>
          {hits.notes.map((note) => (
            <p key={note.id} style={{ fontSize: '0.8125rem', marginBottom: 6 }}>
              <Link href={`/terminal/graph?session=${note.session_id}`} style={{ color: 'var(--accent-strong)' }}>
                note
              </Link>
              {' · '}<span style={{ color: 'var(--muted)' }}>{note.body.slice(0, 110)}</span>
            </p>
          ))}
          {hits.sessions.map((s) => (
            <p key={s.id} style={{ fontSize: '0.8125rem' }}>
              <Link href={`/terminal/graph?session=${s.id}`} style={{ color: 'var(--accent-strong)' }}>{s.title}</Link>
            </p>
          ))}
        </section>
      )}

      {failed ? (
        <EmptyState
          title="Investigations couldn't be loaded"
          description="The persistence service didn't respond. Your sessions are safe on the server — try again in a moment."
          action={<button type="button" className="btn btn--secondary btn--sm" onClick={refresh}>Try again</button>}
        />
      ) : sessions === null ? (
        <Skeleton height={180} />
      ) : sessions.length === 0 ? (
        <EmptyState
          title="No investigations yet"
          description="Start one above, or open the knowledge graph and choose “Start investigation” — everything you pin and write from then on is remembered."
          action={
            <Link href="/terminal/graph" className="btn btn--secondary btn--sm" style={{ textDecoration: 'none' }}>
              Open the graph
            </Link>
          }
        />
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Investigation</th>
                <th scope="col">Tags</th>
                <th scope="col">Last opened</th>
                <th scope="col"><span className="visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link href={`/terminal/graph?session=${s.id}`}
                          style={{ fontWeight: 550, color: 'var(--text)', textDecoration: 'none' }}>
                      {s.title}
                    </Link>
                    {s.description && (
                      <span style={{ display: 'block', fontSize: '0.75rem', color: 'var(--faint)' }}>
                        {s.description}
                      </span>
                    )}
                  </td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                    {s.tags.length > 0 ? s.tags.join(' · ') : '—'}
                  </td>
                  <td style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{timeAgo(s.last_opened_at)}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button type="button" className="btn btn--ghost btn--xs"
                            aria-label={`Delete ${s.title}`}
                            style={{ color: 'var(--faint)' }}
                            onClick={async () => { if (await deleteSession(s.id)) refresh() }}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
