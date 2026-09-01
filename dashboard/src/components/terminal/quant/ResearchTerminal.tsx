'use client'

/**
 * The top of the research terminal: status rail, executive summary, firewall.
 *
 * These three answer, in order, the questions a reviewer asks in the first ten
 * seconds — what is running, what is known, and what stops any of it reaching
 * production. Everything below them on the page is detail.
 *
 * The rail's job is to make one distinction impossible to miss: **a running
 * experiment is not a production system.** A search at 92% with a rising
 * t-statistic reads as momentum unless the promotion state and the holdout
 * state sit in the same row at the same weight. So they do.
 *
 * Nothing here computes a verdict. Every value is read from an API response or
 * rendered as an em dash.
 */

import { int, num, sign } from './format'
import type { SearchState, SelectionState } from './searchTypes'

type RailTone = 'neutral' | 'active' | 'blocked' | 'sealed' | 'pass'

interface RailCell {
  label: string
  value: string
  detail?: string
  tone: RailTone
}

export function StatusRail({
  search,
  production,
  candidates,
  holdoutArmed,
  integrityClean,
}: {
  search: SearchState | null
  production: number | null | undefined
  candidates: number | null | undefined
  holdoutArmed: boolean | undefined
  integrityClean: boolean | null | undefined
}) {
  const state = search?.available ? search.state : 'NOT STARTED'
  const evaluated = search?.configurations_evaluated
  const planned = search?.configurations_planned

  const cells: RailCell[] = [
    {
      label: 'experiment',
      value: search?.experiment_id ?? 'EXP-007',
      detail: 'staged model search',
      tone: 'neutral',
    },
    {
      label: 'search',
      value: state,
      detail:
        state === 'RUNNING' && evaluated && planned
          ? `${int(evaluated)}/${int(planned)} configurations`
          : state === 'COMPLETE' && evaluated
            ? `${int(evaluated)} configurations`
            : undefined,
      tone: state === 'RUNNING' ? 'active' : 'neutral',
    },
    {
      label: 'research state',
      value: 'DEVELOPMENT',
      detail: 'validation folds only',
      tone: 'neutral',
    },
    {
      label: 'promotion',
      value: 'BLOCKED',
      detail: `${int(candidates ?? 0)} candidates`,
      tone: 'blocked',
    },
    {
      // An unknown firewall state is reported as unknown, never as SEALED.
      // Defaulting a safety control to its safe value is how a page ends up
      // reassuring someone about something it never checked.
      label: 'holdout',
      value: holdoutArmed === undefined ? 'UNKNOWN' : holdoutArmed ? 'ARMED' : 'SEALED',
      detail:
        holdoutArmed === undefined
          ? 'firewall state unavailable'
          : holdoutArmed
            ? 'contract armed'
            : 'contract not armed',
      tone: holdoutArmed === undefined ? 'neutral' : holdoutArmed ? 'blocked' : 'sealed',
    },
    {
      label: 'production',
      value: int(production ?? 0),
      detail: 'models serving',
      tone: (production ?? 0) > 0 ? 'pass' : 'neutral',
    },
    {
      label: 'integrity',
      value: integrityClean === false ? 'FAILED' : integrityClean ? 'CLEAN' : 'UNKNOWN',
      detail: 'point-in-time controls',
      tone: integrityClean === false ? 'blocked' : integrityClean ? 'pass' : 'neutral',
    },
  ]

  return (
    <div className="qt-rail" role="group" aria-label="Research status">
      {cells.map((cell) => (
        <div key={cell.label} className={`qt-rail__cell qt-rail__cell--${cell.tone}`}>
          <span className="qt-rail__label">{cell.label}</span>
          <span className="qt-rail__value">{cell.value}</span>
          <span className="qt-rail__detail">{cell.detail ?? ' '}</span>
        </div>
      ))}
    </div>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

/**
 * What is being asked, what is settled, and what is not.
 *
 * The "not yet known" column is the one that matters while a search is in
 * flight. A page that lists only what has been measured invites the reader to
 * treat a partial leaderboard as a conclusion, so the open questions are given
 * the same visual weight as the answered ones.
 */
export function ExecutiveSummary({
  search,
  selection,
  trials,
}: {
  search: SearchState | null
  selection: SelectionState | null
  trials?: number | null
}) {
  const running = search?.state === 'RUNNING'
  const complete = search?.state === 'COMPLETE'
  const mt = search?.multiple_testing
  const selected = selection?.available && selection.verdict

  const settled: [string, string][] = [
    [
      'EXP-004',
      'No learned model beat free factor baselines on the corrected pipeline.',
    ],
    [
      'EXP-005',
      'No additional data source — options, estimates, fundamentals — added information over price.',
    ],
    [
      'EXP-006',
      'The frozen 27-feature set cleared three gates of four. Gross Sharpe +0.384, net Sharpe −0.102 at 10 bp. Six-factor alpha t +0.047.',
    ],
  ]

  const open: [string, string][] = selected
    ? []
    : [
        [
          'candidate selection',
          running
            ? 'Search in progress — final candidate selection unavailable.'
            : complete
              ? 'Search complete; selection has not been run.'
              : 'The search has not been run.',
        ],
        [
          'economics',
          'No backtest, cost sweep, attribution or turnover has been computed for any configuration in this search. Validation IC alone cannot answer whether anything is tradeable.',
        ],
        [
          'gate verdict',
          'Eight predeclared gates. None have been evaluated for this experiment.',
        ],
      ]

  return (
    <section className="qt-exec">
      <header className="qt-exec__head">
        <h2 className="qt-exec__title">
          Was the fixed model ladder the limit?
        </h2>
        <p className="qt-exec__lede">
          Every study before EXP-007 fixed the model ladder and varied one thing. EXP-006&rsquo;s
          winner ran on library defaults because that is what the ladder declared, not because
          anything chose them. This search asks whether a configuration that was never selected
          does better — across families, hyperparameters, feature arms and targets, in four
          controlled stages.
        </p>
      </header>

      <div className="qt-exec__grid">
        <div className="qt-exec__col">
          <h3 className="qt-label">Search scale</h3>
          <dl className="qt-defs">
            <div>
              <dt>configurations</dt>
              <dd>
                {search?.configurations_evaluated !== undefined
                  ? `${int(search.configurations_evaluated)} of ${int(search.configurations_planned)}`
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>cumulative trials</dt>
              <dd>{int(mt?.cumulative_trials ?? trials)}</dd>
            </div>
            <div>
              <dt>required |t|</dt>
              <dd>{num(mt?.expected_max_abs_t_under_null, 2)}</dd>
            </div>
            <div>
              <dt>observed max |t|</dt>
              <dd>{num(mt?.observed_max_abs_t, 2)}</dd>
            </div>
          </dl>
        </div>

        <div className="qt-exec__col">
          <h3 className="qt-label">Settled by prior studies</h3>
          <ul className="qt-list">
            {settled.map(([id, text]) => (
              <li key={id}>
                <span className="qt-list__tag">{id}</span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <div className="qt-exec__col">
          <h3 className="qt-label">
            {open.length ? 'Not yet known' : 'Verdict'}
          </h3>
          {open.length ? (
            <ul className="qt-list qt-list--open">
              {open.map(([id, text]) => (
                <li key={id}>
                  <span className="qt-list__tag qt-list__tag--open">{id}</span>
                  {text}
                </li>
              ))}
            </ul>
          ) : (
            <ul className="qt-list">
              <li>
                <span
                  className={`qt-list__tag ${
                    selection?.verdict?.passed ? '' : 'qt-list__tag--open'
                  }`}
                >
                  {selection?.verdict?.status}
                </span>
                {selection?.verdict?.failed?.length
                  ? `Failed: ${selection.verdict.failed.join(', ')}.`
                  : 'Every predeclared gate passed. Development candidate only — the holdout is untouched and promotion remains blocked.'}
              </li>
            </ul>
          )}
        </div>
      </div>

      <p className="qt-exec__foot">
        <strong>What prevents promotion.</strong> Promotion reads the model registry, not any
        leaderboard on this page. It requires a complete evidence bundle <em>and</em> passing
        numbers — a validation t-statistic is necessary and nowhere near sufficient. EXP-006
        demonstrates the gap precisely: a statistically significant IC, a positive gross Sharpe,
        and a negative net Sharpe once costs are charged.
      </p>
    </section>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

/**
 * The holdout, presented as the boundary it is.
 *
 * Deliberately styled as a barrier rather than a metric card. The holdout is
 * not a number that moved; it is a control with two states, and the page should
 * read wrong the moment it is armed.
 */
export function HoldoutFirewall({
  armed,
  start,
  end,
  sessions,
  touched,
}: {
  armed: boolean | undefined
  start?: string | null
  end?: string | null
  sessions?: number | null
  touched?: boolean
}) {
  return (
    <section
      className={`qt-firewall${armed ? ' qt-firewall--armed' : ''}${
        armed === undefined ? ' qt-firewall--unknown' : ''
      }`}
    >
      <div className="qt-firewall__bar" aria-hidden />
      <div className="qt-firewall__body">
        <div className="qt-firewall__head">
          <span className="qt-firewall__state">
            {armed === undefined ? 'UNKNOWN' : armed ? 'ARMED' : 'SEALED'}
          </span>
          <h3 className="qt-firewall__title">Validation firewall</h3>
        </div>
        <dl className="qt-firewall__facts">
          <div>
            <dt>window</dt>
            <dd>{start && end ? `${start} → ${end}` : '—'}</dd>
          </div>
          <div>
            <dt>sessions</dt>
            <dd>{int(sessions)}</dd>
          </div>
          <div>
            <dt>rows accessed</dt>
            <dd>{touched === false ? 'NONE' : touched ? 'ACCESSED' : 'UNKNOWN'}</dd>
          </div>
          <div>
            <dt>contract</dt>
            <dd>{armed === undefined ? 'UNKNOWN' : armed ? 'ARMED' : 'NOT ARMED'}</dd>
          </div>
        </dl>
        <p className="qt-firewall__note">
          <code>assert_clear</code> runs on the training frame and the validation frame of
          every fold immediately before every fit — several hundred times over this search,
          not once at the boundary. There is no environment variable that relaxes it: setting{' '}
          <code>QUANT_DISABLE_HOLDOUT_FIREWALL</code> makes the firewall raise rather than lift.
          Selection reads validation folds only.
        </p>
      </div>
    </section>
  )
}

/* ────────────────────────────────────────────────────────────────────────── */

/**
 * A compact metric with its methodology attached.
 *
 * The methodology line is not decoration. A Sharpe ratio without its cost
 * assumption and a VaR without its estimator are both unfalsifiable, and a
 * research page that prints them bare is asking to be misread.
 */
export function Metric({
  label,
  value,
  method,
  status,
}: {
  label: string
  value: string
  method?: string
  status?: 'pass' | 'fail' | 'warn' | 'none'
}) {
  return (
    <div className={`qt-metric qt-metric--${status ?? 'none'}`}>
      <span className="qt-metric__label">{label}</span>
      <span className="qt-metric__value">{value}</span>
      {method ? <span className="qt-metric__method">{method}</span> : null}
    </div>
  )
}

/**
 * The EXP-006 headline, arranged so the blocking number cannot be skimmed past.
 *
 * Ordering is deliberate and is the opposite of flattering: the gates it failed
 * come first, at full size, and the strong statistics follow. A layout that
 * leads with IC +0.0290 and t +2.66 and puts net Sharpe last is technically
 * complete and practically a sales page.
 */
export function BlockedHeadline({
  ic,
  icT,
  grossSharpe,
  netSharpe,
  turnover,
  alphaT,
  modelId,
}: {
  ic: number | null | undefined
  icT: number | null | undefined
  grossSharpe: number | null | undefined
  netSharpe: number | null | undefined
  turnover: number | null | undefined
  alphaT: number | null | undefined
  modelId?: string | null
}) {
  return (
    <div className="qt-blocked">
      <div className="qt-blocked__head">
        <span className="qt-blocked__flag">PROMOTION BLOCKED</span>
        <span className="qt-blocked__model">{modelId ?? '—'}</span>
        <span className="qt-blocked__exp">EXP-006 · 27 features · fwd_rank_21</span>
      </div>
      <div className="qt-blocked__metrics">
        <Metric
          label="net Sharpe"
          value={sign(netSharpe, 3)}
          method="after commission, 10 bp assumed half-spread, slippage, impact"
          status={(netSharpe ?? -1) > 0 ? 'pass' : 'fail'}
        />
        <Metric
          label="alpha t-stat"
          value={sign(alphaT, 3)}
          method="six-factor: FF5 + momentum, Newey-West"
          status={(alphaT ?? 0) > 2 ? 'pass' : 'fail'}
        />
        <Metric
          label="turnover"
          value={turnover === null || turnover === undefined ? '—' : `${num(turnover, 1)}×`}
          method="annualised, one-way"
          status={(turnover ?? 99) <= 30 ? 'warn' : 'fail'}
        />
        <Metric
          label="gross Sharpe"
          value={sign(grossSharpe, 3)}
          method="before any cost is charged"
          status={(grossSharpe ?? 0) > 0 ? 'pass' : 'fail'}
        />
        <Metric
          label="validation IC"
          value={sign(ic)}
          method="Spearman, pooled across 8 walk-forward folds"
          status="none"
        />
        <Metric
          label="IC t-stat"
          value={sign(icT, 2)}
          method="Newey-West, Bartlett kernel"
          status={(icT ?? 0) >= 2 ? 'pass' : 'fail'}
        />
      </div>
      <p className="qt-blocked__note">
        A significant t-statistic and a positive gross Sharpe do not make a model
        deployable. The gross edge here is real and small; turnover consumes it at the
        declared cost assumption, and what survives is not distinguishable from factor
        exposure. This is the whole reason the gate exists.
      </p>
    </div>
  )
}
