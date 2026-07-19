/* ============================================================
   Intelligence OS — search as reasoning (v1).

   Question-shaped queries are parsed into intents (pure, testable) and
   dispatched to deterministic pipelines composed from engines that
   already exist. The result is an *answer entity* whose route lands on
   the deterministic evidence (the vault comparison, the company report).

   v1 intents — only what today's engines can answer honestly:
     compare  — "compare NVDA and AMD", "nvda vs amd"
                → latest vault run of each → backend compare() deltas
     changed  — "what changed for NVDA", "nvda what changed since earnings"
                → last two vault runs of that ticker → compare() deltas
   Cross-sectional screens ("improving margins", "insider buying across
   the market") require a screening engine that does not exist yet; they
   are deliberately not faked here (see ROADMAP item 3 notes).

   The LLM appears nowhere in this file: engines answer, routes carry the
   user to evidence. Narration stays where it already lives — on the
   report pages themselves.
   ============================================================ */

import { fetchHistory } from '../persistence'
import type { Entity } from './entities'

const TICKER = /\b([A-Z]{1,5}(?:[.^-][A-Z]{1,2})?)\b/g

export type Intent =
  | { kind: 'compare'; a: string; b: string }
  | { kind: 'changed'; ticker: string }

/** Words that look like tickers but are query vocabulary. */
const STOPWORDS = new Set([
  'VS', 'AND', 'WITH', 'TO', 'COMPARE', 'WHAT', 'CHANGED', 'SINCE', 'FOR',
  'THE', 'A', 'AN', 'OF', 'IN', 'ON', 'SHOW', 'ME', 'LAST', 'EARNINGS',
  'REPORT', 'RUN', 'RUNS', 'CHANGE', 'DIFF', 'BETWEEN', 'HAS', 'HAVE',
])

function tickersIn(raw: string): string[] {
  // Contractions split at word boundaries ("WHAT'S" → "WHAT","S") and the
  // orphaned S would read as a ticker — drop possessive/contraction suffixes.
  const upper = raw.replace(/'(S|RE|VE|LL|D|T)\b/g, '')
  const out: string[] = []
  for (const match of upper.matchAll(TICKER)) {
    const symbol = match[1]
    if (!STOPWORDS.has(symbol) && !out.includes(symbol)) out.push(symbol)
  }
  return out
}

/** Pure intent parser. Case-sensitive on tickers by design: "compare nvda
 *  and amd" still works because the whole query is uppercased first, but
 *  stopwords keep prose words out of the ticker slots. */
export function parseIntent(query: string): Intent | null {
  const upper = query.trim().toUpperCase()
  if (!upper) return null
  const tickers = tickersIn(upper)

  const wantsCompare = /\b(COMPARE|VS\.?|VERSUS|BETWEEN)\b/.test(upper)
  if (wantsCompare && tickers.length >= 2) {
    return { kind: 'compare', a: tickers[0], b: tickers[1] }
  }

  const wantsChanged = /\bWHAT(?:'S| IS| HAS)? CHANGED\b|\bCHANGED SINCE\b|\bWHAT MOVED\b/.test(upper)
  if (wantsChanged && tickers.length >= 1) {
    return { kind: 'changed', ticker: tickers[0] }
  }

  return null
}

async function latestRunIds(ticker: string, count: 1 | 2): Promise<string[]> {
  const page = await fetchHistory({ ticker, page: 1, pageSize: count, sort: 'newest' })
  return page.items.map((item) => item.id)
}

/**
 * Dispatch an intent to its deterministic pipeline and express the answer
 * as entities. Every answer routes to evidence; when prerequisites are
 * missing (no stored runs yet) the answer says so and routes to the fix.
 */
export async function answerIntent(intent: Intent): Promise<Entity[]> {
  if (intent.kind === 'compare') {
    const [aIds, bIds] = await Promise.all([latestRunIds(intent.a, 1), latestRunIds(intent.b, 1)])
    if (aIds.length && bIds.length) {
      return [{
        id: `answer:compare:${intent.a}:${intent.b}`,
        type: 'answer',
        title: `Compare ${intent.a} vs ${intent.b}`,
        subtitle: 'Factor-level deltas between your latest runs of each',
        route: `/terminal/vault?compare=${encodeURIComponent(aIds[0])},${encodeURIComponent(bIds[0])}`,
        keywords: [],
        relationships: [`company:${intent.a}`, `company:${intent.b}`],
      }]
    }
    const missing = aIds.length ? intent.b : intent.a
    return [{
      id: `answer:compare-missing:${missing}`,
      type: 'answer',
      title: `Run ${missing} first, then compare`,
      subtitle: `Comparison needs a stored analysis of each — ${missing} has none yet`,
      route: `/company/${encodeURIComponent(missing)}`,
      keywords: [],
    }]
  }

  // changed
  const ids = await latestRunIds(intent.ticker, 2)
  if (ids.length >= 2) {
    return [{
      id: `answer:changed:${intent.ticker}`,
      type: 'answer',
      title: `What changed for ${intent.ticker}`,
      subtitle: 'Verdict, confidence and factor deltas between your last two runs',
      route: `/terminal/vault?compare=${encodeURIComponent(ids[1])},${encodeURIComponent(ids[0])}`,
      keywords: [],
      relationships: [`company:${intent.ticker}`],
    }]
  }
  return [{
    id: `answer:changed-insufficient:${intent.ticker}`,
    type: 'answer',
    title: ids.length === 1
      ? `Run ${intent.ticker} again to see what changed`
      : `Analyze ${intent.ticker} to start its history`,
    subtitle: ids.length === 1
      ? 'Change detection needs two stored runs — you have one'
      : 'No stored runs yet — the Vault records every analysis automatically',
    route: `/company/${encodeURIComponent(intent.ticker)}`,
    keywords: [],
  }]
}
