/**
 * Object relationships, computed from what the artifacts actually record.
 *
 * A feature knows nothing about the models that use it — but every registry
 * entry lists its features, and inverting that gives the edge. The same holds
 * for datasets, labels and experiments. Nothing here is inferred beyond that
 * inversion: an edge exists because a record names both ends of it.
 *
 * Counts are the point. "Used by 4 models" turns a name in a table into a node
 * in a research network, and a feature used by nothing is a fact worth seeing —
 * it is either new or abandoned, and both are worth knowing before building on
 * it.
 *
 * Edges that are deliberately NOT here, having been looked for:
 *
 *  - **security → factor** and **security → signal.** No artifact names both
 *    ends. A factor and a security are not related because the factor could be
 *    computed for it; every factor could be computed for every security, which
 *    makes the edge meaningless.
 *  - **security → model.** The symbol endpoint carries a `model` field, and it
 *    is null for the securities checked. An edge drawn from a null is an edge
 *    invented to fill a section.
 *  - **factor → feature** and **factor → experiment.** `/api/factors` reports
 *    build progress, not a factor catalogue with lineage. There is nothing to
 *    invert.
 *
 * Each of those would look plausible on screen. None is recorded, so none is
 * drawn.
 */

import type { ObjectKind, ResearchObject } from './objects'

export interface Relation {
  kind: ObjectKind
  /** How this object relates to them, in the artifacts' own terms. */
  verb: string
  count: number
  /** A few examples, for the tooltip. Never the whole set. */
  sample: string[]
  href: string
}

interface RegistryEntry {
  model_id: string
  label: string
  features?: string[]
  experiments_run?: number
  dataset_sources?: { dataset_id: string }[]
}

/** What an experiment artifact names at both ends of an edge. */
export interface ExperimentEdges {
  experiment_id?: string
  features_used?: string[]
  dataset_sources?: { dataset_id: string }[]
  leaderboard?: { model_id?: string }[]
}

interface Graph {
  /** feature name -> model ids that list it */
  featureToModels: Map<string, Set<string>>
  /** dataset id -> model ids that read it */
  datasetToModels: Map<string, Set<string>>
  /** label -> model ids trained against it */
  labelToModels: Map<string, Set<string>>
  /** model id -> its own record */
  models: Map<string, RegistryEntry>
  loadedAt: number
}

let graph: Graph | null = null
let inflight: Promise<Graph | null> | null = null
/** Set once the registry has been asked and refused. Distinguishes a graph
 *  that could not be built from one that has not been requested yet. */
let failed: string | null = null

function push(map: Map<string, Set<string>>, key: string, value: string): void {
  const set = map.get(key) ?? new Set<string>()
  set.add(value)
  map.set(key, set)
}

export async function loadGraph(): Promise<Graph | null> {
  if (graph) return graph
  if (inflight) return inflight
  inflight = (async () => {
    try {
      const r = await fetch('/api/ml/registry')
      if (!r.ok) throw new Error(String(r.status))
      const d: { entries?: RegistryEntry[] } = await r.json()

      const featureToModels = new Map<string, Set<string>>()
      const datasetToModels = new Map<string, Set<string>>()
      const labelToModels = new Map<string, Set<string>>()
      const models = new Map<string, RegistryEntry>()

      for (const e of d.entries ?? []) {
        models.set(e.model_id, e)
        for (const f of e.features ?? []) push(featureToModels, f, e.model_id)
        for (const s of e.dataset_sources ?? []) push(datasetToModels, s.dataset_id, e.model_id)
        if (e.label) push(labelToModels, e.label, e.model_id)
      }

      graph = { featureToModels, datasetToModels, labelToModels, models, loadedAt: Date.now() }
    } catch (e) {
      // Relationships are additive context. Their absence must not stop an
      // object rendering, and a count of zero would be a lie — so nothing is
      // returned rather than an empty graph, and the reason is kept so a
      // surface can say "could not be read" instead of "none".
      graph = null
      failed = e instanceof Error ? e.message : 'the registry request failed'
    }
    inflight = null
    return graph
  })()
  return inflight
}

export function cachedGraph(): Graph | null {
  return graph
}

/** Why the graph is unavailable, or null if it was never asked or succeeded. */
export function graphFailure(): string | null {
  return failed
}

/** Relations for one object, or an empty list where none are recorded. */
export function relationsFor(object: ResearchObject, g: Graph | null): Relation[] {
  if (!g) return []
  const out: Relation[] = []

  const modelRelation = (ids: Set<string> | undefined, verb: string): void => {
    if (!ids?.size) return
    out.push({
      kind: 'model',
      verb,
      count: ids.size,
      sample: [...ids].slice(0, 5),
      href: '/terminal/evidence',
    })
  }

  if (object.kind === 'feature') {
    modelRelation(g.featureToModels.get(object.id), 'used by')
  }

  if (object.kind === 'dataset') {
    modelRelation(g.datasetToModels.get(object.id), 'read by')
  }

  if (object.kind === 'model') {
    const entry = g.models.get(object.id)
    if (entry?.features?.length) {
      out.push({
        kind: 'feature',
        verb: 'uses',
        count: entry.features.length,
        sample: entry.features.slice(0, 5),
        href: '/terminal/data',
      })
    }
    if (entry?.dataset_sources?.length) {
      const ids = [...new Set(entry.dataset_sources.map((s) => s.dataset_id))]
      out.push({
        kind: 'dataset',
        verb: 'reads',
        count: ids.length,
        sample: ids.slice(0, 5),
        href: '/terminal/data',
      })
    }
    if (typeof entry?.experiments_run === 'number' && entry.experiments_run > 0) {
      out.push({
        kind: 'experiment',
        verb: 'tested in',
        count: entry.experiments_run,
        sample: [],
        href: '/terminal/experiments',
      })
    }
    if (entry?.label) {
      const siblings = g.labelToModels.get(entry.label)
      if (siblings && siblings.size > 1) {
        out.push({
          kind: 'model',
          verb: 'shares its label with',
          count: siblings.size - 1,
          sample: [...siblings].filter((m) => m !== object.id).slice(0, 5),
          href: '/terminal/compare',
        })
      }
    }
  }

  return out
}

/**
 * Relations for an experiment, from its own artifact.
 *
 * Kept separate from the registry graph because the source is different: these
 * edges come from the experiment's recorded run, not from inverting a registry.
 * Passing an artifact that names none of them yields an empty list, which the
 * caller must render as "none recorded" rather than as a failure.
 */
export function experimentRelations(artifact: ExperimentEdges | null): Relation[] {
  if (!artifact) return []
  const out: Relation[] = []

  const features = artifact.features_used ?? []
  if (features.length) {
    out.push({
      kind: 'feature', verb: 'trained on', count: features.length,
      sample: features.slice(0, 5), href: '/terminal/data',
    })
  }

  const datasets = [...new Set((artifact.dataset_sources ?? []).map((d) => d.dataset_id))]
  if (datasets.length) {
    out.push({
      kind: 'dataset', verb: 'read', count: datasets.length,
      sample: datasets.slice(0, 5), href: '/terminal/data',
    })
  }

  const models = [...new Set(
    (artifact.leaderboard ?? []).map((m) => m.model_id).filter((m): m is string => Boolean(m)),
  )]
  if (models.length) {
    out.push({
      kind: 'model', verb: 'evaluated', count: models.length,
      sample: models.slice(0, 5), href: '/terminal/evidence',
    })
  }

  return out
}
