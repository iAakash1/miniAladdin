'use client'

/**
 * High conviction — where every condition agrees at once.
 *
 * A distinct concept from Top Ranked Ideas, and deliberately not a view of it.
 * Top Ranked is an ordering: something is always first. This is a threshold:
 * nothing is in it unless it clears every bound, and **most days nothing does**.
 * Merging the two would produce a tier that always has entries, which is a
 * ranking wearing a threshold's name and the single most misleading thing this
 * surface could be.
 *
 * So the empty state is the important state, and it is not an apology. An
 * empty tier means the policy held. What it must not do is stop there: a panel
 * that says only "nothing qualifies" teaches a reader nothing about the bounds
 * being enforced. It shows the near misses and what each was missing, and both
 * come from the backend's own assessment — the same one that decided the tier —
 * so the explanation can never disagree with the decision.
 *
 * Nothing here is a recommendation. A security clearing five conditions has
 * demonstrated that five measurements agree, which is a statement about the
 * evidence and not about what will happen next.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

import { EmptyLine, Panel, Prose, StateBlock, Table, type Column } from '@/components/system'
import { type ExploreRow, type RecommendationsResponse, fetchRecommendations, signalTone } from '@/lib/explore'

const dash = '—'

/** `??` not `||`: 0 is a measurement and must not fall through to a dash. */
const n = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? dash : v.toFixed(digits)

function Conditions({ met, blocked }: { met: string[]; blocked: string[] }) {
  return (
    <ul className="hc__conditions">
      {met.map((c) => (
        <li key={`m-${c}`} data-met="true">
          {/* A mark and a word, never colour alone. */}
          <span aria-hidden>✓</span> <span className="sys-sr-only">Met: </span>{c}
        </li>
      ))}
      {blocked.map((c) => (
        <li key={`b-${c}`} data-met="false">
          <span aria-hidden>✗</span> <span className="sys-sr-only">Not met: </span>{c}
        </li>
      ))}
    </ul>
  )
}

export default function HighConviction({ limit = 5 }: { limit?: number }) {
  const [data, setData] = useState<RecommendationsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reading, setReading] = useState(true)

  useEffect(() => {
    let live = true
    void (async () => {
      try {
        const body = await fetchRecommendations(limit)
        if (live) { setData(body); setReading(false) }
      } catch (e) {
        if (live) {
          setError(e instanceof Error ? e.message : 'the ranking could not be read')
          setReading(false)
        }
      }
    })()
    return () => { live = false }
  }, [limit])

  const columns: Column<ExploreRow>[] = [
    {
      key: 'symbol',
      header: 'Symbol',
      render: (r) => (
        // The canonical shape is ?symbol=, not a path segment: one security,
        // one identity, whichever door the reader came through.
        <Link href={`/terminal/security?symbol=${encodeURIComponent(r.symbol)}`} className="wl__sym">
          {r.symbol}
        </Link>
      ),
    },
    {
      key: 'signal',
      header: 'Signal',
      render: (r) => (
        <span className="xp__signal" data-tone={signalTone(r.model_signal)}>
          {r.model_signal ?? dash}
        </span>
      ),
    },
    { key: 'rank', header: 'Rank', numeric: true, render: (r) => n(r.overall_rank, 1) },
    { key: 'conf', header: 'Confidence', unit: '0–100', numeric: true, render: (r) => n(r.confidence) },
    { key: 'risk', header: 'Risk', unit: '0–100', numeric: true, render: (r) => n(r.risk_score) },
    {
      key: 'complete',
      header: 'Data',
      unit: 'coverage',
      numeric: true,
      render: (r) => (r.data_completeness === null ? dash : `${(r.data_completeness * 100).toFixed(0)}%`),
    },
    {
      key: 'conditions',
      header: 'Conditions',
      render: (r) => <Conditions met={r.conviction_met} blocked={r.conviction_blocked_by} />,
    },
  ]

  if (reading) {
    return (
      <Panel title="High conviction" subtitle="every condition at once">
        <StateBlock state="waking" title="Reading the ranking" />
      </Panel>
    )
  }

  if (error || data === null) {
    return (
      <Panel title="High conviction" subtitle="every condition at once">
        <StateBlock
          state="unavailable"
          title="Cannot be read"
          detail={error ?? 'the ranking could not be read'}
        />
      </Panel>
    )
  }

  const qualifying = data.high_conviction ?? []
  const near = data.near_conviction ?? []

  return (
    <Panel
      title="High conviction"
      subtitle="every condition at once"
      badge={qualifying.length ? `${qualifying.length} QUALIFYING` : 'NONE QUALIFYING'}
      badgeTone={qualifying.length ? 'pass' : 'muted'}
      source={data.conviction_policy_version}
      asOf={data.data_as_of}
      retrievedAt={data.generated_at}
    >
      {qualifying.length ? (
        <>
          <Prose>
            Every condition below agreed at once for these names. That is a
            statement about how well the measurements line up, not a forecast
            and not advice.
          </Prose>
          <Table columns={columns} rows={qualifying} rowKey={(r) => r.symbol} density="compact" />
        </>
      ) : (
        <>
          {/* The expected case, stated as the policy working rather than as a
              shortage. A tier that always had entries would not be a tier. */}
          <EmptyLine label="None qualifying">
            Nothing clears every condition today. That is the normal result —
            this is a threshold, not a ranking, so it is empty whenever the
            measurements disagree.
          </EmptyLine>
          {near.length ? (
            <>
              <Prose>
                The closest, and what each is missing. Ordered by how many
                conditions are unmet — not by preference, and not a
                recommendation.
              </Prose>
              <Table columns={columns} rows={near} rowKey={(r) => r.symbol} density="compact" />
            </>
          ) : (
            <Prose>
              No eligible security has been assessed against the policy yet, so
              there is nothing to report as a near miss either.
            </Prose>
          )}
        </>
      )}

      <Prose>{data.disclaimer}</Prose>
    </Panel>
  )
}
