'use client'

/**
 * Quant Intelligence — the company-page panel that refuses to guess.
 *
 * This is the single place in the product where a research finding is most
 * likely to be mistaken for a recommendation. A number rendered next to a
 * ticker, on a page a user opened to decide something, reads as advice no
 * matter how it is captioned.
 *
 * So the panel is built around the refusal. It asks the API what the deployment
 * status is — read from the model registry, not from any leaderboard — and when
 * no model has been promoted it renders that fact rather than a prediction. It
 * has no fallback path that produces a number from a research artifact, because
 * a fallback is exactly how "experimental" becomes "the model says AAPL".
 *
 * When a model is eventually promoted, the shape below fills in from the same
 * endpoint. Nothing about this component has to be rewritten for that; that was
 * the point of building the empty state first.
 */

import { useEffect, useState } from 'react'

import { quantFetch } from '@/lib/quantApi'

interface SymbolView {
  symbol: string
  deployment_status: string
  message: string
  prediction: number | null
  model: string | null
  disclosure?: string
}

export default function QuantIntelligence({ symbol }: { symbol?: string }) {
  const [view, setView] = useState<SymbolView | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    // `Analysis.ticker` is optional upstream, and requesting
    // /api/quant/symbol/undefined would 422 on every render of a report that
    // never resolved a ticker. Render nothing instead.
    if (!symbol) return
    let live = true
    ;(async () => {
      try {
        const r = await quantFetch<SymbolView>(
          `/api/quant/symbol/${encodeURIComponent(symbol)}`,
        )
        if (!live) return
        if (r.ok) setView(r.data)
        else setFailed(true)
      } catch {
        if (live) setFailed(true)
      }
    })()
    return () => {
      live = false
    }
  }, [symbol])

  if (failed) return null
  if (!view) return null

  const served = view.deployment_status === 'PRODUCTION' && view.prediction !== null

  return (
    <div className="panel qi">
      <div className="qi__head">
        <span className="label">Quant intelligence</span>
        <span className={`qi__status qi__status--${served ? 'live' : 'none'}`}>
          {served ? view.deployment_status : 'NO VALIDATED MODEL'}
        </span>
      </div>

      {served ? (
        <div className="qi__prediction">
          <span className="num qi__value">{view.prediction}</span>
          <span className="u-note">{view.model}</span>
        </div>
      ) : (
        <>
          <p className="body-copy qi__message">{view.message}</p>
          <p className="body-copy u-note">{view.disclosure}</p>
          <p className="body-copy u-note qi__why">
            Five studies have been run and none has produced a model that clears the
            development gates — the best had a positive rank IC but a negative Sharpe
            before costs. Producing a number here anyway would be the most expensive
            thing this product could do. The research is on{' '}
            <a href="/quant">/quant</a>, labelled as research.
          </p>
        </>
      )}
    </div>
  )
}
