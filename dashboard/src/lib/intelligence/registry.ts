/* ============================================================
   Intelligence OS — entity registry.

   Providers are independent, pluggable sources of entities. The registry
   composes them behind one query API with two speed tiers:

     • sync tier   — static + local providers, answered on every keystroke
     • async tier  — network-backed providers (company resolver, vault),
                     merged in when they settle, latest-query-wins

   Clients call `queryIntelligence` and receive ranked, merged results via
   callback; they never know which provider produced an entity. Pure TS —
   no React. UI stays a client of this layer, never part of it.
   ============================================================ */

import { type Entity, type Scored, rankEntities } from './entities'

export interface EntityProvider {
  id: string
  /** sync providers answer instantly; async providers may hit the network. */
  tier: 'sync' | 'async'
  /** Return candidate entities for a query ('' = browsing suggestions). */
  entities(query: string): Entity[] | Promise<Entity[]>
}

const providers: EntityProvider[] = []

export function registerProvider(provider: EntityProvider): void {
  const existing = providers.findIndex((p) => p.id === provider.id)
  if (existing >= 0) providers.splice(existing, 1)
  providers.push(provider)
}

export function registeredProviders(): readonly EntityProvider[] {
  return providers
}

/** Test seam — registries are process-global otherwise. */
export function _resetForTests(): void {
  providers.length = 0
}

export interface IntelligenceResult {
  scored: Scored[]
  /** false while async providers are still settling for this query. */
  settled: boolean
}

let querySequence = 0

/**
 * Query the registry. `onResult` fires once immediately with the sync tier,
 * then once more when async providers settle (if any produce entities).
 * A newer query invalidates older async merges — latest query wins.
 * Returns the sequence id (useful for tests).
 */
export function queryIntelligence(
  query: string,
  recentIds: string[],
  onResult: (result: IntelligenceResult) => void,
): number {
  const seq = ++querySequence
  const syncEntities: Entity[] = []
  const asyncProviders: EntityProvider[] = []

  for (const provider of providers) {
    if (provider.tier === 'sync') {
      try {
        const result = provider.entities(query)
        if (Array.isArray(result)) syncEntities.push(...result)
      } catch {
        /* a broken provider never breaks the surface */
      }
    } else {
      asyncProviders.push(provider)
    }
  }

  const syncScored = rankEntities(query, syncEntities, recentIds)
  onResult({ scored: syncScored, settled: asyncProviders.length === 0 || !query.trim() })

  if (asyncProviders.length === 0 || !query.trim()) return seq

  void Promise.allSettled(
    asyncProviders.map((provider) => Promise.resolve(provider.entities(query))),
  ).then((settled) => {
    if (seq !== querySequence) return // stale — a newer query superseded us
    const asyncEntities: Entity[] = []
    for (const result of settled) {
      if (result.status === 'fulfilled') asyncEntities.push(...result.value)
    }
    // De-duplicate on id: sync sources win (they carry recency/local context).
    const seen = new Set(syncEntities.map((e) => e.id))
    const merged = syncEntities.concat(asyncEntities.filter((e) => !seen.has(e.id)))
    onResult({ scored: rankEntities(query, merged, recentIds), settled: true })
  })
  return seq
}

/* ---------- recents (shared by all clients) ---------- */

const RECENTS_KEY = 'omni_intel_recents_v1'
const RECENTS_MAX = 12

export function readRecents(): Entity[] {
  if (typeof window === 'undefined') return []
  try {
    return JSON.parse(localStorage.getItem(RECENTS_KEY) ?? '[]') as Entity[]
  } catch {
    return []
  }
}

export function recordRecent(entity: Entity): void {
  if (typeof window === 'undefined') return
  const next = [entity, ...readRecents().filter((e) => e.id !== entity.id)].slice(0, RECENTS_MAX)
  try {
    localStorage.setItem(RECENTS_KEY, JSON.stringify(next))
  } catch {
    /* private mode */
  }
}
