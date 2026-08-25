'use client'

/**
 * Decision Provenance — the chain of custody behind one verdict.
 *
 * ## The problem this solves
 *
 * Every other panel in this product presents a *conclusion*: a verdict, a
 * confidence, a factor contribution. None of them let a reader answer the
 * question that decides whether any of it is worth acting on — **where did
 * this come from, and how good was it?**
 *
 * That question is not rhetorical here. Prices come from whichever of five
 * vendors answered first; news from whichever of four did. A run built on
 * fresh Polygon bars and twelve fresh headlines and a run built on a
 * four-day-old stale cache produce the *same shaped* response. Presenting
 * them identically is how a research tool becomes a magic 8-ball.
 *
 * ## What is shown
 *
 * One row per input the engine consumed, carrying: which vendor actually
 * answered, which were tried, how old the answer is, whether it was degraded
 * and why, and which parts of the decision consumed it. Beneath that, the
 * engine's own confidence deductions — verbatim, not recomputed, so this
 * panel can never disagree with the confidence number shown elsewhere.
 *
 * ## What is deliberately not shown
 *
 * No grade, no score, no "reliability rating". The engine already prices
 * these degradations into its confidence (`confidence_losses`); a second
 * opinion here would be a competing judgement dressed as a fact. This panel
 * reports. The engine judges.
 *
 * Missing inputs are rendered as explicitly missing rather than omitted. An
 * absent quality factor and a quality factor that scored neutral look
 * identical in a decomposition, and only one of them means "we did not
 * know".
 */

import { useState } from 'react'

import SourceBadge from '@/components/ui/SourceBadge'
import { StatusPill, type StatusTone } from '@/components/ui/DataMarks'
import type { Provenance, ProvenanceInput } from '@/lib/types'

/* ── stage grouping ─────────────────────────────────────────────────────────
   The rows are grouped by the pipeline stage they belong to rather than
   listed flat, because the pipeline order *is* the explanation: market and
   fundamental inputs feed the factors, evidence feeds the news sleeve, and
   the narrative layer sits after all of it. A flat list of six vendors does
   not tell that story. */
const STAGES: Array<{ kind: string; title: string; blurb: string }> = [
  {
    kind: 'market',
    title: 'Market data',
    blurb: 'Price series the momentum, volatility and relative-strength factors are computed from.',
  },
  {
    kind: 'fundamental',
    title: 'Fundamentals',
    blurb: 'Company and valuation inputs for the value, quality and earnings-drift sleeves.',
  },
  {
    kind: 'evidence',
    title: 'Evidence',
    blurb: 'Headlines, decayed and de-duplicated into an effective sample before they reach the news factor.',
  },
]

const HEALTH_TONE: Record<ProvenanceInput['health'], StatusTone> = {
  ok: 'pos',
  degraded: 'warn',
  missing: 'muted',
}

const HEALTH_LABEL: Record<ProvenanceInput['health'], string> = {
  ok: 'Live',
  degraded: 'Degraded',
  missing: 'Unavailable',
}

/** One input, expandable to the vendors that were tried for it.
 *
 *  Collapsed by default: the fallback chain matters when something went
 *  wrong and is noise when it did not, which is exactly what progressive
 *  disclosure is for. */
function InputRow({ input }: { input: ProvenanceInput }) {
  const [open, setOpen] = useState(false)
  // Only worth expanding when there is more than the one line already shown.
  const expandable =
    input.sources_consulted.length > 1 || input.used_for.length > 0 ||
    (input.contributors?.length ?? 0) > 0

  return (
    <li className={`prov-row prov-row--${input.health}`}>
      <button
        type="button"
        className="prov-row__head"
        aria-expanded={expandable ? open : undefined}
        onClick={() => expandable && setOpen((v) => !v)}
        disabled={!expandable}
      >
        <span className="prov-row__id">
          <span className="prov-row__label">{input.label}</span>
          {input.detail && <span className="prov-row__detail">{input.detail}</span>}
        </span>

        <span className="prov-row__source">
          {/* A parallel row has no single winner to name — several vendors
              answered — so it shows the count and defers the roster to the
              expansion. Naming one of four would misrepresent the fan-out
              as a chain. */}
          {input.parallel && input.contributors ? (
            <span className="prov-row__fanout">
              <span className="num">
                {input.contributors.filter((c) => c.ok).length}/{input.contributors.length}
              </span>
              <span className="u-note"> vendors</span>
            </span>
          ) : input.source ? (
            <SourceBadge name={input.source} />
          ) : (
            <span className="u-note">no source answered</span>
          )}
        </span>

        <span className="prov-row__age num">{input.age ?? '—'}</span>

        <StatusPill tone={HEALTH_TONE[input.health]} label={HEALTH_LABEL[input.health]} />

        {expandable && <span className="prov-row__chev" aria-hidden>{open ? '−' : '+'}</span>}
      </button>

      {/* The reason a row is degraded, always visible — a colour alone is not
          an explanation, and this is the line a reader actually needs. */}
      {input.note && <p className="prov-row__note">{input.note}</p>}

      {open && (
        <div className="prov-row__body">
          {/* Every vendor asked, with what it answered and how long it took.
              This is the row that makes the parallel architecture visible:
              a fallback chain has nothing to put here, because it stopped
              at the first success. */}
          {input.contributors && input.contributors.length > 0 && (
            <ul className="prov-fan">
              {input.contributors.map((c) => (
                <li key={c.provider} className={`prov-fan__row prov-fan__row--${c.ok ? 'ok' : 'off'}`}>
                  <SourceBadge name={c.provider} />
                  <span className="prov-fan__status">{c.ok ? 'answered' : c.status.replace(/_/g, ' ')}</span>
                  <span className="num prov-fan__ms">{Math.round(c.latency_ms)}ms</span>
                </li>
              ))}
            </ul>
          )}
          {input.sources_consulted.length > 1 && !input.parallel && (
            <p className="prov-row__chain">
              <span className="label">Chain</span>
              {input.sources_consulted.map((vendor, i) => (
                <span key={vendor} className={vendor === input.source ? 'prov-vendor is-used' : 'prov-vendor'}>
                  {i > 0 && <span aria-hidden> → </span>}
                  {vendor}
                </span>
              ))}
            </p>
          )}
          {input.used_for.length > 0 && (
            <p className="prov-row__uses">
              <span className="label">Feeds</span>
              {input.used_for.join(' · ')}
            </p>
          )}
          {input.confidence !== null && (
            <p className="prov-row__conf">
              <span className="label">Source confidence</span>
              <span className="num">{input.confidence.toFixed(2)}</span>
              <span className="u-note">
                {input.cached ? 'served from cache' : 'fetched live'}
              </span>
            </p>
          )}
        </div>
      )}
    </li>
  )
}

export default function DecisionProvenance({ provenance }: { provenance: Provenance }) {
  const { summary, inputs, confidence_losses: losses, ai } = provenance
  // Anything the stage list does not name still has to appear — an input
  // silently dropped from an audit trail defeats the point of having one.
  const known = new Set(STAGES.map((s) => s.kind))
  const groups = [
    ...STAGES.map((stage) => ({
      ...stage,
      rows: inputs.filter((i) => i.kind === stage.kind),
    })),
    {
      kind: 'other',
      title: 'Other inputs',
      blurb: '',
      rows: inputs.filter((i) => !known.has(i.kind)),
    },
  ].filter((g) => g.rows.length > 0)

  const clean = summary.degraded === 0 && summary.missing === 0

  return (
    <section className="panel panel--pad prov" aria-labelledby="prov-h">
      <header className="prov__head">
        <div>
          <h2 id="prov-h" className="h-panel">Decision provenance</h2>
          <p className="prov__lede">
            Every input this verdict was computed from, which vendor answered, and how
            good the answer was. Assembled from the same responses the engine consumed.
          </p>
        </div>
        <div className="prov__tally">
          <StatusPill
            tone={clean ? 'pos' : summary.missing > 0 ? 'warn' : 'accent'}
            label={
              clean
                ? `${summary.ok} inputs, all live`
                : `${summary.ok} live · ${summary.degraded} degraded · ${summary.missing} unavailable`
            }
          />
        </div>
      </header>

      <div className="prov__sources">
        <span className="label">Sources</span>
        {summary.sources.length > 0 ? (
          summary.sources.map((s) => <SourceBadge key={s} name={s} />)
        ) : (
          <span className="u-note">none answered</span>
        )}
        {provenance.engine_version && (
          <span className="prov__engine num">{provenance.engine_version}</span>
        )}
        {provenance.elapsed_seconds !== null && (
          <span className="prov__engine num">{provenance.elapsed_seconds.toFixed(1)}s</span>
        )}
      </div>

      {groups.map((group) => (
        <div key={group.kind} className="prov__stage">
          <div className="prov__stage-head">
            <h3 className="prov__stage-title">{group.title}</h3>
            {group.blurb && <p className="prov__stage-blurb">{group.blurb}</p>}
          </div>
          <ul className="prov__list">
            {group.rows.map((row) => (
              <InputRow key={`${row.kind}-${row.label}`} input={row} />
            ))}
          </ul>
        </div>
      ))}

      {/* The engine's own arithmetic, not ours. Shown here because the row
          above explains *why* an input was degraded and this explains what
          that degradation actually cost the confidence figure. */}
      {losses.length > 0 && (
        <div className="prov__stage">
          <div className="prov__stage-head">
            <h3 className="prov__stage-title">What the engine deducted</h3>
            <p className="prov__stage-blurb">
              Confidence starts at 100 and is reduced by measured shortfalls. These are the
              engine&rsquo;s own deductions, shown verbatim.
            </p>
          </div>
          <ul className="prov__losses">
            {losses.map((loss) => (
              <li key={loss.component} className="prov__loss">
                <span className="prov__loss-name" title={loss.component}>{loss.component}</span>
                <span
                  className="prov__loss-bar"
                  aria-hidden
                  style={{ width: `${Math.min(100, Math.abs(loss.points) * 3)}%` }}
                />
                <span className="num prov__loss-pts">−{Math.abs(loss.points)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* The boundary between the deterministic engine and the model. This is
          the claim a reader is most entitled to be sceptical of, so it is
          stated plainly rather than left to be inferred. */}
      <p className="prov__ai">
        <span className="label">Narrative layer</span>
        {ai.generated === null
          ? 'Not run for this analysis.'
          : ai.generated
            ? `Written by ${ai.model ?? 'the language model'}. `
            : 'Language model unavailable — deterministic fallback text shown. '}
        {ai.generated !== null && <>Role: {ai.role}.</>}
      </p>
    </section>
  )
}
