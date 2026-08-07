'use client'

/**
 * Workspace — the room you work in, not a list of links.
 *
 * The previous version was a table of session titles above four navigation
 * tiles. It answered "what investigations exist?" and nothing else, which is
 * why it read as a placeholder: the page carried no evidence that any work
 * had happened, so there was no reason to return to it.
 *
 * Rebuilt around a different premise — **an investigation is a body of work,
 * and the page should show the work.** Each session already stores pinned
 * entities, collections, snapshots, notes and an activity log; none of it was
 * ever surfaced. Every card now renders that substance, so the page answers
 * the question a researcher actually has on returning: *what was I doing, how
 * far did I get, and where do I pick it up?*
 *
 * Three things carry the redesign:
 *
 * **A continue rail.** The most recent investigation gets a full-width resume
 * card with its own state summary. Coming back to research is the dominant
 * action, and it deserves more than being row one of a table.
 *
 * **Substance on every card.** Pins, notes, snapshots and the last action,
 * read straight from the session's stored workspace state. A card with
 * nothing in it says so plainly rather than rendering empty chrome.
 *
 * **Search that shows matches in context.** The old version listed matching
 * note IDs. This shows the matched line with the query highlighted, because
 * finding a note you half-remember is the whole reason to search notes.
 */

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import Skeleton from '@/components/ui/Skeleton'
import { timeAgo } from '@/lib/format'
import {
  createSession,
  deleteSession,
  listSessions,
  openSession,
  searchSessions,
  type ResearchSession,
  type SessionNote,
  type SessionSummary,
} from '@/lib/sessions'

/* ── session substance ────────────────────────────────────────────────────── */

interface Substance {
  pins: number
  notes: number
  snapshots: number
  collections: number
  symbols: string[]
  lastAction: string | null
}

function readSubstance(session: ResearchSession): Substance {
  const state = session.workspace_state
  const activity = state?.activity ?? []
  return {
    pins: state?.pinned?.length ?? 0,
    notes: session.notes?.length ?? 0,
    snapshots: state?.snapshots?.length ?? 0,
    collections: state?.collections?.length ?? 0,
    symbols: (state?.symbols ?? []).slice(0, 6),
    lastAction: activity.length ? activity[activity.length - 1].detail : null,
  }
}

const EMPTY: Substance = {
  pins: 0, notes: 0, snapshots: 0, collections: 0, symbols: [], lastAction: null,
}

function isEmpty(s: Substance) {
  return s.pins + s.notes + s.snapshots + s.collections === 0 && s.symbols.length === 0
}

function Counts({ substance }: { substance: Substance }) {
  const entries = [
    ['pin', substance.pins],
    ['note', substance.notes],
    ['snapshot', substance.snapshots],
    ['collection', substance.collections],
  ] as const
  const shown = entries.filter(([, n]) => n > 0)
  if (!shown.length) return null
  return (
    <span className="ws-counts">
      {shown.map(([noun, n]) => (
        <span key={noun} className="ws-counts__item">
          <strong>{n}</strong> {noun}{n === 1 ? '' : 's'}
        </span>
      ))}
    </span>
  )
}

function Symbols({ symbols }: { symbols: string[] }) {
  if (!symbols.length) return null
  return (
    <span className="ws-symbols">
      {symbols.map((s) => <span key={s} className="ws-symbols__chip">{s}</span>)}
    </span>
  )
}

/* ── search with context ──────────────────────────────────────────────────── */

/** Shows the matched line with the term marked, rather than the fact that a
 *  match exists — you search notes to find the one you half-remember. */
function Excerpt({ body, term }: { body: string; term: string }) {
  const index = body.toLowerCase().indexOf(term.toLowerCase())
  if (index === -1) return <>{body.slice(0, 140)}</>
  const start = Math.max(0, index - 45)
  return (
    <>
      {start > 0 && '…'}
      {body.slice(start, index)}
      <mark className="ws-mark">{body.slice(index, index + term.length)}</mark>
      {body.slice(index + term.length, index + term.length + 70)}
      {body.length > index + term.length + 70 && '…'}
    </>
  )
}

/* ── view ─────────────────────────────────────────────────────────────────── */

export default function SessionsView() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [detail, setDetail] = useState<Record<string, Substance>>({})
  const [failed, setFailed] = useState(false)
  const [title, setTitle] = useState('')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<{ sessions: SessionSummary[]; notes: SessionNote[] } | null>(null)

  const refresh = useCallback(() => {
    listSessions()
      .then(async (list) => {
        setSessions(list)
        setFailed(false)
        // Hydrate substance for the cards actually on screen. Sessions are
        // few and the payloads small; loading them is what turns a list of
        // titles into evidence that work happened.
        const loaded = await Promise.all(
          list.slice(0, 12).map(async (s) => {
            const full = await openSession(s.id).catch(() => null)
            return [s.id, full ? readSubstance(full) : EMPTY] as const
          }),
        )
        setDetail(Object.fromEntries(loaded))
      })
      .catch(() => setFailed(true))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    const term = query.trim()
    if (!term) return
    const timer = setTimeout(() => {
      searchSessions(term).then(setHits).catch(() => setHits(null))
    }, 250)
    return () => clearTimeout(timer)
  }, [query])

  const searching = query.trim().length > 0
  const [resume, ...rest] = sessions ?? []
  const resumeSubstance = resume ? detail[resume.id] ?? EMPTY : EMPTY

  const start = async () => {
    const created = await createSession(title.trim() || 'New investigation')
    if (created) { setTitle(''); refresh() }
  }

  const matchCount = useMemo(
    () => (hits ? hits.sessions.length + hits.notes.length : 0),
    [hits],
  )

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Workspace"
        title="Investigations"
        lede="An investigation remembers the graph you were reading, what you pinned, the snapshots you took and everything you wrote. Leave for a week and open it exactly where you stopped."
        actions={
          <>
            <label htmlFor="new-session" className="visually-hidden">New investigation title</label>
            <input id="new-session" className="input ws-input" value={title}
                   placeholder="Name a new investigation…"
                   onChange={(e) => setTitle(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') void start() }} />
            <button type="button" className="btn btn--primary btn--sm" onClick={() => void start()}>
              Start
            </button>
          </>
        }
      />

      <div className="ws-search">
        <label htmlFor="session-search" className="visually-hidden">Search investigations and notes</label>
        <input id="session-search" className="input ws-input" type="search" value={query}
               placeholder="Search everything you have written…"
               onChange={(e) => setQuery(e.target.value)} />
        {searching && (
          <span className="ws-search__count">
            {hits ? `${matchCount} match${matchCount === 1 ? '' : 'es'}` : 'searching…'}
          </span>
        )}
      </div>

      {searching && hits && (
        <section className="ws-results" aria-label="Search results">
          {matchCount === 0 && (
            <p className="ws-empty-line">
              Nothing matches “{query.trim()}”. Notes are searched in full, so try a word you
              know you wrote.
            </p>
          )}
          {hits.notes.map((note) => (
            <Link key={note.id} href={`/terminal/graph?session=${note.session_id}`} className="ws-result">
              <span className="ws-result__kind">note</span>
              <span className="ws-result__body"><Excerpt body={note.body} term={query.trim()} /></span>
            </Link>
          ))}
          {hits.sessions.map((s) => (
            <Link key={s.id} href={`/terminal/graph?session=${s.id}`} className="ws-result">
              <span className="ws-result__kind">investigation</span>
              <span className="ws-result__body">{s.title}</span>
            </Link>
          ))}
        </section>
      )}

      {!searching && (
        <>
          {failed ? (
            <EmptyState
              title="Investigations couldn't be loaded"
              description="The persistence service didn't respond. Your work is safe on the server — this usually clears in a moment."
              action={<button type="button" className="btn btn--secondary btn--sm" onClick={refresh}>Try again</button>}
            />
          ) : sessions === null ? (
            <div className="ws-grid"><Skeleton height={150} /><Skeleton height={150} /><Skeleton height={150} /></div>
          ) : sessions.length === 0 ? (
            <EmptyState
              title="No investigations yet"
              description="Name one above, or open the knowledge graph and choose “Start investigation”. From then on every entity you pin, every snapshot you take and every note you write is remembered here."
              action={
                <Link href="/terminal/graph" className="btn btn--primary btn--sm" style={{ textDecoration: 'none' }}>
                  Open the graph
                </Link>
              }
            />
          ) : (
            <>
              {/* Continue where you left off — the dominant action, given room. */}
              <Link href={`/terminal/graph?session=${resume.id}`} className="ws-resume">
                <span className="ws-resume__eyebrow">Continue where you left off</span>
                <span className="ws-resume__title">{resume.title}</span>
                {resume.description && <span className="ws-resume__desc">{resume.description}</span>}
                <Symbols symbols={resumeSubstance.symbols} />
                <span className="ws-resume__foot">
                  <Counts substance={resumeSubstance} />
                  <span className="ws-resume__when">opened {timeAgo(resume.last_opened_at)}</span>
                </span>
                {resumeSubstance.lastAction && (
                  <span className="ws-resume__last">Last: {resumeSubstance.lastAction}</span>
                )}
              </Link>

              {rest.length > 0 && (
                <>
                  <h2 className="ws-section">Other investigations</h2>
                  <div className="ws-grid">
                    {rest.map((s) => {
                      const substance = detail[s.id] ?? EMPTY
                      return (
                        <article key={s.id} className="ws-card">
                          <Link href={`/terminal/graph?session=${s.id}`} className="ws-card__link">
                            <span className="ws-card__title">{s.title}</span>
                            {s.description && <span className="ws-card__desc">{s.description}</span>}
                            <Symbols symbols={substance.symbols} />
                            {isEmpty(substance)
                              ? <span className="ws-card__blank">Nothing captured yet — open it to begin.</span>
                              : <Counts substance={substance} />}
                          </Link>
                          <div className="ws-card__foot">
                            <span>{s.tags.length ? s.tags.join(' · ') : timeAgo(s.last_opened_at)}</span>
                            <button type="button" className="btn btn--ghost btn--xs ws-card__delete"
                                    aria-label={`Delete ${s.title}`}
                                    onClick={async () => { if (await deleteSession(s.id)) refresh() }}>
                              Delete
                            </button>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </>
              )}
            </>
          )}

          <nav className="ws-jump" aria-label="Research surfaces">
            {[
              ['/terminal/graph', 'Knowledge graph', 'Entities and how they connect'],
              ['/terminal/factors', 'Factor Lab', 'Does the engine’s ranking predict anything?'],
              ['/terminal/vault', 'Research Vault', 'Every analysis you have run'],
              ['/terminal/validation', 'Validation', 'How well the model performs'],
            ].map(([href, label, description]) => (
              <Link key={href} href={href} className="ws-jump__item">
                <span className="ws-jump__label">{label}</span>
                <span className="ws-jump__desc">{description}</span>
              </Link>
            ))}
          </nav>
        </>
      )}
    </div>
  )
}
