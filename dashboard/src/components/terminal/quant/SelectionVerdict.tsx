'use client'

/**
 * The gate verdict, the experiment timeline, provenance, and the training
 * command.
 *
 * The verdict panel is the one place on this page allowed to say a model
 * passed, and it renders only what `final_selection.json` recorded. It has no
 * fallback that infers a verdict from a leaderboard: the top of a leaderboard is
 * a ranking, and treating it as a candidate is precisely the error the gates
 * exist to catch. When selection has not run, the panel says so.
 */

import { useState } from 'react'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import { Metric } from './ResearchTerminal'
import { int, num, sign } from './format'
import type { SelectionState } from './searchTypes'

/** Gate names in the order they are evaluated, with what each one is for. */
const GATE_PURPOSE: Record<string, string> = {
  ic_t_stat: 'The ordering carries information at all.',
  gross_sharpe: 'The signal makes money before costs.',
  net_sharpe: 'It still makes money after them, at the declared 10 bp half-spread.',
  beats_best_baseline: 'It beats free factors refit on the same folds and label.',
  not_overfit: 'It did not memorise the training fold.',
  survives_search_size:
    'It beats what the best of a zero-skill population this size would show.',
  alpha_credible: 'What is left is not just factor exposure.',
  turnover_tolerable: 'It can be traded at a plausible size.',
  deflated_sharpe:
    'The Sharpe survives deflation against the number of trials, their dispersion, and the return distribution’s skew and kurtosis.',
  selection_carries_information:
    'Picking the in-sample best actually predicts out-of-sample rank. Above 0.5 it predicts the opposite.',
}

export function SelectionVerdict({ selection }: { selection: SelectionState }) {
  if (!selection.available || !selection.verdict) {
    return (
      <div className="qr-callout">
        <div className="qr-banner__head">
          <StatusPill tone="muted" label="NOT SELECTED" />
          <strong>No verdict yet.</strong>
        </div>
        <p className="body-copy u-note">{selection.detail}</p>
        <pre className="qs-command">
          python -m scripts.quant.select_candidate --experiment EXP-007
        </pre>
      </div>
    )
  }

  // When an artifact predates the current gate standard, the read layer
  // restates it from the same recorded numbers. Showing the recorded eight
  // beside two more failing metrics below would be an invitation to ask which
  // one counts; the current standard counts.
  const verdict = selection.current_standard ?? selection.verdict
  const { selected } = selection
  const passed = verdict.passed
  const reproduction = selection.refit_reproduction ?? []
  const reproduces = reproduction.every((r) => r.reproduces)

  return (
    <div className="qs">
      <div className={`qs-banner qs-banner--${passed ? 'candidate' : 'blocked'}`}>
        <div className="qr-banner__head">
          <StatusPill tone={passed ? 'accent' : 'warn'} label={verdict.status} />
          <strong>
            {passed
              ? 'Every gate passed. This is a development candidate.'
              : `Failed ${verdict.failed.length} of ${verdict.gates.length} gates.`}
          </strong>
          {selection.current_standard ? (
            <span className="tp-status tp-status--warn">RESTATED · 10-GATE STANDARD</span>
          ) : null}
        </div>
        <p className="body-copy u-note">{verdict.note}</p>
      </div>



      {selected ? (
        <dl className="qr-grid qr-grid--tight">
          <div>
            <dt>family</dt>
            <dd className="qr-model">{selected.family}</dd>
          </div>
          <div>
            <dt>context</dt>
            <dd className="num">
              {selected.arm}/{selected.target}
            </dd>
          </div>
          <div>
            <dt>ranked by</dt>
            <dd className="u-note">{selected.ranked_by}</dd>
          </div>
        </dl>
      ) : null}

      <h4 className="qr-subhead">Gates</h4>
      <div className="qs-gates">
        {verdict.gates.map((gate) => (
          <div key={gate.gate} className={`qs-gate qs-gate--${gate.passed ? 'pass' : 'fail'}`}>
            <div className="qs-gate__head">
              <span className="qs-gate__name">{gate.gate}</span>
              <StatusPill tone={gate.passed ? 'pos' : 'neg'} label={gate.passed ? 'PASS' : 'FAIL'} />
            </div>
            <div className="qs-gate__row">
              <span className="u-note">observed</span>
              <span className="num">
                {typeof gate.observed === 'number' ? sign(gate.observed, 4) : String(gate.observed ?? '—')}
              </span>
            </div>
            <div className="qs-gate__row">
              <span className="u-note">required</span>
              <span className="num">{gate.required}</span>
            </div>
            <p className="qs-gate__purpose u-note">{GATE_PURPOSE[gate.gate]}</p>
          </div>
        ))}
      </div>

      <SelectionBias selection={selection} />

      {reproduction.length ? (
        <>
          <h4 className="qr-subhead">
            Reproduction check
            <StatusPill
              tone={reproduces ? 'pos' : 'neg'}
              label={reproduces ? 'EXACT' : 'DIVERGED'}
            />
          </h4>
          <div className="ml-scroll">
            <table className="data-table qr-table qr-table--narrow">
              <thead>
                <tr>
                  <th>configuration</th>
                  <th className="num">search IC</th>
                  <th className="num">refit IC</th>
                  <th className="num">delta</th>
                </tr>
              </thead>
              <tbody>
                {reproduction.map((row) => (
                  <tr key={row.config_id}>
                    <td className="qr-model">{row.config_id}</td>
                    <td className="num">{sign(row.search_mean_ic)}</td>
                    <td className="num">{sign(row.refit_mean_ic)}</td>
                    <td className="num">{sign(row.delta, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="body-copy u-note">
            Each finalist is refit from scratch and its IC compared to what the search
            recorded. A non-zero delta means the run is not reproducible, and the selection
            should not be trusted regardless of what the gates say.
          </p>
        </>
      ) : null}
    </div>
  )
}

/**
 * The three statistics that decide whether a result is a discovery or an
 * artifact of having looked many times.
 *
 * Given its own panel because a leaderboard cannot show any of them: they are
 * properties of the *search*, not of a model. A configuration with the best IC
 * in the table and a PBO of 0.93 is the table telling you that the table is not
 * to be trusted.
 */
function SelectionBias({ selection }: { selection: SelectionState }) {
  const cid = selection.selected?.config_id
  const sig = cid ? selection.significance?.[cid] : undefined
  const dsr = sig?.deflated_sharpe
  const mtrl = sig?.minimum_track_record
  const pbo = selection.probability_of_backtest_overfitting

  if (!dsr && !pbo) return null

  const ratio =
    dsr?.observed_sharpe != null && dsr?.expected_max_sharpe_under_null
      ? dsr.observed_sharpe / dsr.expected_max_sharpe_under_null
      : null

  return (
    <>
      <h4 className="qr-subhead">Selection bias</h4>
      <div className="qt-blocked__metrics">
        {dsr ? (
          <Metric
            label="deflated Sharpe p"
            value={num(dsr.deflated_probability, 4)}
            method={`vs ${int(dsr.trials)} trials · needs > 0.95`}
            status={(dsr.deflated_probability ?? 0) > 0.95 ? 'pass' : 'fail'}
          />
        ) : null}
        {pbo?.pbo != null ? (
          <Metric
            label="PBO"
            value={num(pbo.pbo, 3)}
            method={`CSCV, ${int(pbo.splits_evaluated)} splits · needs ≤ 0.20`}
            status={pbo.pbo <= 0.2 ? 'pass' : 'fail'}
          />
        ) : null}
        {dsr ? (
          <Metric
            label="search noise ceiling"
            value={num(dsr.expected_max_sharpe_under_null, 4)}
            method={`Sharpe the best of ${int(dsr.trials)} zero-skill configs would show`}
            status="none"
          />
        ) : null}
        {ratio != null ? (
          <Metric
            label="observed ÷ ceiling"
            value={`${num(ratio, 2)}×`}
            method="above 1.0 is where a result starts being interesting"
            status={ratio > 1 ? 'pass' : 'fail'}
          />
        ) : null}
        {mtrl ? (
          <Metric
            label="track record needed"
            value={int(mtrl.required_periods)}
            method={`periods, for 95% confidence Sharpe > 0 · ${int(mtrl.observed_periods)} available`}
            status={mtrl.sufficient ? 'pass' : 'fail'}
          />
        ) : null}
        {dsr ? (
          <Metric
            label="return distribution"
            value={`γ₁ ${num(dsr.skew, 2)}`}
            method={`excess kurtosis ${num(dsr.excess_kurtosis, 1)} — fat tails lengthen the record required`}
            status="none"
          />
        ) : null}
      </div>
      <p className="body-copy u-note">
        These are properties of the search, not of any model in it. A high IC and
        a PBO above 0.5 together mean the leaderboard ordering does not survive
        out of sample — the in-sample winner lands in the bottom half more often
        than not.
      </p>
    </>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

interface TimelineEntry {
  id: string
  question: string
  result: string
  status: string
  tone: StatusTone
}

/**
 * The research record, in order.
 *
 * Hard-coded because it is a *narrative* of decisions, not a data view — the
 * question each study asked and what invalidated EXP-002 are not fields in any
 * artifact. The metrics elsewhere on this page all come from the API; this is
 * the ledger's story, and it is kept in step with `docs/RESEARCH_LEDGER.md`.
 */
const TIMELINE: TimelineEntry[] = [
  {
    id: 'EXP-002',
    question: 'Does any learned model beat free factors?',
    result: 'Void — a pandas as-of join reset the index and 12 of 39 features carried other rows’ values.',
    status: 'VOID',
    tone: 'neg',
  },
  {
    id: 'EXP-004',
    question: 'The same question again, on the corrected pipeline.',
    result: 'No evidence of edge. Retained as the clean negative result.',
    status: 'NO EDGE',
    tone: 'muted',
  },
  {
    id: 'EXP-005',
    question: 'Do options, estimates or fundamentals add information over price?',
    result: 'No. Every contrast against C_base is negative; fundamentals cost −0.0210.',
    status: 'NO INCREMENTAL VALUE',
    tone: 'muted',
  },
  {
    id: 'EXP-006',
    question: 'Is the frozen 27-feature C_base set tradeable?',
    result:
      'Three gates of four. IC +0.0290, t +2.66, gross Sharpe +0.384 — and net Sharpe −0.102 at 10 bp. Alpha t +0.047.',
    status: 'PROMOTION BLOCKED',
    tone: 'warn',
  },
  {
    id: 'EXP-007',
    question: 'Was the fixed ladder the limit? Search families, hyperparameters, arms and targets.',
    result: 'See above.',
    status: 'SEARCH',
    tone: 'accent',
  },
  {
    id: 'EXP-007-WIN-GPU',
    question: 'Do GPU-native boosters or a small network find what the CPU families did not?',
    result: 'Runs on separate hardware. Never merged into EXP-007.',
    status: 'SEPARATE',
    tone: 'muted',
  },
]

export function ExperimentTimeline({ current }: { current?: string }) {
  return (
    <ol className="qs-timeline">
      {TIMELINE.map((entry) => (
        <li
          key={entry.id}
          className={`qs-timeline__item${entry.id === current ? ' qs-timeline__item--current' : ''}`}
        >
          <div className="qs-timeline__head">
            <span className="qs-timeline__id">{entry.id}</span>
            <StatusPill tone={entry.tone} label={entry.status} />
          </div>
          <p className="qs-timeline__question">{entry.question}</p>
          <p className="body-copy u-note">{entry.result}</p>
        </li>
      ))}
    </ol>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

/**
 * The training control.
 *
 * It shows a command. It does not run one. A web request that starts a
 * ten-hour fit is a denial-of-service endpoint with a friendly label, and the
 * research it would produce could not be attributed to a person who chose to
 * run it.
 */
export function TrainCommand({
  experimentId = 'EXP-007',
  budget = 'overnight',
}: {
  experimentId?: string
  budget?: string
}) {
  const [copied, setCopied] = useState(false)
  const command =
    `python -m src.quant.train \\\n` +
    `  --experiment ${experimentId} \\\n` +
    `  --budget ${budget} \\\n` +
    `  --performance max \\\n` +
    `  --confirm`

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(command.replace(/\\\n\s+/g, ' '))
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="qs">
      <div className="qr-callout">
        <div className="qr-banner__head">
          <StatusPill tone="muted" label="LOCAL ONLY" />
          <strong>Training runs on your machine, not from this page.</strong>
        </div>
        <p className="body-copy u-note">
          Nothing here starts a fit. The overnight search takes hours and saturates every
          core; it belongs in a terminal you can watch, interrupt and resume, attributed to
          the person who chose to run it.
        </p>
      </div>

      <pre className="qs-command">{command}</pre>
      <div className="qs-command__actions">
        <button type="button" className="qs-copy" onClick={copy}>
          {copied ? 'copied' : 'copy command'}
        </button>
        <span className="u-note">
          without <code>--confirm</code> it prints the plan and fits nothing
        </span>
      </div>

      <h4 className="qr-subhead">What it will do</h4>
      <dl className="qr-grid qr-grid--tight">
        <div>
          <dt>workers</dt>
          <dd className="u-note">chosen from cores and measured free RAM</dd>
        </div>
        <div>
          <dt>threads per worker</dt>
          <dd className="num">1</dd>
        </div>
        <div>
          <dt>checkpoint</dt>
          <dd className="u-note">after every configuration</dd>
        </div>
        <div>
          <dt>resume</dt>
          <dd className="u-note">
            add <code>--resume</code>
          </dd>
        </div>
        <div>
          <dt>holdout</dt>
          <dd className="u-note">no code path opens it</dd>
        </div>
      </dl>
      <p className="body-copy u-note">
        Threads per worker is pinned to 1 in every performance mode. Multi-threaded BLAS
        reorders reductions and changes the last bits of a linear fit, so a mode that
        varied it could return a different number from the same data — a performance
        setting must not be able to move a research result.
      </p>

      <h4 className="qr-subhead">Second machine</h4>
      <pre className="qs-command">python -m scripts.quant.win_gpu_worker --confirm</pre>
      <p className="body-copy u-note">
        Runs EXP-007-WIN-GPU on a CUDA machine: xgboost, lightgbm, catboost and a small
        torch MLP, on the same folds and features. It refuses to start without a visible
        GPU rather than falling back to CPU silently. See docs/HEAVY_TRAINING_WINDOWS.md.
      </p>
    </div>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

/** Chain of custody. Every field is what the artifact recorded, or an em dash. */
export function Provenance({
  search,
  fallbackCommit,
}: {
  search: { [k: string]: unknown }
  fallbackCommit?: string | null
}) {
  const dataset = (search.dataset ?? {}) as Record<string, unknown>
  const machine = (search.machine ?? {}) as Record<string, unknown>
  const versions = (search.package_versions ?? {}) as Record<string, string | null>
  const mt = (search.multiple_testing ?? {}) as Record<string, unknown>
  const holdout = (search.holdout ?? {}) as Record<string, unknown>

  const rows: [string, unknown][] = [
    ['experiment', search.experiment_id],
    ['git commit', search.git_commit ?? fallbackCommit],
    ['working tree', search.git_dirty === undefined ? null : search.git_dirty ? 'DIRTY' : 'clean'],
    ['dataset hash', dataset.content_hash],
    ['dataset rows', typeof dataset.rows === 'number' ? int(dataset.rows) : null],
    ['symbols', dataset.symbols],
    ['dates', dataset.dates],
    ['cumulative trials', mt.cumulative_trials],
    ['workers', search.workers],
    ['runtime', typeof search.runtime_seconds === 'number' ? `${num(search.runtime_seconds / 3600, 2)}h` : null],
    ['generated', search.generated_at],
    ['machine', machine.os ?? null],
    ['gpu', machine.gpu_name ?? null],
    ['holdout', holdout.touched === false ? 'SEALED — never read' : holdout.touched],
  ]

  return (
    <div className="qs">
      <dl className="qr-grid qr-grid--tight">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="num">
              {value === null || value === undefined || value === '' ? '—' : String(value)}
            </dd>
          </div>
        ))}
      </dl>
      {Object.keys(versions).length ? (
        <>
          <h4 className="qr-subhead">Package versions</h4>
          <dl className="qr-grid qr-grid--tight">
            {Object.entries(versions).map(([name, version]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd className="num">{version ?? 'not installed'}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}
      <p className="body-copy u-note">
        A dirty working tree means the code that produced these numbers is not exactly what
        is committed. It is recorded rather than hidden, because a result that cannot be
        traced to a commit cannot be reproduced from one.
      </p>
    </div>
  )
}
