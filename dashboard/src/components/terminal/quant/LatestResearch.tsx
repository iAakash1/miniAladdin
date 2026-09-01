'use client'

/**
 * What the newest completed study concluded, shown wherever a *served* model is.
 *
 * The Models workspace serves EXP-006, correctly — it is the only artifact that
 * exists. But a reader there had no way to learn that a later study has since
 * run and concluded, which quietly implies EXP-006 is the current state of the
 * research. It is not; it is the current state of *deployment*, and the two
 * diverged the moment EXP-007 finished.
 *
 * This strip closes that gap in the honest direction. It reports that the newer
 * study produced no replacement and names the reasons, so the served model does
 * not inherit the credibility of research it was not part of.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { quantFetch } from '@/lib/quantApi'
import {
  Metric, MetricGrid, Panel, StateBlock, signed,
} from '@/components/terminal/primitives'
import type { SelectionState } from './searchTypes'

const EXPERIMENT = 'EXP-007'

export default function LatestResearch() {
  const [state, setState] = useState<SelectionState | null>(null)
  const [failed, setFailed] = useState<{ message: string; remedy: string } | null>(null)

  useEffect(() => {
    let live = true
    quantFetch<SelectionState>(`/api/quant/selection/${EXPERIMENT}`)
      .then((r) => {
        if (!live) return
        if (r.ok) setState(r.data)
        else setFailed({ message: r.message, remedy: r.remedy })
      })
      .catch(() => {
        if (live) {
          setFailed({
            message: 'The request never reached a server.',
            remedy: 'Usually the backend is asleep or mid-rollout. Retry shortly.',
          })
        }
      })
    return () => { live = false }
  }, [])

  if (failed) {
    return (
      <Panel title="Latest research" subtitle={EXPERIMENT} status="UNAVAILABLE" statusTone="warn">
        <StateBlock
          kind="offline"
          what={`the ${EXPERIMENT} selection verdict`}
          why={`${failed.message} ${failed.remedy} The served model's own evidence below is read from a committed artifact and is unaffected.`}
        />
      </Panel>
    )
  }

  if (!state) {
    return (
      <Panel title="Latest research" subtitle={EXPERIMENT}>
        <StateBlock kind="loading" what={`the ${EXPERIMENT} selection verdict`} />
      </Panel>
    )
  }

  if (!state.available || !state.verdict) {
    return (
      <Panel title="Latest research" subtitle={EXPERIMENT} status="NOT SELECTED" statusTone="muted">
        <StateBlock
          kind="empty"
          what={`a verdict for ${EXPERIMENT}`}
          why={state.detail ?? 'The search completed but candidate selection has not been run.'}
        />
      </Panel>
    )
  }

  // Prefer the current standard when the artifact predates it, so the count
  // shown matches the gates displayed underneath it.
  const verdict = state.current_standard ?? state.verdict
  const { selected } = state
  const cid = selected?.config_id
  const economics = cid ? state.economics?.[cid] : undefined
  const sig = cid ? state.significance?.[cid] : undefined
  const dsr = sig?.deflated_sharpe
  const pbo = state.probability_of_backtest_overfitting
  const mt = state.multiple_testing

  const num = (v: unknown, d = 3) =>
    typeof v === 'number' ? v.toFixed(d) : '—'

  return (
    <Panel
      title="Latest research"
      subtitle={`${EXPERIMENT} · ${selected?.family ?? '—'}`}
      status={verdict.status}
      statusTone={verdict.passed ? 'pass' : 'fail'}
      source="artifacts/experiments/EXP-007/final_selection.json"
      asOf={state.git_commit ? `commit ${state.git_commit.slice(0, 12)}` : undefined}
    >
      <p className="body-copy u-note" style={{ marginTop: 0 }}>
        {verdict.passed ? (
          <>Every predeclared gate passed. This is a development candidate, not a
          production model — the holdout is untouched and promotion remains blocked.</>
        ) : (
          <>
            The newest completed study did <strong>not</strong> produce a replacement for
            the served model. It failed {verdict.failed.length} of {verdict.gates.length}{' '}
            gates: {verdict.failed.map((g, i) => (
              <span key={g}>{i > 0 ? ', ' : ''}<code>{g}</code></span>
            ))}. The model below remains what is deployed, and remains experimental.
          </>
        )}
      </p>

      <MetricGrid>
        <Metric
          label="net Sharpe"
          value={signed(economics?.net_sharpe as number | undefined, 3)}
          method="after commission, 10 bp assumed half-spread, slippage"
          status={(economics?.net_sharpe as number ?? -1) > 0 ? 'pass' : 'fail'}
        />
        <Metric
          label="IC t-stat"
          value={signed(economics?.ic_t_stat as number | undefined, 2)}
          method={`search-size bar ${num(mt?.expected_max_abs_t_under_null, 2)}`}
          status={
            (economics?.ic_t_stat as number ?? 0) >
            (mt?.expected_max_abs_t_under_null ?? Infinity) ? 'pass' : 'fail'
          }
        />
        <Metric
          label="deflated Sharpe p"
          value={num(dsr?.deflated_probability, 4)}
          method="needs > 0.95 · Bailey & López de Prado"
          status={(dsr?.deflated_probability ?? 0) > 0.95 ? 'pass' : 'fail'}
        />
        <Metric
          label="PBO"
          value={num(pbo?.pbo, 3)}
          method="needs ≤ 0.20 · CSCV"
          status={(pbo?.pbo ?? 1) <= 0.2 ? 'pass' : 'fail'}
        />
        <Metric
          label="trials"
          value={mt?.cumulative_trials ? mt.cumulative_trials.toLocaleString() : '—'}
          method="cumulative across every study on these folds"
        />
        <Metric
          label="turnover"
          value={num(economics?.annualised_turnover, 1)}
          unit="×"
          method="annualised, one-way"
          status={(economics?.annualised_turnover as number ?? 99) <= 30 ? 'warn' : 'fail'}
        />
      </MetricGrid>

      <p className="body-copy u-note">
        <Link href="/quant#verdict">Full gate-by-gate verdict →</Link>
      </p>
    </Panel>
  )
}
