'use client'

import { useMemo } from 'react'

import ClaimTree, { type Claim, type EvidenceState } from '@/components/visual/ClaimTree'
import type { Analysis } from '@/lib/types'

function figure(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`
  return v.toLocaleString('en-US', { maximumFractionDigits: 4 })
}

/** Statement fields as a filing would label them. */
const FIELD_LABEL: Record<string, string> = {
  eps: 'EPS', revenue: 'Revenue', net_income: 'Net income', gross_profit: 'Gross profit',
  operating_income: 'Operating income', ebitda: 'EBITDA', free_cash_flow: 'Free cash flow',
  total_assets: 'Total assets', total_debt: 'Total debt', shares_outstanding: 'Shares outstanding',
}

/** Reconciled claims with each vendor's own reading beneath them. */
export function claimsFor(a: Analysis): Claim[] {
  const claims: Claim[] = []
  const cp = a.consensusPrice
  if (cp) {
    const state: EvidenceState = cp.provider_count < 2 ? 'SINGLE_SOURCE' : cp.conflict ? 'CONFLICTED' : 'AGREED'
    claims.push({
      id: 'price',
      label: 'Last price',
      value: cp.consensus.toFixed(2),
      state,
      detail: cp.provider_count > 1
        ? `${cp.agreement} agree · ${cp.dispersion_pct.toFixed(3)}% spread. The median is shown for reference; every reading is kept.`
        : 'One vendor answered, so there is nothing to reconcile against.',
      observations: cp.readings.map((r) => ({
        provider: r.provider,
        value: r.price.toFixed(2),
        note: [
          r.basis ?? 'basis not stated',
          r.as_of ? `as of ${r.as_of.slice(0, 16).replace('T', ' ')}` : null,
          `${Math.round(r.latency_ms)} ms`,
        ].filter(Boolean).join(' · '),
      })),
    })
  }
  const s = a.statements
  if (s) {
    for (const [key, f] of Object.entries(s.fields)) {
      const state: EvidenceState = f.providers.length < 2 ? 'SINGLE_SOURCE' : f.agrees ? 'AGREED' : 'CONFLICTED'
      const conflict = s.conflicts.find((c) => c.field === key)
      claims.push({
        id: `st-${key}`,
        label: FIELD_LABEL[key] ?? key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()),
        value: figure(f.value),
        state,
        detail: conflict
          ? `Vendors differ by ${conflict.spread_pct.toFixed(1)}% — shown side by side, never averaged.`
          : s.period ? `${s.period} reporting period` : 'The vendors did not state a reporting period.',
        observations: f.observations?.length
          ? f.observations.map((o) => ({ provider: o.provider, value: figure(o.value) }))
          : f.providers.map((p) => ({ provider: p, value: '—', note: 'reported; value not broken out per vendor' })),
      })
    }
  }
  return claims
}

/** The claims panel: every reconciled figure with the readings behind it. */
export function Claims({ a }: { a: Analysis }) {
  const claims = useMemo(() => claimsFor(a), [a])
  if (!claims.length) return null
  const agreed = claims.filter((c) => c.state === 'AGREED').length
  const single = claims.filter((c) => c.state === 'SINGLE_SOURCE').length
  const conflicted = claims.filter((c) => c.state === 'CONFLICTED').length
  return (
    <section className="sys-panel">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">Claims and their sources</h2>
          <span className="sys-panel-sub">{agreed} agreed · {single} single source · {conflicted} conflicted</span>
        </div>
      </header>
      <div className="sys-panel-body">
        <ClaimTree claims={claims} />
      </div>
    </section>
  )
}
