'use client'

/**
 * Model Intelligence — what the machine-learning layer measured, including the
 * measurements that argue against it.
 *
 * The design problem this page solves is not "show model performance". It is
 * the opposite: a leaderboard sorted by one metric is a marketing surface, and
 * a research tool whose UI only looks good when the answer is favourable is
 * not a research tool. Three decisions follow from that.
 *
 * **The verdict leads, and it is ordered worst-finding-first.** A model that
 * clears the significance bar but loses to transaction costs is headlined as
 * losing to costs. `NO STATISTICALLY USEFUL SIGNAL FOUND` is rendered in the
 * same weight as a positive result, not in an apologetic footnote.
 *
 * **Baselines are in the same table as learned models, marked but not
 * separated.** A baseline in its own section is a rhetorical baseline. When
 * momentum beats gradient boosting — which it often does — the reader should
 * see the two adjacent rows, not have to compare across panels.
 *
 * **Every number that would flatter a model is shown beside the number that
 * discounts it.** Mean IC next to its Newey-West t. Net Sharpe next to the
 * deflated-Sharpe probability and the experiment count it was selected from.
 * Gross next to net. The cost sweep instead of one convenient spread.
 *
 * When no study has been run the page says so and prints the command. It does
 * not compute a cheap approximation to have something to render, because a
 * reader cannot tell a placeholder from a result.
 */

import { useEffect, useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import Section from '@/components/ui/Section'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import EmptyState from '@/components/ui/EmptyState'
import ModelInference from '@/components/terminal/quant/ModelInference'
import EngineOffline from '@/components/terminal/quant/EngineOffline'
import LatestResearch from '@/components/terminal/quant/LatestResearch'
import { quantFetch, type QuantFailure } from '@/lib/quantApi'

// ── contracts ────────────────────────────────────────────────────────────────

interface Validity {
  valid: boolean
  reason?: string
  audit?: string
  surviving_models?: string[]
  surviving_note?: string
}

interface Overview {
  status: string
  /** Which study these numbers are. The page previously rendered a study it
   *  could not name, which is how it went on serving a voided one. */
  experiment_id?: string | null
  source_artifact?: string | null
  validity?: Validity
  reason?: string
  remediation?: string
  generated_at?: string
  git_commit?: string
  runtime_seconds?: number
  dataset?: {
    dataset_version?: string
    rows?: number
    symbols?: number
    dates?: number
    start?: string
    end?: string
    content_hash?: string
  }
  guards?: { passed?: boolean; total?: number; failed?: number; checks?: GuardCheck[] }
  universe?: {
    unique_members?: number
    snapshots?: number
    ever_exited?: number
    start?: string
    end?: string
    point_in_time?: boolean
    notes?: string[]
  }
  regime?: {
    method?: string
    distribution?: Record<string, number>
    current?: string | null
    agreement?: { normalised_mutual_information?: number | null; overlapping_dates?: number }
  }
  labels?: LabelHeadline[]
  feature_count?: number
  dependency_versions?: Record<string, string>
}

interface GuardCheck {
  check: string
  passed: boolean
  detail: string
}

interface LabelHeadline {
  label: string
  horizon_sessions: number
  best_model: string
  mean_ic: number | null
  ic_t_stat: number | null
  fold_ic_positive_rate: number | null
  experiments: number | null
  median_ic: number | null
  train_ic_gap: number | null
  net_sharpe: number | null
  alpha_significant: boolean | null
  deflated_sharpe_probability: number | null
  pbo: number | null
  verdict: string
}

interface ModelRow {
  model_id: string
  kind: 'baseline' | 'learned'
  folds: number
  mean_ic: number | null
  ic_t_stat: number | null
  ic_ir: number | null
  rmse_vs_zero: number | null
  directional_edge: number | null
  fold_ic_positive_rate: number | null
  train_mean_ic: number | null
  train_ic_gap: number | null
  backtest: Record<string, number | null>
  cost_sensitivity: Array<{
    half_spread_bps: number
    net_sharpe: number | null
    gross_sharpe: number | null
    net_cagr: number | null
    annualised_turnover: number | null
  }>
  factor_attribution: {
    alpha_annualised?: number | null
    alpha_t_stat?: number | null
    alpha_significant?: boolean | null
    betas?: Record<string, number>
    r_squared?: number | null
    verdict?: string
  }
  regime_performance: Array<{
    regime: string
    observations: number
    mean_ic?: number | null
    ic_t_stat?: number | null
    note?: string
  }>
  significance: {
    deflated_sharpe?: {
      observed_sharpe?: number
      deflated_probability?: number | null
      expected_max_sharpe_under_null?: number
      trials?: number
      significant?: boolean | null
    }
    minimum_track_record?: { required_periods?: number | null; observed_periods?: number; sufficient?: boolean }
  }
  explanation: {
    kind?: string
    description?: string
    caveat?: string
    top?: Array<[string, number]>
  }
}

interface LabelReport {
  status: string
  validity?: Validity
  reason?: string
  label?: string
  horizon_sessions?: number
  walk_forward?: {
    scheme?: string
    fold_count?: number
    holdout_start?: string | null
    holdout_end?: string | null
    embargo_sessions?: number
    label_horizon_sessions?: number
    folds?: Array<{
      index: number
      train_start: string
      train_end: string
      validation_start: string
      validation_end: string
      gap_sessions: number
    }>
  }
  fold_rows?: Array<{ index: number; train_rows: number; validation_rows: number }>
  experiment_distribution?: {
    experiments?: number
    best?: number
    median?: number
    worst?: number
    above_zero?: number
    note?: string
  }
  probability_of_backtest_overfitting?: { pbo?: number | null; interpretation?: string; note?: string }
  models?: ModelRow[]
}

// ── formatting ───────────────────────────────────────────────────────────────

const n4 = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(4) : '—'
const n2 = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—'
const pct = (v: number | null | undefined, digits = 1) =>
  typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(digits)}%` : '—'
const int = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString() : '—'

/** Significance at |t| > 2, rendered as a state rather than a colour alone. */
function tTone(t: number | null | undefined): StatusTone {
  if (typeof t !== 'number' || !Number.isFinite(t)) return 'muted'
  return Math.abs(t) > 2 ? 'pos' : 'muted'
}

/** A generalisation gap this large means the model fitted its training fold and
 *  carried none of it forward. 0.05 is roughly twice any validation IC observed
 *  here, so a gap above it is not a marginal difference. */
function gapIsSevere(gap: number | null | undefined): boolean {
  return typeof gap === 'number' && Number.isFinite(gap) && gap > 0.05
}

/** The verdict's own tone. A null result is neutral, never alarming — it is
 *  the expected outcome of an honest test, not a malfunction. */
function verdictTone(verdict: string): StatusTone {
  if (verdict.startsWith('NO STATISTICALLY USEFUL SIGNAL')) return 'muted'
  if (verdict.startsWith('Survives')) return 'pos'
  if (verdict.includes('not costs') || verdict.includes('does not beat')) return 'warn'
  return 'warn'
}

// ── view ─────────────────────────────────────────────────────────────────────

export default function ModelIntelligenceView() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [report, setReport] = useState<LabelReport | null>(null)
  const [label, setLabel] = useState<string>('')
  const [error, setError] = useState<QuantFailure | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    quantFetch<Overview>('/api/ml/overview')
      .then((r) => {
        if (!r.ok) throw r
        return r.data
      })
      .then((data: Overview) => {
        if (cancelled) return
        setOverview(data)
        const first = data.labels?.[0]?.label
        if (first) setLabel(first)
        setLoading(false)
      })
      .catch((e) => {
        if (cancelled) return
        setError(e as QuantFailure)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!label) return
    let cancelled = false
    quantFetch<LabelReport>(`/api/ml/labels/${label}`)
      .then((r) => {
        if (!r.ok) throw r
        return r.data
      })
      .then((data: LabelReport) => {
        if (!cancelled) setReport(data)
      })
      .catch(() => {
        if (!cancelled) setReport(null)
      })
    return () => {
      cancelled = true
    }
  }, [label])

  if (loading) return <p className="body-copy u-note">Reading study artifacts…</p>
  if (error) {
    return (
      <>
        <PageHeader
          eyebrow="Research"
          title="Model Intelligence"
          lede="The served specification and the evidence that keeps it experimental."
        />
        <EngineOffline failure={error} title="Model research API" onRetry={() => window.location.reload()} />
      </>
    )
  }

  if (!overview || overview.status !== 'available') {
    return (
      <>
        <PageHeader
          eyebrow="Research"
          title="Model Intelligence"
          lede="The served specification and the evidence that keeps it experimental."
        />
        <Section
          id="deployed-model"
          title="Deployed model"
          summary="served · experimental · promotion blocked"
          defaultOpen
        >
          <ModelInference />
        </Section>
        <EmptyState
          titleAs="h2"
          title="No study has been run"
          description={
            overview?.reason ??
            'The study artifact is absent. Nothing is estimated in its place: an approximation rendered where a walk-forward result belongs cannot be told apart from the real thing.'
          }
          action={
            <pre className="ml-command">
              {overview?.remediation ?? 'python -m scripts.quant.study --all-labels'}
            </pre>
          }
        />
      </>
    )
  }

  const dataset = overview.dataset ?? {}
  const guards = overview.guards ?? {}
  const universe = overview.universe ?? {}

  return (
    <>
      {overview.validity && !overview.validity.valid && (
        <div className="ml-retraction" role="alert">
          <StatusPill tone="neg" label="results void" />
          <div>
            <strong>This study was invalidated by a later audit.</strong>{' '}
            {overview.validity.reason}
            {overview.validity.surviving_models?.length ? (
              <>
                {' '}Unaffected and still valid:{' '}
                {overview.validity.surviving_models.map((m) => (
                  <code key={m}>{m}</code>
                ))}
                . {overview.validity.surviving_note}
              </>
            ) : null}{' '}
            The artifact is retained rather than deleted, because removing it would
            erase the multiple-testing exposure it created. See{' '}
            <code>{overview.validity.audit}</code>.
          </div>
        </div>
      )}

      <PageHeader
        eyebrow="Research"
        title="Model Intelligence"
        lede="Out-of-sample results for every model evaluated, with the numbers that argue against each one shown beside the numbers that flatter it."
        meta={
          <>
            <span>
              dataset <code>{dataset.dataset_version}</code>
            </span>
            <span>
              {int(dataset.rows)} rows · {int(dataset.symbols)} symbols · {int(dataset.dates)} dates
            </span>
            <span>
              {dataset.start} → {dataset.end}
            </span>
            <span>
              <StatusPill
                tone={guards.passed ? 'pos' : 'neg'}
                label={`guards ${(guards.total ?? 0) - (guards.failed ?? 0)}/${guards.total ?? 0}`}
              />
            </span>
          </>
        }
      />

      {/* What is DEPLOYED and what the research currently CONCLUDES are two
          different things, and they diverged when EXP-007 finished. Serving
          EXP-006 without saying so implies it is the current state of the
          research rather than the current state of deployment. */}
      <LatestResearch />

      <Section
        id="deployed-model"
        title="Deployed model"
        summary="served · experimental · promotion blocked"
        defaultOpen
      >
        <ModelInference />
      </Section>

      {/* ── headline verdicts ─────────────────────────────────────────── */}
      <div className="ml-verdicts">
        {(overview.labels ?? []).map((row) => (
          <button
            key={row.label}
            type="button"
            className={`ml-verdict${label === row.label ? ' ml-verdict--active' : ''}`}
            onClick={() => setLabel(row.label)}
            aria-pressed={label === row.label}
          >
            <div className="ml-verdict__head">
              <span className="ml-verdict__label">{row.label}</span>
              <span className="u-note">{row.horizon_sessions}d horizon</span>
            </div>
            <div className="ml-verdict__best">
              best: <strong>{row.best_model}</strong>
            </div>
            <div className="ml-verdict__stats">
              <span>
                IC <strong>{n4(row.mean_ic)}</strong>
              </span>
              <span>
                t <strong>{n2(row.ic_t_stat)}</strong>
              </span>
              <span>
                gap <strong>{n4(row.train_ic_gap)}</strong>
              </span>
              <span>
                of <strong>{row.experiments ?? '—'}</strong> tried
              </span>
            </div>
            <div className="ml-verdict__text">
              <StatusPill tone={verdictTone(row.verdict)} label={shortVerdict(row.verdict)} />
              <p>{row.verdict}</p>
            </div>
          </button>
        ))}
      </div>

      {/* ── the leaderboard ───────────────────────────────────────────── */}
      {report?.status === 'available' && (
        <Section
          id="ml-leaderboard"
          title={`Every model evaluated — ${report.label}`}
          /* The study is named from the artifact, not a literal. A page that
             cannot say which study it renders is how a voided one went on
             being served under these headings. */
          summary={`${report.models?.length ?? 0} configurations, none filtered`}
          defaultOpen
        >
          <p className="body-copy u-note">
            Sorted by out-of-sample mean rank IC. Nothing is removed: baselines sit in the
            same table as learned models because a baseline in its own panel is a
            rhetorical baseline. Three columns matter more than the sort order.{' '}
            <strong>gap</strong> is train IC minus validation IC — large and positive
            means the model memorised its training fold and carried nothing forward.{' '}
            <strong>rmse/zero above 1.00</strong> means it predicts magnitude worse than
            predicting zero, whatever its ordering does. <strong>folds +</strong> is the
            share of folds with a positive IC; a model at 0.05 in every fold is a
            different proposition from one averaging 0.05 out of +0.20 and −0.10.
          </p>
          <div className={`ml-scroll${report.validity && !report.validity.valid ? ' ml-void' : ''}`}>
            <table className="data-table ml-table">
              <thead>
                <tr>
                  <th>model</th>
                  <th className="num">val IC</th>
                  <th className="num">train IC</th>
                  <th className="num">gap</th>
                  <th className="num">NW t</th>
                  <th className="num">folds +</th>
                  <th className="num">rmse/zero</th>
                  <th className="num">gross SR</th>
                  <th className="num">net SR</th>
                  <th className="num">turnover</th>
                  <th className="num">alpha t</th>
                  <th className="num">DSR p</th>
                </tr>
              </thead>
              <tbody>
                {(report.models ?? []).map((m) => (
                  <tr key={m.model_id} className={m.kind === 'baseline' ? 'ml-row--baseline' : ''}>
                    <td>
                      <span className="ml-model">{m.model_id}</span>
                      {m.kind === 'baseline' && (
                        <span className="ml-tag">baseline</span>
                      )}
                    </td>
                    <td className="num">{n4(m.mean_ic)}</td>
                    <td className="num u-note">{n4(m.train_mean_ic)}</td>
                    <td className={`num${gapIsSevere(m.train_ic_gap) ? ' ml-neg' : ''}`}>
                      {n4(m.train_ic_gap)}
                    </td>
                    <td className="num">
                      <StatusPill tone={tTone(m.ic_t_stat)} label={n2(m.ic_t_stat)} />
                    </td>
                    <td className="num">{pct(m.fold_ic_positive_rate, 0)}</td>
                    <td className="num">{n2(m.rmse_vs_zero)}</td>
                    <td className="num">{n2(m.backtest?.gross_sharpe)}</td>
                    <td className="num">{n2(m.backtest?.net_sharpe)}</td>
                    <td className="num">{n2(m.backtest?.annualised_turnover)}</td>
                    <td className="num">
                      <StatusPill
                        tone={m.factor_attribution?.alpha_significant ? 'pos' : 'muted'}
                        label={n2(m.factor_attribution?.alpha_t_stat)}
                      />
                    </td>
                    <td className="num">
                      {n2(m.significance?.deflated_sharpe?.deflated_probability)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {report.experiment_distribution && (
            <div className="u-note ml-note">
              <strong>Selection context.</strong>{' '}
              {report.experiment_distribution.experiments} configurations evaluated; best IC{' '}
              {n4(report.experiment_distribution.best)}, median{' '}
              {n4(report.experiment_distribution.median)}, worst{' '}
              {n4(report.experiment_distribution.worst)},{' '}
              {report.experiment_distribution.above_zero} above zero.{' '}
              {report.experiment_distribution.note}
            </div>
          )}
        </Section>
      )}

      {/* ── walk-forward ──────────────────────────────────────────────── */}
      {report?.status === 'available' && report.walk_forward && (
        <Section
          id="ml-walkforward"
          title="Walk-forward design"
          summary={`${report.walk_forward.fold_count} folds · ${report.walk_forward.label_horizon_sessions}+${report.walk_forward.embargo_sessions} session gap`}
        >
          <p className="body-copy u-note">
            Purge removes the label horizon; embargo removes a further margin for serial
            correlation. They are separate because they answer separate questions. The
            holdout is not a fold — nothing in the validation package evaluates against it.
          </p>
          <div className="ml-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>fold</th>
                  <th>train</th>
                  <th className="num">gap</th>
                  <th>validate</th>
                  <th className="num">train rows</th>
                  <th className="num">val rows</th>
                </tr>
              </thead>
              <tbody>
                {(report.walk_forward.folds ?? []).map((f) => {
                  const rows = report.fold_rows?.find((r) => r.index === f.index)
                  return (
                    <tr key={f.index}>
                      <td>{f.index}</td>
                      <td className="mono">
                        {f.train_start} → {f.train_end}
                      </td>
                      <td className="num">{f.gap_sessions}</td>
                      <td className="mono">
                        {f.validation_start} → {f.validation_end}
                      </td>
                      <td className="num">{int(rows?.train_rows)}</td>
                      <td className="num">{int(rows?.validation_rows)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {report.walk_forward.holdout_start && (
            <div className="u-note ml-note">
              <strong>Untouched holdout:</strong> {report.walk_forward.holdout_start} →{' '}
              {report.walk_forward.holdout_end}. Reserved before any fold was generated and
              evaluated by nothing above.
            </div>
          )}
          {report.probability_of_backtest_overfitting?.pbo != null && (
            <div className="u-note ml-note">
              <strong>Probability of backtest overfitting:</strong>{' '}
              {n2(report.probability_of_backtest_overfitting.pbo)}.{' '}
              {report.probability_of_backtest_overfitting.interpretation}
            </div>
          )}
        </Section>
      )}

      {/* ── cost sensitivity ──────────────────────────────────────────── */}
      {report?.status === 'available' && (
        <Section
          id="ml-costs"
          title="Does it survive transaction costs?"
          summary="net Sharpe across spread assumptions"
        >
          <p className="body-copy u-note">
            The half-spread is <strong>assumed</strong>, not observed — the price dataset
            carries no bid/ask. A single net figure is therefore a claim about the
            assumption as much as about the strategy, so the whole sweep is shown.
          </p>
          <div className="ml-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>model</th>
                  <th className="num">gross SR</th>
                  <th className="num">1 bp</th>
                  <th className="num">5 bp</th>
                  <th className="num">10 bp</th>
                  <th className="num">20 bp</th>
                </tr>
              </thead>
              <tbody>
                {(report.models ?? [])
                  .filter((m) => m.cost_sensitivity?.length)
                  .map((m) => (
                    <tr key={m.model_id}>
                      <td className="ml-model">{m.model_id}</td>
                      <td className="num">{n2(m.cost_sensitivity[0]?.gross_sharpe)}</td>
                      {[1, 5, 10, 20].map((bps) => {
                        const row = m.cost_sensitivity.find((c) => c.half_spread_bps === bps)
                        const value = row?.net_sharpe
                        return (
                          <td
                            key={bps}
                            className={`num${typeof value === 'number' && value < 0 ? ' ml-neg' : ''}`}
                          >
                            {n2(value)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* ── regime ────────────────────────────────────────────────────── */}
      {report?.status === 'available' && (
        <Section
          id="ml-regime"
          title="Does it work in the regime we are in?"
          summary={overview.regime?.current ?? 'regime unknown'}
        >
          <p className="body-copy u-note">
            A model that earned its whole average in one volatility spike is not a
            constant-IC model. Regimes below `{overview.regime?.method}` boundaries are
            fixed constants, not fitted, so they cannot have been chosen to suit a result.
            A regime with too few observations reports its count and no metric.
          </p>
          {(report.models ?? [])
            .filter((m) => m.regime_performance?.length)
            .slice(0, 4)
            .map((m) => (
              <div key={m.model_id} className="ml-regime-block">
                <h3 className="h-panel ml-model">{m.model_id}</h3>
                <div className="ml-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>regime</th>
                        <th className="num">obs</th>
                        <th className="num">mean IC</th>
                        <th className="num">t</th>
                        <th>note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {m.regime_performance.map((r) => (
                        <tr key={r.regime}>
                          <td>{r.regime}</td>
                          <td className="num">{int(r.observations)}</td>
                          <td className="num">{n4(r.mean_ic)}</td>
                          <td className="num">{n2(r.ic_t_stat)}</td>
                          <td className="u-note">{r.note ?? ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
        </Section>
      )}

      {/* ── explanation ───────────────────────────────────────────────── */}
      {report?.status === 'available' && (
        <Section
          id="ml-explain"
          title="What the models attribute their output to"
          summary="model explanation — not a causal claim"
        >
          {(report.models ?? [])
            .filter((m) => m.explanation?.top?.length)
            .map((m) => (
              <div key={m.model_id} className="ml-explain">
                <div className="ml-explain__head">
                  <span className="ml-model">{m.model_id}</span>
                  <span className="ml-tag">{m.explanation.kind}</span>
                </div>
                <p className="u-note">{m.explanation.description}</p>
                <ul className="ml-explain__bars">
                  {(m.explanation.top ?? []).slice(0, 8).map(([name, value]) => (
                    <li key={name}>
                      <span className="ml-explain__name">{name}</span>
                      <span
                        className={`ml-explain__bar${value < 0 ? ' ml-explain__bar--neg' : ''}`}
                        style={{
                          width: `${Math.min(
                            100,
                            Math.abs(value) /
                              Math.max(
                                ...(m.explanation.top ?? []).map(([, v]) => Math.abs(v)),
                                1e-9,
                              ) *
                              100,
                          )}%`,
                        }}
                      />
                      <span className="num">{n4(value)}</span>
                    </li>
                  ))}
                </ul>
                <p className="ml-caveat">{m.explanation.caveat}</p>
              </div>
            ))}
        </Section>
      )}

      {/* ── provenance ────────────────────────────────────────────────── */}
      <Section
        id="ml-provenance"
        title="Where these numbers come from"
        summary={`${overview.universe?.unique_members ?? '—'} names ever eligible`}
      >
        <dl className="ml-prov">
          {/* Which study, first. Everything below describes it. */}
          <dt>Study</dt>
          <dd>
            <code>{overview.experiment_id ?? 'unnamed'}</code>
            {overview.source_artifact ? (
              <> · read from <code>{overview.source_artifact}</code></>
            ) : null}
            {overview.validity?.valid === false ? (
              <> · <strong>VOID</strong></>
            ) : null}
          </dd>
          <dt>Dataset</dt>
          <dd>
            <code>{dataset.dataset_version}</code> · content hash{' '}
            <code>{dataset.content_hash}</code>
          </dd>
          <dt>Universe</dt>
          <dd>
            {int(universe.unique_members)} unique members across {int(universe.snapshots)}{' '}
            monthly rebalances, {int(universe.ever_exited)} membership exits.{' '}
            {universe.point_in_time ? 'Point-in-time membership.' : 'NOT point-in-time.'}
          </dd>
          <dt>Guards</dt>
          <dd>
            <ul className="ml-guards">
              {(guards.checks ?? []).map((c) => (
                <li key={c.check}>
                  <StatusPill tone={c.passed ? 'pos' : 'neg'} label={c.check} />
                  <span className="u-note">{c.detail}</span>
                </li>
              ))}
            </ul>
          </dd>
          <dt>Reproducibility</dt>
          <dd>
            git <code>{overview.git_commit}</code> ·{' '}
            {Object.entries(overview.dependency_versions ?? {})
              .map(([k, v]) => `${k} ${v}`)
              .join(' · ')}
          </dd>
          <dt>Limitations</dt>
          <dd>
            <ul>
              {(universe.notes ?? []).map((note) => (
                <li key={note} className="u-note">
                  {note}
                </li>
              ))}
            </ul>
          </dd>
        </dl>
      </Section>
    </>
  )
}

/** A four-word reading for the pill; the full sentence sits beside it. */
function shortVerdict(verdict: string): string {
  if (verdict.startsWith('NO STATISTICALLY USEFUL SIGNAL')) return 'no signal found'
  if (verdict.startsWith('Survives')) return 'survives every test'
  if (verdict.includes('does not beat')) return 'loses to baseline'
  if (verdict.includes('not costs') || verdict.includes('survives significance but not costs'))
    return 'lost to costs'
  if (verdict.includes('explained by factor')) return 'explained by factors'
  if (verdict.includes('configurations tried')) return 'fails multiple-comparison'
  return 'see detail'
}
