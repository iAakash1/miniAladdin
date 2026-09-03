'use client'

/**
 * How well the model has actually predicted this security.
 *
 * The rest of this workspace describes a security. This panel describes our
 * record against it, which is a different and less comfortable question, and it
 * belongs on the same page for exactly that reason — a score read without the
 * track record behind it is a number with no history.
 *
 * Four things it is built to keep visible.
 *
 * **A verdict travels with the reason it was reached.** The health label is
 * derived from information coefficient, hit rate and sample count against
 * thresholds documented in the metric glossary, and the reasons are listed
 * rather than summarised into a colour.
 *
 * **Failure modes are flagged, not buried.** Distribution drift, unstable
 * factor signs and a degenerate confusion matrix each get a line. "None
 * flagged" is stated explicitly too — an empty section reads as an absent check
 * rather than a passed one.
 *
 * **Recent skill is compared against the full window.** A model whose lifetime
 * IC is respectable and whose last rolling window is near zero has stopped
 * working, and a single lifetime average hides exactly that.
 *
 * **The limitations are the product, not a disclaimer.** One ticker is not a
 * portfolio; a costless long/flat test is not a tradeable result. Those bound
 * what the numbers above can support and are stated where they are read.
 */

import { useEffect, useMemo, useState } from 'react'

import { Panel, Prose, StateBlock, Strip } from '@/components/system'
import { TimeSeries } from '@/components/system/charts'
import { failureModes, overallHealth } from '@/lib/validationInsights'

interface Backtest {
  ticker: string
  scope_note?: string
  samples: number
  period?: { start: string; end: string }
  ic: number | null
  baseline_12_1_ic?: number | null
  rolling_ic?: Array<{ date: string; ic: number }>
  recent?: { rolling_ic_last: number | null; verdict_flips_last6: number }
  hit_rate: number | null
  directional_samples?: number
  confusion_matrix?: Record<'long' | 'flat' | 'short', { up: number; down: number }>
  strategy?: Record<string, number | null>
  score_distribution?: Array<{ bin: string; count: number }>
  factor_diagnostics?: Record<string, { ic: number | null; sign_stability: number | null; samples: number }>
  prediction_drift_psi?: number | null
  psi_note?: string
  error?: string
}

const HEALTH_STATE = { pos: 'recorded', warn: 'stale', neg: 'blocked' } as const

export default function ModelValidation({ ticker }: { ticker: string }) {
  const [data, setData] = useState<Backtest | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/backtest/${encodeURIComponent(ticker)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Backtest) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [ticker])

  const health = useMemo(() => {
    if (!data) return null
    return overallHealth({
      ic: data.ic,
      hitRate: data.hit_rate,
      sharpe: (data.strategy?.sharpe ?? null) as number | null,
      samples: data.samples,
    })
  }, [data])

  const flags = useMemo(() => {
    if (!data) return []
    return failureModes({
      psi: data.prediction_drift_psi ?? null,
      factorDiagnostics: data.factor_diagnostics ?? {},
      confusionMatrix: data.confusion_matrix ?? { long: { up: 0, down: 0 }, flat: { up: 0, down: 0 }, short: { up: 0, down: 0 } },
      scoreDistribution: data.score_distribution ?? [],
    })
  }, [data])

  if (error) {
    return (
      <Panel title="Model record" state="unavailable">
        <StateBlock
          state="unavailable"
          title={`No validation could be read for ${ticker}`}
          detail={`Request failed: ${error}. Nothing is shown in its place.`}
        />
      </Panel>
    )
  }
  if (!data) return null
  if (data.error) {
    return (
      <Panel title="Model record" state="unavailable">
        <StateBlock state="unavailable" title={`Cannot validate ${ticker}`} detail={data.error} />
      </Panel>
    )
  }

  const recent = data.recent?.rolling_ic_last ?? null
  // A model whose lifetime average is respectable and whose latest window is
  // near zero has stopped working. The average alone hides exactly that.
  const decayed = recent !== null && data.ic !== null && recent < data.ic - 0.03

  return (
    <>
      <Panel
        title="Model record"
        subtitle={`against ${data.ticker}`}
        state={health ? HEALTH_STATE[health.tone] : 'unavailable'}
        badge={health?.label.toUpperCase()}
        badgeTone={health?.tone === 'pos' ? 'pass' : health?.tone === 'neg' ? 'fail' : 'warn'}
        asOf={data.period ? `${data.period.start} → ${data.period.end}` : undefined}
      >
        <Strip metrics={[
          { label: 'Information coefficient', value: data.ic, kind: 'ic' },
          { label: 'Baseline 12-1 IC', value: data.baseline_12_1_ic ?? null, kind: 'ic' },
          { label: 'Hit rate', value: data.hit_rate, kind: 'share' },
          { label: 'Samples', value: data.samples, kind: 'count' },
          { label: 'Sharpe', value: (data.strategy?.sharpe ?? null) as number | null, kind: 'sharpe' },
        ]} />

        {/* The verdict never travels without the reasons behind it. */}
        {health?.reasons.length ? (
          <ul className="sys-reasons">
            {health.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        ) : null}

        {data.scope_note ? <Prose size="tight" caution>{data.scope_note}</Prose> : null}
      </Panel>

      {data.rolling_ic?.length ? (
        <Panel
          title="Recent skill against the full window"
          state={decayed ? 'stale' : 'recorded'}
          badge={decayed ? 'RUNNING BELOW AVERAGE' : undefined}
          badgeTone="warn"
        >
          <TimeSeries
            series={[{ name: 'rolling IC', points: data.rolling_ic.map((p) => ({ x: p.date, y: p.ic })) }]}
            unit="rolling information coefficient"
            method="expanding walk-forward, recomputed weekly"
            kind="ic"
            zeroLine
            height={200}
          />
          <Strip metrics={[
            { label: 'Latest rolling IC', value: recent, kind: 'ic' },
            { label: 'Full window', value: data.ic, kind: 'ic' },
            { label: 'Verdict flips, last 6', value: data.recent?.verdict_flips_last6 ?? null, kind: 'count' },
          ]} />
          {decayed ? (
            <Prose caution>
              The most recent window is running materially below the lifetime
              average. A single lifetime figure would hide that, which is the
              reason both are shown together rather than one summarising the other.
            </Prose>
          ) : null}
        </Panel>
      ) : null}

      <Panel
        title="Failure modes"
        state={flags.length ? 'blocked' : 'recorded'}
        badge={flags.length ? `${flags.length} FLAGGED` : 'NONE FLAGGED'}
        badgeTone={flags.length ? 'fail' : 'pass'}
      >
        {flags.length ? (
          <ul className="sys-reasons sys-reasons--flagged">
            {flags.map((flag) => <li key={flag}>{flag}</li>)}
          </ul>
        ) : (
          // Stated rather than left empty. An absent section reads as a check
          // that was never run, not as one that passed.
          <Prose>
            No known failure mode is flagged for {data.ticker} over the tested
            window. Drift, factor sign stability and the confusion matrix were
            each checked.
          </Prose>
        )}
        {data.psi_note ? <Prose size="fine">{data.psi_note}</Prose> : null}
      </Panel>

      <Panel title="What this cannot tell you" state="recorded">
        <Prose>
          Beyond the scope stated with the verdict above, these bound what this
          panel supports:
        </Prose>
        <ul className="sys-reasons">
          <li>
            This validates one security at a time. It is not a portfolio-level
            backtest and says nothing about diversification.
          </li>
          <li>
            The long/flat strategy test assumes no transaction costs, no
            slippage, no taxes and no borrow fees. The costed figures are in the
            experiment&rsquo;s own backtest, not here.
          </li>
          <li>
            Signals recompute weekly on an expanding window. A live product
            re-scoring more often on newer data would not reproduce these numbers.
          </li>
        </ul>
      </Panel>
    </>
  )
}
