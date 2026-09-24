import type { ReactNode } from 'react'

import { Diverging } from './Panels'
import { factorName } from './derive'
import type { Analysis } from '@/lib/types'

/** A compact document table. Header and cell rows walk the same `head` array. */
export function Table({ head, rows, numeric = [] }: { head: string[]; rows: ReactNode[][]; numeric?: number[] }) {
  return (
    <div className="sys-scroll-x">
      <table className="sys-table sys-table--compact rp-table">
        <thead><tr>{head.map((h, i) => <th key={h} scope="col" className={numeric.includes(i) ? 'num' : undefined}>{h}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j} className={numeric.includes(j) ? 'num' : undefined}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * Where the confidence and risk numbers come from: every deduction from a
 * 100-point base, and every weighted risk component. Both are the engine's
 * own arithmetic, shown so either figure can be checked by hand.
 */
export function DeterministicConclusion({ a }: { a: Analysis }) {
  const q = a.quant
  if (!q) return null
  const losses = [...q.confidenceLosses].sort((x, y) => y.points - x.points)
  const riskRows = [...q.riskComponents].sort((x, y) => y.contribution - x.contribution)
  return (
    <>
      <div className="rp-cols">
        <div>
          <h3 className="rp-h3">Confidence composition</h3>
          <Table
            head={['Component', 'Points']}
            numeric={[1]}
            rows={[
              ['Model confidence base', '100'],
              ...losses.map((l) => [`Less: ${l.component}`, `−${l.points}`]),
              [<strong key="t">Confidence</strong>, <strong key="v">{a.engineConfidence ?? '—'}</strong>],
            ]}
          />
        </div>
        <div>
          <h3 className="rp-h3">Risk composition</h3>
          <Table
            head={['Component', 'Percentile', 'Weight', 'Contribution']}
            numeric={[1, 2, 3]}
            rows={[
              ...riskRows.map((c) => [c.name.replace(/_/g, ' '), c.percentile.toFixed(1), c.weight.toFixed(2), c.contribution.toFixed(2)]),
              [<strong key="t">Risk score</strong>, '', '', <strong key="v">{q.riskScore}</strong>],
            ]}
          />
        </div>
      </div>
      {a.decisionQuality ? (
        <p className="rp-note">
          Evidence quality <strong>{a.decisionQuality.grade.toLowerCase()}</strong> — {a.decisionQuality.summary}
        </p>
      ) : null}
    </>
  )
}

/** Every factor the engine computed, by absolute contribution. */
export function FactorTable({ a }: { a: Analysis }) {
  const factors = [...(a.quant?.factors ?? [])].sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution))
  if (!factors.length) return null
  const signed = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(3)}`
  return (
    <Table
      head={['Factor', 'Family', 'Value', 'z', 'Contribution', '']}
      numeric={[2, 3, 4]}
      rows={factors.map((f) => [
        factorName(f.name), f.family,
        f.value === null ? '—' : f.value.toFixed(4),
        f.z === null ? '—' : f.z.toFixed(2),
        <span key="c" className={f.contribution >= 0 ? 'sys-pos' : 'sys-neg'}>{signed(f.contribution)}</span>,
        <Diverging key="b" value={f.contribution} max={0.08} />,
      ])}
    />
  )
}
