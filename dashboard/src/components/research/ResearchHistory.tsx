'use client'

/**
 * Research history, on the stock page itself.
 *
 * The data behind this has existed for a while — `AnalysisRepository`
 * auto-persists every completed `/api/research/{ticker}` run for the
 * authenticated reader, and `compare()` computes a deterministic factor,
 * family, macro and risk delta between any two stored runs, entirely in
 * Python, with no model involved. `/terminal/vault` already renders all of
 * it. What was missing is the one place a reader would actually look for
 * it: this page, the moment they reopen a name they have researched before.
 *
 * Two things render here, both read-only summaries of the same repository:
 *
 *   A compact timeline — signal, confidence, risk, per run — so "have I
 *   looked at this before, and what did I conclude" is answerable without
 *   leaving the page.
 *
 *   "Since your last analysis" — the deterministic diff between the two most
 *   recent runs, rendered as plain sentences. The sentences are templated
 *   from `compare()`'s own delta objects (family contribution rose or fell,
 *   by how much), never generated. A model narrating a numeric difference it
 *   was not shown computing is exactly the failure mode this avoids — the
 *   arithmetic is compare()'s, the wording is a fixed lookup, and neither
 *   reads a number the other did not produce.
 *
 * Renders nothing when the reader has no session: history is personal data,
 * `/api/history` requires auth, and a signed-out visitor gets silence here
 * rather than a login prompt bolted onto an anonymous research view.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock, signed } from '@/components/system'
import {
  fetchComparison, fetchHistory,
  type CompareResult, type HistoryItem,
} from '@/lib/persistence'
import { signalTone } from '@/lib/explore'

type Mode = 'beginner' | 'intermediate' | 'advanced'

const dash = '—'

/** Mechanical and direction-only: "contributed more/less", never a value
 *  judgement like "improved" — a family already negative that becomes less
 *  negative did contribute more, and calling that "worse" would be wrong.
 *  Exported for its own unit test, independent of the component that uses it. */
export function familyLine(delta: { label: string; before: number | null; after: number | null; delta: number }): string {
  if (delta.before === null && delta.after !== null) return `${delta.label} is now measured.`
  if (delta.before !== null && delta.after === null) return `${delta.label} could not be measured this time.`
  return delta.delta > 0
    ? `${delta.label} contributed more to the score.`
    : `${delta.label} contributed less to the score.`
}

function SinceLastAnalysis({ result, mode }: { result: CompareResult; mode: Mode }) {
  const changedFamilies = result.families.filter((f) => f.changed)
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
  const unchangedFamilies = result.families.filter((f) => !f.changed)
  const signalChanged = result.before.verdict !== result.after.verdict

  return (
    <div className="rh__since">
      <p className="rh__since-head">
        {signalChanged ? (
          <>
            <span className="xp__signal" data-tone={signalTone(result.before.verdict)}>{result.before.verdict}</span>
            {' → '}
            <span className="xp__signal" data-tone={signalTone(result.after.verdict)}>{result.after.verdict}</span>
          </>
        ) : (
          <>Signal unchanged: <span className="xp__signal" data-tone={signalTone(result.after.verdict)}>{result.after.verdict}</span></>
        )}
      </p>

      {changedFamilies.length ? (
        <>
          <p className="rh__label">Why</p>
          <ul className="rh__list">
            {changedFamilies.map((f) => (
              <li key={f.family}>
                {familyLine(f)}
                {mode !== 'beginner' ? (
                  <span className="rh__delta">
                    {' '}({signed(f.before, 3)} → {signed(f.after, 3)})
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {unchangedFamilies.length ? (
        <>
          <p className="rh__label">Unchanged</p>
          <ul className="rh__list rh__list--muted">
            {unchangedFamilies.map((f) => <li key={f.family}>{f.label}</li>)}
          </ul>
        </>
      ) : null}

      {mode !== 'beginner' ? (
        <p className="rh__meta">
          Confidence {result.before.confidence ?? dash} → {result.after.confidence ?? dash}
          {'  ·  '}
          Risk {result.before.risk_level ?? dash} → {result.after.risk_level ?? dash}
          {result.macro.srm_delta !== null ? (
            <>{'  ·  '}Macro regime {signed(result.macro.srm_before, 2)} → {signed(result.macro.srm_after, 2)}</>
          ) : null}
        </p>
      ) : null}
    </div>
  )
}

function Timeline({ items }: { items: HistoryItem[] }) {
  return (
    <ol className="rh__timeline">
      {items.map((item) => (
        <li key={item.id} className="rh__run">
          <span className="rh__date">{item.created_at.slice(0, 10)}</span>
          <span className="xp__signal" data-tone={signalTone(item.verdict)}>{item.verdict}</span>
          <span className="rh__stat">Confidence {item.confidence ?? dash}</span>
          <span className="rh__stat">Risk {item.risk_level ?? dash}</span>
        </li>
      ))}
    </ol>
  )
}

export default function ResearchHistory({ ticker, mode = 'beginner' }: { ticker: string; mode?: Mode }) {
  const [items, setItems] = useState<HistoryItem[] | null>(null)
  const [comparison, setComparison] = useState<CompareResult | null>(null)
  const [signedIn, setSignedIn] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    // The resets live inside the async body rather than the effect itself: a
    // new ticker means the previous timeline is no longer about this page,
    // and setting state synchronously in the effect body is exactly the
    // cascading-render shape React warns about.
    void (async () => {
      setItems(null)
      setComparison(null)
      setFailed(false)
      try {
        const page = await fetchHistory({ ticker, pageSize: 6, sort: 'newest' })
        if (!live) return
        setItems(page.items)
        if (page.items.length >= 2) {
          // Newest two: index 0 is the run just completed, index 1 the one
          // before it. compare() reorders chronologically on its own, so the
          // call order here does not need to match "before"/"after".
          try {
            const result = await fetchComparison(page.items[1].id, page.items[0].id)
            if (live) setComparison(result)
          } catch {
            /* the timeline still renders without the diff */
          }
        }
      } catch (error) {
        if (!live) return
        // 401 means no session — this panel goes silent, not into an error
        // state, because a signed-out research view is a normal state and
        // history is not something to prompt an anonymous reader to unlock.
        if (error instanceof Error && error.message === '401') setSignedIn(false)
        else setFailed(true)
      }
    })()
    return () => { live = false }
  }, [ticker])

  if (!signedIn) return null
  if (failed) {
    return (
      <Panel title="Research history" subtitle={`your past analyses of ${ticker}`}>
        <StateBlock state="unavailable" title="Could not be read" detail="History is temporarily unavailable." />
      </Panel>
    )
  }
  if (items === null) return null // one quiet beat rather than a skeleton for a panel this far down the page

  return (
    <Panel
      title="Research history"
      subtitle={`your past analyses of ${ticker}`}
      actions={<Link href="/terminal/vault" className="sys-meta sys-meta--strong">Open vault →</Link>}
    >
      {items.length === 0 ? (
        <EmptyLine label="First analysis">
          This is your first recorded analysis of {ticker}. Future analyses will show what changed.
        </EmptyLine>
      ) : (
        <>
          {comparison ? (
            <>
              <p className="rh__label">Since your last analysis</p>
              <SinceLastAnalysis result={comparison} mode={mode} />
            </>
          ) : items.length === 1 ? (
            <Prose size="fine">One analysis recorded so far. The next one will show what changed.</Prose>
          ) : null}
          <p className="rh__label" style={{ marginTop: comparison ? 'var(--gap)' : 0 }}>Timeline</p>
          <Timeline items={items} />
        </>
      )}
    </Panel>
  )
}
