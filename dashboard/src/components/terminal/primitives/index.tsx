'use client'

/**
 * Terminal primitives — the shared vocabulary for displaying a number.
 *
 * ## Why this module exists
 *
 * Before it, every workspace invented its own shape for "a metric with some
 * context": the quant terminal had one, the models page had another, portfolio
 * had a third. They disagreed on what context a number needs, which meant each
 * one decided independently whether to show a methodology, an as-of date, or a
 * source — and the honest ones were the exception rather than the rule.
 *
 * The contract here is deliberately strict. A `Metric` takes a value **and**
 * the things that make the value interpretable. It is more work to render a
 * number this way, and that is the point: a Sharpe ratio without its cost
 * assumption and a VaR without its estimator are both unfalsifiable, and a
 * component that makes it easy to omit them will have them omitted.
 *
 * ## Adapted from OpenBB's widget model
 *
 * OpenBB's workspace widgets carry title, description, source, timestamp and
 * parameters alongside their data rather than beside it in documentation.
 * `Panel` takes the same position: the provenance strip is part of the
 * container, so a panel cannot be built without deciding what it says about
 * where its numbers came from. Concept only — no OpenBB code is used here, and
 * both OpenBB and Fincept are AGPL-3.0.
 *
 * ## Every state is designed
 *
 * `StateBlock` exists because "Loading…" and "Something went wrong" are the two
 * least useful strings in software. A loading state should name what is being
 * fetched; a failure should name what failed and what the reader can do.
 */

import type { ReactNode } from 'react'

export type Tone = 'pass' | 'fail' | 'warn' | 'info' | 'muted'

/** Em dash for anything absent. Never zero — a measured zero and a missing
 *  value must not render identically. */
export const dash = (v: unknown): string =>
  v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))
    ? '—'
    : String(v)

export function signed(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v >= 0 ? '+' : '') + v.toFixed(digits)
}

/* ── panel ────────────────────────────────────────────────────────────────── */

export interface PanelSource {
  /** Where the number came from — an artifact path, an endpoint, a provider. */
  source?: string
  /** The date the data describes, not the date it was fetched. */
  asOf?: string | null
  /** When this client last retrieved it. Distinct from `asOf` on purpose:
   *  fresh delivery of stale data is a thing that happens. */
  retrievedAt?: string | null
  /** A short status word — LIVE, RECORDED, STALE, UNAVAILABLE. */
  status?: string
  statusTone?: Tone
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  ...provenance
}: PanelSource & {
  title: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
}) {
  const { source, asOf, retrievedAt, status, statusTone } = provenance
  const hasFooter = Boolean(source || asOf || retrievedAt)
  return (
    <section className="tp-panel">
      <header className="tp-panel__head">
        <div className="tp-panel__id">
          <h3 className="tp-panel__title">{title}</h3>
          {subtitle ? <span className="tp-panel__subtitle">{subtitle}</span> : null}
        </div>
        {status ? (
          <span className={`tp-status tp-status--${statusTone ?? 'muted'}`}>{status}</span>
        ) : null}
        {actions ? <div className="tp-panel__actions">{actions}</div> : null}
      </header>
      <div className="tp-panel__body">{children}</div>
      {hasFooter ? (
        <footer className="tp-panel__foot">
          {source ? <span>source <b>{source}</b></span> : null}
          {asOf ? <span>as of <b>{asOf}</b></span> : null}
          {retrievedAt ? <span>retrieved <b>{retrievedAt}</b></span> : null}
        </footer>
      ) : null}
    </section>
  )
}

/* ── metric ───────────────────────────────────────────────────────────────── */

export function Metric({
  label,
  value,
  unit,
  method,
  status = 'muted',
  emphasis = false,
}: {
  label: string
  value: string
  /** Rendered smaller and adjacent, so `18.47` and `×` never merge into a
   *  single unreadable token. */
  unit?: string
  /** How the number was produced. Shown, not hidden behind a tooltip: a
   *  methodology a reader has to hunt for is one they will not read. */
  method?: string
  status?: Tone
  emphasis?: boolean
}) {
  return (
    <div className={`tp-metric tp-metric--${status}${emphasis ? ' tp-metric--lead' : ''}`}>
      <span className="tp-metric__label">{label}</span>
      <span className="tp-metric__value">
        {value}
        {unit ? <em className="tp-metric__unit">{unit}</em> : null}
      </span>
      {method ? <span className="tp-metric__method">{method}</span> : null}
    </div>
  )
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="tp-metrics">{children}</div>
}

/* ── states ───────────────────────────────────────────────────────────────── */

export type StateKind = 'loading' | 'empty' | 'error' | 'offline' | 'locked'

const STATE_TONE: Record<StateKind, Tone> = {
  loading: 'info',
  empty: 'muted',
  error: 'fail',
  offline: 'warn',
  locked: 'warn',
}

/**
 * A designed state, not a spinner.
 *
 * `what` names the thing — "EXP-007 selection verdict", not "data". `why`
 * explains the cause when it is known, and is omitted rather than guessed at.
 * `action` is what the reader can actually do, which is frequently nothing, in
 * which case saying so is better than implying a retry will help.
 */
export function StateBlock({
  kind,
  what,
  why,
  action,
}: {
  kind: StateKind
  what: string
  why?: string
  action?: ReactNode
}) {
  const verb = {
    loading: 'Loading',
    empty: 'No data for',
    error: 'Could not load',
    offline: 'Service unavailable for',
    locked: 'Not available:',
  }[kind]
  return (
    <div className={`tp-state tp-state--${kind}`}>
      <div className="tp-state__head">
        <span className={`tp-status tp-status--${STATE_TONE[kind]}`}>
          {kind.toUpperCase()}
        </span>
        <strong>
          {verb} {what}
          {kind === 'loading' ? '…' : ''}
        </strong>
      </div>
      {why ? <p className="tp-state__why">{why}</p> : null}
      {action ? <div className="tp-state__action">{action}</div> : null}
    </div>
  )
}

/* ── provenance chain ─────────────────────────────────────────────────────── */

export interface ProvenanceLink {
  stage: string
  value: string | null | undefined
  detail?: string
}

/**
 * The chain from raw data to the number on screen, as an ordered list.
 *
 * Rendered as a chain rather than a table because the *order* is the claim:
 * each stage is derived from the one above it, and a reader checking
 * reproducibility walks it downward.
 */
export function ProvenanceChain({ links }: { links: ProvenanceLink[] }) {
  return (
    <ol className="tp-chain">
      {links.map((link) => (
        <li key={link.stage} className="tp-chain__link">
          <span className="tp-chain__stage">{link.stage}</span>
          <span className="tp-chain__value">{dash(link.value)}</span>
          {link.detail ? <span className="tp-chain__detail">{link.detail}</span> : null}
        </li>
      ))}
    </ol>
  )
}

/* ── envelope-driven metric ───────────────────────────────────────────────── */

/**
 * Anything the server can send in an envelope.
 *
 * Declared structurally rather than imported so the primitives stay usable
 * outside the quant surface; the shape is `src/services/envelope.py`.
 */
export interface EnvelopeLike {
  value: number | null
  status: string
  source: string
  as_of: string | null
  method: string | null
  unit: string | null
  detail: string | null
}

/** Statuses that license rendering the number as usable. */
const TRUSTWORTHY = new Set(['live', 'recorded'])

/**
 * Render a metric straight from a server envelope.
 *
 * The methodology comes from the server, so it cannot drift between the two
 * components that happen to show the same number — which it previously did,
 * because each restated it in its own JSX.
 *
 * A value that is not trustworthy renders its status instead of its number.
 * There is no path here that prints a figure the server declined to vouch for.
 */
export function EnvelopeMetric({
  label,
  envelope,
  digits = 4,
  signed: withSign = true,
  status,
  emphasis = false,
}: {
  label: string
  envelope: EnvelopeLike | undefined
  digits?: number
  signed?: boolean
  /** Pass/fail against a gate. Omitted leaves the metric neutral — a colour
   *  here is a verdict, and most numbers are not verdicts. */
  status?: Tone
  emphasis?: boolean
}) {
  if (!envelope) {
    return <Metric label={label} value="—" method="not served" status="muted" />
  }
  const usable = TRUSTWORTHY.has(envelope.status) && envelope.value !== null
  const shown = usable
    ? (withSign ? signed(envelope.value, digits) : (envelope.value as number).toFixed(digits))
    : envelope.status.toUpperCase()

  return (
    <Metric
      label={label}
      value={shown}
      unit={usable ? envelope.unit ?? undefined : undefined}
      method={usable ? envelope.method ?? undefined : envelope.detail ?? undefined}
      status={usable ? (status ?? 'muted') : 'warn'}
      emphasis={emphasis}
    />
  )
}
