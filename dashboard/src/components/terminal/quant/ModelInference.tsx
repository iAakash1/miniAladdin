'use client'

/**
 * Model intelligence and inference — the deployed EXP-006 model.
 *
 * This is the part of the page most likely to be misread, so it is built around
 * three refusals.
 *
 * **It never renders a prediction without its status.** `EXPERIMENTAL` and
 * `BLOCKED` sit next to the number, not in a footnote, and the units line says
 * the output is a cross-sectional rank — not a return, not a price, not advice.
 *
 * **It never implies a live signal.** The feature snapshot is frozen and dated;
 * its as-of date is rendered beside the prediction. A stale vector presented
 * without its date is indistinguishable from a live one.
 *
 * **It degrades rather than disappears.** The inference service is on a free
 * plan and will cold-start and time out. When it does, this renders the reason
 * and the rest of the research page is unaffected — the evidence is the product,
 * the model is an annotation on it.
 */

import { useCallback, useEffect, useState } from 'react'
import { StatusPill } from '@/components/ui/DataMarks'
import { f, sign } from '@/components/terminal/quant/format'
import { quantFetch } from '@/lib/quantApi'

interface DeployedModel {
  status?: string
  detail?: string
  remedy?: string
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
  model?: DeployedModel
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

export default function ModelInference() {
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
  const live = status?.configured && status?.health?.model_loaded
  const spec = model?.specification_metrics

  return (
    <>
      {/* ── model intelligence ── */}
      <div className="qi-card">
        <div className="qi-card__head">
          <div>
            <span className="label">Deployed model</span>
            <strong className="qr-model">
              {model?.registry_key ?? 'gradient_boosting@4.0:fwd_rank_21'}
            </strong>
          </div>
          <div className="qi-card__pills">
            <StatusPill tone={live ? 'accent' : 'muted'} label={live ? 'SERVICE READY' : 'SERVICE UNAVAILABLE'} />
            <StatusPill tone="warn" label={model?.research_status ?? 'EXPERIMENTAL'} />
            <StatusPill tone="neg" label={`PROMOTION ${model?.promotion_status ?? 'BLOCKED'}`} />
          </div>
        </div>

        {spec && (
          <>
            <dl className="qi-metrics">
              <div><dt>IC</dt><dd className="num">{sign(spec.mean_ic)}</dd></div>
              <div><dt>IC t-stat</dt><dd className="num">{sign(spec.ic_t_stat, 2)}</dd></div>
              <div><dt>gross Sharpe</dt><dd className="num">{sign(spec.gross_sharpe, 3)}</dd></div>
              <div className="qr-fail">
                <dt>net Sharpe</dt><dd className="num">{sign(spec.net_sharpe, 3)}</dd>
              </div>
              <div><dt>alpha t-stat</dt><dd className="num">{sign(spec.alpha_t_stat, 3)}</dd></div>
              <div><dt>turnover</dt><dd className="num">{f(spec.annualised_turnover, 1)}×</dd></div>
              <div><dt>trials</dt><dd className="num">{spec.cumulative_trials ?? '—'}</dd></div>
            </dl>
            <p className="body-copy u-note qi-caveat">
              <strong>These describe the specification, not this artifact.</strong>{' '}
              {spec.caveat ?? ''} They were estimated from eight separate walk-forward
              fits; the deployed file is one fit of the same specification over the whole
              pre-holdout window.
            </p>
          </>
        )}

        {model?.promotion_blocked_by && (
          <div className="qi-block">
            <span className="label">Why promotion is blocked</span>
            <p className="body-copy">
              <code>{model.promotion_blocked_by.gate}</code> — observed{' '}
              <strong className="num">{f(model.promotion_blocked_by.observed, 3)}</strong>,
              required {model.promotion_blocked_by.required}.
            </p>
            <p className="body-copy u-note">{model.promotion_blocked_by.detail}</p>
          </div>
        )}

        <dl className="qr-grid qr-grid--tight">
          <div><dt>experiment</dt><dd className="num">{model?.experiment_id ?? 'EXP-006'}</dd></div>
          <div><dt>target</dt><dd className="num">{model?.target ?? 'fwd_rank_21'}</dd></div>
          <div><dt>horizon</dt><dd className="num">{model?.horizon_sessions ?? 21} sessions</dd></div>
          <div><dt>features</dt><dd className="num">{model?.feature_count ?? 27}</dd></div>
          <div><dt>training cutoff</dt><dd className="num">{model?.training_cutoff ?? '—'}</dd></div>
          <div><dt>dataset hash</dt><dd className="num">{(model?.dataset_content_hash ?? '—').slice(0, 16)}</dd></div>
        </dl>
      </div>

      {/* ── inference ── */}
      <div className="qi-card">
        <div className="qi-card__head">
          <span className="label">Model inference</span>
          <StatusPill tone="warn" label="RESEARCH ONLY" />
        </div>

        {!live ? (
          <div className="qi-down">
            <p className="body-copy">
              The inference service is not reachable, so no prediction is produced.
            </p>
            <p className="body-copy u-note">
              {status?.health?.error ?? status?.health?.detail ?? 'Not configured.'}{' '}
              {status?.health?.remedy ?? ''} The research evidence above is read from
              local artifacts and is unaffected.
            </p>
          </div>
        ) : (
          <>
            <div className="qi-run">
              <label htmlFor="qi-ticker" className="u-note">Ticker</label>
              <input
                id="qi-ticker"
                className="qi-input"
                value={ticker}
                maxLength={10}
                onChange={(e) => setTicker(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && run()}
                aria-label="Ticker symbol"
              />
              <button type="button" className="btn btn--sm" onClick={run} disabled={busy}>
                {busy ? 'scoring…' : 'Predict'}
              </button>
            </div>

            {result?.status === 'ok' && result.predictions?.length ? (
              <>
                {result.predictions.map((p) => (
                  <div key={p.symbol} className="qi-result">
                    <div className="qi-result__value">
                      <span className="qi-result__num num">{sign(p.prediction, 4)}</span>
                      <span className="u-note">
                        21-session cross-sectional rank · {p.symbol}
                      </span>
                    </div>
                    <dl className="qr-grid qr-grid--tight">
                      <div><dt>model</dt><dd className="num">{result.model_id}@4.0</dd></div>
                      <div><dt>experiment</dt><dd className="num">{result.experiment_id}</dd></div>
                      <div><dt>features as of</dt><dd className="num">{result.feature_as_of}</dd></div>
                      <div>
                        <dt>features supplied</dt>
                        <dd className="num">{p.features_supplied}/{p.features_expected}</dd>
                      </div>
                      <div><dt>status</dt><dd className="num">{result.research_status}</dd></div>
                      <div><dt>promotion</dt><dd className="num">{result.promotion_status}</dd></div>
                    </dl>
                  </div>
                ))}
                <p className="body-copy u-note qi-disclaimer">
                  <strong>This is not a buy or sell signal.</strong> The output is a rank
                  relative to the other 249 names in the universe over a 21-session
                  horizon — not a return, not a price target, not investment advice. It
                  comes from a model whose net Sharpe is negative at the assumed cost and
                  which the registry refuses to promote. Features are a frozen snapshot
                  dated {result.feature_as_of}, not live market data.
                </p>
              </>
            ) : result ? (
              <div className="qi-down">
                <p className="body-copy">{result.detail ?? 'No prediction produced.'}</p>
                {!!result.not_covered?.length && (
                  <p className="body-copy u-note">
                    Not in the snapshot universe: {result.not_covered.join(', ')}. The
                    universe is the top 250 US names by trailing dollar volume on the
                    snapshot date.
                  </p>
                )}
              </div>
            ) : (
              <p className="body-copy u-note">
                Enter a ticker from the top-250 universe to score it against the deployed
                research model.
              </p>
            )}
          </>
        )}
      </div>
    </>
  )
}
