/**
 * Comparison infrastructure.
 *
 * Anything with named fields can be compared against anything else of the same
 * kind, and the rules for what a difference means live here rather than in each
 * workspace.
 *
 * The rule that matters: a difference is only shown as better or worse when the
 * metric declares a direction. Most do not. A turnover of 18× is not worse than
 * 6× without knowing what the strategy is, and colouring it red would be an
 * opinion dressed as a measurement. Fields with no declared direction render
 * their delta in neutral ink.
 *
 * Missing on one side is never treated as zero, and never treated as equal. It
 * is its own outcome — "not comparable" — because a model that did not record a
 * deflated Sharpe has not matched one that recorded 0.
 */
'use client'

import type { ReactNode } from 'react'
import { format, type Kind } from '@/lib/quantity'
import { delta } from '@/lib/semantics'

export type Direction = 'higher-better' | 'lower-better' | 'none'

export interface CompareField {
  key: string
  label: string
  unit?: string
  /** Only 'higher-better' and 'lower-better' colour a delta. */
  direction?: Direction
  /** Numeric extraction. Return null for "not recorded". */
  value: (row: Record<string, unknown>) => number | null
  /** Optional display override; defaults to the numeric value. */
  display?: (row: Record<string, unknown>) => ReactNode
  digits?: number
  /**
   * What kind of quantity this is. Precision, sign handling and unit come from
   * the shared number system, so a Sharpe reads the same in a comparison as it
   * does in the table the reader arrived from. `digits` still overrides it for
   * the rare field the kinds do not describe.
   */
  kind?: Kind
  group?: string
}

export interface CompareSubject {
  id: string
  label: string
  detail?: string
  data: Record<string, unknown>
  /**
   * What the subject's numbers are measured against — its prediction target,
   * its horizon, its units. Two subjects with different bases are not
   * comparable, however identically their fields are named.
   *
   * A mean IC against `fwd_rank_21` is a rank correlation over a 21-session
   * cross-sectional rank. A mean IC against `fwd_ret_21` is a correlation with
   * a return. Both are "mean_ic", both are dimensionless, and subtracting one
   * from the other produces a number with no meaning whatsoever — which will
   * nonetheless be rendered in green if it happens to be positive.
   *
   * Leave it undefined and every subject is assumed commensurable, which is
   * correct when a caller is comparing like with like by construction.
   */
  basis?: string
}

type Outcome = 'better' | 'worse' | 'same' | 'incomparable'

/**
 * Whether a value beats its baseline.
 *
 * The comparison used to carry its own direction table and its own
 * subtraction. Both now come from the semantic layer, so a metric's direction
 * is a property of the metric rather than of the screen it happens to be on —
 * which is what stops one workspace calling a rising drawdown an improvement
 * while another calls it a regression.
 *
 * A field may still declare a direction, and it wins. Some quantities carry a
 * direction from their role rather than their kind: cost share of gross is a
 * proportion, and proportions have no inherent better end, but a smaller one
 * is unambiguously the better result here.
 */
function outcome(
  a: number | null,
  b: number | null,
  field: CompareField,
  other: { kind: Kind; basis?: string },
  self: { kind: Kind; basis?: string },
): Outcome {
  const d = delta(a, b, self, other)
  if (d.interpretation === 'incomparable') return 'incomparable'
  if (d.interpretation === 'unchanged') return 'same'

  if (field.direction && field.direction !== 'none') {
    if (d.value === null) return 'incomparable'
    return (field.direction === 'higher-better') === (d.value > 0) ? 'better' : 'worse'
  }
  return d.interpretation === 'better' ? 'better'
    : d.interpretation === 'worse' ? 'worse'
      : 'same'
}

function fmt(v: number | null, kind: Kind | undefined, digits: number | undefined): string {
  if (v === null) return '—'
  // A field naming its kind goes through the shared system. One naming only
  // digits keeps its own precision, which is what the older call sites expect.
  if (kind) return format(v, kind, digits === undefined ? undefined : { digits }).text
  return v.toFixed(digits ?? 4)
}

export function Compare({
  subjects, fields, baselineId,
}: {
  subjects: CompareSubject[]
  fields: CompareField[]
  /** The column everything else is measured against. Defaults to the first. */
  baselineId?: string
}) {
  if (subjects.length < 2) {
    return (
      <div style={{ padding: 'var(--d-5)', color: 'var(--ink-faint)', fontSize: 'var(--t-meta)', fontFamily: 'var(--font-mono)' }}>
        Select at least two to compare.
      </div>
    )
  }

  const baseline = subjects.find((s) => s.id === baselineId) ?? subjects[0]
  const groups = [...new Set(fields.map((f) => f.group ?? 'Metrics'))]

  return (
    <div className="sys-scroll-x">
      <table className="sys-table sys-table--compact">
        <thead>
          <tr>
            <th style={{ position: 'sticky', left: 0, zIndex: 3, background: 'var(--p-sunken)', minWidth: 150 }}>Metric</th>
            {subjects.map((s) => {
              // Incomparability is a property of the column, not of each row in
              // it. Saying so once in the header beats repeating it against
              // every metric, which is a phrase a reader stops seeing by the
              // third line and a table that then looks merely broken.
              const off = s.id !== baseline.id
                && s.basis !== undefined && baseline.basis !== undefined
                && s.basis !== baseline.basis
              return (
                <th key={s.id} className="num" style={{ minWidth: 118 }} data-incomparable={off ? '' : undefined}>
                  {s.label}
                  {s.id === baseline.id ? <span className="unit">baseline</span> : s.detail ? <span className="unit">{s.detail}</span> : null}
                  {off ? (
                    <span
                      className="unit sys-incomparable"
                      title={`Measured against ${s.basis}; the baseline is measured against ${baseline.basis}. The two are not on one scale, so no differences are shown in this column.`}
                    >
                      not comparable with the baseline
                    </span>
                  ) : null}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <>
              <tr key={`g-${g}`}>
                <td
                  colSpan={subjects.length + 1}
                  className="sys-label"
                  style={{ background: 'var(--p-sunken)', fontSize: 'var(--t-micro)', height: 'var(--row-compact)' }}
                >
                  {g}
                </td>
              </tr>
              {fields.filter((f) => (f.group ?? 'Metrics') === g).map((f) => {
                const base = f.value(baseline.data)
                return (
                  <tr key={f.key}>
                    <td style={{ position: 'sticky', left: 0, zIndex: 1, background: 'var(--p-panel)' }}>
                      <span style={{ fontFamily: 'var(--font-mono)' }}>{f.label}</span>
                      {f.unit ? <span className="sys-meta" style={{ marginLeft: 6 }}>{f.unit}</span> : null}
                    </td>
                    {subjects.map((s) => {
                      const v = f.value(s.data)
                      const isBase = s.id === baseline.id
                      // A subject measured against a different target is not
                      // comparable to the baseline, so no delta is formed and
                      // no better/worse verdict is claimed.
                      // Comparability is decided by the semantic layer: same
                      // class, same scale, same basis, and a kind whose
                      // difference means anything at all.
                      const self = { kind: f.kind ?? 'ratio' as Kind, basis: s.basis }
                      const against = { kind: f.kind ?? 'ratio' as Kind, basis: baseline.basis }
                      const diff = isBase ? null : delta(v, base, self, against)
                      const commensurable = diff === null || diff.interpretation !== 'incomparable'
                      const o = isBase ? 'same' : outcome(v, base, f, against, self)
                      const deltaValue = diff?.value ?? null
                      const cls = o === 'better' ? 'sys-pos' : o === 'worse' ? 'sys-neg' : ''
                      return (
                        <td key={s.id} className="num">
                          <span className={cls}>
                            {f.display ? f.display(s.data) : fmt(v, f.kind, f.digits)}
                          </span>
                          {/* No delta and no verdict; the column header says
                              why, once. */}
                          {!isBase && !commensurable ? null : deltaValue !== null ? (
                            <span
                              className="sys-meta"
                              style={{ marginLeft: 5, color: o === 'better' ? 'var(--e-pos)' : o === 'worse' ? 'var(--e-neg)' : 'var(--ink-faint)' }}
                              title={f.direction && f.direction !== 'none'
                                ? `${o} than the baseline`
                                : 'no declared direction: this difference is not better or worse'}
                            >
                              {diff?.formatted?.text ?? fmt(deltaValue, f.kind, f.digits)}
                              {/* A difference has its own unit — × for a ratio,
                                  pp between two percentages. Without it a ratio
                                  of 0.67 is indistinguishable from a difference
                                  of 0.67. */}
                              {diff?.unit ? <span className="unit">{diff.unit}</span> : null}
                            </span>
                          ) : !isBase && (v === null || base === null) ? (
                            <span className="sys-meta sys-null" style={{ marginLeft: 5 }} title="one side did not record this; an absent value is not a match and not a zero">
                              n/c
                            </span>
                          ) : null}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Legend, so the colouring rule is stated rather than guessed at. */
export function CompareLegend() {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--d-4)', padding: 'var(--d-2) var(--d-3)', borderTop: '1px solid var(--rule)' }}>
      <span className="sys-meta"><span className="sys-pos">green</span> better on a metric with a declared direction</span>
      <span className="sys-meta"><span className="sys-neg">red</span> worse on the same</span>
      <span className="sys-meta">neutral delta: no declared direction, so the difference is not an improvement</span>
      <span className="sys-meta"><span className="sys-null">n/c</span> one side did not record it — not a match, not a zero</span>
    </div>
  )
}
