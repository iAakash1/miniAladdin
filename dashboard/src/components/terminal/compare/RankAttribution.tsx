'use client'

/**
 * Why one security ranks above another.
 *
 * Every number here is a subtraction the ranking already performed. The
 * composite is a weighted sum of four terms, so the gap between two securities
 * splits into four contributions that add back up to it exactly, and this
 * panel shows that decomposition ordered by which term did the most work.
 *
 * It is deliberately not a generated explanation. Asked why NVDA ranks above
 * AMD, a model produces fluent, plausible reasons — market position, product
 * cycle, execution — none of which are inputs to the ranking at all. The
 * reader would come away believing the ordering considered things it has never
 * looked at, and nothing on the page would contradict them.
 *
 * The caveat is shown every time and is not boilerplate: ranking above is a
 * position on one composite score, not a claim that one security is the better
 * holding. Both can carry the same signal.
 */

import { useEffect, useState } from 'react'

import {
  AvailabilityNote, type AvailabilityPayload, isAvailable,
} from '@/components/system/Availability'
import { EmptyLine, Panel, Prose, StateBlock, Table, type Column } from '@/components/system'

interface Contribution {
  key: string
  label: string
  reading: string
  weight: number
  a_value: number | null
  b_value: number | null
  difference: number | null
  contribution: number
  share: number
  inverted: boolean
}

interface Attribution extends AvailabilityPayload {
  a?: string
  b?: string
  a_rank?: number | null
  b_rank?: number | null
  rank_gap?: number | null
  leader?: string | null
  level?: boolean
  contributions?: Contribution[]
  unavailable_reason?: string | null
  caveat?: string
  summary?: string
  version?: string
  /** Snapshot provenance, so the panel can date the ordering it explains. */
  data_as_of?: string | null
  universe_version?: string
  stale?: boolean
}

const dash = '—'

/** `??` not `||`: a contribution of exactly 0 is a measurement. */
const num = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined || !Number.isFinite(v) ? dash : v.toFixed(digits)

const signedNum = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined || !Number.isFinite(v)
    ? dash
    : `${v > 0 ? '+' : ''}${v.toFixed(digits)}`

export default function RankAttribution({ a, b }: { a: string; b: string }) {
  const [data, setData] = useState<Attribution | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reading, setReading] = useState(true)

  useEffect(() => {
    let live = true
    void (async () => {
      // The resets live inside the async body rather than in the effect: a
      // fresh pair means the previous answer is no longer about these two
      // securities, and leaving it on screen under a new heading would
      // attribute one comparison's arithmetic to another.
      setReading(true)
      setError(null)
      setData(null)
      try {
        const res = await fetch(
          `/api/compare/rank?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`,
        )
        if (!res.ok) {
          if (live) { setError(`The ordering could not be explained (${res.status}).`); setReading(false) }
          return
        }
        const body = (await res.json()) as Attribution
        if (live) { setData(body); setReading(false) }
      } catch {
        if (live) { setError('OmniSignal could not be reached.'); setReading(false) }
      }
    })()
    return () => { live = false }
  }, [a, b])

  if (reading) {
    return (
      <Panel title="Why this order" subtitle={`${a} against ${b}`}>
        <StateBlock state="waking" title="Reading the ranking" />
      </Panel>
    )
  }

  if (error || data === null) {
    return (
      <Panel title="Why this order" subtitle={`${a} against ${b}`}>
        <StateBlock state="unavailable" title="Not explained" detail={error ?? 'no response'} />
      </Panel>
    )
  }

  if (!isAvailable(data)) {
    return (
      <Panel title="Why this order" subtitle={`${a} against ${b}`}>
        <AvailabilityNote payload={data} />
      </Panel>
    )
  }

  const leader = data.leader ?? null
  const contributions = data.contributions ?? []

  const columns: Column<Contribution>[] = [
    { key: 'label', header: 'Term', render: (c) => c.label },
    {
      key: 'weight', header: 'Weight', numeric: true,
      render: (c) => `${(c.weight * 100).toFixed(0)}%`,
    },
    { key: 'a', header: data.a ?? 'A', numeric: true, render: (c) => num(c.a_value) },
    { key: 'b', header: data.b ?? 'B', numeric: true, render: (c) => num(c.b_value) },
    {
      key: 'contribution',
      header: 'Effect on the gap',
      unit: 'rank points',
      numeric: true,
      render: (c) => (
        <span data-favours={c.contribution === 0 ? undefined : c.contribution > 0 ? 'a' : 'b'}>
          {signedNum(c.contribution)}
        </span>
      ),
    },
    { key: 'share', header: 'Share of movement', numeric: true, render: (c) => `${c.share.toFixed(0)}%` },
  ]

  return (
    <Panel
      title="Why this order"
      subtitle={`${data.a} against ${data.b}`}
      badge={leader ? `${leader} LEADS` : data.level ? 'LEVEL' : undefined}
      badgeTone={leader ? 'info' : 'muted'}
      source={data.version}
      asOf={data.data_as_of ?? null}
    >
      {data.unavailable_reason ? (
        <EmptyLine label="Not decomposable">{data.unavailable_reason}</EmptyLine>
      ) : (
        <>
          {data.summary ? <Prose>{data.summary}</Prose> : null}

          <Table
            columns={columns}
            rows={contributions}
            rowKey={(c) => c.key}
            density="compact"
            empty={<EmptyLine label="No terms">Nothing to decompose.</EmptyLine>}
          />

          {/* The identity, stated where a reader can check it. An explanation
              whose parts do not add to the whole is describing a different
              subtraction from the one the ranking performed. */}
          <p className="ask__meta">
            {data.a} ranks {num(data.a_rank)}, {data.b} ranks {num(data.b_rank)}: a gap of{' '}
            {signedNum(data.rank_gap, 1)} rank points. The effects above sum to that gap
            exactly — the ranking is a weighted sum, so this is its arithmetic, not an
            estimate of it.
          </p>

          <ul className="ra__readings">
            {contributions.map((c) => (
              <li key={c.key}>
                <strong>{c.label}</strong> — {c.reading}
                {c.inverted ? '; a lower number contributes more here' : ''}.
              </li>
            ))}
          </ul>
        </>
      )}

      <Prose>{data.caveat}</Prose>
    </Panel>
  )
}
