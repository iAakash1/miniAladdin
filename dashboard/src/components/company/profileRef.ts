import type { MetricRef } from '@/components/system/MetricContext'
import type { CompanyProfile } from '@/lib/types'

/**
 * Where a merged profile field came from, for the value inspector.
 *
 * The research engine merges several vendors per field and records who
 * contributed and where they disagreed. A disputed figure shown as settled is
 * the most dangerous kind of number here — Apple's headcount has been 166,000
 * to one vendor and 150,000 to another — so the merge is never presented as
 * one vendor's figure. Returns null when the payload says nothing about the
 * field's sources, in which case the value renders plainly.
 */
export function profileRef(
  profile: CompanyProfile,
  field: string,
  label: string,
  display: string,
  retrievedAt?: string | null,
): MetricRef | null {
  const providers = profile.field_sources?.[field]
  const c = profile.conflicts?.find((x) => x.field === field)
  const conflict = c ? { observations: c.observations, spreadPct: c.spread_pct ?? null } : undefined
  if (!providers?.length && !conflict) return null
  return {
    label,
    display,
    providers,
    conflict,
    claim: `${label} is ${display}.`,
    observation: providers?.length
      ? `Reported by ${providers.length} vendor${providers.length === 1 ? '' : 's'}: ${providers.join(', ')}.`
      : 'A single merged value; the engine did not record which vendors contributed.',
    assumptions: [
      'The vendors are describing the same entity — a ticker can be reassigned after a delisting.',
      conflict
        ? 'The merge produced one figure from observations that disagree; the reported value is not any single vendor’s number.'
        : 'The vendors agree, so the merged value is also each of theirs.',
    ],
    failsWhen: [
      'A vendor is stale — profile fields are refreshed far less often than quotes.',
      conflict
        ? 'The disagreement above is material to your use of the figure.'
        : 'A vendor silently changes its definition of the field, which the merge cannot detect while they still agree.',
    ],
    source: 'research engine, merged from the vendors below',
    retrievedAt: retrievedAt ?? undefined,
    freshness: 'read once per research run and shared with every panel on this page',
  }
}
