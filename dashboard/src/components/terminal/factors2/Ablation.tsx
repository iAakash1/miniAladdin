'use client'

/**
 * The feature-family ablation, and its negative result.
 *
 * Each arm adds one pre-registered data family to a fixed price-volatility-
 * volume-macro base. Options, analyst estimate revisions and announcement-gated
 * statement fundamentals were each tried. None improved the base, and the peak
 * arm is the one containing no fundamental data at all.
 *
 * That is the most commercially inconvenient finding in the study, which is
 * exactly why it gets a workspace panel rather than a footnote. Three things
 * this panel is built to prevent:
 *
 * **Reading the winning arm as an edge.** The best IC on this page is a maximum
 * over every arm-by-model configuration tried, against a trial count the study
 * itself carries. Both counts are read from the payload rather than written
 * into this file, because a number quoted in prose stops being true the moment
 * the study is re-run and nothing tells you it has.
 *
 * **Reading a best-of bar as a comparison.** Best-of-six is biased upward by
 * construction — take six draws from noise and the largest is positive. The
 * honest statistic is how many of the six models each family improved, and that
 * is the number given the headline treatment.
 *
 * **Reading a skipped arm as a zero.** A skipped arm renders its reason, never
 * a number. An arm that could not be run is not an arm that found nothing.
 */

import { useEffect, useState } from 'react'

import { Grid, Panel, Prose, StateBlock, Status, Value } from '@/components/system'
import { BarRows } from '@/components/system/charts'

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
}

interface Contrast {
  arm: string
  families_added: string[]
  mean_delta?: number | null
  median_delta?: number | null
  models_improved: number
  models_compared: number
}

interface Payload {
  trials_used_for_correction?: number | null
  ablation?: {
    ran: boolean
    arms?: ArmRow[]
    contrasts?: Contrast[]
    base_arm?: string
    interpretation?: string
  }
}

/**
 * EXP-005 is the study that ran the ablation. Any other experiment id renders
 * the "no ablation was run" state rather than an empty panel, because an arm
 * that was never registered and an arm that found nothing are different facts.
 */
export default function Ablation({ experimentId = 'EXP-005' }: { experimentId?: string }) {
  const [data, setData] = useState<Payload | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetch(`/api/quant/experiments/${encodeURIComponent(experimentId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: Payload) => { if (alive) setData(d) })
      .catch((e: Error) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [experimentId])

  if (error) {
    return (
      <Panel title="Feature-family ablation" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The ablation could not be read"
          detail={`Request failed: ${error}. Nothing is shown in its place.`}
        />
      </Panel>
    )
  }
  if (!data) return null

  const ablation = data.ablation
  if (!ablation?.ran) {
    return (
      <Panel title="Feature-family ablation" state="unavailable">
        <StateBlock
          state="unavailable"
          title="No ablation was run for this experiment"
          detail="Arms are pre-registered before a study runs. There is nothing to report here rather than nothing to show."
        />
      </Panel>
    )
  }

  const arms = ablation.arms ?? []
  const base = ablation.base_arm ?? 'C_base'
  const usable = arms.filter((a) => !a.skipped && a.best_ic != null)
  const trials = data.trials_used_for_correction ?? null
  // How many configurations the peak is a maximum over: one per model per arm
  // that actually ran. Counted from the data, never asserted in prose.
  const configurations = (ablation.contrasts ?? []).reduce(
    (most, c) => Math.max(most, c.models_compared), 0,
  ) * usable.length

  return (
    <>
      <Panel
        title="Feature-family ablation"
        subtitle={`${arms.length} pre-registered arms`}
        state="recorded"
        badge="HYPOTHESIS — NOT A RESULT"
        badgeTone="warn"
      >
        <Prose tone="strong">
          <strong>Additional datasets did not demonstrate incremental predictive
          value.</strong> Options, analyst estimate revisions and
          announcement-gated statement fundamentals were each added to a
          price-volatility-volume-macro base. None improved it, and the peak is
          the arm containing no fundamental data at all.
        </Prose>
        <Prose caution>
          The highest observed t-statistic is <strong>not</strong> evidence of an
          edge.{' '}
          {configurations > 0 ? <>It is the maximum over {configurations} configurations. </> : null}
          {trials !== null ? (
            <>
              This study corrects against {trials} cumulative trials, and the
              largest statistic a zero-skill population of that size would be
              expected to produce is of comparable size.
            </>
          ) : (
            <>The trial count behind it could not be read, so no correction is claimed here.</>
          )}
        </Prose>

        {usable.length ? (
          <div style={{ marginTop: 'var(--d-4)' }}>
            <BarRows
              kind="ic"
              rows={usable.map((a) => ({
                label: a.arm,
                value: a.best_ic as number,
                note: a.arm === base ? 'base — no fundamental data' : a.families.join(' + '),
              }))}
            />
            <Prose size="fine">
              Best model per arm, Spearman IC. These bars are a best-of and are
              therefore biased upward; the per-model contrast below is the honest
              comparison.
            </Prose>
          </div>
        ) : null}

        <div className="sys-scroll-x" style={{ marginTop: 'var(--d-4)' }}>
          <table className="sys-table sys-table--compact">
            <thead>
              <tr>
                <th>Arm</th><th>Families</th><th className="num">Features</th>
                <th className="num">Best IC</th><th className="num">t</th><th>Hypothesis</th>
              </tr>
            </thead>
            <tbody>
              {arms.map((a) => (
                <tr key={a.arm} data-selected={a.arm === base}>
                  <td className="sys-mono">{a.arm}</td>
                  <td><span className="sys-meta">{a.families.join(' + ')}</span></td>
                  <td className="num">
                    {a.skipped ? <span className="sys-meta">—</span> : <Value value={a.feature_count} kind="count" />}
                  </td>
                  <td className="num">
                    {/* A skipped arm never renders a number. An arm that could
                        not be run is not an arm that found nothing. */}
                    {a.skipped ? <Status state="unavailable" label="SKIPPED" /> : <Value value={a.best_ic} kind="ic" />}
                  </td>
                  <td className="num">
                    {a.skipped ? <span className="sys-meta">—</span> : <Value value={a.best_t} kind="tstat" />}
                  </td>
                  <td><span className="sys-meta">{a.skipped ? a.reason : a.hypothesis}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="Does the source add information over the base?" state="recorded">
        <Grid>
          {(ablation.contrasts ?? []).map((c) => {
            const helps = (c.mean_delta ?? 0) > 0 && c.models_improved > c.models_compared / 2
            return (
              <div key={c.arm} className="sys-panel-inset" data-tone={helps ? 'pass' : 'fail'}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 'var(--d-2)' }}>
                  <strong>{c.families_added.join(', ') || c.arm}</strong>
                  <Status
                    state={helps ? 'recorded' : 'blocked'}
                    label={helps ? 'ADDS INFORMATION' : 'NO IMPROVEMENT'}
                  />
                </div>
                <div style={{ display: 'flex', gap: 'var(--d-4)', marginTop: 'var(--d-2)', flexWrap: 'wrap' }}>
                  <span className="sys-meta">mean ΔIC <Value value={c.mean_delta} kind="ic" /></span>
                  <span className="sys-meta">median ΔIC <Value value={c.median_delta} kind="ic" /></span>
                  <span className="sys-meta sys-meta--strong">
                    improved {c.models_improved}/{c.models_compared}
                  </span>
                </div>
              </div>
            )
          })}
        </Grid>
        {/* The study's own words, not a paraphrase of them. */}
        {ablation.interpretation ? <Prose tone="strong">{ablation.interpretation}</Prose> : null}
        <Prose caution>
          <strong>Models improved over models compared</strong> is the honest
          headline. A best-of comparison is a maximum over as many draws as there
          are models, and is biased upward by construction — take enough draws
          from noise and the largest is positive.
        </Prose>
      </Panel>
    </>
  )
}
