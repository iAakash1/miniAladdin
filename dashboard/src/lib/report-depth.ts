import { normalizeAi } from './api'
import type { AiAnalysis, RawAiAnalysis, ReportDepth } from './types'

/**
 * Explanation depth for the research narrative.
 *
 * Depth is how much the narrative explains — never which evidence, figures or
 * decision it uses. Every depth is written from the same server-held evidence
 * snapshot and passes the same validator, so switching depth re-explains one
 * research run rather than starting another.
 */
export const DEPTHS: Array<{ key: ReportDepth; label: string; blurb: string }> = [
  { key: 'beginner', label: 'Beginner', blurb: 'Plain language, with each financial term explained where it first appears.' },
  { key: 'intermediate', label: 'Intermediate', blurb: 'Balanced professional research: why the important figures matter.' },
  { key: 'advanced', label: 'Advanced', blurb: 'Dense analysis: factor contributions, evidence states and provenance in full.' },
]

export const DEFAULT_DEPTH: ReportDepth = 'intermediate'

const KEY = 'omni-report-depth'

export function isDepth(value: unknown): value is ReportDepth {
  return value === 'beginner' || value === 'intermediate' || value === 'advanced'
}

/** The reader's last choice on this device, a convenience only. */
export function storedDepth(): ReportDepth {
  try {
    const v = typeof window === 'undefined' ? null : window.localStorage.getItem(KEY)
    return isDepth(v) ? v : DEFAULT_DEPTH
  } catch {
    return DEFAULT_DEPTH
  }
}

export function rememberDepth(depth: ReportDepth): void {
  try { window.localStorage.setItem(KEY, depth) } catch { /* private mode: not remembered */ }
}

export class NarrativeExpired extends Error {}

/** Re-explain a research run's evidence snapshot at another depth. */
export async function fetchNarrative(ticker: string, snapshotId: string, depth: ReportDepth): Promise<AiAnalysis> {
  const { authFetch } = await import('./persistence')
  const res = await authFetch(`/api/research/${encodeURIComponent(ticker)}/narrative`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapshot_id: snapshotId, depth }),
  })
  if (res.status === 410) throw new NarrativeExpired('snapshot expired')
  if (!res.ok) throw new Error(`the narrative service returned ${res.status}`)
  const body = (await res.json()) as { ai?: RawAiAnalysis }
  const ai = normalizeAi(body.ai ?? null)
  if (!ai) throw new Error('the narrative service returned no narrative')
  return ai
}
