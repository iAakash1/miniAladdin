/**
 * The searchable object catalogue.
 *
 * Search needs every object in one list, but the objects live behind six
 * different endpoints with six different shapes. This is the one place that
 * knows how to flatten them, so the search UI stays a search UI.
 *
 * Loaded once and cached for the session. Every source is optional: a failing
 * endpoint removes its kind from the results and is reported, rather than
 * failing the whole catalogue. Search that silently returns nothing because one
 * upstream is down is worse than search that says which part is missing.
 */

import type { ResearchObject } from './objects'

export interface Catalogue {
  objects: ResearchObject[]
  failed: { source: string; reason: string }[]
  loadedAt: number
}

let cache: Catalogue | null = null
let inflight: Promise<Catalogue> | null = null

async function json<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(String(r.status))
  return r.json() as Promise<T>
}

async function collect(
  source: string,
  load: () => Promise<ResearchObject[]>,
  failed: { source: string; reason: string }[],
): Promise<ResearchObject[]> {
  try {
    return await load()
  } catch (e) {
    failed.push({ source, reason: (e as Error).message })
    return []
  }
}

export async function loadCatalogue(force = false): Promise<Catalogue> {
  if (!force && cache) return cache
  if (!force && inflight) return inflight

  const failed: { source: string; reason: string }[] = []

  inflight = (async () => {
    const groups = await Promise.all([
      collect('features', async () => {
        const d = await json<{
          features: { name: string; group?: string; point_in_time_safe?: boolean; lookback_sessions?: number | null }[]
        }>('/api/ml/features')
        return (d.features ?? []).map((f) => ({
          kind: 'feature' as const, id: f.name, label: f.name,
          detail: [f.group, f.lookback_sessions ? `${f.lookback_sessions}d lookback` : null]
            .filter(Boolean).join(' · ') || undefined,
          state: f.point_in_time_safe ? 'recorded' : 'blocked',
        }))
      }, failed),

      collect('datasets', async () => {
        const d = await json<{ datasets: { dataset_id: string; source?: string; point_in_time?: string }[] }>('/api/ml/datasets')
        return (d.datasets ?? []).map((s) => ({
          kind: 'dataset' as const, id: s.dataset_id, label: s.dataset_id,
          detail: [s.source, s.point_in_time].filter(Boolean).join(' · ') || undefined,
          state: 'recorded',
        }))
      }, failed),

      collect('models', async () => {
        const d = await json<{
          leaderboard: {
            model_id: string; label?: string; status?: string
            mean_ic?: number | null; ic_t_stat?: number | null; net_sharpe?: number | null
          }[]
        }>('/api/ml/registry')
        const seen = new Set<string>()
        const out: ResearchObject[] = []
        for (const m of d.leaderboard ?? []) {
          if (seen.has(m.model_id)) continue
          seen.add(m.model_id)
          // The headline figure travels with the result, so choosing between
          // two models in the palette does not require opening both.
          const ic = typeof m.mean_ic === 'number' && Number.isFinite(m.mean_ic)
            ? `IC ${m.mean_ic >= 0 ? '+' : ''}${m.mean_ic.toFixed(4)}`
            : null
          out.push({
            kind: 'model', id: m.model_id, label: m.model_id,
            detail: [m.label, ic].filter(Boolean).join(' · ') || undefined,
            state: m.status,
          })
        }
        return out
      }, failed),

      collect('experiments', async () => {
        const d = await json<{ experiments: { experiment_id: string; status?: string; void?: boolean }[] }>('/api/quant/experiments')
        return (d.experiments ?? []).map((x) => ({
          kind: 'experiment' as const, id: x.experiment_id, label: x.experiment_id,
          detail: x.void ? 'void' : x.status, state: x.void ? 'unavailable' : 'recorded',
        }))
      }, failed),

      collect('methodology', async () => {
        const d = await json<{ entries: { name: string; unit?: string; annualisation?: string }[] }>('/api/quant/methodology')
        return (d.entries ?? []).map((m) => ({
          kind: 'method' as const, id: m.name, label: m.name,
          detail: [m.unit, m.annualisation && m.annualisation !== 'none' ? m.annualisation.replace(/_/g, ' ') : null]
            .filter(Boolean).join(' · ') || undefined,
          state: 'recorded',
        }))
      }, failed),

      collect('portfolio', async () => {
        const d = await json<{ weights?: { symbol: string; side?: string }[] }>('/api/quant/portfolio')
        return (d.weights ?? []).map((w) => ({
          kind: 'security' as const, id: w.symbol, label: w.symbol,
          detail: w.side, state: 'recorded',
        }))
      }, failed),
    ])

    cache = { objects: groups.flat(), failed, loadedAt: Date.now() }
    inflight = null
    return cache
  })()

  return inflight
}

export function cachedCatalogue(): Catalogue | null {
  return cache
}
