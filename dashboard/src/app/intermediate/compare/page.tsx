import ExperienceCompare from '@/components/intermediate/ExperienceCompare'
import IntermediateShell from '@/components/intermediate/IntermediateShell'

export default async function IntermediateComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>
}) {
  const params = await searchParams
  const a = (params.a ?? '').toUpperCase()
  const b = (params.b ?? '').toUpperCase()
  return (
    <IntermediateShell title="Compare" subtitle={a && b ? `${a} against ${b}` : 'company against company'}>
      <ExperienceCompare a={a} b={b} mode="intermediate" />
    </IntermediateShell>
  )
}
