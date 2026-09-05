'use client'

/**
 * What this security has, and where it is.
 *
 * The context column used to hold three paragraphs of onboarding — what the
 * page answers, what a ticker is, that predictions are not instructions. All
 * true, all read once, and all occupying a fifth of the screen on every visit
 * for the rest of the reader's life. The provenance those paragraphs were
 * standing in for now travels with the figures themselves.
 *
 * This replaces them with the one thing a column beside an object should do:
 * say what the object is made of. Each row is a section of the page with the
 * count it actually contains — ten filings, twenty-eight ratios, thirteen
 * articles — and clicking it goes there.
 *
 * It doubles as the honest loading indicator this page never had. The research
 * fan-out takes between twenty-five and sixty-five seconds; until now that was
 * invisible unless you happened to be looking at the section that was waiting.
 * Here the whole shape of the object fills in as it arrives, so the wait reads
 * as progress rather than as absence.
 *
 * Counts are read from the payload and never inferred. A section whose data
 * did not come back says so; it does not show a zero.
 */

import { useEffect, useState } from 'react'

import { Panel } from '@/components/system'
import { fetchResearch } from '@/lib/research-cache'

/** What a row can say about itself, in the order the page presents them. */
interface Section {
  id: string
  label: string
  /** The real count, when the payload carries one. */
  count?: number | null
  /** A word where a count would be meaningless — "blocked", "live". */
  note?: string | null
  /** Nothing came back for this section. */
  absent?: boolean
}

interface Payload {
  profile?: Record<string, unknown>
  ratios?: Record<string, unknown>
  ownership?: Record<string, unknown>
  filings?: { filings?: unknown[]; xbrl?: Record<string, unknown[]> }
  news_stream?: { collected?: number; unique?: number }
  series_integrity?: { providers?: string[] }
  statements?: { reported?: unknown[] }
  street_intelligence?: { recommendations?: { analysts?: number } }
}

/* Every answer is tagged with the symbol it belongs to, so a slow reply for
   one name can never overwrite a fast one for the next. Waiting is not a
   state that has to be set — it is simply the absence of an answer for the
   symbol currently on screen, derived at render. Setting it synchronously in
   the effect is what triggers the cascading render React warns about. */
type Answer =
  | { for: string; sections: Section[] }
  | { for: string; reason: string }

export default function SecurityContext({ symbol }: { symbol: string }) {
  const [answer, setAnswer] = useState<Answer | null>(null)

  useEffect(() => {
    let alive = true
    fetchResearch(symbol)
      .then((raw) => {
        if (!alive) return
        const d = (raw ?? {}) as Payload
        const n = (v: unknown) => (v && typeof v === 'object' ? Object.keys(v).length : 0)

        setAnswer({
          for: symbol,
          sections: [
            { id: 'sec-company', label: 'Company', absent: !d.profile, note: d.profile ? 'live' : null },
            { id: 'sec-fundamentals', label: 'Fundamentals', count: n(d.ratios) || null, absent: !n(d.ratios) },
            { id: 'sec-fundamentals', label: 'Ownership', count: n(d.ownership) || null, absent: !n(d.ownership) },
            {
              id: 'sec-company',
              label: 'Filings',
              count: d.filings?.filings?.length ?? null,
              absent: !d.filings?.filings?.length,
            },
            {
              id: 'sec-market',
              label: 'Market statistics',
              note: 'derived here',
            },
            {
              id: 'sec-financials',
              label: 'Filed financials',
              // Concepts that came back with at least one fact. A concept
              // present but empty is not something this page can show.
              count: Object.values(d.filings?.xbrl ?? {}).filter((v) => Array.isArray(v) && v.length).length || null,
              absent: !Object.values(d.filings?.xbrl ?? {}).some((v) => Array.isArray(v) && v.length),
            },
            {
              id: 'sec-reported',
              label: 'Reported figures',
              /* Comparable groups, not raw figures: the same concept arrives
                 on several bases and periods, and the count that matters is
                 how many distinct measurements came back. */
              count: d.statements?.reported?.length ?? null,
              absent: !d.statements?.reported?.length,
            },
            {
              id: 'sec-quality',
              label: 'Data quality',
              /* Providers actually reconciled against each other, which is
                 not the same as providers asked. A name where only one vendor
                 answered has nothing to cross-check and says so rather than
                 showing a one. */
              count: d.series_integrity?.providers?.length ?? null,
              absent: !d.series_integrity?.providers?.length,
            },
            {
              id: 'sec-street',
              label: 'Street',
              /* Analysts on the ratings panel. The price-target panel counts
                 a different number and neither is authoritative, so the index
                 names one and the section shows both. */
              count: d.street_intelligence?.recommendations?.analysts ?? null,
              absent: !d.street_intelligence?.recommendations?.analysts,
            },
            {
              id: 'sec-options',
              label: 'Options',
              // Options come from a different endpoint and a different
              // provider, so this index cannot count them. It says where the
              // section is; the section says whether there is anything in it.
              note: 'read separately',
            },
            {
              id: 'sec-company',
              label: 'Coverage',
              // The coverage panel counts collected articles; the same number
              // here so the column and the section cannot disagree.
              count: d.news_stream?.collected ?? null,
              absent: d.news_stream?.collected == null,
            },
          ],
        })
      })
      .catch((e: Error) => { if (alive) setAnswer({ for: symbol, reason: e.message }) })
    return () => { alive = false }
  }, [symbol])

  const settled = answer?.for === symbol ? answer : null
  const ready = settled && 'sections' in settled ? settled : null
  const failed = settled && 'reason' in settled ? settled : null
  const waiting = !settled

  return (
    <Panel title="On this page" subtitle={symbol}>
      <ul className="objidx">
        {/* Price is on the fast path and is always here by the time anything
            else is, so it is listed as present rather than counted. */}
        <li className="objidx__row">
          <a className="objidx__k" href="#sec-price">Price</a>
          <span className="objidx__v">chart</span>
        </li>

        {ready ? ready.sections.map((s) => (
          <li className="objidx__row" key={s.label}>
            <a className="objidx__k" href={`#${s.id}`}>{s.label}</a>
            <span className={`objidx__v${s.absent ? ' objidx__v--absent' : ''}`}>
              {s.absent
                ? 'none returned'
                : s.count != null ? s.count.toLocaleString() : (s.note ?? '—')}
            </span>
          </li>
        )) : null}

        {waiting ? (
          <li className="objidx__row objidx__row--waiting">
            <span className="objidx__k">Research layer</span>
            <span className="objidx__v">reading…</span>
          </li>
        ) : null}

        {failed ? (
          <li className="objidx__row">
            <span className="objidx__k">Research layer</span>
            <span className="objidx__v objidx__v--absent" title={failed.reason}>unavailable</span>
          </li>
        ) : null}
      </ul>

      <p className="objidx__foot">
        {waiting
          ? 'The research fan-out takes half a minute. Price and history above are already final.'
          : failed
            /* Said plainly rather than reusing the success line, which claimed
               these were "what the providers returned" when nothing was. */
            ? 'The research service did not answer, so this name has no section counts. Price and history above come from the market providers and are unaffected.'
            : 'Counts are what the providers returned for this name.'}
      </p>
    </Panel>
  )
}
