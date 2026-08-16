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

import CompanyMark from '@/components/ui/CompanyMark'
import Link from 'next/link'
import { useCallback, useEffect, useMemo, useState } from 'react'

import EmptyState from '@/components/ui/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import ConfirmButton from '@/components/ui/ConfirmButton'
import { StatusPill } from '@/components/ui/DataMarks'
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

/**
 * An investigation's contents, kept *typed*.
 *
 * The previous version reduced everything to four counts, which made a note
 * and a company indistinguishable — the exact flattening that made the old
 * graph meaningless. A note is prose, a company is an entity, a snapshot is
 * a saved state, and each is rendered as what it is.
 */
interface Substance {
  entities: string[]
  notes: SessionNote[]
  snapshots: Array<{ id: string; label: string; at: string }>
  collections: Array<{ name: string; entity_ids: string[] }>
  activity: Array<{ at: string; action: string; detail: string }>
  thesis: string | null
}

function readSubstance(session: ResearchSession): Substance {
  const state = session.workspace_state
  return {
    entities: state?.symbols ?? [],
    notes: session.notes ?? [],
    snapshots: state?.snapshots ?? [],
    collections: state?.collections ?? [],
    activity: state?.activity ?? [],
    // The first pinned note reads as the thesis: it is the thing the
    // researcher chose to keep at the top of their own investigation.
    thesis: (session.notes ?? []).find((n) => n.pinned)?.body ?? null,
  }
}

const EMPTY: Substance = {
  entities: [], notes: [], snapshots: [], collections: [], activity: [], thesis: null,
}

function isEmpty(s: Substance) {
  return s.entities.length + s.notes.length + s.snapshots.length + s.collections.length === 0
}

/**
 * How far along an investigation is, from what it actually contains.
 *
 * Not a stored field and not a guess: an investigation with nothing in it is
 * empty, one with entities but nothing written is a scan, and one carrying
 * notes or snapshots is work in progress. The three states are exactly the
 * three shapes the substance can take, so this reports the record rather
 * than scoring it.
 */
function stage(s: Substance): { tone: 'muted' | 'accent' | 'pos'; label: string } {
  if (isEmpty(s)) return { tone: 'muted', label: 'Empty' }
  if (s.notes.length || s.snapshots.length) return { tone: 'pos', label: 'In progress' }
  return { tone: 'accent', label: 'Scoped' }
}

/** Counts, but each one links to the kind of thing it counts. */
function Counts({ substance }: { substance: Substance }) {
  const entries = [
    ['entity', substance.entities.length],
    ['note', substance.notes.length],
    ['snapshot', substance.snapshots.length],
    ['collection', substance.collections.length],
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
      {symbols.slice(0, 6).map((s) => (
        <span key={s} className="ws-symbols__chip">
          <CompanyMark ticker={s} size={14} />
          {s}
        </span>
      ))}
      {symbols.length > 6 && <span className="ws-symbols__more">+{symbols.length - 6}</span>}
    </span>
  )
}

/* ── typed object rendering ───────────────────────────────────────────────── */

/**
 * A note looks like prose. A company looks like an entity. A snapshot looks
 * like a saved state. Rendering all three as identical cards is what made
 * the old workspace read as "arbitrary objects in a graph".
 */
function ThesisBlock({ thesis }: { thesis: string }) {
  return (
    <div className="ws-thesis">
      <span className="ws-thesis__tag">Thesis</span>
      <p className="ws-thesis__body">{thesis}</p>
    </div>
  )
}

function NoteList({ notes }: { notes: SessionNote[] }) {
  if (!notes.length) return null
  return (
    <ul className="ws-notes">
      {notes.slice(0, 3).map((note) => (
        <li key={note.id} className="ws-note">
          {note.pinned && <span className="ws-note__pin" aria-label="Pinned">◆</span>}
          <span className="ws-note__body">{note.body.slice(0, 120)}</span>
          {note.refs.length > 0 && (
            <span className="ws-note__refs">
              {note.refs.slice(0, 3).map((r) => r.label ?? r.id).join(' · ')}
            </span>
          )}
        </li>
      ))}
      {notes.length > 3 && <li className="ws-note ws-note--more">+{notes.length - 3} more</li>}
    </ul>
  )
}

function ActivityTrail({ activity }: { activity: Substance['activity'] }) {
  if (!activity.length) return null
  return (
    <ol className="ws-trail">
      {activity.slice(-4).reverse().map((event, index) => (
        <li key={`${event.at}-${index}`} className="ws-trail__item">
          <span className="ws-trail__action">{event.action}</span>
          <span className="ws-trail__detail">{event.detail}</span>
          <span className="ws-trail__when">{timeAgo(event.at)}</span>
        </li>
      ))}
    </ol>
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

/** A placeholder shaped like the card that replaces it.
 *
 *  Three featureless 150px rectangles were standing in for investigation
 *  cards whose structure is entirely predictable — title, symbols, counts,
 *  footer. A skeleton is a promise about layout, and it only pays off when
 *  the real thing arrives in the same shape; a blank slab promises nothing
 *  and the swap lands as a jump. This borrows the card's own classes so the
 *  two stay in step by construction rather than by memory. */
function InvestigationSkeleton() {
  return (
    <article className="ws-card ws-card--skeleton" aria-hidden="true">
      <div className="ws-card__link">
        <span className="ws-skel ws-skel--title" />
        <span className="ws-skel ws-skel--symbols" />
        <span className="ws-skel ws-skel--counts" />
      </div>
      <div className="ws-card__foot">
        <span className="ws-skel ws-skel--meta" />
      </div>
    </article>
  )
}

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
        <span className="input-wrap srch" style={{ display: 'block' }}>
          <input id="session-search" className="input ws-input srch__field" type="search" value={query}
                 placeholder="Search everything you have written…"
                 onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button type="button" className="srch__clear" aria-label="Clear search"
                    onClick={() => setQuery('')}>
              ✕
            </button>
          )}
        </span>
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
            <div className="ws-grid" aria-busy="true">
              {[0, 1, 2].map((i) => <InvestigationSkeleton key={i} />)}
            </div>
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
              <Link
                href={`/terminal/graph?session=${resume.id}`}
                className="ws-resume"
                /* Physical depth carrying a real count. Adapted from the
                   Uiverse stacked-card family, whose mechanism is two
                   pseudo-element layers behind the card with
                   `transform-origin: bottom`, fanning out on hover to imply
                   a stack of pages. Here the number of layers is the number
                   of captured snapshots (0, 1, or 2+), so the card looks as
                   thick as the investigation actually is — accumulated work
                   is visible before the card is read. Capped at two layers
                   because a third is indistinguishable. */
                data-depth={Math.min(
                  2,
                  // Any captured substance counts, not snapshots alone. Keying
                  // depth to snapshots meant a card with notes and pinned
                  // entities still rendered dead flat, so the affordance was
                  // invisible on every real investigation.
                  resumeSubstance.snapshots.length
                    + resumeSubstance.notes.length
                    + resumeSubstance.entities.length,
                )}
              >
                <span className="ws-resume__eyebrow">
                  Continue where you left off
                  <StatusPill {...stage(resumeSubstance)} />
                </span>
                <span className="ws-resume__title">{resume.title}</span>
                {resume.description && <span className="ws-resume__desc">{resume.description}</span>}
                {resumeSubstance.thesis && <ThesisBlock thesis={resumeSubstance.thesis} />}
                <Symbols symbols={resumeSubstance.entities} />
                <NoteList notes={resumeSubstance.notes} />
                <span className="ws-resume__foot">
                  <Counts substance={resumeSubstance} />
                  <span className="ws-resume__when">opened {timeAgo(resume.last_opened_at)}</span>
                </span>
                <ActivityTrail activity={resumeSubstance.activity} />
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
                            <span className="ws-card__head">
                              <span className="ws-card__title">{s.title}</span>
                              <StatusPill {...stage(substance)} />
                            </span>
                            {s.description && <span className="ws-card__desc">{s.description}</span>}
                            <Symbols symbols={substance.entities} />
                            {isEmpty(substance)
                              ? <span className="ws-card__blank">Nothing captured yet — open it to begin.</span>
                              : <Counts substance={substance} />}
                          </Link>
                          <div className="ws-card__foot">
                            <span>{s.tags.length ? s.tags.join(' · ') : timeAgo(s.last_opened_at)}</span>
                            <ConfirmButton
                              className="btn btn--ghost btn--xs ws-card__delete"
                              description={`Delete investigation ${s.title}`}
                              confirmLabel="Delete?"
                              onConfirm={() => deleteSession(s.id)}
                              onDone={refresh}
                            >
                              Delete
                            </ConfirmButton>
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
