'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'

import { FAMILY_LABEL, FAMILY_ORDER, factorName, familyScore } from './derive'
import { companyHref } from '@/lib/context-commands'
import type { Analysis } from '@/lib/types'

export function Pending({ title, rows = 3 }: { title: string; rows?: number }) {
  return (
    <section className="sys-panel" aria-busy="true">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title"><h2 className="sys-panel-title">{title}</h2></div>
      </header>
      <div className="sys-loading">
        {Array.from({ length: rows }, (_, i) => (
          <span key={i} className="sys-skeleton" style={{ height: 8, width: `${[72, 54, 63, 40][i % 4]}%` }} />
        ))}
      </div>
    </section>
  )
}

export function Card({ title, sub, more, children, flush }: {
  title: string
  sub?: ReactNode
  more?: { href: string; label: string }
  children: ReactNode
  flush?: boolean
}) {
  return (
    <section className="sys-panel">
      <header className="sys-panel-head">
        <div className="sys-panel-head__title">
          <h2 className="sys-panel-title">{title}</h2>
          {sub ? <span className="sys-panel-sub">{sub}</span> : null}
        </div>
        {more ? <Link className="cw-more" href={more.href}>{more.label}</Link> : null}
      </header>
      <div className={flush ? 'sys-panel-body sys-panel-body--flush' : 'sys-panel-body'}>{children}</div>
    </section>
  )
}

/** A score in [-1, 1] as a bar from the centre line. */
export function Diverging({ value, max = 1 }: { value: number | null; max?: number }) {
  if (value === null || !Number.isFinite(value)) return <span className="div-bar div-bar--empty" aria-hidden />
  const w = Math.min(1, Math.abs(value) / max) * 50
  return (
    <span className="div-bar" aria-hidden>
      <span
        className="div-bar__fill"
        data-tone={value > 0.005 ? 'pos' : value < -0.005 ? 'neg' : 'muted'}
        style={value >= 0 ? { left: '50%', width: `${w}%` } : { left: `${50 - w}%`, width: `${w}%` }}
      />
    </span>
  )
}

/** The deterministic decomposition: family scores, weights and the largest contributions. */
export function Drivers({ a, links = true }: { a: Analysis; links?: boolean }) {
  const q = a.quant
  if (!q) {
    return (
      <Card title="Signal decomposition">
        <p className="cw-muted">The scorecard was not returned for this run, so no decomposition is shown.</p>
      </Card>
    )
  }
  const factors = [...q.factors].sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution)).slice(0, 5)
  return (
    <Card
      title="Signal decomposition"
      sub={<>composite <span className="sys-num">{q.rawScore >= 0 ? '+' : ''}{q.rawScore.toFixed(2)}</span></>}
      more={links ? { href: `${companyHref(a.ticker, 'report')}#drivers`, label: `All ${q.factors.length} factors` } : undefined}
    >
      <table className="cw-fam">
        <thead>
          <tr>
            <th scope="col">Family</th>
            <th scope="col" className="num">Weight</th>
            <th scope="col" className="num">Score</th>
            <th scope="col"><span className="visually-hidden">Direction</span></th>
          </tr>
        </thead>
        <tbody>
          {FAMILY_ORDER.map((f) => {
            const s = familyScore(a, f)
            return (
              <tr key={f}>
                <td>{FAMILY_LABEL[f]}</td>
                <td className="num">{q.weightsUsed[f] !== undefined ? `${Math.round(q.weightsUsed[f] * 100)}%` : '—'}</td>
                <td className="num">{s === null ? <span className="sys-null">—</span> : `${s >= 0 ? '+' : ''}${s.toFixed(2)}`}</td>
                <td className="cw-fam__bar"><Diverging value={s} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="cw-note">
        Macro gate <span className="sys-num">×{q.macroGate.toFixed(2)}</span> applies to the momentum sleeve only
        {q.stressProbability !== null ? <> · stress probability <span className="sys-num">{(q.stressProbability * 100).toFixed(1)}%</span></> : null}
      </p>
      <h3 className="cw-sub">Largest contributions</h3>
      <ul className="cw-contrib">
        {factors.map((f) => (
          <li key={f.name}>
            <span className={`sys-num ${f.contribution >= 0 ? 'sys-pos' : 'sys-neg'}`}>{f.contribution >= 0 ? '+' : ''}{f.contribution.toFixed(3)}</span>
            <span className="cw-contrib__name">{factorName(f.name)}</span>
            <span className="cw-contrib__fam">{f.family}</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/** How complete and consistent the evidence behind a run was. */
export function EvidenceCondition({ a, links = true }: { a: Analysis; links?: boolean }) {
  const p = a.provenance
  const q = a.quant
  const losses = [...(q?.confidenceLosses ?? [])].sort((x, y) => y.points - x.points)
  const problems = (p?.inputs ?? []).filter((i) => i.health !== 'ok')
  const cp = a.consensusPrice
  const si = a.seriesIntegrity
  const statementConflicts = a.statements?.conflicts.length ?? 0
  const total = p ? p.summary.total : 0
  return (
    <Card
      title="Evidence condition"
      sub={a.decisionQuality ? `quality ${a.decisionQuality.grade.toLowerCase()}` : undefined}
      more={links ? { href: companyHref(a.ticker, 'evidence'), label: 'Inspect evidence' } : undefined}
    >
      {p ? (
        <>
          <div className="cw-health" role="img" aria-label={`${p.summary.ok} inputs ok, ${p.summary.degraded} degraded, ${p.summary.missing} missing`}>
            <span className="cw-health__seg" data-tone="pos" style={{ flex: p.summary.ok }} />
            <span className="cw-health__seg" data-tone="warn" style={{ flex: p.summary.degraded }} />
            <span className="cw-health__seg" data-tone="neg" style={{ flex: p.summary.missing }} />
          </div>
          <p className="cw-health__legend">
            <span><b className="sys-num">{p.summary.ok}</b> of {total} inputs ok</span>
            <span><b className="sys-num">{p.summary.degraded}</b> degraded</span>
            <span><b className="sys-num">{p.summary.missing}</b> missing</span>
          </p>
          {problems.length ? (
            <ul className="cw-issues">
              {problems.slice(0, 4).map((i) => (
                <li key={i.label} data-tone={i.health === 'missing' ? 'neg' : 'warn'}>
                  <span className="cw-issues__label">{i.label}</span>
                  <span className="cw-issues__note">{i.note ?? i.health}</span>
                </li>
              ))}
            </ul>
          ) : <p className="cw-muted">Every input answered from a live source.</p>}
        </>
      ) : <p className="cw-muted">This run carries no provenance record.</p>}

      <dl className="cw-kv">
        <div>
          <dt>Price</dt>
          <dd>{cp ? (cp.provider_count > 1 ? `${cp.agreement} agree · ${cp.dispersion_pct.toFixed(3)}% spread` : 'single source') : '—'}</dd>
        </div>
        <div>
          <dt>History</dt>
          <dd>{si && si.providers.length > 1 ? `${si.agreement_pct.toFixed(1)}% agree · ${si.shared_sessions} sessions` : 'single source'}</dd>
        </div>
        <div>
          <dt>Statements</dt>
          <dd>{a.statements ? `${a.statements.providers.length} vendors · ${statementConflicts} conflict${statementConflicts === 1 ? '' : 's'}` : '—'}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            {a.engineConfidence !== null ? <>100 → <b className="sys-num">{a.engineConfidence}</b></> : '—'}
            {losses.length ? <span className="cw-kv__sub"> · {losses.slice(0, 3).map((l) => `−${l.points} ${l.component.toLowerCase()}`).join(', ')}</span> : null}
          </dd>
        </div>
      </dl>
    </Card>
  )
}
