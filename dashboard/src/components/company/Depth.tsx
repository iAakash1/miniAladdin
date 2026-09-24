'use client'

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { DEPTHS, NarrativeExpired, fetchNarrative, rememberDepth, storedDepth } from '@/lib/report-depth'
import type { AiAnalysis, Analysis, ReportDepth } from '@/lib/types'

type Status = 'ready' | 'writing' | 'expired' | 'failed' | 'unavailable'

export interface NarrativeControl {
  /** The depth the reader asked for. */
  depth: ReportDepth
  /** The depth of the narrative on screen — lags `depth` while one is written. */
  shownDepth: ReportDepth
  status: Status
  /** Whether this run can be re-explained at all: it needs a generated
   *  narrative and a server-held evidence snapshot. */
  canSwitch: boolean
  setDepth: (depth: ReportDepth) => void
  retry: () => void
}

const Ctx = createContext<NarrativeControl | null>(null)

export function NarrativeProvider({ value, children }: { value: NarrativeControl | null; children: ReactNode }) {
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useNarrativeControl(): NarrativeControl | null {
  return useContext(Ctx)
}

/**
 * The narrative at the depth the reader chose.
 *
 * The research run's own narrative is kept; another depth is requested from
 * the same evidence snapshot and cached per snapshot and depth, so switching
 * back is instant and nothing upstream is called again. The deterministic
 * output never passes through here — only `analysis.ai` is replaced.
 */
export function useNarrative(analysis: Analysis | null): { ai: AiAnalysis | null; control: NarrativeControl | null } {
  const base = analysis?.ai ?? null
  const baseDepth: ReportDepth = base?.depth ?? 'intermediate'
  const snapshot = base?.generated ? base.snapshotId : null
  const [depth, setDepthState] = useState<ReportDepth>(() => storedDepth())
  const [written, setWritten] = useState<Record<string, AiAnalysis>>({})
  const [problem, setProblem] = useState<{ key: string; kind: 'expired' | 'failed' } | null>(null)
  const [attempt, setAttempt] = useState(0)
  const inFlight = useRef(new Set<string>())

  const key = snapshot ? `${snapshot}:${depth}` : null
  const wanted = depth !== baseDepth && key ? written[key] ?? null : null
  const needsWriting = Boolean(key && depth !== baseDepth && !wanted && problem?.key !== key)

  // One request per snapshot and depth. Results are stored under their own key,
  // so a reply that lands after the reader has moved on is kept for when they
  // come back rather than applied to whatever is on screen.
  useEffect(() => {
    if (!needsWriting || !key || !snapshot || !analysis || inFlight.current.has(key)) return
    inFlight.current.add(key)
    fetchNarrative(analysis.ticker, snapshot, depth)
      .then((ai) => setWritten((w) => ({ ...w, [key]: ai })))
      .catch((e: unknown) => setProblem({ key, kind: e instanceof NarrativeExpired ? 'expired' : 'failed' }))
      .finally(() => inFlight.current.delete(key))
  }, [needsWriting, key, snapshot, analysis, depth, attempt])

  const ai = depth === baseDepth ? base : wanted ?? base
  const shownDepth: ReportDepth = depth === baseDepth ? baseDepth : wanted ? depth : baseDepth
  const status: Status = !base?.generated ? 'unavailable'
    : depth === baseDepth || wanted ? 'ready'
      : !snapshot ? 'unavailable'
        : problem?.key === key ? problem.kind
          : 'writing'

  const control = useMemo<NarrativeControl | null>(() => (analysis ? {
    depth,
    shownDepth,
    status,
    canSwitch: Boolean(snapshot),
    setDepth: (next) => {
      rememberDepth(next)
      setDepthState(next)
    },
    retry: () => {
      setProblem(null)
      setAttempt((n) => n + 1)
    },
  } : null), [analysis, depth, shownDepth, status, snapshot])

  return { ai, control }
}

const LABEL: Record<ReportDepth, string> = { beginner: 'beginner', intermediate: 'intermediate', advanced: 'advanced' }

/** The depth selector, with what each depth means and what is happening. */
export function DepthControl({ compact = false }: { compact?: boolean }) {
  const c = useNarrativeControl()
  if (!c) return null
  const current = DEPTHS.find((d) => d.key === c.depth) ?? DEPTHS[1]
  return (
    <div className={compact ? 'dp dp--compact' : 'dp'}>
      <div className="dp-seg" role="radiogroup" aria-label="Explanation depth">
        {DEPTHS.map((d) => {
          const locked = !c.canSwitch && d.key !== c.shownDepth
          return (
            <button
              key={d.key}
              type="button"
              role="radio"
              aria-checked={(c.canSwitch ? c.depth : c.shownDepth) === d.key}
              disabled={locked}
              className="dp-opt"
              title={locked ? 'This run has no evidence snapshot to re-explain' : d.blurb}
              onClick={() => c.setDepth(d.key)}
            >
              {d.label}
            </button>
          )
        })}
      </div>
      {!compact ? <p className="dp-blurb">{current.blurb}</p> : null}
      {c.status === 'writing' ? (
        <p className="dp-status" role="status">
          <span className="dp-status__bar" aria-hidden />
          Writing the {LABEL[c.depth]} explanation from the same evidence — the signal and every figure stay as they are.
        </p>
      ) : c.status === 'expired' ? (
        <p className="dp-status" data-tone="warn" role="status">
          This run&apos;s evidence is no longer held on the server, so it cannot be re-explained. Showing the {LABEL[c.shownDepth]} explanation; run the research again to change depth.
        </p>
      ) : c.status === 'failed' ? (
        <p className="dp-status" data-tone="warn" role="status">
          The {LABEL[c.depth]} explanation could not be written. Showing the {LABEL[c.shownDepth]} one.
          <button type="button" className="dp-retry" onClick={c.retry}>Retry</button>
        </p>
      ) : null}
    </div>
  )
}
