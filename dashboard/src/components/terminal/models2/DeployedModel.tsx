'use client'

/**
 * The deployed EXP-006 model, and inference against it.
 *
 * This is the part of the product most likely to be misread, so it is built
 * around three refusals.
 *
 * **It never renders a prediction without its status.** EXPERIMENTAL and
 * BLOCKED sit next to the number rather than in a footnote, and the units line
 * says the output is a cross-sectional rank — not a return, not a price, not
 * advice.
 *
 * **It never implies a live signal.** The feature snapshot is frozen and dated,
 * and its as-of date is rendered beside the prediction. A stale vector shown
 * without its date is indistinguishable from a live one.
 *
 * **It degrades rather than disappears.** The inference service is on a free
 * plan and will cold-start and time out. When it does, this renders the reason
 * and nothing else on the page is affected — the evidence is the product, and
 * the model is an annotation on it.
 */

import { useCallback, useEffect, useState } from 'react'

import { Metric, MetricGrid, Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { quantFetch } from '@/lib/quantApi'

interface DeployedModelInfo {
  status?: string
  registry_key?: string
  model_id?: string
  model_version?: string
  experiment_id?: string
  target?: string
  horizon_sessions?: number
  feature_count?: number
  training_cutoff?: string
  research_status?: string
  promotion_status?: string
  prediction_units?: string
  dataset_content_hash?: string
  artifact_sha256?: string
  promotion_blocked_by?: {
    gate?: string; required?: string; observed?: number | null; detail?: string
  }
  specification_metrics?: {
    mean_ic?: number; ic_t_stat?: number; gross_sharpe?: number; net_sharpe?: number
    alpha_t_stat?: number
    annualised_turnover?: number; half_spread_bps?: number; cumulative_trials?: number
    caveat?: string; source?: string
  }
  fit_scope?: { rows?: number; start?: string; end?: string; note?: string }
}

interface InferenceStatus {
  configured: boolean
  health?: {
    status?: string; model_loaded?: boolean; detail?: string; remedy?: string; error?: string
  }
  model?: DeployedModelInfo
}

interface Prediction {
  status: string
  detail?: string
  remedy?: string
  predictions?: Array<{
    symbol: string; prediction: number | null
    features_supplied: number; features_expected: number
  }>
  feature_as_of?: string
  prediction_units?: string
  model_id?: string
  experiment_id?: string
  research_status?: string
  promotion_status?: string
  not_covered?: string[]
}

export default function DeployedModel() {
  const [status, setStatus] = useState<InferenceStatus | null>(null)
  const [ticker, setTicker] = useState('AAPL')
  const [result, setResult] = useState<Prediction | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const r = await quantFetch<InferenceStatus>('/api/quant/inference/status')
        if (live) setStatus(r.ok ? r.data : { configured: false })
      } catch {
        if (live) setStatus({ configured: false })
      }
    })()
    return () => { live = false }
  }, [])

  const run = useCallback(async () => {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return
    setBusy(true)
    try {
      const r = await quantFetch<Prediction>(
        `/api/quant/inference/predict/${encodeURIComponent(symbol)}`,
      )
      setResult(r.ok ? r.data : { status: 'unavailable', detail: r.message, remedy: r.remedy })
    } finally {
      setBusy(false)
    }
  }, [ticker])

  const model = status?.model
  const live = Boolean(status?.configured && status?.health?.model_loaded)
  const spec = model?.specification_metrics

  return (
    <>
      <Panel
        title="Deployed model"
        subtitle={model?.registry_key ?? 'gradient_boosting@4.0:fwd_rank_21'}
        state="experimental"
        badge={`PROMOTION ${model?.promotion_status ?? 'BLOCKED'}`}
        badgeTone="fail"
        actions={<Status state={live ? 'live' : 'unavailable'} label={live ? 'SERVICE READY' : 'SERVICE UNAVAILABLE'} />}
      >
        {spec ? (
          <>
            <MetricGrid>
              <Metric label="IC" value={<Value value={spec.mean_ic} kind="ic" />} />
              <Metric label="IC t-stat" value={<Value value={spec.ic_t_stat} kind="tstat" />} />
              <Metric label="gross Sharpe" value={<Value value={spec.gross_sharpe} kind="sharpe" />} />
              <Metric label="net Sharpe" value={<Value value={spec.net_sharpe} kind="sharpe" />} tone="fail" />
              <Metric label="alpha t-stat" value={<Value value={spec.alpha_t_stat} kind="tstat" />} />
              <Metric label="turnover" value={<Value value={spec.annualised_turnover} kind="multiple" />} />
              <Metric label="trials" value={<Value value={spec.cumulative_trials} kind="count" />} />
            </MetricGrid>
            <Prose size="tight" caution>
              <strong>These describe the specification, not this artifact.</strong>{' '}
              {spec.caveat ?? ''} They were estimated from eight separate walk-forward
              fits; the deployed file is one fit of the same specification over the
              whole pre-holdout window.
            </Prose>
          </>
        ) : null}

        {model?.promotion_blocked_by ? (
          <div style={{ marginTop: 'var(--d-3)' }}>
            <StateBlock
              state="blocked"
              title={`Blocked — ${model.promotion_blocked_by.gate ?? 'a promotion gate'}`}
              detail={model.promotion_blocked_by.detail}
            >
              <Prose size="tight">
                Observed <Value value={model.promotion_blocked_by.observed} kind="sharpe" />,
                required {model.promotion_blocked_by.required}.
              </Prose>
            </StateBlock>
          </div>
        ) : null}

        <MetricGrid>
          <Metric label="experiment" value={model?.experiment_id ?? 'EXP-006'} />
          <Metric label="target" value={model?.target ?? 'fwd_rank_21'} />
          <Metric label="horizon" value={<Value value={model?.horizon_sessions ?? 21} kind="sessions" />} />
          <Metric label="features" value={<Value value={model?.feature_count ?? 27} kind="count" />} />
          <Metric label="training cutoff" value={model?.training_cutoff ?? '—'} />
          <Metric label="dataset hash" value={(model?.dataset_content_hash ?? '—').slice(0, 16)} />
        </MetricGrid>
      </Panel>

      <Panel
        title="Inference"
        subtitle="research only"
        state={live ? 'experimental' : 'unavailable'}
      >
        {!live ? (
          <StateBlock
            state="unavailable"
            title="No prediction is produced"
            detail={`${status?.health?.error ?? status?.health?.detail ?? 'The inference service is not configured.'} ${status?.health?.remedy ?? ''}`}
          >
            <Prose size="tight">
              The research evidence elsewhere on this page is read from local
              artifacts and is unaffected by this.
            </Prose>
          </StateBlock>
        ) : (
          <>
            <div className="sys-run">
              <label htmlFor="mi-ticker" className="sys-label">Ticker</label>
              <input
                id="mi-ticker"
                className="sys-input sys-mono"
                value={ticker}
                maxLength={10}
                onChange={(e) => setTicker(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void run() }}
                aria-label="Ticker symbol"
              />
              <button type="button" className="sys-btn" onClick={() => void run()} disabled={busy}>
                {busy ? 'scoring…' : 'Predict'}
              </button>
            </div>

            {result?.status === 'ok' && result.predictions?.length ? (
              <>
                {result.predictions.map((p) => (
                  <div key={p.symbol} style={{ marginTop: 'var(--d-3)' }}>
                    <Metric
                      label={`21-session cross-sectional rank · ${p.symbol}`}
                      value={<Value value={p.prediction} kind="rank" />}
                      lead
                    />
                    <MetricGrid>
                      <Metric label="model" value={`${result.model_id ?? '—'}@4.0`} />
                      <Metric label="experiment" value={result.experiment_id ?? '—'} />
                      <Metric label="features as of" value={result.feature_as_of ?? '—'} />
                      <Metric
                        label="features supplied"
                        value={`${p.features_supplied}/${p.features_expected}`}
                      />
                      <Metric label="status" value={result.research_status ?? '—'} />
                      <Metric label="promotion" value={result.promotion_status ?? '—'} />
                    </MetricGrid>
                  </div>
                ))}
                <Prose size="tight" caution>
                  <strong>This is not a buy or sell signal.</strong> The output is a
                  rank relative to the other 249 names in the universe over a
                  21-session horizon — not a return, not a price target, not
                  investment advice. It comes from a model whose net Sharpe is
                  negative at the assumed cost and which the registry refuses to
                  promote. Features are a frozen snapshot dated{' '}
                  {result.feature_as_of ?? 'an unstated date'}, not live market data.
                </Prose>
              </>
            ) : result ? (
              <StateBlock
                state="unavailable"
                title="No prediction produced"
                detail={result.detail}
              >
                {result.not_covered?.length ? (
                  <Prose size="tight">
                    Not in the snapshot universe: {result.not_covered.join(', ')}. The
                    universe is the top 250 US names by trailing dollar volume on the
                    snapshot date.
                  </Prose>
                ) : null}
              </StateBlock>
            ) : (
              <Prose size="tight">
                Enter a ticker from the top-250 universe to score it against the
                deployed research model.
              </Prose>
            )}
          </>
        )}
      </Panel>
    </>
  )
}
