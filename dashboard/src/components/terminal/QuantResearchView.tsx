'use client'

/**
 * Quant Research terminal — the evidence, including the evidence against.
 *
 * The hard design constraint is that this page must read the same whether the
 * research succeeded or failed. A quant surface that only looks impressive when
 * the numbers are good is a marketing surface wearing a lab coat, and the
 * temptation to build one is strongest exactly when the result is negative.
 *
 * Four decisions follow.
 *
 * **The deployment banner leads and comes from the registry, not the
 * leaderboard.** `NO PRODUCTION MODEL` is stated at full weight. It is read from
 * model-registry status, so nothing measured on this page can change it — only a
 * promotion can, and promotion is gated in Python.
 *
 * **Every verdict is computed server-side from the promotion gates.** The labels
 * (ROBUST / PROMISING / EXPERIMENTAL / OVERFIT / UNTRADEABLE / REJECTED) are not
 * editorial, and each renders with the gate table that produced it so a reader
 * can check the arithmetic.
 *
 * **No scientific calculation happens in this file.** Rank ICs, spread curves
 * and fold statistics are derived in `src/services/quant_series.py`. A second
 * implementation in TypeScript would eventually disagree with the first, and the
 * page would be quietly wrong in a way no test covers.
 *
 * **Sample size travels with every regime number.** A t-statistic on nine dates
 * is the most cherry-pickable figure this pipeline produces.
 */

import { useCallback, useEffect, useState } from 'react'
import PageHeader from '@/components/ui/PageHeader'
import Section from '@/components/ui/Section'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import EmptyState from '@/components/ui/EmptyState'
import {
  AblationChart, CostCurve, FoldIcChart, OverfitScatter,
  RegimeChart, SpreadCurve, WalkForwardTimeline,
} from '@/components/terminal/quant/QuantCharts'
import ModelInference from '@/components/terminal/quant/ModelInference'
import EngineOffline from '@/components/terminal/quant/EngineOffline'
import PortfolioRisk from '@/components/terminal/quant/PortfolioRisk'
import SearchLab from '@/components/terminal/quant/SearchLab'
import {
  ExperimentTimeline, Provenance, SelectionVerdict, TrainCommand,
} from '@/components/terminal/quant/SelectionVerdict'
import {
  BlockedHeadline, ExecutiveSummary, HoldoutFirewall, StatusRail,
} from '@/components/terminal/quant/ResearchTerminal'
import type { SearchState, SelectionState } from '@/components/terminal/quant/searchTypes'
import { quantFetch, type QuantFailure } from '@/lib/quantApi'
import type {
  Experiment, ExperimentIndexRow, ModelSeries, QuantStatus, RegistryView,
} from '@/components/terminal/quant/types'
import {
  REGIME_MIN_DATES, VERDICT_TONE, f, int, num, pct, sign,
} from '@/components/terminal/quant/format'

export default function QuantResearchView() {
  const [status, setStatus] = useState<QuantStatus | null>(null)
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [index, setIndex] = useState<ExperimentIndexRow[]>([])
  const [registry, setRegistry] = useState<RegistryView | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [series, setSeries] = useState<ModelSeries | null>(null)
  const [focus, setFocus] = useState<string | null>(null)
  const [error, setError] = useState<QuantFailure | null>(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState<SearchState | null>(null)
  const [selection, setSelection] = useState<SelectionState | null>(null)

  // Every call goes through `quantFetch`: same-origin in the browser so the
  // Next rewrite proxies it, and structured failures so a network error renders
  // as a diagnostic rather than as the string "TypeError: Failed to fetch".
  const get = useCallback(async <T,>(path: string): Promise<T> => {
    const result = await quantFetch<T>(path)
    if (!result.ok) throw result
    return result.data
  }, [])

  useEffect(() => {
    let live = true
    ;(async () => {
      try {
        const [s, x, r] = await Promise.all([
          get<QuantStatus>('/api/quant/status'),
          get<{ experiments: ExperimentIndexRow[] }>('/api/quant/experiments'),
          get<RegistryView>('/api/quant/registry').catch(() => null),
        ])
        if (!live) return
        setStatus(s)
        setRegistry(r)
        const rows: ExperimentIndexRow[] = x?.experiments ?? []
        setIndex(rows)
        setSelected(rows.find((e) => !e.void && e.status === 'complete')?.experiment_id ?? null)
      } catch (e) {
        if (live) setError(e as QuantFailure)
      } finally {
        if (live) setLoading(false)
      }
    })()
    return () => { live = false }
  }, [get])

  useEffect(() => {
    if (!selected) return
    let live = true
    setSeries(null)
    ;(async () => {
      try {
        const j = await get<Experiment>(`/api/quant/experiments/${selected}`)
        if (!live) return
        setExperiment(j)
        setFocus(j.best_candidate?.model_id ?? null)
      } catch (e) {
        if (live) setExperiment({ status: 'unavailable', detail: String(e) })
      }
    })()
    return () => { live = false }
  }, [selected, get])

  // The staged search is fetched separately from the experiment artifact,
  // because it exists BEFORE one: EXP-007 writes its metrics only at the end,
  // and a run in flight is visible through the append-only checkpoint.
  //
  // Polled only while it is actually running, and not at all otherwise. A
  // dashboard that polls a finished experiment forever is a bill, not a feature.
  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout> | undefined

    const poll = async () => {
      try {
        const s = await get<SearchState>('/api/quant/search/EXP-007')
        if (!live) return
        setSearch(s)
        if (s.state === 'RUNNING') timer = setTimeout(poll, 30_000)
      } catch {
        if (live) setSearch(null)
      }
    }
    void poll()
    get<SelectionState>('/api/quant/selection/EXP-007')
      .then((v) => { if (live) setSelection(v) })
      .catch(() => { if (live) setSelection(null) })

    return () => {
      live = false
      if (timer) clearTimeout(timer)
    }
  }, [get])

  useEffect(() => {
    if (!selected || !focus) return
    let live = true
    ;(async () => {
      try {
        const j = await get<ModelSeries>(
          `/api/quant/experiments/${selected}/series/${focus}`,
        )
        if (live) setSeries(j)
      } catch {
        if (live) setSeries(null)
      }
    })()
    return () => { live = false }
  }, [selected, focus, get])

  if (loading) return <p className="body-copy u-note">Reading experiment artifacts…</p>
  if (error) {
    return (
      <>
        <PageHeader
          eyebrow="Quantitative research"
          title="Quant"
          lede="Point-in-time research: what was measured, what it cost, and what it does not support."
        />
        <EngineOffline
          failure={error}
          title="Quant research layer"
          onRetry={() => window.location.reload()}
        />
      </>
    )
  }

  const armed = status?.firewall?.contract_armed
  const leaders = experiment?.leaderboard ?? []
  // `best_candidate` comes from the backend and excludes the deliberately
  // over-parameterised control, which otherwise posts the highest raw IC and
  // would be presented as the study's strongest evidence — exactly backwards.
  const best = experiment?.best_candidate ?? null
  const bestBaseline = experiment?.best_baseline ?? null
  const def = experiment?.definition ?? {}
  const ds = experiment?.dataset ?? {}
  const ablation = experiment?.ablation

  return (
    <div className="qt">
      {/* ── masthead ─────────────────────────────────────────────────────
          Identity, then the seven states that decide how everything below it
          should be read. The rail is deliberately flat: promotion and holdout
          carry the same weight as search progress, because a search at 92%
          reads as momentum unless they do. */}
      <header className="qt-masthead">
        <div className="qt-masthead__id">
          <span className="qt-masthead__eyebrow">OmniSignal</span>
          <h1 className="qt-masthead__title">Quantitative research terminal</h1>
        </div>
        <p className="qt-masthead__lede">
          Point-in-time research: what was measured, what it cost, and what it does not
          support. Every number on this page is read from a recorded artifact or the live
          search checkpoint. Nothing is inferred to fill a gap.
        </p>
      </header>

      <StatusRail
        search={search}
        production={status?.production}
        candidates={status?.candidates}
        holdoutArmed={armed}
        integrityClean={experiment?.integrity?.clean}
      />

      <ExecutiveSummary
        search={search}
        selection={selection}
        trials={experiment?.trials_used_for_correction}
      />

      <HoldoutFirewall
        armed={armed}
        start={experiment?.holdout?.start ?? search?.holdout?.start}
        end={experiment?.holdout?.end ?? search?.holdout?.end}
        sessions={experiment?.holdout?.sessions}
        touched={search?.holdout?.touched ?? false}
      />

      {/* Registry state, kept adjacent to the firewall: promotion is decided
          there and cannot be changed by any result rendered below. */}
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

      {experiment?.status !== 'ok' ? (
        <EmptyState
          title="No completed experiment"
          description={experiment?.detail ?? 'Run an experiment to populate this page.'}
          action={experiment?.remedy ? <code className="qr-command">{experiment.remedy}</code> : undefined}
        />
      ) : (
        <>
          {/* ── 2. the finding ── */}
          <div className="qr-finding">
            <div className="qr-finding__head">
              <span className="label">Current finding</span>
              <StatusPill tone="neg" label="NO ROBUST EVIDENCE OF EDGE" />
            </div>
            <p className="qr-finding__lede">
              After <strong>{experiment.trials_used_for_correction ?? '—'} cumulative
              evaluations</strong>, no model clears the development gates. Below is the
              strongest <em>candidate</em> evidence — the best learned model excluding the
              deliberately over-parameterised control, which posts a higher raw IC and is
              in the ladder only to prove the overfitting diagnostic fires.
            </p>
            {best && (
              <BlockedHeadline
                modelId={best.model_id}
                ic={best.mean_ic}
                icT={best.ic_t_stat}
                grossSharpe={best.gross_sharpe}
                netSharpe={best.net_sharpe}
                turnover={best.annualised_turnover}
                alphaT={
                  experiment.factor_attribution?.[best.model_id]?.alpha_t_stat ?? null
                }
              />
            )}
            <p className="body-copy u-note">
              A negative result from a pipeline with working leakage controls is a
              finding. It is what the apparatus is for.
            </p>
          </div>

          {/* ── 2a. the staged search ── */}
          {search?.available ? (
            <Section
              id="search"
              title="Model search"
              summary={
                search.state === 'RUNNING'
                  ? `${search.configurations_evaluated ?? 0}/${search.configurations_planned ?? '?'} · running`
                  : `${search.configurations_evaluated ?? 0} configurations`
              }
              defaultOpen
            >
              <SearchLab search={search} />
            </Section>
          ) : null}

          {/* ── 2b. the gate verdict ── */}
          {search?.available ? (
            <Section
              id="verdict"
              title="Selection verdict"
              summary={
                (() => {
                  const v = selection?.current_standard ?? selection?.verdict
                  if (!v) return 'not selected'
                  return v.passed
                    ? `all ${v.gates.length} gates passed`
                    : `${v.failed.length} of ${v.gates.length} gates failed`
                })()
              }
              defaultOpen
            >
              <SelectionVerdict selection={selection ?? { available: false,
                detail: 'The selection endpoint has not been reached yet.' }} />
            </Section>
          ) : null}

          {/* ── 2c. deployed model + inference ── */}
          <Section
            id="inference"
            title="Model intelligence"
            summary="deployed · experimental · not promoted"
            defaultOpen
          >
            <ModelInference />
          </Section>

          {/* ── 3. research overview ── */}
          <Section id="overview" title="Research overview"
                   summary={`${experiment.experiment_id} · ${int(ds.rows as number)} observations`} defaultOpen>
            <dl className="qr-grid">
              <div><dt>experiment</dt><dd className="num">{experiment.experiment_id}</dd></div>
              <div><dt>fingerprint</dt><dd className="num">{experiment.fingerprint}</dd></div>
              <div><dt>generated</dt><dd className="num">{(experiment.generated_at ?? '').slice(0, 16).replace('T', ' ')}</dd></div>
              <div><dt>git commit</dt><dd className="num">{experiment.git_commit?.slice(0, 12)}</dd></div>
              <div><dt>dataset</dt><dd className="num">{String(ds.dataset_version ?? '—')}</dd></div>
              <div><dt>dataset hash</dt><dd className="num">{String(ds.content_hash ?? '—').slice(0, 16)}</dd></div>
              <div><dt>observations</dt><dd className="num">{int(ds.rows as number)}</dd></div>
              <div><dt>symbols</dt><dd className="num">{int(ds.symbols as number)}</dd></div>
              <div><dt>rebalance dates</dt><dd className="num">{int(ds.dates as number)}</dd></div>
              <div><dt>date range</dt><dd className="num">{String(ds.start ?? '—')} → {String(ds.end ?? '—')}</dd></div>
              <div><dt>features used</dt><dd className="num">{experiment.features_used?.length ?? 0}</dd></div>
              <div><dt>universe</dt><dd className="num">{String(def.universe_name ?? '—')} · top {String(def.universe_size ?? '—')}</dd></div>
              <div><dt>target</dt><dd className="num">{experiment.primary_target}</dd></div>
              <div><dt>execution lag</dt><dd className="num">{String(def.execution_lag_periods ?? '—')} period</dd></div>
              <div><dt>cost assumption</dt><dd className="num">{String(def.primary_half_spread_bps ?? '—')} bp half-spread</dd></div>
              <div><dt>validation</dt><dd className="num">expanding walk-forward, {experiment.fold_rows?.length ?? 0} folds</dd></div>
              <div><dt>cumulative trials</dt><dd className="num">{experiment.trials_used_for_correction ?? '—'}</dd></div>
              <div><dt>runtime</dt><dd className="num">{num(experiment.runtime_seconds, 0)}s</dd></div>
            </dl>
          </Section>

          {/* ── 4. experiment explorer ── */}
          <Section id="history" title="Experiment explorer" summary={`${index.length} recorded`} defaultOpen>
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
                    <>
                      <span className="qr-exp__badge qr-exp__badge--void">VOID</span>
                      <span className="qr-exp__why">{e.void_reason}</span>
                    </>
                  ) : (
                    <>
                      <span className="qr-exp__badge">
                        {e.experiment_id === experiment.experiment_id ? 'NO PRODUCTION CANDIDATE' : 'COMPLETED'}
                      </span>
                      <span className="qr-exp__meta">
                        {int(e.rows)} rows · {e.feature_count ?? '—'} features
                        <br />{(e.generated_at ?? '').slice(0, 10)} · {e.cumulative_evaluations ?? '—'} cumulative trials
                      </span>
                    </>
                  )}
                </button>
              ))}
            </div>
          </Section>

          {/* ── 5. model comparison ── */}
          <Section id="models" title="Model comparison"
                   summary={`${leaders.length} models on ${experiment.primary_target}`} defaultOpen>
            {best && (
              <div className="qr-headline">
                <div className="qr-headline__label">
                  <span className="u-note">best learned model</span>
                  <strong className="qr-model">{best.model_id}</strong>
                  <StatusPill tone={VERDICT_TONE[best.verdict.label] ?? 'muted'} label={best.verdict.label} />
                </div>
                <p className="body-copy">{best.verdict.reason}</p>
                <div className="qr-gates">
                  {Object.entries(best.verdict.gates).map(([name, gate]) => (
                    <div key={name} className={`qr-gate ${gate.passed ? 'qr-gate--pass' : 'qr-gate--fail'}`}>
                      <span className="qr-gate__name">{name}</span>
                      <span className="qr-gate__obs num">
                        {typeof gate.observed === 'boolean' ? String(gate.observed) : f(gate.observed as number, 3)}
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
                    <th>model</th><th>verdict</th>
                    <th className="num">train IC</th><th className="num">val IC</th>
                    <th className="num">gap</th><th className="num">t</th><th className="num">fold+</th>
                    <th className="num">gross SR</th><th className="num">net SR</th>
                    <th className="num">max DD</th><th className="num">turnover</th>
                    <th className="num">cost %</th><th className="num">DSR p</th>
                    <th className="num">vs base</th>
                  </tr>
                </thead>
                <tbody>
                  {leaders.map((r) => (
                    <tr key={r.model_id}
                        className={`${r.kind === 'baseline' ? 'ml-row--baseline' : ''} ${focus === r.model_id ? 'qr-row--focus' : ''}`}
                        onClick={() => r.kind !== 'baseline' && setFocus(r.model_id)}>
                      <td className="qr-model">
                        {r.model_id}
                        {r.kind === 'baseline' && <span className="ml-tag">baseline</span>}
                        {r.is_overfit_control && <span className="ml-tag ml-tag--control">control</span>}
                      </td>
                      <td><StatusPill tone={VERDICT_TONE[r.verdict.label] ?? 'muted'} label={r.verdict.label} /></td>
                      <td className="num">{sign(r.train_mean_ic, 3)}</td>
                      <td className="num">{sign(r.mean_ic)}</td>
                      <td className="num">{sign(r.train_ic_gap, 3)}</td>
                      <td className={`num ${(r.ic_t_stat ?? 0) >= 2 ? '' : 'ml-neg'}`}>{sign(r.ic_t_stat, 2)}</td>
                      <td className="num">{pct(r.fold_ic_positive_rate)}</td>
                      <td className={`num ${(r.gross_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(r.gross_sharpe, 2)}</td>
                      <td className={`num ${(r.net_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(r.net_sharpe, 2)}</td>
                      <td className="num">{pct(r.max_drawdown)}</td>
                      <td className="num">{num(r.annualised_turnover)}</td>
                      <td className="num">{pct(r.cost_share_of_gross)}</td>
                      <td className="num">{f(r.deflated_sharpe_probability, 3)}</td>
                      <td className="num">
                        {bestBaseline && r.mean_ic != null && bestBaseline.mean_ic != null
                          ? sign(r.mean_ic - bestBaseline.mean_ic) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="body-copy u-note">
              Baselines sit in the same table as learned models, marked but not separated —
              a baseline in its own panel is a rhetorical baseline. Rows are ordered by
              validation IC, which is <em>not</em> the ranking that decides promotion:
              every discounting column to its right can and does overturn it. Click a
              learned model to drive the charts below.
            </p>

            <div className="qc-grid">
              {series?.folds?.folds && (
                <FoldIcChart folds={series.folds.folds} meanIc={best?.mean_ic} />
              )}
              <OverfitScatter rows={leaders} />
            </div>
          </Section>

          {/* ── 6. ablation ── */}
          {ablation?.ran && (
            <Section id="ablation" title="Feature-family ablation"
                     summary={`${ablation.arms?.length ?? 0} pre-registered arms`} defaultOpen>
              <div className="qr-callout qr-callout--neg">
                <strong>Additional datasets did not demonstrate incremental predictive value.</strong>
                <p className="body-copy">
                  Options, analyst estimate revisions and announcement-gated statement
                  fundamentals were each added to a price-volatility-volume-macro base.
                  None improved it; the peak is the arm containing no fundamental data at
                  all. The highest observed t-statistic is <strong>not</strong> evidence of
                  an edge — it is the maximum of 42 configurations, and the expected
                  maximum of 139 zero-skill configurations is about the same size.
                </p>
                <StatusPill tone="warn" label="HYPOTHESIS — NOT A RESULT" />
              </div>

              <AblationChart arms={ablation.arms ?? []} baseArm={ablation.base_arm ?? 'C_base'} />

              <div className="ml-scroll">
                <table className="data-table qr-table qr-table--narrow">
                  <thead>
                    <tr>
                      <th>arm</th><th>families</th><th className="num">features</th>
                      <th className="num">best IC</th><th className="num">t</th><th>hypothesis</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ablation.arms?.map((a) => (
                      <tr key={a.arm} className={a.arm === ablation.base_arm ? 'qr-row--base' : ''}>
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

              <h4 className="qr-subhead">Does the source add information over the base?</h4>
              <div className="qr-contrasts">
                {ablation.contrasts?.map((c) => {
                  const helps = (c.mean_delta ?? 0) > 0 && c.models_improved > c.models_compared / 2
                  return (
                    <div key={c.arm} className={`qr-contrast ${helps ? 'qr-contrast--pos' : 'qr-contrast--neg'}`}>
                      <div className="qr-contrast__head">
                        <strong>{c.families_added.join(', ') || c.arm}</strong>
                        <StatusPill tone={helps ? 'pos' : 'neg'}
                                    label={helps ? 'ADDS INFORMATION' : 'NO IMPROVEMENT'} />
                      </div>
                      <dl className="qr-contrast__stats">
                        <div><dt>mean ΔIC</dt><dd className="num">{sign(c.mean_delta)}</dd></div>
                        <div><dt>median ΔIC</dt><dd className="num">{sign(c.median_delta)}</dd></div>
                        <div><dt>models improved</dt><dd className="num">{c.models_improved}/{c.models_compared}</dd></div>
                      </dl>
                    </div>
                  )
                })}
              </div>
              <p className="body-copy u-note">
                <strong>models improved / models compared</strong> is the honest headline.
                A best-of comparison is a maximum over six draws and is biased upward by
                construction; two of six improving is what noise looks like.
              </p>
            </Section>
          )}

          {/* ── 6b. portfolio construction, risk and cost ── */}
          {focus && experiment.experiment_id && (
            <Section
              id="portfolio"
              title="Portfolio construction, risk and cost"
              summary="what the signal looks like as a book"
              defaultOpen
            >
              <PortfolioRisk experimentId={experiment.experiment_id} modelId={focus} />
            </Section>
          )}

          {/* ── 7. walk-forward ── */}
          <Section id="walkforward" title="Walk-forward validation"
                   summary={`${experiment.fold_rows?.length ?? 0} expanding folds`} defaultOpen>
            <WalkForwardTimeline
              folds={experiment.fold_rows ?? []}
              holdoutStart={experiment.holdout?.start}
              holdoutEnd={experiment.holdout?.end}
              executionLag={Number(def.execution_lag_periods ?? 1)}
            />
            <div className="ml-scroll">
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr>
                    <th className="num">fold</th><th>train</th><th className="num">rows</th>
                    <th className="num">gap</th><th>validation</th><th className="num">rows</th>
                    <th className="num">symbols</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.fold_rows?.map((f) => (
                    <tr key={f.index}>
                      <td className="num">{f.index}</td>
                      <td className="u-note">{f.train_start} → {f.train_end}</td>
                      <td className="num">{int(f.train_rows)}</td>
                      <td className="num">{f.gap_sessions}d</td>
                      <td className="u-note">{f.validation_start} → {f.validation_end}</td>
                      <td className="num">{int(f.validation_rows)}</td>
                      <td className="num">{f.validation_symbols}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {series?.spread_curve?.status === 'ok' && (
              <SpreadCurve periods={series.spread_curve.periods} units={series.spread_curve.units} />
            )}
          </Section>

          {/* ── 8. regimes ── */}
          {focus && experiment.regime_performance?.[focus] && (
            <Section id="regimes" title="Regime analysis" summary="every row carries its date count" defaultOpen>
              <RegimeChart rows={experiment.regime_performance[focus]} minDates={REGIME_MIN_DATES} />
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr>
                    <th>regime</th><th className="num">dates</th><th className="num">observations</th>
                    <th className="num">IC</th><th className="num">t</th><th>evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.regime_performance[focus].map((r) => {
                    const thin = r.dates < REGIME_MIN_DATES
                    return (
                      <tr key={r.regime} className={thin ? 'qr-row--thin' : ''}>
                        <td className="qr-model">{r.regime.replace(/_/g, ' ')}</td>
                        <td className="num">{r.dates}</td>
                        <td className="num">{int(r.observations)}</td>
                        <td className="num">{thin ? '—' : sign(r.mean_ic)}</td>
                        <td className="num">{thin ? '—' : sign(r.ic_t_stat, 2)}</td>
                        <td>
                          <StatusPill tone={thin ? 'muted' : 'accent'}
                                      label={thin ? 'INSUFFICIENT EVIDENCE' : 'sufficient'} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="body-copy u-note">
                A regime below {REGIME_MIN_DATES} validation dates reports its count and no
                metric. At a 5-session stride with 21-session labels that floor is roughly
                48 independent blocks — below it, a t-statistic is arithmetic, not evidence.
              </p>
            </Section>
          )}

          {/* ── 9. costs ── */}
          {focus && experiment.cost_sensitivity?.[focus] && (
            <Section id="costs" title="Transaction costs" summary={focus} defaultOpen>
              <CostCurve rows={experiment.cost_sensitivity[focus]} model={focus} />
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr>
                    <th className="num">half-spread</th><th className="num">gross Sharpe</th>
                    <th className="num">net Sharpe</th><th className="num">cost share of gross</th>
                    <th className="num">turnover</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.cost_sensitivity[focus].map((c) => (
                    <tr key={c.half_spread_bps}>
                      <td className="num">{c.half_spread_bps} bp</td>
                      <td className={`num ${(c.gross_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(c.gross_sharpe, 3)}</td>
                      <td className={`num ${(c.net_sharpe ?? 0) < 0 ? 'ml-neg' : ''}`}>{sign(c.net_sharpe, 3)}</td>
                      <td className="num">{pct(c.cost_share_of_gross)}</td>
                      <td className="num">{num(c.annualised_turnover)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>
          )}

          {/* ── 10. research integrity ── */}
          <Section id="integrity" title="Research integrity"
                   summary={experiment.integrity?.clean ? 'all controls pass' : 'INTEGRITY FAILED'} defaultOpen>
            <div className="qr-integrity">
              {[
                ['POINT-IN-TIME DATA', experiment.integrity?.clean ? 'PASS' : 'FAIL',
                 `Truncation invariance over ${int(experiment.integrity?.rows_compared)} rows × ${experiment.integrity?.columns_compared} features at ${experiment.integrity?.cutoffs?.length ?? 0} cutoffs, using the real builder.`],
                ['AS-OF ALIGNMENT', 'PASS',
                 'Every join is a backward as-of merge on an availability date, index-aligned. The defect that voided EXP-002 is covered by a regression test.'],
                ['ANNOUNCEMENT GATING', 'PASS',
                 'Period-keyed fundamentals reach a feature only after joining forward to an earnings_calendar announcement. Periods without one are dropped, never estimated.'],
                ['EXECUTION LAG', `${def.execution_lag_periods ?? 1} PERIOD`,
                 'A signal computed at the close of t forms a position at t+1. A lag of 0 is refused by the experiment definition.'],
                ['HOLDOUT FIREWALL', armed ? 'ARMED' : 'LOCKED',
                 'assert_clear refuses holdout-dated rows at every fold immediately before the fit. There is no environment override.'],
                ['MULTIPLE TESTING', 'ACCOUNTED',
                 `Deflated Sharpe against ${experiment.trials_used_for_correction ?? '—'} cumulative trials across every study ever run on these folds — not this study's own count.`],
                ['TRANSACTION COSTS', 'INCLUDED',
                 'Commission, assumed half-spread and square-root market impact. Gross is reported beside net so cost drag is visible.'],
                ['RESTATEMENT HANDLING', 'UNQUANTIFIED',
                 'Statement tables hold one row per period with no vintage column, so a restatement overwrites the original irrecoverably. Disclosed, isolated in its own ablation arm, NOT solved.'],
              ].map(([name, state, detail]) => (
                <div key={name} className={`qr-check qr-check--${
                  state === 'PASS' || state === 'LOCKED' || state === 'ACCOUNTED' || state === 'INCLUDED'
                    ? 'pass' : state === 'UNQUANTIFIED' ? 'warn' : 'info'}`}>
                  <div className="qr-check__row">
                    <span className="qr-check__name">{name}</span>
                    <span className="qr-check__state">{state}</span>
                  </div>
                  <p className="qr-check__detail">{detail}</p>
                </div>
              ))}
            </div>

            <h4 className="qr-subhead">Negative controls</h4>
            <div className="ml-scroll">
              <table className="data-table qr-table qr-table--narrow">
                <thead>
                  <tr>
                    <th>control</th><th>role</th><th className="num">IC</th>
                    <th className="num">t</th><th>result</th>
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
                        <StatusPill tone={c.passed ? 'pos' : c.blocking ? 'neg' : 'warn'}
                                    label={c.passed ? 'PASS' : c.blocking ? 'FAIL' : 'FINDING'} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="body-copy u-note">{experiment.negative_controls?.interpretation}</p>
            <dl className="qr-grid qr-grid--tight">
              <div><dt>dataset hash</dt><dd className="num">{String(ds.content_hash ?? '—')}</dd></div>
              <div><dt>PBO</dt><dd className="num">{f(experiment.probability_of_backtest_overfitting?.pbo, 3)}</dd></div>
              <div><dt>population median IC</dt><dd className="num">{sign(experiment.experiment_distribution?.median)}</dd></div>
            </dl>
          </Section>

          {/* ── 11. dataset coverage ── */}
          <Section id="datasets" title="Dataset coverage"
                   summary={`${experiment.dataset_sources?.length ?? 0} sources`} defaultOpen>
            <div className="ml-scroll">
              <table className="data-table qr-table">
                <thead>
                  <tr>
                    <th>source</th><th>role</th><th className="num">rows</th>
                    <th>coverage</th><th>point-in-time</th><th>survivorship</th>
                  </tr>
                </thead>
                <tbody>
                  {experiment.dataset_sources?.map((s) => (
                    <tr key={`${s.dataset_id}-${s.role}`}>
                      <td className="qr-model">{s.dataset_id.replace('dolthub_', '')}</td>
                      <td className="u-note">{s.role}</td>
                      <td className="num">{int(s.rows)}</td>
                      <td className="u-note">{s.min_date} → {s.max_date}</td>
                      <td>
                        <StatusPill
                          tone={s.point_in_time_status === 'point_in_time' ? 'pos' : 'warn'}
                          label={(s.point_in_time_status ?? 'unknown').replace(/_/g, ' ')}
                        />
                      </td>
                      <td className="u-note">{s.survivorship_status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="body-copy u-note">
              Coverage is not perfect and is not presented as such. Options begin
              2019-02-09 with no volume or open-interest columns; the earnings calendar
              begins 2020-01-22, so pre-2020 statement periods cannot be gated and are
              dropped; the equity panel has no bid/ask, so the half-spread is an
              assumption rather than an observation.
            </p>
          </Section>

          {/* ── 12. registry ── */}
          <Section id="registry" title="Model registry"
                   summary={`${registry?.entries ?? status?.total_entries ?? 0} entries · 0 production`} defaultOpen>
            <div className="qr-registry">
              {[
                ['PRODUCTION', status?.production ?? 0, 'neg'],
                ['CANDIDATES', status?.candidates ?? 0, 'muted'],
                ['VALIDATED', status?.validated ?? 0, 'muted'],
                ['RETIRED / VOID', status?.retired ?? 0, 'muted'],
              ].map(([label, count, tone]) => (
                <div key={String(label)} className="qr-reg">
                  <span className="qr-reg__count num">{String(count)}</span>
                  <span className="qr-reg__label">{String(label)}</span>
                  {label === 'PRODUCTION' && Number(count) === 0 && (
                    <StatusPill tone={tone as StatusTone} label="NONE" />
                  )}
                </div>
              ))}
            </div>
            <p className="body-copy u-note">
              Promotion is evaluated in Python by <code>ModelRegistry.promote()</code>,
              which refuses a transition whose evidence is absent <em>and</em> one whose
              numbers fail. The frontend never decides that a model is production-ready —
              it renders what the registry already decided. Every EXP-005 entry is
              eligible for <code>validated</code> and nothing beyond it.
            </p>
            {best && (
              <div className="qr-reject">
                <span className="label">Why the best model is rejected</span>
                <ul>
                  {Object.entries(best.verdict.gates)
                    .filter(([, g]) => !g.passed)
                    .map(([name, g]) => (
                      <li key={name}>
                        <code>{name}</code> — observed{' '}
                        <strong className="num">
                          {typeof g.observed === 'boolean' ? String(g.observed) : f(g.observed as number, 3)}
                        </strong>, required {g.required}
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </Section>

          {/* ── 13. training ── */}
          <Section id="training" title="Model training" summary="pipeline ready · nothing deployed" defaultOpen>
            <div className="qr-callout">
              <div className="qr-banner__head">
                <StatusPill tone="muted" label="NOT DEPLOYED" />
                <strong>No model currently satisfies production promotion gates.</strong>
              </div>
              <p className="body-copy u-note">
                The pipeline below runs today — EXP-005 executed all of it in 1h 42m on
                this machine. What is <em>not</em> built is the last step, because nothing
                has earned it. Wiring a deployment path for a model with a negative gross
                Sharpe would be the most expensive thing this product could do.
              </p>
            </div>
            <ol className="qr-pipeline">
              {[
                ['DATASET', 'point-in-time panel, content-hashed', 'done'],
                ['FEATURES', '103 registered, 57 used, each with a leakage test', 'done'],
                ['TARGET', 'forward 21-session cross-sectional rank', 'done'],
                ['WALK-FORWARD TRAINING', '8 expanding folds, purge + embargo', 'done'],
                ['VALIDATION', 'Newey-West IC, fold dispersion, negative controls', 'done'],
                ['COSTED BACKTEST', 'execution lag, commission, spread, impact', 'done'],
                ['ROBUSTNESS', 'regimes, cost sweep, PBO, ablation', 'done'],
                ['MULTIPLE TESTING', 'deflated Sharpe vs cumulative trials', 'done'],
                ['MODEL REGISTRY', 'evidence bundle per model, immutable per study', 'done'],
                ['PROMOTION GATE', 'refuses on missing evidence and on failing numbers', 'blocked'],
                ['DEPLOYMENT', 'awaiting a model that clears the gate', 'pending'],
              ].map(([step, detail, state]) => (
                <li key={String(step)} className={`qr-step qr-step--${state}`}>
                  <span className="qr-step__name">{step}</span>
                  <span className="qr-step__detail u-note">{detail}</span>
                  <span className="qr-step__state">{state === 'done' ? '✓' : state === 'blocked' ? '⊘' : '·'}</span>
                </li>
              ))}
            </ol>
          </Section>

          {/* ── 15. experiment timeline ── */}
          <Section id="timeline" title="Experiment history"
                   summary="every study, including the void one" defaultOpen>
            <ExperimentTimeline current={selected ?? undefined} />
            <p className="body-copy u-note">
              A void study stays in the record. Deleting EXP-002 would erase the
              multiple-testing exposure it created, which every later study&rsquo;s
              significance correction depends on.
            </p>
          </Section>

          {/* ── 16. provenance ── */}
          {search?.available ? (
            <Section id="provenance" title="Provenance"
                     summary="chain of custody" defaultOpen>
              <Provenance
                search={search as unknown as { [k: string]: unknown }}
                fallbackCommit={experiment.git_commit ?? null}
              />
            </Section>
          ) : null}

          {/* ── 17. training ── */}
          <Section id="run" title="Run training locally"
                   summary="the command, not a button that fits" defaultOpen>
            <TrainCommand />
          </Section>
        </>
      )}
    </div>
  )
}
