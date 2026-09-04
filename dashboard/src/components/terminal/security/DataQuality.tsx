'use client'

/**
 * How much of this can be relied on.
 *
 * The research payload has always carried two cross-provider audits and the
 * interface has never shown either. `series_integrity` reconciles the daily
 * closes every vendor returned against each other, session by session.
 * `consensus_price` collects each vendor's last price with the basis it was
 * measured on. Both were computed on every request and discarded.
 *
 * Exposing them turned up a defect in the second one.
 *
 * For Apple the payload reports `conflict: true`, four providers, and a
 * dispersion of 2.25%. Read as it stands that says the vendors disagree about
 * Apple's price by seven dollars. They do not. Three of them report a *last
 * sale* — 321.03, 320.98 and 321.03, a spread of 0.02% — and the fourth
 * reports the *previous session's close*, from the day before. The 2.25% is
 * the distance between a last sale and a prior close. It is not disagreement;
 * it is two different measurements taken a day apart, differenced.
 *
 * So the readings are grouped by what they measure before anything is said
 * about whether they agree, and the judgement comes from `comparable()` —
 * the same engine the comparison page and the security page use — rather
 * than from a rule written here. A vendor that does not state its basis is
 * its own group, because an unstated basis cannot be assumed to match a
 * stated one.
 *
 * The first audit needed no correction, only a caveat it was not carrying.
 * Agreement is measured on sessions at least two providers returned, and for
 * Apple that is 65 of 92. "100% agreed" is true of the 71% of the series that
 * could be checked at all; the remaining 27 sessions rest on one vendor and
 * were never cross-checked by anything. A quality panel that reported the
 * first number without the second would be doing the thing it exists to stop.
 *
 * Nothing here is scored. There is no letter grade, no percentage of health
 * and no weighted index, because every one of those is an opinion wearing a
 * number's clothes. Each figure is a count of something that was actually
 * counted, next to what it was counted over.
 */

import { useEffect, useState } from 'react'

import { EmptyLine, Inspectable, Panel, Prose, StateBlock, Value } from '@/components/system'
import { comparable } from '@/lib/semantics'
import { fetchResearch } from '@/lib/research-cache'
import { format } from '@/lib/quantity'
import { timeAgo } from '@/lib/format'

interface Integrity {
  providers?: string[]
  coverage?: Record<string, number>
  shared_sessions?: number
  union_sessions?: number
  agreeing_sessions?: number
  agreement_pct?: number
  max_divergence_pct?: number
  tolerance_pct?: number
  conflicts?: { date?: string; divergence_pct?: number; readings?: Record<string, number> }[]
  conflict_count?: number
  adjustment_mismatch?: {
    provider?: string
    ratio?: number
    stability?: number
    sessions?: number
    likely_split?: string | null
  }[]
  session_gaps?: Record<string, number>
}

interface Reading {
  provider?: string
  price?: number | null
  basis?: string | null
  as_of?: string | null
  latency_ms?: number | null
}

interface Consensus {
  consensus?: number | null
  dispersion_pct?: number | null
  provider_count?: number
  agreeing?: number
  agreement?: string
  conflict?: boolean
  readings?: Reading[]
}

/** A vendor that returned a price without saying what the price is of. */
export const UNSTATED = 'basis not stated'

/** The widest gap in a set of prices, as a percentage of the smallest. */
export function spreadPct(prices: number[]): number | null {
  if (prices.length < 2) return null
  const lo = Math.min(...prices)
  const hi = Math.max(...prices)
  return lo > 0 ? ((hi - lo) / lo) * 100 : null
}

export interface Priced { provider?: string; price: number; basis?: string | null; as_of?: string | null; latency_ms?: number | null }

export interface ReadingAssessment {
  /** Readings that carried a usable number, cheapest first. */
  sorted: Priced[]
  /**
   * The same readings in reading order: grouped by basis, cheapest first
   * inside each group, with the unlabelled ones last.
   *
   * Sorting the table by price alone interleaved the bases — the previous
   * session's close landed between two last sales — which is precisely the
   * mixing the panel exists to undo. A table that argues one thing in prose
   * and shows another in its row order teaches the reader to trust neither.
   */
  ordered: Priced[]
  /** Readings by what they measure. A missing basis is its own group. */
  groups: Map<string, Priced[]>
  /** The bases vendors actually named. */
  stated: string[]
  /** The verdict on the two readings that produce the widest gap. */
  extremes: ReturnType<typeof comparable> | null
  /** The widest spread found *inside* a single basis — real disagreement. */
  worstWithin: { basis: string; n: number; spread: number } | null
}

/**
 * What the vendor readings actually say, before anything is claimed about
 * whether they agree.
 *
 * Pulled out of the component because it is the part that can be wrong in a
 * way nobody would see. Grouping by basis and asking `comparable()` about the
 * two extreme readings is the whole correction this panel makes to the
 * payload's own conflict flag; leaving it inline would mean the only check on
 * it was reading the JSX.
 */
export function assessReadings(input: readonly Reading[]): ReadingAssessment {
  const readings = input.filter(
    (r): r is Priced => typeof r.price === 'number' && Number.isFinite(r.price),
  )

  const groups = new Map<string, Priced[]>()
  for (const r of readings) {
    const key = r.basis?.trim() || UNSTATED
    const list = groups.get(key)
    if (list) list.push(r)
    else groups.set(key, [r])
  }

  const sorted = [...readings].sort((a, b) => a.price - b.price)
  const lowest = sorted[0]
  const highest = sorted[sorted.length - 1]

  /* The two readings that produce the payload's dispersion. Asking the
     semantic layer about *these two* is what explains the number a reader is
     looking at, rather than about some other pair that happens to differ. */
  const extremes = lowest && highest && lowest !== highest
    ? comparable(
      { kind: 'currency', basis: lowest.basis ?? undefined },
      { kind: 'currency', basis: highest.basis ?? undefined },
    )
    : null

  /* Agreement measured only where it means something: inside one basis. */
  const within = [...groups.entries()]
    .map(([basis, rs]) => ({ basis, n: rs.length, spread: spreadPct(rs.map((r) => r.price)) }))
    .filter((g): g is { basis: string; n: number; spread: number } => g.spread !== null)

  const stated = [...groups.keys()].filter((b) => b !== UNSTATED)
  const ordered = [...stated, ...(groups.has(UNSTATED) ? [UNSTATED] : [])]
    .flatMap((b) => [...groups.get(b)!].sort((x, y) => x.price - y.price))

  return {
    sorted,
    ordered,
    groups,
    stated,
    extremes,
    worstWithin: within.length ? within.reduce((a, b) => (b.spread > a.spread ? b : a)) : null,
  }
}

/**
 * What the providers are each measuring, as one sentence.
 *
 * Here rather than in the JSX because building an English list out of nested
 * ternaries in a template produced "2 report the last sale and 1 reports the
 * previous session close, and 1 does not say" — two conjunctions doing the
 * work of one, from a list-joining rule that only ever handled two items.
 */
export function describeGroups(a: ReadingAssessment): string {
  const clauses = a.stated.map((b) => {
    const n = a.groups.get(b)!.length
    return `${n} report${n === 1 ? 's' : ''} the ${b}`
  })
  const unstated = a.groups.get(UNSTATED)
  if (unstated) {
    clauses.push(
      `${unstated.length} do${unstated.length === 1 ? 'es' : ''} not say what the figure is of`,
    )
  }
  if (clauses.length <= 1) return clauses[0] ?? ''
  if (clauses.length === 2) return `${clauses[0]} and ${clauses[1]}`
  return `${clauses.slice(0, -1).join(', ')}, and ${clauses[clauses.length - 1]}`
}

type Answer =
  | { for: string; integrity: Integrity | null; consensus: Consensus | null }
  | { for: string; error: string }

export default function DataQuality({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = raw as { series_integrity?: Integrity; consensus_price?: Consensus }
        setAnswer({
          for: symbol,
          integrity: d.series_integrity ?? null,
          consensus: d.consensus_price ?? null,
        })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, error: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  if (!settled) {
    return (
      <Panel title="Data quality" subtitle="how much of this can be relied on" state="waking">
        <StateBlock state="waking" title="Reconciling the providers against each other" />
      </Panel>
    )
  }
  if ('error' in settled) {
    return (
      <Panel title="Data quality" subtitle="how much of this can be relied on" state="unavailable">
        <StateBlock
          state="unavailable"
          title="The cross-provider audit could not be read"
          detail={`${settled.error}. The price and chart above come from a single provider path and are unaffected — but nothing has checked them against a second vendor.`}
        />
      </Panel>
    )
  }

  const { integrity, consensus } = settled

  if (!integrity && !consensus) {
    return (
      <EmptyLine label="Data quality">
        No cross-provider reconciliation was returned for this security. That
        happens when fewer than two providers answered, in which case there was
        nothing to check one against — it is not a statement that the data
        above agreed.
      </EmptyLine>
    )
  }

  /* ── the price series, provider against provider ──────────────────────── */

  const cov = integrity?.coverage ?? {}
  const union = integrity?.union_sessions ?? 0
  const shared = integrity?.shared_sessions ?? 0
  /* Sessions exactly one vendor returned. `shared` counts dates with two or
     more providers, so this is the part of the series that no second source
     ever saw — the number the agreement percentage above it does not cover. */
  const unchecked = union && shared ? union - shared : 0
  const covered = union ? (shared / union) * 100 : null
  const gaps = Object.entries(integrity?.session_gaps ?? {}).filter(([, n]) => n > 0)

  /* ── the last price, reading against reading ──────────────────────────── */

  const assessment = assessReadings(consensus?.readings ?? [])
  const { sorted, ordered, groups, extremes, worstWithin } = assessment
  const readings = sorted
  const lowest = sorted[0]
  const highest = sorted[sorted.length - 1]

  return (
    <Panel title="Data quality" subtitle="how much of this can be relied on" flush>

      {integrity ? (
        <div className="dq__block">
          <div className="dq__head">
            <span className="sys-label">Price history</span>
            <span className="sys-meta">
              {(integrity.providers ?? []).length} providers reconciled session by session
            </span>
          </div>

          <p className="dq__lede">
            {shared.toLocaleString()} of {union.toLocaleString()} sessions were
            returned by more than one provider.{' '}
            {typeof integrity.agreeing_sessions === 'number'
              && typeof integrity.tolerance_pct === 'number' ? (
              <>
                {integrity.agreeing_sessions === shared
                  ? `All ${shared.toLocaleString()} agreed`
                  : `${integrity.agreeing_sessions.toLocaleString()} of them agreed`}{' '}
                within {integrity.tolerance_pct}%
                {typeof integrity.max_divergence_pct === 'number'
                  ? `, the widest gap on any one session being ${integrity.max_divergence_pct}%`
                  : ''}.
              </>
            ) : null}
          </p>

          {unchecked > 0 ? (
            <p className="dq__caveat">
              The other {unchecked.toLocaleString()} came from one provider
              only and were never checked against a second source. Agreement
              above describes{' '}
              {covered !== null ? `${covered.toFixed(0)}%` : 'part'} of the
              series, not all of it.
            </p>
          ) : null}

          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact dq__tbl">
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col" className="num">Sessions returned</th>
                  <th scope="col" className="num">Missing from the overlap</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(cov).sort((a, b) => b[1] - a[1]).map(([p, n]) => (
                  <tr key={p}>
                    <td>{p}</td>
                    <td className="num">
                      <Inspectable refValue={{
                        label: `${p} · sessions returned`,
                        display: n.toLocaleString(),
                        claim: `${p} returned ${n.toLocaleString()} daily closes for this security.`,
                        observation: `A count of bars in ${p}'s response, against ${union.toLocaleString()} distinct sessions across all providers.`,
                        method: 'counted from the bars each provider returned — vendors interpret a request for the same window differently, so a lower count is usually a shorter window rather than missing data',
                        source: p,
                        status: 'recorded',
                        failsWhen: [
                          'The provider was asked for, and correctly returned, a shorter window than another provider — in which case this is not a coverage defect.',
                        ],
                      }}>
                        {n.toLocaleString()}
                      </Inspectable>
                    </td>
                    <td className="num">
                      {integrity.session_gaps?.[p]
                        ? <Value value={integrity.session_gaps[p]} kind="count" digits={0} />
                        : <span className="sys-null" title="no session missing inside the window every provider covers">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {gaps.length ? (
            <Prose size="fine">
              A missing session is counted only inside the window every
              provider covers, so it is a session that vendor genuinely lacks
              while others have it — not a vendor penalised for being asked for
              a shorter history.
            </Prose>
          ) : null}

          {integrity.conflict_count ? (
            <div className="dq__alert">
              <div className="sys-label">Sessions where the providers disagree</div>
              <ul>
                {(integrity.conflicts ?? []).slice(0, 5).map((c) => (
                  <li key={c.date}>
                    {c.date} — {c.divergence_pct}% apart:{' '}
                    {Object.entries(c.readings ?? {})
                      .map(([p, v]) => `${p} ${v}`)
                      .join(', ')}
                  </li>
                ))}
              </ul>
              <p>
                {integrity.conflict_count} session
                {integrity.conflict_count === 1 ? '' : 's'} exceeded the{' '}
                {integrity.tolerance_pct}% tolerance. Nothing here has been
                reconciled or corrected — the chart above draws one provider&apos;s
                series, and on these dates a different provider reported a
                different close.
              </p>
            </div>
          ) : null}

          {integrity.adjustment_mismatch?.length ? (
            <div className="dq__alert">
              <div className="sys-label">A provider is adjusting differently</div>
              <ul>
                {integrity.adjustment_mismatch.map((m) => (
                  <li key={m.provider}>
                    {m.provider} sits at {m.ratio}× the median across{' '}
                    {m.sessions} sessions
                    {m.likely_split ? `, which is close to a ${m.likely_split} split` : ''}
                  </li>
                ))}
              </ul>
              <p>
                A stable ratio rather than a scatter is the signature of a
                split or dividend adjustment policy, not of a wrong print.
                Nothing has been rescaled: guessing at an adjustment is how a
                chart becomes confidently wrong.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* ── last price ─────────────────────────────────────────────────── */}

      {readings.length ? (
        <div className="dq__block">
          <div className="dq__head">
            <span className="sys-label">Last price</span>
            <span className="sys-meta">
              {readings.length} providers, {groups.size === 1
                ? 'all measuring the same thing'
                : `measuring ${groups.size} different things`}
            </span>
          </div>

          {groups.size > 1 ? (
            <p className="dq__lede">
              These are not all answers to the same question.{' '}
              {describeGroups(assessment)}.
            </p>
          ) : null}

          <div className="sys-scroll-x">
            <table className="sys-table sys-table--compact dq__tbl">
              <thead>
                <tr>
                  <th scope="col">Provider</th>
                  <th scope="col" className="num">Price</th>
                  <th scope="col">What it measures</th>
                  <th scope="col">Observed</th>
                  <th scope="col" className="num">Reply</th>
                </tr>
              </thead>
              <tbody>
                {ordered.map((r) => (
                  <tr key={r.provider ?? String(r.price)}>
                    <td>{r.provider ?? 'unnamed provider'}</td>
                    <td className="num">
                      <Inspectable refValue={{
                        label: `${r.provider ?? 'provider'} · last price`,
                        display: format(r.price, 'currency').text,
                        claim: r.basis
                          ? `${r.provider ?? 'This provider'} reports the ${r.basis} at ${format(r.price, 'currency').text}.`
                          : `${r.provider ?? 'This provider'} reports ${format(r.price, 'currency').text} without saying what the figure is of.`,
                        observation: r.as_of
                          ? `One reading, observed ${r.as_of}.`
                          : 'One reading, with no observation time supplied.',
                        source: r.provider,
                        asOf: r.as_of ?? undefined,
                        method: r.basis
                          ? `as reported, on a ${r.basis} basis — not averaged with any other provider`
                          : 'as reported — the provider did not state the basis, so this cannot be assumed to be a last sale',
                        status: 'live',
                        freshness: 'read once per research request',
                        failsWhen: r.basis
                          ? [`Compared with a reading on any basis other than a ${r.basis}, the difference is a change of measurement rather than a change in price.`]
                          : ['The basis is unknown, so any difference from another provider cannot be attributed to the market rather than to the measurement.'],
                      }}>
                        <Value value={r.price} kind="currency" />
                      </Inspectable>
                    </td>
                    <td>
                      {r.basis
                        ? r.basis
                        : <span className="dq__unstated" title="the provider returned a price without stating what it is a price of">not stated</span>}
                    </td>
                    <td className="dq__when">
                      {r.as_of
                        ? <>{r.as_of.slice(0, 10)}<span className="dq__ago">{timeAgo(r.as_of)}</span></>
                        : <span className="sys-null">—</span>}
                    </td>
                    <td className="num">
                      {typeof r.latency_ms === 'number'
                        ? <Value value={r.latency_ms} kind="count" digits={0} />
                        : <span className="sys-null">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {extremes && !extremes.ok ? (
            <div className="dq__alert">
              <div className="sys-label">
                {consensus?.conflict
                  ? 'The flagged conflict is a difference of measurement'
                  : 'The spread is a difference of measurement'}
              </div>
              <p>
                The widest gap here is between {lowest.provider} at{' '}
                {format(lowest.price, 'currency').text} and {highest.provider}{' '}
                at {format(highest.price, 'currency').text}
                {typeof consensus?.dispersion_pct === 'number'
                  ? `, which the payload reports as a dispersion of ${consensus.dispersion_pct}%`
                  : ''}. Those two figures are {extremes.reason}, so
                differencing them measures the change of basis, not a
                disagreement about price.
              </p>
              {worstWithin && worstWithin.n > 1 ? (
                <p>
                  Among the {worstWithin.n} providers that do report the{' '}
                  {worstWithin.basis}, the spread is{' '}
                  {worstWithin.spread.toFixed(2)}%. That is the number that
                  describes whether these vendors agree.
                </p>
              ) : null}
            </div>
          ) : null}

          {extremes?.caveat ? (
            <div className="dq__alert">
              <div className="sys-label">One provider does not say what it measured</div>
              <p>{extremes.caveat}. Its reading cannot be treated as
                agreeing or disagreeing with the others, because what it is a
                price of was never stated.</p>
            </div>
          ) : null}

          {typeof consensus?.consensus === 'number' ? (
            <Prose size="fine">
              The payload also carries a single consensus figure of{' '}
              {format(consensus.consensus, 'currency').text} and does not
              record how it was chosen. It is shown here rather than in the
              price above the chart, and it is not used to compute anything:
              an unlabelled aggregation of readings on different bases is not
              a price this product is willing to assert.
            </Prose>
          ) : null}
        </div>
      ) : null}

      <Prose size="fine">
        Every count here was counted, not scored. There is no quality grade,
        because a grade would fold coverage, agreement and freshness — three
        things with different causes and different remedies — into one number
        that hides all three. Agreement between providers is evidence that a
        figure was recorded consistently; it is not evidence that it is right,
        and vendors sharing an upstream source can agree in error.
      </Prose>
    </Panel>
  )
}
