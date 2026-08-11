'use client'

/**
 * ResearchLoader — the pipeline, while it runs.
 *
 * A spinner says "something is happening". For work that genuinely takes
 * ten to sixty seconds, that is indistinguishable from a frozen screen, and
 * the user's only signal is the absence of one.
 *
 * This shows the actual pipeline instead. Every stage named here is a real
 * step the backend performs, in execution order.
 *
 * ## The honesty rule
 *
 * **A stage is only marked complete when completion is known.**
 *
 * Most of these pipelines are a single request — the backend does not stream
 * stage-level progress, so we cannot truthfully claim "fundamentals done".
 * So stages have three states and the middle one carries no claim:
 *
 *   done     the caller told us this finished. Only ever set from a real
 *            signal passed in through `completed`.
 *   active   currently expected to be running, from measured typical
 *            durations. Says "in progress", never "finished".
 *   pending  not reached.
 *
 * The footer says outright that timing is estimated. A progress bar that
 * pretends to know would be a lie told sixty times a day, and the whole
 * product is built on not telling that kind of lie.
 *
 * Motion is one pulse on the active row and nothing else. The brief asked
 * for a research terminal doing work, not an animation showcase.
 */

import { useEffect, useState } from 'react'

export type StageState = 'done' | 'active' | 'passed' | 'pending'

/**
 * Which of the four states a stage is in. Pure, and exported, because this
 * is where the honesty rule actually lives — a comment cannot be run.
 *
 * Four states, not three. A stage the pipeline has moved past but has not
 * *confirmed* finished is neither "done" nor "not reached", and collapsing
 * it into `pending` produced a visibly incoherent list on the live company
 * page: stage 1 ticked, stage 2 looking untouched, stage 3 pulsing away.
 * `passed` says "no longer running" without claiming completion.
 *
 * The invariant that matters: `done` is returned only for stages the caller
 * counted in `completed` — never inferred from `active`.
 */
export function stageState(index: number, completed: number, active: number): StageState {
  if (index < completed) return 'done'
  if (index === active) return 'active'
  return index < active ? 'passed' : 'pending'
}

export interface LoaderStage {
  /** Imperative, present tense: "Fetching market data". */
  label: string
  /** One line on what this step actually does. */
  detail: string
  /** Measured typical duration in ms — used only to advance the highlight. */
  typicalMs: number
}

export default function ResearchLoader({
  title,
  subject,
  stages,
  completed = 0,
  active: reported,
  detail,
  fraction,
  note,
}: {
  /** What is being done — "Researching", "Building factor panel". */
  title: string
  /** What it is being done to — a ticker, a universe. */
  subject?: string
  stages: LoaderStage[]
  /** Stages the caller *knows* have finished. Only these get a checkmark. */
  completed?: number
  /** The stage the caller *knows* is running, when the work reports it.
   *  Overrides the timer entirely — a real signal always beats an estimate. */
  active?: number
  /** Live sub-progress for the running stage, e.g. "12 / 30 symbols".
   *  Only ever a real count — never a synthesised percentage. */
  detail?: string
  /** Fraction 0-1 of the active stage that is genuinely complete, when the
   *  backend reports a countable unit of work (symbols fetched, filings
   *  loaded). Omit it and the active stage shows an indeterminate sweep
   *  instead — which asserts "working", not "this far along".
   *
   *  There is no third option here on purpose: a bar derived from elapsed
   *  time against an estimate is the fake progress this whole component
   *  exists to avoid. */
  fraction?: number
  note?: string
}) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const started = Date.now()
    const tick = setInterval(() => setElapsed(Date.now() - started), 250)
    return () => clearInterval(tick)
  }, [])

  // Which stage is *expected* to be running, from cumulative typical
  // durations. Never advances past the last stage: overrunning the estimate
  // means the last step is still going, not that everything finished.
  let cumulative = 0
  let expected = stages.length - 1
  for (let index = 0; index < stages.length; index += 1) {
    cumulative += stages[index].typicalMs
    if (elapsed < cumulative) {
      expected = index
      break
    }
  }
  // A reported stage wins outright. Letting the timer run ahead of it would
  // highlight a step the server has not started — the specific lie this
  // component exists to avoid — and it also put two rows in an active state
  // at the same time.
  const active = reported !== undefined ? reported : Math.max(expected, completed)
  const estimating = reported === undefined
  const seconds = Math.floor(elapsed / 1000)
  const known = typeof fraction === 'number' && Number.isFinite(fraction)
  const clamped = known ? Math.min(1, Math.max(0, fraction)) : 0

  return (
    <section className="rl" aria-live="polite" aria-busy="true">
      <header className="rl__head">
        <span className="rl__pulse" aria-hidden />
        <h2 className="rl__title">
          {title}
          {subject && <span className="rl__subject">{subject}</span>}
        </h2>
      </header>

      <ol className="rl__stages">
        {stages.map((stage, index) => {
          const state = stageState(index, completed, active)
          return (
            <li key={stage.label} className={`rl__stage is-${state}`}>
              <span className="rl__mark" aria-hidden>
                {state === 'done' ? '✓' : state === 'passed' ? '·' : ''}
              </span>
              <span className="rl__text">
                <span className="rl__label">
                  {stage.label}
                  {state === 'active' && <span className="visually-hidden"> — in progress</span>}
                  {state === 'done' && <span className="visually-hidden"> — complete</span>}
                  {state === 'passed' && <span className="visually-hidden"> — no longer running</span>}
                </span>
                <span className="rl__detail">
                  {state === 'active' && detail ? detail : stage.detail}
                </span>
                {/* The rail only appears on the running stage. Determinate
                    when the server counted something real, indeterminate
                    otherwise — the two look different on purpose, so a
                    filling bar always means measured work. */}
                {state === 'active' && (
                  known ? (
                    <span
                      className="rl__rail"
                      role="progressbar"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(clamped * 100)}
                    >
                      <span className="rl__rail__fill" style={{ transform: `scaleX(${clamped})` }} />
                    </span>
                  ) : (
                    <span className="rl__rail rl__rail--seeking" aria-hidden>
                      <span className="rl__rail__sweep" />
                    </span>
                  )
                )}
              </span>
            </li>
          )
        })}
      </ol>

      <p className="rl__foot">
        {seconds}s elapsed
        {note ? ` · ${note}` : ''}
        {' · '}
        <span className="rl__caveat">
          {estimating
            ? 'stage timing is estimated; only ticked steps are confirmed complete'
            : 'stages reported by the running job'}
        </span>
      </p>
    </section>
  )
}

/* Pipelines, defined next to the loader so the stages stay honest to what
   the backend actually runs. Durations are from observed cold runs. */

export const ANALYSIS_STAGES: LoaderStage[] = [
  { label: 'Fetching market data', detail: 'daily bars through the provider fallback chain', typicalMs: 3500 },
  { label: 'Computing indicators', detail: 'momentum, reversal, volatility and relative strength', typicalMs: 1800 },
  { label: 'Evaluating fundamentals', detail: 'valuation, quality and analyst positioning', typicalMs: 3000 },
  { label: 'Analysing news', detail: 'headline sentiment, weighted by source and recency', typicalMs: 3500 },
  { label: 'Building research', detail: 'scorecard, risk assessment and written synthesis', typicalMs: 6000 },
]

/* These mirror `STAGES` in factor_lab_service.py exactly, in the order the
   build performs them. They previously listed price history first and SEC
   filings third; the builder loads filings for the whole universe *before*
   it fetches a single price series, so the labels described a pipeline that
   does not exist and the highlight jumped backwards when the real stage
   arrived. Durations are from a measured cold mega30 build (34.5 s total). */
export const FACTOR_LAB_STAGES: LoaderStage[] = [
  { label: 'Loading SEC filings', detail: 'fundamentals dated by when each figure was published', typicalMs: 6000 },
  { label: 'Building the point-in-time panel', detail: 'price history per symbol, each factor from a window truncated at its own date', typicalMs: 22000 },
  { label: 'Measuring forward returns', detail: 'what actually happened after each observation date', typicalMs: 3000 },
  { label: 'Running the estimators', detail: 'rank IC, overlap correction, portfolios, attribution', typicalMs: 2000 },
]
