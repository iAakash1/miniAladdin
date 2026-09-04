/**
 * miniAladdin design system — React primitives.
 *
 * Every workspace composes from these. The rule they enforce together is the
 * one the audits kept proving matters: a number is never shown without its
 * unit, its status and a way to ask where it came from.
 *
 * `Value` is the centre of it. It refuses to render a bare number.
 */
'use client'

import type { ReactNode } from 'react'

import { useMetrics, type MetricRef } from './MetricContext'
import { format, type Kind } from '@/lib/quantity'

/* ── research state ───────────────────────────────────────────────────────
   The product's vocabulary for trust. Deliberately separate from sign: one
   says where a number came from, the other says whether it is good news. */

export type Tone = 'pass' | 'fail' | 'warn' | 'info' | 'muted'

export type ResearchState =
  | 'live' | 'recorded' | 'stale' | 'waking' | 'unavailable'
  | 'blocked' | 'experimental' | 'candidate' | 'production' | 'unknown'

const STATE_TITLE: Record<ResearchState, string> = {
  live:         'Observed now, inside its freshness window',
  recorded:     'A fact read from a stored artifact — it cannot go stale',
  stale:        'Real, but past its freshness window',
  waking:       'A cold service is starting; no value yet',
  unavailable:  'Refused or absent. No value is being shown in its place',
  blocked:      'A research constraint prevents this, not an error',
  experimental: 'Exists and is measured, but is not promotable',
  candidate:    'Cleared the development gates; holdout not yet spent',
  production:   'Armed and serving',
  unknown:      'State could not be determined',
}

export function Status({ state, label }: { state: ResearchState; label?: string }) {
  return (
    <span className="sys-status" data-state={state} title={STATE_TITLE[state]}>
      {label ?? state}
    </span>
  )
}

/* ── value ────────────────────────────────────────────────────────────────
   The single way a number reaches the screen. */

export interface ValueProps {
  value: number | string | null | undefined
  /**
   * What kind of quantity this is. Decides precision, sign handling, unit and
   * whether the sign carries meaning — so an information coefficient looks the
   * same on every screen instead of carrying three decimals here and five
   * there, which implies a precision the estimate does not have.
   */
  kind?: Kind
  /** Rendered small after the number. Overrides the kind's own unit. */
  unit?: string
  /** Overrides the kind's precision. For a headline figure, not an opt-out. */
  digits?: number
  /** Prefix a + on positives. For figures where direction is the point. */
  signed?: boolean
  /** Colour by sign. Off by default: most numbers are not good or bad. */
  tone?: boolean
  /** Shown on hover — method, frequency, period, source. */
  title?: string
  /** Handbook key. Makes the figure inspectable. */
  measure?: string
  /** Full reference, when the caller knows more than the handbook does. */
  inspect?: MetricRef
}

export function Value({
  value, kind, unit, digits, signed, tone, title, measure, inspect,
}: ValueProps) {
  const metrics = useMetrics()

  // One formatter for every figure in the product. A component that reaches
  // for toFixed is a component that will disagree with its neighbour.
  const q = format(value, kind ?? 'ratio', {
    digits,
    signed,
    unit,
    tone,
  })

  if (q.absent) {
    // An em dash, never a zero. The audits found three places where invalid
    // mathematics rendered as 0.0 and read as a real measurement.
    return <span className="sys-num sys-null" title={title ?? 'no value'}>—</span>
  }

  const numeric = typeof value === 'number'
  const cls = q.tone && numeric
    ? value > 0 ? 'sys-pos' : value < 0 ? 'sys-neg' : ''
    : ''

  const body = (
    <>
      {q.text}
      {q.unit ? <span className="u" style={{ fontSize: 'var(--t-micro)', color: 'var(--ink-faint)', marginLeft: 3 }}>{q.unit}</span> : null}
    </>
  )

  // A figure that declares what it is becomes a control: the definition, the
  // method, the unit and what would make it wrong are one click away, and the
  // hover carries the one-line purpose so the common case needs no click.
  if (measure || inspect) {
    const ref: MetricRef = inspect ?? { measure, label: title ?? measure ?? 'value', display: q.text, unit: q.unit }
    const purpose = metrics.summary(ref.measure)
    return (
      <button
        type="button"
        className={`sys-num sys-num--live ${cls}`}
        title={purpose ? `${purpose}\n\nClick for method, source and failure conditions.` : title}
        onClick={(e) => { e.stopPropagation(); metrics.inspect({ ...ref, display: q.text, unit: q.unit ?? ref.unit }) }}
      >
        {body}
      </button>
    )
  }

  return <span className={`sys-num ${cls}`} title={title}>{body}</span>
}

/* ── panel ────────────────────────────────────────────────────────────── */

export interface PanelProvenance {
  /** Where the panel's numbers came from. Rendered in the footer. */
  source?: string | null
  /** The date the data describes. */
  asOf?: string | null
  /** When it was fetched. Different from asOf, and the difference matters. */
  retrievedAt?: string | null
}

export function Panel({
  title, subtitle, actions, state, badge, badgeTone = 'muted',
  children, flush = false, seam = false, source, asOf, retrievedAt,
}: PanelProvenance & {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  /** Research state. Drives the hairline along the panel's top edge. */
  state?: ResearchState
  /** Continue from the rule directly above instead of starting a new edge.
   *  For a panel that is part of the object above it, not the next one down. */
  seam?: boolean
  /** Free text for a verdict a research state cannot express — "NOT SELECTED",
   *  "3 OF 8 GATES". Sits beside the state rather than replacing it. */
  badge?: string
  badgeTone?: Tone
  children: ReactNode
  flush?: boolean
}) {
  // A panel that names its source in a footer answers "where did this come
  // from" without the reader leaving it, which is the cheapest provenance
  // there is and the reason it is on the panel rather than in a drawer.
  const hasFooter = Boolean(source || asOf || retrievedAt)
  return (
    <section className={`sys-panel${seam ? ' sys-panel--seam' : ''}`} data-state={state}>
      <header className="sys-panel-head">
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--d-2)', minWidth: 0 }}>
          <h2 className="sys-label" style={{ margin: 0 }}>{title}</h2>
          {subtitle ? <span className="sys-meta">{subtitle}</span> : null}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--d-2)', flex: 'none', marginLeft: 'auto' }}>
          {badge ? <span className="sys-badge" data-tone={badgeTone}>{badge}</span> : null}
          {state ? <Status state={state} /> : null}
          {actions}
        </div>
      </header>
      <div className={`sys-panel-body${flush ? ' sys-panel-body--flush' : ''}`}>{children}</div>
      {hasFooter ? (
        <footer className="sys-panel-foot">
          {source ? <span>source <b>{source}</b></span> : null}
          {asOf ? <span>as of <b>{asOf}</b></span> : null}
          {retrievedAt ? <span>retrieved <b>{retrievedAt}</b></span> : null}
        </footer>
      ) : null}
    </section>
  )
}

/** The standard workspace grid. Replaces per-page inline grid styles. */
export function Grid({
  children, variant,
}: {
  children: ReactNode
  variant?: 'wide' | 'halves'
}) {
  return (
    <div className={`sys-grid${variant ? ` sys-grid--${variant}` : ''}`}>{children}</div>
  )
}

/* ── metric strip ───────────────────────────────────────────────────────
   The replacement for a grid of cards. */

export interface StripMetric {
  label: string
  value: number | string | null | undefined
  /** Quantity kind. Decides precision and unit; see lib/quantity. */
  kind?: Kind
  unit?: string
  digits?: number
  signed?: boolean
  tone?: boolean
  title?: string
  /** Handbook key. Renders the badge that opens how this number is computed. */
  method?: string
}

export function Strip({ metrics }: { metrics: StripMetric[] }) {
  return (
    <div className="sys-strip">
      {metrics.map((m) => (
        <div className="sys-strip-item" key={m.label}>
          <span className="k" title={m.label}>{m.label}</span>
          {/* The full value on hover, since a long text value is clipped to
              keep it out of the cell beside it. */}
          <span className="v" title={typeof m.value === 'string' ? m.value : undefined}>
            <Value
              value={m.value} kind={m.kind} unit={m.unit} digits={m.digits}
              signed={m.signed} tone={m.tone} title={m.title}
              measure={m.method}
              inspect={m.method ? { measure: m.method, label: m.label, display: '', unit: m.unit, note: m.title } : undefined}
            />
            {/* The badge that turns a figure into something you can ask about.
                Hidden until the strip is hovered, so a row of metrics reads as
                figures rather than as a row of controls. */}
            {m.method ? (
              <a
                className="sys-method"
                href={`/terminal/handbook?measure=${encodeURIComponent(m.method)}`}
                title={`How ${m.label} is computed, and what makes it fail`}
                aria-label={`Methodology for ${m.label}`}
              >
                ƒ
              </a>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  )
}

/* ── state block ────────────────────────────────────────────────────────
   Empty, error and data-gated states. §29 and §30: never "coming soon",
   never a silent zero. A gated capability says what it needs. */

/**
 * A section that has nothing in it yet, stated as a line.
 *
 * A bordered rectangle containing an apology is the most expensive way a
 * product can say "nothing here". It costs a card's worth of space, it draws
 * the eye first because it is a box, and it makes a new reader's first screen
 * look broken rather than empty.
 *
 * Absence is information and belongs in the hierarchy at the weight it
 * deserves: the section keeps its name, because the name says what would be
 * here, and one sentence says why it is not and what fills it.
 *
 * StateBlock is still right where absence is an event — a provider refused, a
 * request failed. This is for absence that is simply the starting condition.
 */
export function EmptyLine({
  label, children,
}: { label: string; children: ReactNode }) {
  return (
    <section className="emptyline">
      <h2 className="emptyline__k">{label}</h2>
      <p className="emptyline__v">{children}</p>
    </section>
  )
}

export function StateBlock({
  state, title, detail, requires, coverage, children,
}: {
  state: ResearchState
  title: string
  detail?: string
  /** For a data-gated capability: exactly what is missing. */
  requires?: string[]
  /** What the current data actually covers. */
  coverage?: string
  /** Further explanation. A blocked state usually needs more than one line. */
  children?: ReactNode
}) {
  return (
    <div style={{ padding: 'var(--d-5) var(--d-4)', textAlign: 'left' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--d-2)', marginBottom: 'var(--d-2)' }}>
        <Status state={state} />
        <span className="sys-lead">{title}</span>
      </div>
      {detail ? (
        <p style={{ margin: '0 0 var(--d-3)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)', maxWidth: '60ch', lineHeight: 'var(--lh-body)' }}>
          {detail}
        </p>
      ) : null}
      {requires?.length ? (
        <div style={{ marginTop: 'var(--d-3)' }}>
          <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>Required</div>
          <ul style={{ margin: 0, paddingLeft: 'var(--d-4)', fontSize: 'var(--t-body)', color: 'var(--ink-muted)' }}>
            {requires.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      ) : null}
      {coverage ? (
        <div style={{ marginTop: 'var(--d-3)' }}>
          <div className="sys-label" style={{ marginBottom: 'var(--d-1)' }}>Current coverage</div>
          <div className="sys-meta">{coverage}</div>
        </div>
      ) : null}
      {children ? <div style={{ marginTop: 'var(--d-3)' }}>{children}</div> : null}
      {requires?.length ? (
        <p style={{ marginTop: 'var(--d-3)', marginBottom: 0, fontSize: 'var(--t-meta)', color: 'var(--ink-faint)' }}>
          No synthetic values are shown in place of the missing data.
        </p>
      ) : null}
    </div>
  )
}

/* ── table ──────────────────────────────────────────────────────────────── */

export interface Column<T> {
  key: string
  header: string
  /** Unit qualifier shown under the header, e.g. "bps", "ann.", "21d". */
  unit?: string
  numeric?: boolean
  width?: string
  render: (row: T) => ReactNode
}

export function Table<T>({
  columns, rows, rowKey, density = 'normal', onSelect, selectedKey, empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  density?: 'compact' | 'normal' | 'relaxed'
  onSelect?: (row: T) => void
  selectedKey?: string
  empty?: ReactNode
}) {
  if (!rows.length) {
    return <>{empty ?? <StateBlock state="unavailable" title="No rows" />}</>
  }
  const cls = `sys-table${density === 'compact' ? ' sys-table--compact' : density === 'relaxed' ? ' sys-table--relaxed' : ''}`
  return (
    <div className="sys-scroll-x">
      <table className={cls}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.numeric ? 'num' : undefined} style={c.width ? { width: c.width } : undefined} scope="col">
                {c.header}
                {c.unit ? <span className="unit">{c.unit}</span> : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row)
            return (
              <tr
                key={key}
                data-selected={selectedKey === key}
                onClick={onSelect ? () => onSelect(row) : undefined}
                onKeyDown={onSelect ? (e) => { if (e.key === 'Enter') onSelect(row) } : undefined}
                tabIndex={onSelect ? 0 : undefined}
                style={onSelect ? { cursor: 'pointer' } : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={c.numeric ? 'num' : undefined}>{c.render(row)}</td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ── provenance ─────────────────────────────────────────────────────────
   §24 of the product brief: every important number answers where it came
   from. Rendered as a chain because that is what it is. */

export interface ProvenanceStep {
  label: string
  value: string
  href?: string
}

export function Provenance({ steps }: { steps: ProvenanceStep[] }) {
  if (!steps.length) return null
  return (
    <ol style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {steps.map((s, i) => (
        <li
          key={s.label}
          style={{
            display: 'grid',
            gridTemplateColumns: '14px 1fr',
            gap: 'var(--d-2)',
            paddingBottom: i === steps.length - 1 ? 0 : 'var(--d-2)',
          }}
        >
          <div style={{ position: 'relative', display: 'flex', justifyContent: 'center' }}>
            <span style={{ width: 5, height: 5, background: 'var(--ink-faint)', marginTop: 5, flex: 'none' }} />
            {i < steps.length - 1 ? (
              <span style={{ position: 'absolute', top: 12, bottom: -4, width: 1, background: 'var(--rule)' }} />
            ) : null}
          </div>
          <div style={{ minWidth: 0 }}>
            <div className="sys-label" style={{ fontSize: 'var(--t-micro)' }}>{s.label}</div>
            <div className="sys-meta" style={{ color: 'var(--ink)', wordBreak: 'break-word' }}>
              {s.href ? <a href={s.href} style={{ color: 'inherit' }}>{s.value}</a> : s.value}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

/* ── section ────────────────────────────────────────────────────────────── */

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--d-2)' }}>
      <div className="sys-label">{title}</div>
      {children}
    </div>
  )
}

/* ── metric ─────────────────────────────────────────────────────────────
   One figure with its method stated beneath it, for the places where a single
   number carries a whole argument — a verdict, a gate outcome, a headline
   statistic. A methodology the reader has to hunt for is one they will not
   read.

   The strip's hover badge is right everywhere else: twenty figures each with a
   line of prose underneath is unreadable. Density decides which is correct. */

export function Metric({
  label, value, unit, method, tone = 'muted', lead = false,
}: {
  label: string
  /**
   * Prefer passing a <Value>, so precision comes from the quantity's kind
   * rather than from this call site. A plain string is still accepted for
   * things that are not quantities — an identifier, a date, a model key — but
   * a number formatted by the caller is how two screens end up quoting the
   * same statistic to different precision.
   */
  value: ReactNode
  unit?: string
  method?: string
  tone?: Tone
  lead?: boolean
}) {
  return (
    <div className={`sys-metric${lead ? ' sys-metric--lead' : ''}`} data-tone={tone}>
      <span className="sys-metric__label">{label}</span>
      <span className="sys-metric__value">
        {value}
        {unit ? <em className="sys-metric__unit">{unit}</em> : null}
      </span>
      {method ? <span className="sys-metric__method">{method}</span> : null}
    </div>
  )
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="sys-metrics">{children}</div>
}

/** Formatting helpers the metric callers share. */
export const dash = (v: unknown): string =>
  v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v)) ? '—' : String(v)

export function signed(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`
}

/* ── prose ──────────────────────────────────────────────────────────────
   Explanatory text inside a panel, with a reading measure.

   This product argues with the reader in a lot of places — why a gate is
   unmet, why a zero-fill is not conservative, why a curve is not an equity
   curve. Those arguments were being written as inline styles, thirty-eight
   copies of the same declaration, which is how a paragraph ends up at a
   different size on the screen that most needs it read.

   A caution paragraph gets a rule rather than a coloured background. A block
   of colour behind text is read once and then ignored; a rule beside it stays
   legible for eight hours. */

export function Prose({
  children, size = 'body', tone, caution = false,
}: {
  children: ReactNode
  size?: 'body' | 'tight' | 'fine'
  tone?: 'strong'
  /** For a paragraph the reader must not skip. */
  caution?: boolean
}) {
  const classes = [
    'sys-prose',
    size !== 'body' ? `sys-prose--${size}` : '',
    tone === 'strong' ? 'sys-prose--strong' : '',
    caution ? 'sys-prose--caution' : '',
  ].filter(Boolean).join(' ')
  return <p className={classes}>{children}</p>
}
