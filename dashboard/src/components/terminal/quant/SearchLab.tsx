'use client'

/**
 * EXP-007 search lab — progress, families, overfitting, and what the search
 * costs itself in significance.
 *
 * Three rules this file exists to enforce visually:
 *
 * 1. **A running search is progress, not a result.** Every panel says PARTIAL
 *    while `state === 'RUNNING'`, and no configuration is ever styled as a
 *    winner before selection has run.
 * 2. **Green means a gate passed, not that a number is positive.** The
 *    leaderboard's top row is tinted by its overfitting diagnosis, not by its
 *    IC, so the highest IC in the table can — and often does — render amber.
 * 3. **The bar is shown beside the number.** Observed max |t| is meaningless
 *    without the threshold a search of this size has to clear, so they are
 *    never displayed apart.
 */

import { useMemo, useState } from 'react'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import { f, int, num, sign } from './format'
import type { SearchConfigRow, SearchState } from './searchTypes'

const DIAGNOSIS_TONE: Record<string, StatusTone> = {
  HEALTHY: 'pos',
  OVERFIT: 'warn',
  UNSTABLE: 'warn',
  UNDERFIT: 'muted',
  FAILED: 'neg',
}

/** Order matters: this is the sequence the stages actually run in. */
const STAGE_LABEL: Record<string, string> = {
  screen: 'screen — every family, coarse',
  tune: 'tune — the families that competed',
  context: 'context — arms × targets',
  robustness: 'robustness — neighbours of each finalist',
}

function hours(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  return seconds < 3600 ? `${(seconds / 60).toFixed(0)}m` : `${(seconds / 3600).toFixed(2)}h`
}

/**
 * The generalisation-gap bar.
 *
 * Both bars are scaled by the same divisor so their lengths are comparable —
 * scaling each to its own maximum would make a model that memorises the
 * training fold look identical to one that generalises, which is the single
 * most misleading thing this panel could do.
 */
function GapBar({ train, validation }: { train: number | null; validation: number | null }) {
  if (train === null || validation === null) {
    return <span className="u-note">not measured</span>
  }
  const scale = Math.max(Math.abs(train), Math.abs(validation), 0.05)
  const width = (v: number) => `${Math.max(0, (Math.abs(v) / scale) * 100)}%`
  const gap = train - validation
  return (
    <div className="qs-gap">
      <div className="qs-gap__row">
        <span className="qs-gap__label">TRAIN</span>
        <span className="qs-gap__track">
          <span className="qs-gap__fill qs-gap__fill--train" style={{ width: width(train) }} />
        </span>
        <span className="qs-gap__value num">{sign(train)}</span>
      </div>
      <div className="qs-gap__row">
        <span className="qs-gap__label">VALID</span>
        <span className="qs-gap__track">
          <span className="qs-gap__fill qs-gap__fill--valid" style={{ width: width(validation) }} />
        </span>
        <span className="qs-gap__value num">{sign(validation)}</span>
      </div>
      <div className="qs-gap__row qs-gap__row--summary">
        <span className="qs-gap__label">GAP</span>
        <span className="qs-gap__track" />
        <span className="qs-gap__value num">{sign(gap)}</span>
      </div>
    </div>
  )
}

export default function SearchLab({ search }: { search: SearchState }) {
  const [family, setFamily] = useState<string>('all')
  const [diagnosis, setDiagnosis] = useState<string>('all')
  const [expanded, setExpanded] = useState<string | null>(null)

  const running = search.state === 'RUNNING'
  const rows = useMemo(() => {
    const all = search.leaderboard ?? []
    return all.filter(
      (r) =>
        (family === 'all' || r.family === family) &&
        (diagnosis === 'all' || r.diagnosis === diagnosis),
    )
  }, [search.leaderboard, family, diagnosis])

  if (!search.available) {
    return (
      <div className="qr-callout">
        <div className="qr-banner__head">
          <StatusPill tone="muted" label="NOT STARTED" />
          <strong>{search.experiment_id} has not been run.</strong>
        </div>
        <p className="body-copy u-note">{search.detail}</p>
      </div>
    )
  }

  const mt = search.multiple_testing
  const diagnoses = search.diagnoses ?? {}
  const evaluated = search.configurations_evaluated ?? 0
  const planned = search.configurations_planned ?? null

  return (
    <div className="qs">
      {/* ── progress ──────────────────────────────────────────────────── */}
      <div className={`qs-banner qs-banner--${running ? 'running' : 'complete'}`}>
        <div className="qr-banner__head">
          <StatusPill tone={running ? 'accent' : 'pos'} label={search.state} />
          <strong>
            {int(evaluated)}
            {planned ? ` of ${int(planned)}` : ''} configurations
            {search.configurations_failed ? ` · ${search.configurations_failed} failed` : ''}
          </strong>
        </div>
        {planned ? (
          <div className="qs-progress">
            <span
              className="qs-progress__fill"
              style={{ width: `${Math.min(100, search.progress_pct ?? 0)}%` }}
            />
            <span className="qs-progress__label num">{num(search.progress_pct, 1)}%</span>
          </div>
        ) : null}
        <p className="body-copy u-note">{search.note}</p>
      </div>

      {/* ── stages ────────────────────────────────────────────────────── */}
      {search.stages?.length ? (
        <>
          <h4 className="qr-subhead">Stages</h4>
          <div className="ml-scroll">
            <table className="data-table qr-table qr-table--narrow">
              <thead>
                <tr>
                  <th>stage</th>
                  <th className="num">configs</th>
                  <th className="num">failed</th>
                  <th className="num">worker time</th>
                </tr>
              </thead>
              <tbody>
                {search.stages.map((s) => (
                  <tr key={s.stage}>
                    <td className="qr-model">{STAGE_LABEL[s.stage] ?? s.stage}</td>
                    <td className="num">{int(s.evaluated)}</td>
                    <td className="num">{s.failed ? int(s.failed) : '—'}</td>
                    <td className="num">{hours(s.worker_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {/* ── multiple testing ──────────────────────────────────────────── */}
      {mt ? (
        <>
          <h4 className="qr-subhead">
            What this search costs itself
            {mt.provisional ? <span className="qs-tag">PROVISIONAL</span> : null}
          </h4>
          <dl className="qr-grid qr-grid--tight">
            <div>
              <dt>configurations tested</dt>
              <dd className="num">{int(mt.new_trials)}</dd>
            </div>
            <div>
              <dt>cumulative trials</dt>
              <dd className="num">{int(mt.cumulative_trials)}</dd>
            </div>
            <div>
              <dt>expected max |t| under null</dt>
              <dd className="num">{num(mt.expected_max_abs_t_under_null, 2)}</dd>
            </div>
            <div>
              <dt>observed max |t|</dt>
              <dd className="num">{num(mt.observed_max_abs_t, 2)}</dd>
            </div>
            {mt.bonferroni_threshold_5pct ? (
              <div>
                <dt>Bonferroni 5%</dt>
                <dd className="num">{num(mt.bonferroni_threshold_5pct, 2)}</dd>
              </div>
            ) : null}
            <div>
              <dt>clears the bar</dt>
              <dd>
                {mt.observed_clears_threshold === null ? (
                  <StatusPill tone="muted" label="UNKNOWN" />
                ) : (
                  <StatusPill
                    tone={mt.observed_clears_threshold ? 'accent' : 'warn'}
                    label={mt.observed_clears_threshold ? 'ABOVE' : 'BELOW'}
                  />
                )}
              </dd>
            </div>
          </dl>
          <p className="body-copy u-note">
            {mt.caveat}
            {mt.provisional
              ? ` The threshold is computed at the ${mt.basis} because the final trial count is what a result must face — not the count reached so far.`
              : ''}
          </p>
        </>
      ) : null}

      {/* ── overfitting census ────────────────────────────────────────── */}
      {Object.keys(diagnoses).length ? (
        <>
          <h4 className="qr-subhead">Overfitting census</h4>
          <div className="qs-census">
            {(['HEALTHY', 'OVERFIT', 'UNSTABLE', 'UNDERFIT', 'FAILED'] as const).map((key) =>
              diagnoses[key] ? (
                <div key={key} className={`qs-census__cell qs-census__cell--${key.toLowerCase()}`}>
                  <span className="qs-census__count num">{int(diagnoses[key])}</span>
                  <span className="qs-census__label">{key}</span>
                </div>
              ) : null,
            )}
          </div>
          <p className="body-copy u-note">
            OVERFIT means the train-minus-validation IC gap exceeds 0.15, whatever the
            validation score. Those configurations are kept in the trial count and shown
            here; they are excluded from advancing, not deleted. UNSTABLE means the IC was
            positive in fewer than half the folds — right on average, wrong half the time.
          </p>
        </>
      ) : null}

      {/* ── families ──────────────────────────────────────────────────── */}
      {search.families?.length ? (
        <>
          <h4 className="qr-subhead">By family</h4>
          <div className="ml-scroll">
            <table className="data-table qr-table">
              <thead>
                <tr>
                  <th>family</th>
                  <th className="num">tried</th>
                  <th className="num">overfit</th>
                  <th className="num">failed</th>
                  <th className="num">best IC</th>
                  <th className="num">t</th>
                  <th className="num">gap</th>
                  <th className="num">worst gap</th>
                  <th className="num">time</th>
                </tr>
              </thead>
              <tbody>
                {search.families.map((row) => (
                  <tr key={row.family}>
                    <td className="qr-model">{row.family}</td>
                    <td className="num">{int(row.evaluated)}</td>
                    <td className="num">{row.overfit ? int(row.overfit) : '—'}</td>
                    <td className="num">{row.failed ? int(row.failed) : '—'}</td>
                    <td className="num">{sign(row.best_ic)}</td>
                    <td className="num">{sign(row.best_t, 2)}</td>
                    <td className="num">{sign(row.best_gap)}</td>
                    <td className="num">{sign(row.worst_gap)}</td>
                    <td className="num">{hours(row.seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="body-copy u-note">
            &ldquo;Best&rdquo; is each family&rsquo;s strongest <em>non-overfit</em>
            configuration. A family whose only good number comes from a memorising
            configuration has not shown that it competes.
          </p>
        </>
      ) : null}

      {/* ── leaderboard ───────────────────────────────────────────────── */}
      {search.leaderboard?.length ? (
        <>
          <h4 className="qr-subhead">Configurations</h4>
          <div className="qs-filters">
            <label>
              family
              <select value={family} onChange={(e) => setFamily(e.target.value)}>
                <option value="all">all</option>
                {(search.families ?? []).map((row) => (
                  <option key={row.family} value={row.family}>
                    {row.family}
                  </option>
                ))}
              </select>
            </label>
            <label>
              diagnosis
              <select value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)}>
                <option value="all">all</option>
                {Object.keys(diagnoses).map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>
            <span className="u-note">{rows.length} shown</span>
          </div>
          <div className="ml-scroll">
            <table className="data-table qr-table">
              <thead>
                <tr>
                  <th>configuration</th>
                  <th>stage</th>
                  <th>context</th>
                  <th className="num">IC</th>
                  <th className="num">t</th>
                  <th className="num">train IC</th>
                  <th className="num">gap</th>
                  <th className="num">folds +</th>
                  <th>diagnosis</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <ConfigRow
                    key={row.config_id}
                    row={row}
                    open={expanded === row.config_id}
                    onToggle={() =>
                      setExpanded(expanded === row.config_id ? null : row.config_id)
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
          <p className="body-copy u-note">
            Rejected configurations are listed, never hidden. Ordering is by validation IC
            with overfit configurations pushed down — it decides what gets examined, not
            what wins. Nothing here is a candidate until the gates have run.
          </p>
        </>
      ) : null}
    </div>
  )
}

function ConfigRow({
  row,
  open,
  onToggle,
}: {
  row: SearchConfigRow
  open: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr className={`qs-row qs-row--${row.diagnosis.toLowerCase()}`} onClick={onToggle}>
        <td className="qr-model">
          <span className="qs-disclose">{open ? '−' : '+'}</span> {row.family}
        </td>
        <td className="u-note">{row.stage}</td>
        <td className="u-note">
          {row.arm}/{row.target}
        </td>
        <td className="num">{sign(row.mean_ic)}</td>
        <td className="num">{sign(row.ic_t_stat, 2)}</td>
        <td className="num">{sign(row.train_mean_ic)}</td>
        <td className="num">{sign(row.train_ic_gap)}</td>
        <td className="num">
          {row.fold_ic_positive_rate === null ? '—' : `${(row.fold_ic_positive_rate * 100).toFixed(0)}%`}
        </td>
        <td>
          <StatusPill tone={DIAGNOSIS_TONE[row.diagnosis] ?? 'muted'} label={row.diagnosis} />
        </td>
      </tr>
      {open ? (
        <tr className="qs-detail">
          <td colSpan={9}>
            <div className="qs-detail__grid">
              <div>
                <h5 className="qr-subhead">Generalisation</h5>
                <GapBar train={row.train_mean_ic} validation={row.mean_ic} />
              </div>
              <div>
                <h5 className="qr-subhead">Hyperparameters</h5>
                <dl className="qr-grid qr-grid--tight">
                  {Object.entries(row.params ?? {}).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd className="num">
                        {typeof value === 'number' ? f(value, 4) : String(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
              <div>
                <h5 className="qr-subhead">Run</h5>
                <dl className="qr-grid qr-grid--tight">
                  <div>
                    <dt>features</dt>
                    <dd className="num">{int(row.feature_count)}</dd>
                  </div>
                  <div>
                    <dt>folds</dt>
                    <dd className="num">{int(row.folds)}</dd>
                  </div>
                  <div>
                    <dt>IC IR</dt>
                    <dd className="num">{sign(row.ic_ir, 3)}</dd>
                  </div>
                  <div>
                    <dt>fit time</dt>
                    <dd className="num">{num(row.seconds, 1)}s</dd>
                  </div>
                </dl>
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  )
}
