'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'
import AiPanel from '@/components/terminal/AiPanel'
import CompanyBand from '@/components/terminal/CompanyBand'
import QuantPanel from '@/components/terminal/QuantPanel'
import EmptyState from '@/components/ui/EmptyState'
import Skeleton from '@/components/ui/Skeleton'
import { normalizeAnalysis } from '@/lib/api'
import { fmtDate, timeAgo } from '@/lib/format'
import {
  type CompareResult,
  type HistoryFilters,
  type HistoryItem,
  type HistoryPage,
  type SavedReport,
  deleteHistory,
  deleteSavedReport,
  fetchComparison,
  fetchHistory,
  fetchHistoryDetail,
  fetchSavedReports,
  saveReport,
  updateSavedReport,
} from '@/lib/persistence'
import type { Analysis, RawResearchResponse } from '@/lib/types'

const VERDICTS = ['Strong Buy', 'Buy', 'Hold', 'Sell', 'Strong Sell']
const PAGE_SIZE = 20

function verdictTone(verdict: string): string {
  return verdict.includes('Buy') ? 'badge--pos' : verdict.includes('Sell') ? 'badge--neg' : 'badge--warn'
}

export type Mode = { view: 'history' } | { view: 'saved' } | { view: 'detail'; id: string } | { view: 'compare'; a: string; b: string }

/** Mode ↔ URL: /terminal/vault[?view=saved | ?id=… | ?compare=a,b].
 *  Every vault state is a real, bookmarkable URL and browser Back always
 *  returns to the previous vault state instead of leaving the page. */
export function modeFromParams(params: URLSearchParams): Mode {
  const id = params.get('id')
  if (id) return { view: 'detail', id }
  const compare = params.get('compare')
  if (compare && compare.includes(',')) {
    const [a, b] = compare.split(',', 2)
    if (a && b) return { view: 'compare', a, b }
  }
  return params.get('view') === 'saved' ? { view: 'saved' } : { view: 'history' }
}

export function modeToQuery(mode: Mode): string {
  switch (mode.view) {
    case 'saved':
      return '?view=saved'
    case 'detail':
      return `?id=${encodeURIComponent(mode.id)}`
    case 'compare':
      return `?compare=${encodeURIComponent(mode.a)},${encodeURIComponent(mode.b)}`
    default:
      return ''
  }
}

/**
 * Research Vault — every analysis the account has ever run, recorded
 * automatically by the backend. Search, filter, reopen any past report
 * through the same components the Analyze page uses, bookmark runs with
 * notes, and compare two runs factor-by-factor (all deltas computed
 * deterministically on the backend).
 */
export default function VaultView() {
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const mode = modeFromParams(new URLSearchParams(params.toString()))
  const setMode = useCallback(
    (next: Mode) => router.push(`${pathname}${modeToQuery(next)}`, { scroll: true }),
    [router, pathname],
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div>
        <h2 className="h-panel" style={{ fontSize: '1rem', marginBottom: 6 }}>Research Vault</h2>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', maxWidth: '78ch', lineHeight: 1.6 }}>
          Every analysis you run is recorded to your account automatically — reopen any past
          report exactly as it was, or compare two runs to see which factors moved the verdict.
        </p>
      </div>

      {(mode.view === 'history' || mode.view === 'saved') && (
        <>
          <div className="seg" role="group" aria-label="Vault section" style={{ alignSelf: 'flex-start' }}>
            <button
              type="button"
              className="seg__btn"
              aria-pressed={mode.view === 'history'}
              onClick={() => setMode({ view: 'history' })}
            >
              All analyses
            </button>
            <button
              type="button"
              className="seg__btn"
              aria-pressed={mode.view === 'saved'}
              onClick={() => setMode({ view: 'saved' })}
            >
              Saved reports
            </button>
          </div>
          {mode.view === 'history' ? <HistoryBrowser onOpen={setMode} /> : <SavedBrowser onOpen={setMode} />}
        </>
      )}

      {mode.view === 'detail' && (
        <DetailView id={mode.id} onBack={() => setMode({ view: 'history' })} />
      )}
      {mode.view === 'compare' && (
        <CompareView a={mode.a} b={mode.b} onBack={() => setMode({ view: 'history' })} />
      )}
    </div>
  )
}

/* ── history list ──────────────────────────────────────────────────────────── */

function HistoryBrowser({ onOpen }: { onOpen: (mode: Mode) => void }) {
  const [page, setPage] = useState<HistoryPage | null>(null)
  const [failed, setFailed] = useState(false)
  const [filters, setFilters] = useState<HistoryFilters>({ sort: 'newest', page: 1 })
  const [selected, setSelected] = useState<string[]>([])
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let alive = true
    queueMicrotask(() => {
      if (alive) setFailed(false)
    })
    fetchHistory({ ...filters, pageSize: PAGE_SIZE })
      .then((result) => {
        if (alive) setPage(result)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [filters, reloadKey])

  const patchFilters = useCallback((patch: Partial<HistoryFilters>) => {
    setPage(null)
    setFilters((f) => ({ ...f, ...patch, page: patch.page ?? 1 }))
  }, [])

  const toggleSelect = (id: string) => {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((s) => s !== id)
        : [...current.slice(-1), id], // keep at most the previous one + this
    )
  }

  const totalPages = page ? Math.max(1, Math.ceil(page.total / PAGE_SIZE)) : 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <label htmlFor="vault-q" className="visually-hidden">Search ticker or company</label>
        <input
          id="vault-q"
          className="input"
          type="search"
          placeholder="Search ticker or company…"
          style={{ maxWidth: 240, height: 32, fontSize: '0.8125rem' }}
          onChange={(e) => patchFilters({ q: e.target.value.trim() || undefined })}
        />
        <label htmlFor="vault-verdict" className="visually-hidden">Filter by verdict</label>
        <select
          id="vault-verdict"
          className="input"
          style={{ maxWidth: 150, height: 32, fontSize: '0.8125rem' }}
          value={filters.verdict ?? ''}
          onChange={(e) => patchFilters({ verdict: e.target.value || undefined })}
        >
          <option value="">All verdicts</option>
          {VERDICTS.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
        <label htmlFor="vault-from" className="visually-hidden">From date</label>
        <input
          id="vault-from"
          className="input num"
          type="date"
          style={{ maxWidth: 150, height: 32, fontSize: '0.75rem' }}
          onChange={(e) => patchFilters({ from: e.target.value || undefined })}
        />
        <label htmlFor="vault-to" className="visually-hidden">To date</label>
        <input
          id="vault-to"
          className="input num"
          type="date"
          style={{ maxWidth: 150, height: 32, fontSize: '0.75rem' }}
          onChange={(e) => patchFilters({ to: e.target.value || undefined })}
        />
        <label htmlFor="vault-sort" className="visually-hidden">Sort</label>
        <select
          id="vault-sort"
          className="input"
          style={{ maxWidth: 140, height: 32, fontSize: '0.8125rem' }}
          value={filters.sort}
          onChange={(e) => patchFilters({ sort: e.target.value as HistoryFilters['sort'] })}
        >
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="confidence">By confidence</option>
        </select>
        {selected.length === 2 && (
          <button
            type="button"
            className="btn btn--accent btn--sm"
            style={{ marginLeft: 'auto' }}
            onClick={() => onOpen({ view: 'compare', a: selected[0], b: selected[1] })}
          >
            Compare selected
          </button>
        )}
      </div>

      {failed && (
        <EmptyState
          title="Your research history couldn't be loaded"
          description="The persistence service didn't respond — nothing is lost. Try again in a moment."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={() => setReloadKey((k) => k + 1)}>
              Try again
            </button>
          }
        />
      )}

      {!failed && page === null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }} aria-busy="true">
          <Skeleton height={44} />
          <Skeleton height={44} />
          <Skeleton height={44} />
        </div>
      )}

      {!failed && page !== null && page.items.length === 0 && (
        <EmptyState
          title="No analyses recorded yet"
          description="Run an analysis on the Analyze tab — every completed run is stored here automatically, with its full report and scorecard."
        />
      )}

      {!failed && page !== null && page.items.length > 0 && (
        <>
          <p style={{ fontSize: '0.6875rem', color: 'var(--faint)' }}>
            Select two runs to compare which factors moved. Reports open exactly as generated.
          </p>
          <div className="panel" style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ minWidth: 760 }}>
              <caption className="visually-hidden">Recorded analyses</caption>
              <thead>
                <tr>
                  <th scope="col"><span className="visually-hidden">Select for comparison</span></th>
                  <th scope="col">When</th>
                  <th scope="col">Ticker</th>
                  <th scope="col">Company</th>
                  <th scope="col">Verdict</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Confidence</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Composite</th>
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {page.items.map((item) => (
                  <HistoryRow
                    key={item.id}
                    item={item}
                    selected={selected.includes(item.id)}
                    onSelect={() => toggleSelect(item.id)}
                    onOpen={() => onOpen({ view: 'detail', id: item.id })}
                    onDeleted={() => setReloadKey((k) => k + 1)}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
              {page.total} analyses · page {page.page} of {totalPages}
            </span>
            <span style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={page.page <= 1}
                onClick={() => patchFilters({ page: page.page - 1 })}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={page.page >= totalPages}
                onClick={() => patchFilters({ page: page.page + 1 })}
              >
                Next
              </button>
            </span>
          </div>
        </>
      )}
    </div>
  )
}

function HistoryRow({
  item, selected, onSelect, onOpen, onDeleted,
}: {
  item: HistoryItem
  selected: boolean
  onSelect: () => void
  onOpen: () => void
  onDeleted: () => void
}) {
  const [bookmarked, setBookmarked] = useState(false)
  return (
    <tr>
      <td>
        <input
          type="checkbox"
          aria-label={`Select ${item.ticker} run from ${fmtDate(item.created_at)} for comparison`}
          checked={selected}
          onChange={onSelect}
          style={{ accentColor: 'var(--accent)' }}
        />
      </td>
      <td className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
        {fmtDate(item.created_at)} · {timeAgo(item.created_at)}
      </td>
      <td className="mono" style={{ fontWeight: 600 }}>{item.ticker}</td>
      <td style={{ fontSize: '0.8125rem', color: 'var(--muted)' }}>{item.company_name ?? '—'}</td>
      <td>
        <span className={`badge ${verdictTone(item.verdict)}`} style={{ height: 19, fontSize: '0.625rem' }}>
          {item.verdict}
        </span>
      </td>
      <td className="num" style={{ textAlign: 'right' }}>
        {item.confidence !== null ? `${item.confidence}%` : '—'}
      </td>
      <td className="num" style={{ textAlign: 'right' }}>
        {item.composite_score !== null
          ? `${item.composite_score >= 0 ? '+' : ''}${item.composite_score.toFixed(3)}`
          : '—'}
      </td>
      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
        <button type="button" className="btn btn--ghost btn--xs" onClick={onOpen}>
          Open
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--xs"
          title={bookmarked ? 'Saved' : 'Save to reports'}
          aria-label={bookmarked ? `${item.ticker} run saved` : `Save ${item.ticker} run to reports`}
          onClick={() => {
            void saveReport(item.id).then((saved) => setBookmarked(Boolean(saved)))
          }}
          style={{ color: bookmarked ? 'var(--accent)' : undefined }}
        >
          {bookmarked ? '★' : '☆'}
        </button>
        <button
          type="button"
          className="btn btn--ghost btn--xs"
          aria-label={`Delete ${item.ticker} run from ${fmtDate(item.created_at)}`}
          style={{ color: 'var(--faint)' }}
          onClick={() => {
            void deleteHistory(item.id).then((ok) => ok && onDeleted())
          }}
        >
          ✕
        </button>
      </td>
    </tr>
  )
}

/* ── saved reports ─────────────────────────────────────────────────────────── */

function SavedBrowser({ onOpen }: { onOpen: (mode: Mode) => void }) {
  const [saved, setSaved] = useState<SavedReport[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [editing, setEditing] = useState<{ id: string; title: string; notes: string } | null>(null)

  useEffect(() => {
    let alive = true
    queueMicrotask(() => {
      if (alive) setFailed(false)
    })
    fetchSavedReports()
      .then((rows) => {
        if (alive) setSaved(rows)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [reloadKey])

  if (failed) {
    return (
      <EmptyState
        title="Saved reports couldn't be loaded"
        description="The persistence service didn't respond — your bookmarks are safe on the server."
        action={
          <button type="button" className="btn btn--secondary btn--sm" onClick={() => setReloadKey((k) => k + 1)}>
            Try again
          </button>
        }
      />
    )
  }
  if (saved === null) return <Skeleton height={160} />
  if (saved.length === 0) {
    return (
      <EmptyState
        title="No saved reports yet"
        description="Bookmark an analysis with the ☆ button — on a fresh run, or on any row under All analyses — and it will be pinned here with room for your own notes."
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {saved.map((report) => {
        const isEditing = editing?.id === report.id
        return (
          <article key={report.id} className="panel" style={{ padding: '16px 18px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
              {report.analysis && (
                <>
                  <span className="mono" style={{ fontWeight: 600 }}>{report.analysis.ticker}</span>
                  <span className={`badge ${verdictTone(report.analysis.verdict)}`} style={{ height: 19, fontSize: '0.625rem' }}>
                    {report.analysis.verdict}
                  </span>
                </>
              )}
              <span style={{ fontSize: '0.875rem', fontWeight: 550 }}>
                {report.custom_title ?? report.analysis?.company_name ?? 'Saved analysis'}
              </span>
              <span className="num" style={{ marginLeft: 'auto', fontSize: '0.6875rem', color: 'var(--faint)' }}>
                saved {timeAgo(report.saved_at)}
              </span>
            </div>

            {isEditing ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                <label htmlFor={`title-${report.id}`} className="visually-hidden">Custom title</label>
                <input
                  id={`title-${report.id}`}
                  className="input"
                  style={{ height: 32, fontSize: '0.8125rem', maxWidth: 420 }}
                  placeholder="Custom title…"
                  value={editing.title}
                  onChange={(e) => setEditing({ ...editing, title: e.target.value })}
                />
                <label htmlFor={`notes-${report.id}`} className="visually-hidden">Notes</label>
                <textarea
                  id={`notes-${report.id}`}
                  className="input"
                  style={{ height: 88, fontSize: '0.8125rem', padding: '8px 12px', resize: 'vertical' }}
                  placeholder="Your notes on this analysis…"
                  value={editing.notes}
                  onChange={(e) => setEditing({ ...editing, notes: e.target.value })}
                />
                <span style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn--accent btn--sm"
                    onClick={() => {
                      void updateSavedReport(report.id, {
                        custom_title: editing.title,
                        notes: editing.notes,
                      }).then((updated) => {
                        if (updated) {
                          setSaved((rows) => rows?.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)) ?? null)
                        }
                        setEditing(null)
                      })
                    }}
                  >
                    Save notes
                  </button>
                  <button type="button" className="btn btn--ghost btn--sm" onClick={() => setEditing(null)}>
                    Cancel
                  </button>
                </span>
              </div>
            ) : (
              report.notes && (
                <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', lineHeight: 1.6, marginTop: 10, maxWidth: '78ch', whiteSpace: 'pre-wrap' }}>
                  {report.notes}
                </p>
              )
            )}

            {!isEditing && (
              <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
                <button
                  type="button"
                  className="btn btn--secondary btn--sm"
                  onClick={() => onOpen({ view: 'detail', id: report.analysis_history_id })}
                >
                  Open report
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={() =>
                    setEditing({ id: report.id, title: report.custom_title ?? '', notes: report.notes ?? '' })
                  }
                >
                  Edit notes
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  style={{ marginLeft: 'auto', color: 'var(--faint)' }}
                  onClick={() => {
                    void deleteSavedReport(report.id).then((ok) => {
                      if (ok) setSaved((rows) => rows?.filter((r) => r.id !== report.id) ?? null)
                    })
                  }}
                >
                  Remove
                </button>
              </div>
            )}
          </article>
        )
      })}
    </div>
  )
}

/* ── reopen a stored analysis ──────────────────────────────────────────────── */

function DetailView({ id, onBack }: { id: string; onBack: () => void }) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [meta, setMeta] = useState<HistoryItem | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    fetchHistoryDetail(id)
      .then((row) => {
        if (!alive) return
        setMeta(row)
        setAnalysis(normalizeAnalysis(row.quant_payload as RawResearchResponse))
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [id])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button type="button" className="btn btn--secondary btn--sm" onClick={onBack}>
          ← Back to Vault
        </button>
        {meta && (
          <span className="num" style={{ fontSize: '0.75rem', color: 'var(--faint)' }}>
            as generated {fmtDate(meta.created_at)} · {timeAgo(meta.created_at)}
          </span>
        )}
      </div>

      {failed && (
        <EmptyState
          title="This analysis couldn't be opened"
          description="The stored report didn't load — it may have been deleted, or the service is briefly unavailable."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={onBack}>
              Back to Vault
            </button>
          }
        />
      )}
      {!failed && analysis === null && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} aria-busy="true">
          <Skeleton height={148} />
          <Skeleton height={330} />
        </div>
      )}
      {analysis !== null && (
        <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <CompanyBand analysis={{ ...analysis, historyId: null }} />
          <AiPanel analysis={analysis} />
          <QuantPanel analysis={analysis} />
        </div>
      )}
    </div>
  )
}

/* ── deterministic comparison ──────────────────────────────────────────────── */

function DeltaBar({ delta, max }: { delta: number; max: number }) {
  const half = 50
  const width = Math.min(half, (Math.abs(delta) / Math.max(max, 0.001)) * half)
  return (
    <div style={{ position: 'relative', height: 6, background: 'var(--surface-2)', borderRadius: 3, flex: 1, minWidth: 120 }}>
      <span style={{ position: 'absolute', left: '50%', top: -2, bottom: -2, width: 1, background: 'var(--line-strong)' }} />
      <span
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: delta >= 0 ? '50%' : `${half - width}%`,
          width: `${width}%`,
          background: delta >= 0 ? 'var(--pos)' : 'var(--neg)',
          borderRadius: 3,
        }}
      />
    </div>
  )
}

function CompareView({ a, b, onBack }: { a: string; b: string; onBack: () => void }) {
  const [result, setResult] = useState<CompareResult | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    fetchComparison(a, b)
      .then((r) => {
        if (alive) setResult(r)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [a, b])

  const maxFamilyDelta = result
    ? Math.max(0.001, ...result.families.map((f) => Math.abs(f.delta)))
    : 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button type="button" className="btn btn--secondary btn--sm" onClick={onBack}>
          ← Back to Vault
        </button>
        <h3 className="h-panel">Run comparison</h3>
      </div>

      {failed && (
        <EmptyState
          title="These runs couldn't be compared"
          description="One of the analyses may have been deleted, or the service is briefly unavailable."
          action={
            <button type="button" className="btn btn--secondary btn--sm" onClick={onBack}>
              Back to Vault
            </button>
          }
        />
      )}
      {!failed && result === null && <Skeleton height={320} />}

      {result !== null && (
        <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!result.same_ticker && (
            <p className="badge badge--warn" style={{ alignSelf: 'flex-start' }}>
              Different tickers — deltas compare two separate names
            </p>
          )}

          {/* Verdict + confidence movement */}
          <section aria-label="Verdict change" className="panel" style={{ padding: '18px 20px' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'clamp(20px, 5vw, 64px)' }}>
              {[result.before, result.after].map((run, index) => (
                <div key={run.id}>
                  <p className="label" style={{ marginBottom: 8 }}>
                    {index === 0 ? 'Before' : 'After'} · {fmtDate(run.created_at)}
                  </p>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                    <span className="mono" style={{ fontWeight: 600 }}>{run.ticker}</span>
                    <span className={`badge ${verdictTone(run.verdict)}`}>{run.verdict}</span>
                    <span className="num" style={{ fontSize: '0.875rem', fontWeight: 600 }}>
                      {run.confidence !== null ? `${run.confidence}%` : '—'}
                    </span>
                    <span className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                      {run.composite_score !== null
                        ? `composite ${run.composite_score >= 0 ? '+' : ''}${run.composite_score.toFixed(3)}`
                        : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--muted)', marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--line)' }}>
              {result.before.verdict === result.after.verdict
                ? `The verdict held at ${result.after.verdict}`
                : `The verdict moved ${result.before.verdict} → ${result.after.verdict}`}
              {result.before.confidence !== null && result.after.confidence !== null && (
                <> · confidence {result.before.confidence}% → {result.after.confidence}%</>
              )}
              {result.risk.level_before && result.risk.level_after && (
                <> · risk {result.risk.level_before.toLowerCase()} → {result.risk.level_after.toLowerCase()}</>
              )}
            </p>
          </section>

          {/* Family deltas */}
          <section aria-label="Factor family deltas" className="panel" style={{ padding: '18px 20px' }}>
            <h4 className="h-panel" style={{ marginBottom: 4 }}>What moved</h4>
            <p style={{ fontSize: '0.75rem', color: 'var(--faint)', marginBottom: 14 }}>
              Contribution change per signal family, computed by the engine from both stored scorecards.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {result.families.map((family) => (
                <div key={family.family} style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span style={{ width: 96, flexShrink: 0, fontSize: '0.75rem', fontWeight: family.changed ? 600 : 400, color: family.changed ? 'var(--text)' : 'var(--muted)' }}>
                    {family.label}
                  </span>
                  <span className="num" style={{ width: 130, flexShrink: 0, fontSize: '0.75rem', color: 'var(--muted)' }}>
                    {family.before !== null ? family.before.toFixed(3) : '—'} → {family.after !== null ? family.after.toFixed(3) : '—'}
                  </span>
                  <DeltaBar delta={family.delta} max={maxFamilyDelta} />
                  <span className="num" style={{ width: 64, textAlign: 'right', flexShrink: 0, fontSize: '0.75rem', fontWeight: 600, color: !family.changed ? 'var(--faint)' : family.delta >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                    {family.delta >= 0 ? '+' : ''}{family.delta.toFixed(3)}
                  </span>
                </div>
              ))}
              {/* Macro + risk rows use the same layout */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', paddingTop: 8, borderTop: '1px solid var(--line)' }}>
                <span style={{ width: 96, flexShrink: 0, fontSize: '0.75rem', color: 'var(--muted)' }}>Macro (SRM)</span>
                <span className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                  {result.macro.srm_before ?? '—'} → {result.macro.srm_after ?? '—'}
                  {result.macro.srm_delta !== null && (
                    <span style={{ color: result.macro.srm_delta > 0 ? 'var(--warn)' : 'var(--muted)' }}>
                      {' '}({result.macro.srm_delta >= 0 ? '+' : ''}{result.macro.srm_delta})
                    </span>
                  )}
                </span>
                <span style={{ width: 96, flexShrink: 0, fontSize: '0.75rem', color: 'var(--muted)', marginLeft: 24 }}>Risk score</span>
                <span className="num" style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                  {result.risk.score_before ?? '—'} → {result.risk.score_after ?? '—'}
                </span>
              </div>
            </div>
          </section>

          {/* Per-factor table */}
          <section aria-label="Per-factor deltas" className="panel" style={{ padding: '18px 20px' }}>
            <h4 className="h-panel" style={{ marginBottom: 12 }}>Factor detail</h4>
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table" style={{ minWidth: 520 }}>
                <thead>
                  <tr>
                    <th scope="col">Factor</th>
                    <th scope="col">Family</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Before</th>
                    <th scope="col" style={{ textAlign: 'right' }}>After</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {result.factors.map((factor) => (
                    <tr key={factor.name} style={{ opacity: factor.changed ? 1 : 0.55 }}>
                      <td style={{ fontWeight: factor.changed ? 600 : 400 }}>{factor.name}</td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{factor.family ?? '—'}</td>
                      <td className="num" style={{ textAlign: 'right' }}>
                        {factor.before !== null ? factor.before.toFixed(3) : '—'}
                      </td>
                      <td className="num" style={{ textAlign: 'right' }}>
                        {factor.after !== null ? factor.after.toFixed(3) : '—'}
                      </td>
                      <td className="num" style={{ textAlign: 'right', fontWeight: 600, color: !factor.changed ? 'var(--faint)' : factor.delta >= 0 ? 'var(--pos)' : 'var(--neg)' }}>
                        {factor.delta >= 0 ? '+' : ''}{factor.delta.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
