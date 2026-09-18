import Link from 'next/link'

import { Panel, Prose, Strip } from '@/components/system'

export default function EvidenceHealth({
  ticker,
  completeness,
  sources,
  fresh,
  conflicts,
  mode = 'advanced',
}: {
  ticker: string
  completeness: number | null
  sources: number | null
  fresh: boolean | null
  conflicts: number | null
  mode?: 'beginner' | 'intermediate' | 'advanced'
}) {
  return (
    <Panel
      title="Evidence health"
      subtitle="what this analysis could actually support"
      actions={
        <Link
          href={`/evidence/${encodeURIComponent(ticker)}?mode=${mode}`}
          className="sys-meta sys-meta--strong"
        >
          Evidence Inspector →
        </Link>
      }
    >
      <Strip metrics={[
        {
          label: 'Complete',
          value: completeness === null ? null : `${Math.round(completeness * 100)}%`,
        },
        { label: 'Sources', value: sources, kind: 'count' },
        { label: 'Freshness', value: fresh === null ? 'not reported' : fresh ? 'fresh' : 'degraded' },
        { label: 'Critical conflicts', value: conflicts, kind: 'count' },
      ]} />
      <Prose size="fine">
        Completeness is the engine&apos;s coverage measure. Source count and
        conflicts come from the same provenance payload used to build this
        analysis; missing values stay unreported rather than being treated as
        clean.
      </Prose>
    </Panel>
  )
}
