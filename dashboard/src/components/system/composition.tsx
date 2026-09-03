/**
 * Composition primitives: the identity, controls and loading shapes every
 * workspace shares.
 *
 * These exist because the same three things were being rebuilt inline on every
 * page with slightly different spacing each time — an identity block, a row of
 * controls, and something to show while data arrives. A product where those
 * differ per screen does not read as one product however consistent its colours
 * are.
 */
'use client'

import type { ReactNode } from 'react'

import { Status, Value, type ResearchState } from './index'
import type { Kind } from '@/lib/quantity'
import { Relations } from './Relations'
import type { ResearchObject } from '@/lib/research/objects'

/* ── object header ──────────────────────────────────────────────────────── */

export interface HeaderFact {
  label: string
  value: number | string | null | undefined
  /** Quantity kind. Decides precision and unit; see lib/quantity. */
  kind?: Kind
  unit?: string
  digits?: number
  signed?: boolean
  tone?: boolean
  title?: string
  /**
   * The documented measure this figure is, by its handbook name. Makes the
   * masthead fact inspectable: a reader can ask what it is, how it was
   * produced and what would make it wrong.
   *
   * These are the headline numbers on a workspace, which makes them the ones a
   * reader is most likely to quote elsewhere — and therefore the ones that
   * least deserve to be unexplainable.
   */
  method?: string
}

export function ObjectHeader({
  glyph, name, kind, state, detail, facts, actions, object,
}: {
  /** One or two characters. The object kind's mark. */
  glyph: string
  name: string
  kind?: string
  state?: ResearchState
  detail?: ReactNode
  /** Up to six. More than that is a metric strip, not an identity. */
  facts?: HeaderFact[]
  actions?: ReactNode
  /**
   * When given, the masthead shows what this object connects to — counts
   * computed by inverting what the artifacts record, not inferred.
   */
  object?: ResearchObject
}) {
  return (
    <header className="sys-object">
      <div className="sys-object-id">
        <span className="sys-object-glyph" aria-hidden>{glyph}</span>
        <div style={{ minWidth: 0 }}>
          <h1 className="sys-object-name">{name}</h1>
          <div className="sys-object-sub">
            {kind ? <span className="sys-label" style={{ fontSize: 'var(--t-micro)' }}>{kind}</span> : null}
            {state ? <Status state={state} /> : null}
            {detail ? <span className="sys-meta">{detail}</span> : null}
          </div>
          {object ? <Relations object={object} /> : null}
        </div>
      </div>

      {facts?.length ? (
        <div className="sys-object-facts">
          {facts.slice(0, 6).map((f) => (
            <div className="sys-object-fact" key={f.label}>
              <span className="k" title={f.title}>{f.label}</span>
              <span className="v">
                <Value
                  value={f.value} kind={f.kind} unit={f.unit} digits={f.digits}
                  signed={f.signed} tone={f.tone} title={f.title}
                  measure={f.method}
                />
              </span>
            </div>
          ))}
        </div>
      ) : null}

      {actions ? (
        <div style={{ display: 'flex', gap: 'var(--d-1)', alignItems: 'center', flexWrap: 'wrap' }}>
          {actions}
        </div>
      ) : null}
    </header>
  )
}

/* ── toolbar ────────────────────────────────────────────────────────────── */

export function Toolbar({
  children, top = false,
}: {
  children: ReactNode
  /** Set when the toolbar is the first thing in the workspace. */
  top?: boolean
}) {
  return <div className={`sys-toolbar${top ? ' sys-toolbar--top' : ''}`}>{children}</div>
}

export function ToolbarGroup({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="sys-toolbar-group">
      {label ? <span className="sys-label" style={{ fontSize: 'var(--t-micro)', marginRight: 2 }}>{label}</span> : null}
      {children}
    </div>
  )
}

export function ToolbarSeparator() {
  return <span className="sys-toolbar-sep" aria-hidden />
}

export function ToolbarSpacer() {
  return <span className="sys-toolbar-spacer" />
}

/* ── segmented control ──────────────────────────────────────────────────── */

export function Segmented<T extends string>({
  options, value, onChange, label,
}: {
  options: readonly T[] | readonly { value: T; label: string }[]
  value: T
  onChange: (next: T) => void
  label?: string
}) {
  const items = options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
  return (
    <div className="sys-seg" role="group" aria-label={label}>
      {items.map((o) => (
        <button
          key={o.value}
          className="sys-btn"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          type="button"
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ── skeletons ──────────────────────────────────────────────────────────── */

/**
 * Loading that keeps the shape of what is coming, so the layout does not jump
 * when it arrives and the reader knows what to expect while they wait.
 */
export function TableSkeleton({ rows = 8, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="visually-hidden">Loading table</span>
      {Array.from({ length: rows }, (_, r) => (
        <div className="sys-skeleton-row" key={r}>
          {Array.from({ length: columns }, (_, c) => (
            <span
              key={c}
              className="sys-skeleton sys-skeleton-cell"
              style={{
                // Widths vary by column so the shape reads as a table rather
                // than as a stack of identical bars.
                flex: c === 0 ? '0 0 22%' : '1 1 0',
                opacity: 1 - r * 0.06,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ChartSkeleton({ height = 180 }: { height?: number }) {
  return (
    <div
      aria-busy="true"
      style={{ height, display: 'flex', alignItems: 'flex-end', gap: 3, padding: 'var(--d-2)' }}
    >
      <span className="visually-hidden">Loading chart</span>
      {Array.from({ length: 40 }, (_, i) => (
        <span
          key={i}
          className="sys-skeleton"
          style={{
            flex: 1,
            // A plausible silhouette rather than a flat block, so the shape
            // says "a series is coming" and not "something is broken".
            height: `${28 + Math.abs(Math.sin(i * 0.7)) * 58}%`,
          }}
        />
      ))}
    </div>
  )
}

export function StripSkeleton({ items = 6 }: { items?: number }) {
  return (
    <div className="sys-strip" aria-busy="true">
      <span className="visually-hidden">Loading metrics</span>
      {Array.from({ length: items }, (_, i) => (
        <div className="sys-strip-item" key={i}>
          <span className="sys-skeleton" style={{ display: 'block', height: 7, width: '58%', marginBottom: 7 }} />
          <span className="sys-skeleton" style={{ display: 'block', height: 12, width: '76%' }} />
        </div>
      ))}
    </div>
  )
}

/* ── method badge ───────────────────────────────────────────────────────── */

/**
 * The affordance that turns a number into something you can ask about. Hidden
 * until its row is hovered so a dense table is not peppered with icons, and
 * always reachable by keyboard.
 */
export function MethodBadge({ href, title }: { href: string; title: string }) {
  return (
    <a className="sys-method" href={href} title={title} aria-label={title}>
      ƒ
    </a>
  )
}
