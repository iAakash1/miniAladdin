'use client'

/**
 * Quant Research — the evidence, including the evidence against.
 *
 * The hard design constraint here is that this page must read the same whether
 * the research succeeded or failed. A quant surface that only looks impressive
 * when the numbers are good is a marketing surface wearing a lab coat, and the
 * temptation to build one is strongest exactly when the result is negative.
 *
 * Four decisions follow.
 *
 * **The deployment banner is first and comes from the registry, not the
 * leaderboard.** `NO PRODUCTION MODEL` is stated at full weight at the top of
 * the page. It is read from model-registry status, so no result on this page
 * can change it — only an actual promotion can.
 *
 * **Every verdict is computed server-side from the promotion gates.** The
 * labels (ROBUST / PROMISING / EXPERIMENTAL / OVERFIT / UNTRADEABLE / REJECTED)
 * are not editorial. Each renders with the gate table that produced it, so a
 * reader can see the arithmetic and disagree with it.
 *
 * **Regime rows never appear without their date counts.** A t-statistic on nine
 * dates is the single most cherry-pickable number this pipeline produces, so
 * the count sits in the same row and thin regimes render INSUFFICIENT rather
 * than a number.
 *
 * **Void experiments stay in the history.** Deleting EXP-002 would erase the
 * multiple-testing exposure that every later significance claim is discounted
 * against.
 */

import { useEffect, useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import Section from '@/components/ui/Section'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import EmptyState from '@/components/ui/EmptyState'

const API = process.env.NEXT_PUBLIC_API_URL ?? ''

// ── contracts ────────────────────────────────────────────────────────────────

interface Gate {
  observed: number | boolean | null
  required: string
  passed: boolean
}

interface Verdict {
  label: string
  reason: string
  gates: Record<string, Gate>
}

interface LeaderRow {
  model_id: string
  kind?: string
  mean_ic?: number | null
  ic_t_stat?: number | null
  train_mean_ic?: number | null
  train_ic_gap?: number | null
  fold_ic_positive_rate?: number | null
  gross_sharpe?: number | null
  net_sharpe?: number | null
  max_drawdown?: number | null
  annualised_turnover?: number | null
  cost_share_of_gross?: number | null
  deflated_sharpe_probability?: number | null
  beats_best_baseline?: boolean | null
  verdict: Verdict
}

interface ArmRow {
  arm: string
  families: string[]
  hypothesis: string
  skipped: boolean
  reason?: string
  feature_count: number
  best_model?: string | null
  best_ic?: number | null
  best_t?: number | null
  models: Array<{ model_id: string; mean_ic?: number | null; ic_t_stat?: number | null }>
}

interface Contrast {
  arm: string
  families_added: string[]
  mean_delta?: number | null
  median_delta?: number | null
  models_improved: number
  models_compared: number
}

interface RegimeRow {
  regime: string
  dates: number
  observations: number
  mean_ic?: number | null
  ic_t_stat?: number | null
}

interface Experiment {
  status: string
  detail?: string
  remedy?: string
  experiment_id?: string
  void?: boolean
  void_reason?: string
  definition?: Record<string, unknown>
  fingerprint?: string
  generated_at?: string
  git_commit?: string
  machine?: Record<string, unknown>
  runtime_seconds?: number
  dataset?: Record<string, unknown>
  universe?: Record<string, unknown>
  features_used?: string[]
  integrity?: { clean?: boolean; rows_compared?: number; columns_compared?: number; cutoffs?: string[] }
  negative_controls?: {
    controls?: Array<{ control: string; mean_ic: number; t_stat: number; blocking: boolean; passed: boolean; role?: string }>
    blocking_failed?: string[]
    interpretation?: string
  }
  holdout?: Record<string, unknown>
  regimes?: { distribution?: Record<string, number> }
  primary_target?: string
  leaderboard?: LeaderRow[]
  walk_forward_plan?: Record<string, unknown>
  fold_rows?: Array<Record<string, unknown>>
  cost_sensitivity?: Record<string, Array<{ half_spread_bps: number; net_sharpe?: number | null; cost_share_of_gross?: number | null }>>
  regime_performance?: Record<string, RegimeRow[]>
  probability_of_backtest_overfitting?: { pbo?: number | null; configurations?: number; aligned_periods?: number }
  experiment_distribution?: { experiments?: number; best?: number; median?: number; above_zero?: number }
  trials_used_for_correction?: number
  ablation?: { ran: boolean; arms?: ArmRow[]; contrasts?: Contrast[]; base_arm?: string; interpretation?: string }
}

interface Status {
  deployment_status: string
  message: string
  production: number
  candidates: number
  validated: number
  retired: number
  total_entries: number
  firewall?: { headline?: string; contract_armed?: boolean; window?: { start?: string | null; end?: string | null } }
}

interface ExperimentIndexRow {
  experiment_id: string
  void: boolean
  void_reason?: string | null
  status?: string
  objective?: string
  generated_at?: string
  dataset_version?: string
  rows?: number
  feature_count?: number
  cumulative_evaluations?: number
}

// ── formatting ───────────────────────────────────────────────────────────────

/** Every numeric formatter returns an em dash for null, never 0. A zero that
 *  means "not measured" is the most expensive lie a research UI can tell. */
const f = (v: number | null | undefined, d = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d)
const sign = (v: number | null | undefined, d = 4) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d)
const pct = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(0)}%`
const num = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d)
const int = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString()

const VERDICT_TONE: Record<string, StatusTone> = {
  ROBUST: 'pos',
  PROMISING: 'accent',
  EXPERIMENTAL: 'muted',
  OVERFIT: 'warn',
  UNTRADEABLE: 'warn',
  REJECTED: 'neg',
}

/** Below this many validation dates a regime reports its count and nothing else.
 *  Mirrors REGIME_MIN_DATES in scripts/quant/register_experiment.py. */
const REGIME_MIN_DATES = 200

// ── view ─────────────────────────────────────────────────────────────────────

export default function QuantResearchView() {
  const [status, setStatus] = useState<Status | null>(null)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [index, setIndex] = useState<ExperimentIndexRow[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const [s, x] = await Promise.all([
          fetch(`${API}/api/quant/status`).then((r) => r.json()),
          fetch(`${API}/api/quant/experiments`).then((r) => r.json()),
        ])
        if (!live) return
        setStatus(s)
        setIndex(x.experiments ?? [])
        const first = (x.experiments ?? []).find(
          (e: ExperimentIndexRow) => !e.void && e.status === 'complete',
        )
        setSelected(first?.experiment_id ?? null)
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : 'request failed')
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    if (!selected) return
    let live = true
    ;(async () => {
      try {
        const r = await fetch(`${API}/api/quant/experiments/${selected}`)
        const j = await r.json()
        if (live) setExperiment(r.ok ? j : { status: 'unavailable', detail: j.detail })
      } catch (e) {
        if (live) setError(e instanceof Error ? e.message : 'request failed')
      }
    })()
    return () => {
      live = false
    }
  }, [selected])

  if (loading) return <p className="body-copy u-note">Reading experiment artifacts…</p>
  if (error) {
    return (
      <EmptyState
        title="Quant research layer unreachable"
        description={error}
      />
    )
  }

  const armed = status?.firewall?.contract_armed
  const leaders = experiment?.leaderboard ?? []
  const learned = leaders.filter((r) => r.kind !== 'baseline')
  const best = learned.reduce<LeaderRow | null>(
    (acc, r) => (r.mean_ic != null && (!acc || (acc.mean_ic ?? -1) < r.mean_ic) ? r : acc),
    null,
  )

  return (
    <>
      <PageHeader
        eyebrow="Quantitative research"
        title="Quant"
        lede="Point-in-time research: what was measured, what it cost, and what it does not support."
      />

      {/* ── the banner that no result on this page can change ── */}
      <div className={`qr-banner qr-banner--${(status?.deployment_status ?? 'NO_MODEL').toLowerCase()}`}>
        <div className="qr-banner__head">
          <StatusPill
            tone={status?.deployment_status === 'PRODUCTION' ? 'pos' : 'neg'}
            label={status?.deployment_status ?? 'NO_MODEL'}
          />
          <strong>{status?.message}</strong>
        </div>
        <p className="body-copy u-note">
          Read from the model registry, not from any leaderboard below. A result on this
          page cannot promote a model; only a registry promotion can, and that requires
          evidence this research has not produced.
        </p>
        <dl className="qr-banner__stats">
          <div><dt>production</dt><dd className="num">{status?.production ?? 0}</dd></div>
          <div><dt>candidates</dt><dd className="num">{status?.candidates ?? 0}</dd></div>
          <div><dt>validated</dt><dd className="num">{status?.validated ?? 0}</dd></div>
          <div><dt>retired / void</dt><dd className="num">{status?.retired ?? 0}</dd></div>
        </dl>
      </div>

      {/* ── holdout ── */}
      <div className={`qr-holdout ${armed ? 'qr-holdout--armed' : ''}`}>
        <span className="qr-holdout__lock" aria-hidden>{armed ? '◉' : '⬛'}</span>
        <div>
          <strong>{status?.firewall?.headline ?? 'HOLDOUT LOCKED'}</strong>
          <p className="body-copy u-note">
            {status?.firewall?.window?.start
              ? `${status.firewall.window.start} → ${status.firewall.window.end}. `
              : ''}
            Single-use and untouched. The firewall refuses holdout-dated rows at fit time,
            not merely by convention — see src/quant/study/firewall.py.
          </p>
        </div>
      </div>

      {/* ── experiment selector ── */}
      <Section id="history" title="Experiment history" summary={`${index.length} recorded`} defaultOpen>
        <p className="body-copy u-note">
          Invalidated studies stay listed. Deleting one would erase the multiple-testing
          exposure that every later significance claim is discounted against.
        </p>
        <div className="qr-experiments">
          {index.map((e) => (
            <button
              key={e.experiment_id}
              type="button"
              className={`qr-exp ${selected === e.experiment_id ? 'qr-exp--active' : ''} ${e.void ? 'qr-exp--void' : ''}`}
              onClick={() => !e.void && e.status === 'complete' && setSelected(e.experiment_id)}
              disabled={e.void || e.status !== 'complete'}
            >
              <span className="qr-exp__id">{e.experiment_id}</span>
              {e.void ? (
                <span className="qr-exp__badge qr-exp__badge--void">VOID</span>
              ) : (
                <span className="qr-exp__meta">
                  {int(e.rows)} rows · {e.feature_count ?? '—'} features
                </span>
              )}
              {e.void && <span className="qr-exp__why">{e.void_reason}</span>}
            </button>
          ))}
        </div>
      </Section>

      {experiment?.status !== 'ok' ? (
        <EmptyState
          title="No completed experiment"
          description={experiment?.detail ?? 'Run an experiment to populate this page.'}
          action={experiment?.remedy ? <code className="qr-command">{experiment.remedy}</code> : undefined}
        />
      ) : (
        <>
          {/* ── model intelligence ── */}
          <Section
            id="models"
            title="Model intelligence"
            summary={`${leaders.length} models on ${experiment.primary_target}`}
            defaultOpen
          >
            {best && (
              <div className="qr-headline">
                <div className="qr-headline__label">
                  <span className="u-note">best learned model</span>
                  <strong className="qr-model">{best.model_id}</strong>
                  <StatusPill
                    tone={VERDICT_TONE[best.verdict.label] ?? 'muted'}
                    label={best.verdict.label}
                  />
                </div>
                <p className="body-copy">{best.verdict.reason}</p>
                <div className="qr-gates">
                  {Object.entries(best.verdict.gates).map(([name, gate]) => (
                    <div key={name} className={`qr-gate ${gate.passed ? 'qr-gate--pass' : 'qr-gate--fail'}`}>
                      <span className="qr-gate__name">{name}</span>
                      <span className="qr-gate__obs num">
                        {typeof gate.observed === 'boolean'
                          ? String(gate.observed)
                          : f(gate.observed as number, 3)}
                      </span>
                      <span className="qr-gate__req u-note">{gate.required}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="ml-scroll">
              <table className="data-table qr-table">
                <thead>
                  <tr>
                    <th>model</th>
                    <th>verdict</th>
                    <th className="num">val IC</th>
                    <th className="num">t</th>
                    <th className="num">train gap</th>
                    <th className="num">fold+</th>
                    <th className="num">gross SR</th>
                    <th className="num">net SR</th>
                    <th className="num">turnover</th>
                    <th className="num">cost %</th>
                    <th className="num">DSR p</th>
                  </tr>
                </thead>
                <tbody>
                  {leaders.map((r) => (
                    <tr key={r.model_id} className={r.kind === 'baseline' ? 'ml-row--baseline' : ''}>
                      <td className="qr-model">
                        {r.model_id}
                        {r.kind === 'baseline' && <span className="ml-tag">baseline</span>}
                      </td>
                      <td>
                        <StatusPill tone={VERDICT_TONE[r.verdict.label] ?? 'muted'} label={r.verdict.label} />
                      </td>
                      <td className="num">{sign(r.mean_ic)}</td>
                      <td className={`num ${(r.ic_t_stat ?? 0) >= 2 ? '' : 'ml-neg'}`}>{sign(r.ic_t_stat, 2)}</td>
                      <td className="num">{sign(r.train_ic_gap, 3)}</td>
                      <td className="num">{pct(r.fold_ic_positive_rate)}</td>
                      <td className={`num ${(r.gross_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(r.gross_sharpe, 2)}</td>
                      <td className={`num ${(r.net_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(r.net_sharpe, 2)}</td>
                      <td className="num">{num(r.annualised_turnover)}</td>
                      <td className="num">{pct(r.cost_share_of_gross)}</td>
                      <td className="num">{f(r.deflated_sharpe_probability, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="body-copy u-note">
              Baselines sit in the same table as learned models, marked but not separated.
              A baseline in its own panel is a rhetorical baseline.
            </p>
          </Section>

          {/* ── ablation ── */}
          {experiment.ablation?.ran && (
            <Section
              id="ablation"
              title="Feature-family ablation"
              summary={`${experiment.ablation.arms?.length ?? 0} pre-registered arms`}
            >
              <p className="body-copy u-note">{experiment.ablation.interpretation}</p>
              <div className="ml-scroll">
                <table className="data-table qr-table">
                  <thead>
                    <tr>
                      <th>arm</th>
                      <th>families</th>
                      <th className="num">features</th>
                      <th className="num">best IC</th>
                      <th className="num">t</th>
                      <th>hypothesis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {experiment.ablation.arms?.map((a) => (
                      <tr key={a.arm} className={a.arm === experiment.ablation?.base_arm ? 'qr-row--base' : ''}>
                        <td className="qr-model">{a.arm}</td>
                        <td className="u-note">{a.families.join(' + ')}</td>
                        <td className="num">{a.skipped ? '—' : a.feature_count}</td>
                        <td className="num">{a.skipped ? 'SKIPPED' : sign(a.best_ic)}</td>
                        <td className="num">{a.skipped ? '—' : sign(a.best_t, 2)}</td>
                        <td className="u-note qr-hypothesis">{a.skipped ? a.reason : a.hypothesis}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {!!experiment.ablation.contrasts?.length && (
                <>
                  <h4 className="qr-subhead">Does the source add information over the base?</h4>
                  <div className="qr-contrasts">
                    {experiment.ablation.contrasts.map((c) => {
                      const helps = (c.mean_delta ?? 0) > 0 && c.models_improved > c.models_compared / 2
                      return (
                        <div key={c.arm} className={`qr-contrast ${helps ? 'qr-contrast--pos' : 'qr-contrast--neg'}`}>
                          <div className="qr-contrast__head">
                            <strong>{c.families_added.join(', ') || c.arm}</strong>
                            <StatusPill
                              tone={helps ? 'pos' : 'neg'}
                              label={helps ? 'ADDS INFORMATION' : 'NO IMPROVEMENT'}
                            />
                          </div>
                          <dl className="qr-contrast__stats">
                            <div><dt>mean ΔIC</dt><dd className="num">{sign(c.mean_delta)}</dd></div>
                            <div><dt>median ΔIC</dt><dd className="num">{sign(c.median_delta)}</dd></div>
                            <div>
                              <dt>models improved</dt>
                              <dd className="num">{c.models_improved}/{c.models_compared}</dd>
                            </div>
                          </dl>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </Section>
          )}

          {/* ── leakage ── */}
          <Section
            id="integrity"
            title="Leakage controls"
            summary={experiment.integrity?.clean ? 'integrity CLEAN' : 'integrity FAILED'}
          
            
            >
            <dl className="qr-banner__stats">
              <div>
                <dt>truncation invariance</dt>
                <dd>{experiment.integrity?.clean ? 'CLEAN' : 'FAILED'}</dd>
              </div>
              <div><dt>rows compared</dt><dd className="num">{int(experiment.integrity?.rows_compared)}</dd></div>
              <div><dt>features compared</dt><dd className="num">{experiment.integrity?.columns_compared ?? '—'}</dd></div>
              <div><dt>cutoffs</dt><dd className="num">{experiment.integrity?.cutoffs?.length ?? 0}</dd></div>
            </dl>
            <div className="ml-scroll">
            <table className="data-table qr-table qr-table--narrow">
              <thead>
                <tr>
                  <th>negative control</th><th>role</th>
                  <th className="num">IC</th><th className="num">t</th><th>result</th>
                </tr>
              </thead>
              <tbody>
                {experiment.negative_controls?.controls?.map((c) => (
                  <tr key={c.control}>
                    <td className="qr-model">{c.control}</td>
                    <td className="u-note">{c.blocking ? 'blocking' : 'diagnostic'}</td>
                    <td className="num">{sign(c.mean_ic)}</td>
                    <td className="num">{sign(c.t_stat, 2)}</td>
                    <td>
                      <StatusPill
                        tone={c.passed ? 'pos' : c.blocking ? 'neg' : 'warn'}
                        label={c.passed ? 'PASS' : c.blocking ? 'FAIL' : 'FINDING'}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="body-copy u-note">{experiment.negative_controls?.interpretation}</p>
          </Section>

          {/* ── regimes ── */}
          {best && experiment.regime_performance?.[best.model_id] && (
            <Section
              id="regimes"
              title="Regime analysis"
              summary="every row carries its date count"
            
            
            >
              <p className="body-copy u-note">
                A regime below {REGIME_MIN_DATES} validation dates reports its count and no
                metric. A t-statistic on nine dates is the most cherry-pickable number this
                pipeline produces.
              </p>
              <div className="ml-scroll">
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr>
                    <th>regime</th><th className="num">dates</th><th className="num">obs</th>
                    <th className="num">IC</th><th className="num">t</th><th>evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.regime_performance[best.model_id].map((r) => {
                    const thin = r.dates < REGIME_MIN_DATES
                    return (
                      <tr key={r.regime} className={thin ? 'qr-row--thin' : ''}>
                        <td className="qr-model">{r.regime}</td>
                        <td className="num">{r.dates}</td>
                        <td className="num">{int(r.observations)}</td>
                        <td className="num">{thin ? '—' : sign(r.mean_ic)}</td>
                        <td className="num">{thin ? '—' : sign(r.ic_t_stat, 2)}</td>
                        <td>
                          <StatusPill
                            tone={thin ? 'muted' : 'accent'}
                            label={thin ? 'INSUFFICIENT' : 'sufficient'}
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              </div>
            </Section>
          )}

          {/* ── costs ── */}
          {best && experiment.cost_sensitivity?.[best.model_id] && (
            <Section id="costs" title="Cost sensitivity" summary={`${best.model_id}`}
            
            >
              <div className="ml-scroll">
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr><th className="num">half-spread</th><th className="num">net Sharpe</th><th className="num">cost share</th></tr>
                </thead>
                <tbody>
                  {experiment.cost_sensitivity[best.model_id].map((c) => (
                    <tr key={c.half_spread_bps}>
                      <td className="num">{c.half_spread_bps} bp</td>
                      <td className={`num ${(c.net_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(c.net_sharpe, 3)}</td>
                      <td className="num">{pct(c.cost_share_of_gross)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
              <p className="body-copy u-note">
                A strategy that only survives at zero cost has failed. Gross Sharpe is shown
                in the model table above: if it is negative, no cost assumption rescues it.
              </p>
            </Section>
          )}

          {/* ── overfitting ── */}
          <Section id="overfit" title="Overfitting diagnostics" summary="trial-count adjusted"
            
            >
            <dl className="qr-banner__stats">
              <div>
                <dt>PBO</dt>
                <dd className="num">{f(experiment.probability_of_backtest_overfitting?.pbo, 3)}</dd>
              </div>
              <div>
                <dt>configurations</dt>
                <dd className="num">{experiment.probability_of_backtest_overfitting?.configurations ?? '—'}</dd>
              </div>
              <div>
                <dt>cumulative trials</dt>
                <dd className="num">{experiment.trials_used_for_correction ?? '—'}</dd>
              </div>
              <div>
                <dt>population median IC</dt>
                <dd className="num">{sign(experiment.experiment_distribution?.median)}</dd>
              </div>
            </dl>
            <p className="body-copy u-note">
              Deflated Sharpe is computed against the CUMULATIVE trial count across every
              study ever run on these folds, not against this study&apos;s own count.
              Resetting it because the code changed is how multiple-testing bias is laundered.
            </p>
          </Section>

          {/* ── provenance ── */}
          <Section id="provenance" title="Data provenance" summary={String(experiment.dataset?.dataset_version ?? '')}
            
            >
            <dl className="qr-banner__stats qr-banner__stats--wide">
              <div><dt>dataset</dt><dd className="num">{String(experiment.dataset?.dataset_version ?? '—')}</dd></div>
              <div><dt>content hash</dt><dd className="num">{String(experiment.dataset?.content_hash ?? '—').slice(0, 16)}</dd></div>
              <div><dt>rows</dt><dd className="num">{int(experiment.dataset?.rows as number)}</dd></div>
              <div><dt>symbols</dt><dd className="num">{int(experiment.dataset?.symbols as number)}</dd></div>
              <div><dt>dates</dt><dd className="num">{int(experiment.dataset?.dates as number)}</dd></div>
              <div><dt>features used</dt><dd className="num">{experiment.features_used?.length ?? 0}</dd></div>
              <div><dt>git commit</dt><dd className="num">{experiment.git_commit?.slice(0, 12) ?? '—'}</dd></div>
              <div><dt>fingerprint</dt><dd className="num">{experiment.fingerprint ?? '—'}</dd></div>
              <div><dt>runtime</dt><dd className="num">{num(experiment.runtime_seconds, 0)}s</dd></div>
            </dl>
          </Section>
        </>
      )}
    </>
  )
}
