'use client'

/**
 * Portfolio construction, risk and cost for the current signal.
 *
 * Shows what the research signal would look like *as a book*: weights, risk
 * contributions, concentration, and the cost waterfall that turns a positive
 * gross number negative.
 *
 * Two things this is careful about.
 *
 * **Units.** The target is a cross-sectional rank in [−1, 1], so every risk and
 * cost figure here is in rank units, not currency. The panel says so rather than
 * letting a reader assume percentages. The Sharpe figures that carry evidential
 * weight come from the experiment's costed backtest, not from this view.
 *
 * **Status.** An allocation built from a model with a negative net Sharpe is an
 * illustration of how the signal would be held — not a recommendation to hold
 * it. The disclaimer travels with the numbers, and the allocator is selectable
 * so the reader can see that the choice of allocator does not rescue it.
 */

import { useEffect, useState } from 'react'
import { StatusPill } from '@/components/ui/DataMarks'
import { f, pct, sign } from '@/components/terminal/quant/format'
import { quantFetch } from '@/lib/quantApi'

interface RiskMetric {
  value: number | null
  method: string
  observations: number
  caveat?: string | null
}

interface PortfolioView {
  status: string
  detail?: string
  as_of?: string
  method?: string
  allocation?: {
    method: string
    feasible: boolean
    gross_exposure: number
    net_exposure: number
    names: number
    max_weight: number
    effective_names: number
    diagnostics?: Record<string, unknown>
    violations?: string[]
    notes?: string[]
  }
  weights?: Array<{
    symbol: string; weight: number; side: string
    signal: number | null; risk_share: number | null
  }>
  risk?: {
    metrics: Record<string, RiskMetric>
    exposure?: Record<string, number>
    concentration?: Record<string, number | string | null>
    turnover?: Record<string, number | string>
    risk_contributions?: Array<{
      symbol: string; weight: number; marginal: number; component: number; share: number
    }>
  }
  cost?: {
    breakdown?: Record<string, number>
    waterfall?: Record<string, number | boolean | string[]>
    assumptions?: Record<string, number | string>
  }
  units?: string
  disclaimer?: string
}

const METHODS = [
  'risk_parity', 'equal_weight', 'inverse_volatility', 'minimum_variance',
  'maximum_diversification', 'mean_variance', 'min_cvar_heuristic',
]

const WATERFALL_STEPS: Array<[string, string]> = [
  ['gross', 'Gross'],
  ['after_commission', 'After commission'],
  ['after_spread', 'After spread'],
  ['after_slippage', 'After slippage'],
  ['net', 'Net (after impact)'],
]

export default function PortfolioRisk({
  experimentId,
  modelId,
}: {
  experimentId: string
  modelId: string
}) {
  const [method, setMethod] = useState('risk_parity')
  const [view, setView] = useState<PortfolioView | null>(null)
  const [busy, setBusy] = useState(true)

  // The state update lives inside the async body, not in the effect's
  // synchronous path: setting state synchronously in an effect triggers a
  // cascading render, which React's lint rule flags for good reason.
  useEffect(() => {
    let live = true
    void (async () => {
      setBusy(true)
      const r = await quantFetch<PortfolioView>(
        `/api/quant/portfolio?experiment_id=${encodeURIComponent(experimentId)}` +
          `&model_id=${encodeURIComponent(modelId)}&method=${encodeURIComponent(method)}`,
      )
      if (!live) return
      setView(r.ok ? r.data : { status: 'unavailable', detail: r.message })
      setBusy(false)
    })()
    return () => { live = false }
  }, [experimentId, modelId, method])

  if (busy && !view) return <p className="body-copy u-note">Constructing the book…</p>
  if (!view || view.status !== 'ok') {
    return (
      <p className="body-copy u-note">
        {view?.detail ?? 'Portfolio construction is unavailable for this experiment.'}
      </p>
    )
  }

  const a = view.allocation!
  const risk = view.risk!
  const waterfall = view.cost?.waterfall ?? {}
  const flips = Boolean(waterfall.sign_flips)

  return (
    <>
      <div className="qp-controls">
        <label htmlFor="qp-method" className="u-note">Allocator</label>
        <select
          id="qp-method"
          className="qi-input qp-select"
          value={method}
          onChange={(e) => setMethod(e.target.value)}
        >
          {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <StatusPill tone={a.feasible ? 'accent' : 'warn'}
                    label={a.feasible ? 'CONSTRAINTS MET' : 'INFEASIBLE'} />
        <span className="u-note">as of {view.as_of}</span>
      </div>

      <dl className="qi-metrics">
        <div><dt>gross</dt><dd className="num">{f(a.gross_exposure, 3)}</dd></div>
        <div><dt>net</dt><dd className="num">{sign(a.net_exposure, 3)}</dd></div>
        <div><dt>names</dt><dd className="num">{a.names}</dd></div>
        <div><dt>effective N</dt><dd className="num">{f(a.effective_names, 1)}</dd></div>
        <div><dt>max weight</dt><dd className="num">{pct(a.max_weight)}</dd></div>
        <div><dt>turnover</dt><dd className="num">{f(risk.turnover?.one_way as number, 3)}</dd></div>
      </dl>

      {!!a.violations?.length && (
        <p className="body-copy u-note">
          Constraint violations: <strong>{a.violations.join(', ')}</strong>
        </p>
      )}

      {/* ── cost waterfall ── */}
      <h4 className="qr-subhead">Cost waterfall — where the sign changes</h4>
      <div className="qp-waterfall">
        {WATERFALL_STEPS.map(([key, label]) => {
          const value = Number(waterfall[key] ?? 0)
          return (
            <div key={key} className={`qp-step ${value < 0 ? 'qp-step--neg' : ''}`}>
              <span className="qp-step__label">{label}</span>
              <span className="qp-step__value num">{sign(value, 6)}</span>
            </div>
          )
        })}
      </div>
      <p className="body-copy u-note">
        {flips ? (
          <><strong>The sign flips between gross and net.</strong>{' '}</>
        ) : null}
        Each layer is peeled off separately — cheapest and most certain first,
        most model-dependent last — so a reader can stop at whichever assumption
        they are willing to believe. Half-spread is{' '}
        <strong>{String(view.cost?.assumptions?.half_spread_source ?? 'assumed')}</strong>.
      </p>

      {/* ── risk, with methods ── */}
      <h4 className="qr-subhead">Risk — every metric names its method</h4>
      <div className="ml-scroll">
        <table className="data-table qr-table qr-table--narrow">
          <thead>
            <tr><th>metric</th><th className="num">value</th><th>method</th><th className="num">obs</th></tr>
          </thead>
          <tbody>
            {Object.entries(risk.metrics).map(([name, m]) => (
              <tr key={name}>
                <td className="qr-model">{name}</td>
                <td className="num">{m.value === null ? '—' : f(m.value, 5)}</td>
                <td className="u-note">
                  {m.method}
                  {m.caveat && <><br /><em className="qp-caveat">{m.caveat}</em></>}
                </td>
                <td className="num">{m.observations}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="body-copy u-note">
        Historical and parametric figures are reported <strong>separately</strong> and
        never averaged: they answer the same question under different assumptions,
        and on this data they disagree.
      </p>

      {/* ── weights + risk contribution ── */}
      <h4 className="qr-subhead">Book — largest positions by weight</h4>
      <div className="ml-scroll">
        <table className="data-table qr-table qr-table--narrow">
          <thead>
            <tr>
              <th>symbol</th><th>side</th><th className="num">weight</th>
              <th className="num">signal</th><th className="num">risk share</th>
            </tr>
          </thead>
          <tbody>
            {view.weights?.slice(0, 15).map((w) => (
              <tr key={w.symbol}>
                <td className="qr-model">{w.symbol}</td>
                <td className="u-note">{w.side}</td>
                <td className={`num ${w.weight < 0 ? 'ml-neg' : ''}`}>{sign(w.weight, 4)}</td>
                <td className="num">{sign(w.signal, 4)}</td>
                <td className="num">{pct(w.risk_share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="body-copy u-note">
        <strong>Risk share</strong> is the position&apos;s component contribution to
        portfolio volatility, divided by total. Components sum to portfolio
        volatility by construction — asserted in the risk engine, because a
        contribution table that does not add up is the usual symptom of a
        misaligned index. Concentration:{' '}
        <strong>{String(risk.concentration?.effective_names ?? '—')}</strong>{' '}
        effective names from {String(risk.concentration?.names ?? '—')} holdings.
      </p>

      <div className="qp-disclaimer">
        <StatusPill tone="warn" label="ILLUSTRATION — NOT A RECOMMENDATION" />
        <p className="body-copy u-note">{view.disclaimer}</p>
        <p className="body-copy u-note">{view.units}</p>
      </div>
    </>
  )
}
