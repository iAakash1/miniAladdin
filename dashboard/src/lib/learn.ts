/* ============================================================
   Learn Knowledge Center — the unified glossary index.

   One authoritative index over the four authored glossaries (technical,
   street, validation metrics, factor library). Every topic gets a stable
   slug and a permanent URL (/learn/{slug}); the Intelligence OS glossary
   provider and the company-page cross-links both consume THIS index, so
   there is exactly one aggregation in the codebase.

   Pure data + pure functions — unit-tested in node.
   ============================================================ */

import { FACTOR_GLOSSARY } from './factorGlossary'
import { METRIC_GLOSSARY, type MetricEntry } from './metricGlossary'
import { STREET_GLOSSARY, TECHNICAL_GLOSSARY } from './technicalGlossary'

export type LearnSource = 'technical' | 'street' | 'metric' | 'factor'

export const SOURCE_LABELS: Record<LearnSource, string> = {
  technical: 'Technical analysis',
  street: 'Street & insiders',
  metric: 'Validation & statistics',
  factor: 'Factor library',
}

export interface LearnTopic {
  slug: string
  source: LearnSource
  key: string
  entry: MetricEntry
}

function buildIndex(): Record<string, LearnTopic> {
  const sources: Array<[LearnSource, Record<string, MetricEntry>]> = [
    ['technical', TECHNICAL_GLOSSARY],
    ['street', STREET_GLOSSARY],
    ['metric', METRIC_GLOSSARY as Record<string, MetricEntry>],
    ['factor', FACTOR_GLOSSARY as unknown as Record<string, MetricEntry>],
  ]
  const index: Record<string, LearnTopic> = {}
  for (const [source, glossary] of sources) {
    for (const [key, entry] of Object.entries(glossary)) {
      const slug = `${source}-${key.toLowerCase()}`
      index[slug] = { slug, source, key, entry }
    }
  }
  return index
}

export const LEARN_INDEX: Record<string, LearnTopic> = buildIndex()

export function learnRoute(source: LearnSource, key: string): string {
  return `/learn/${source}-${key.toLowerCase()}`
}

export function allTopics(): LearnTopic[] {
  return Object.values(LEARN_INDEX)
}

/** Same-source neighbors — the natural "related concepts" for a topic. */
export function relatedTopics(slug: string, limit = 5): LearnTopic[] {
  const topic = LEARN_INDEX[slug]
  if (!topic) return []
  return allTopics()
    .filter((t) => t.source === topic.source && t.slug !== slug)
    .slice(0, limit)
}
