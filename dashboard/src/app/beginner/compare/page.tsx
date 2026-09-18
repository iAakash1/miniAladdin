import SimpleShell from '@/components/beginner/SimpleShell'
import ExperienceCompare from '@/components/intermediate/ExperienceCompare'

export default async function BeginnerComparePage({
  searchParams,
}: {
  searchParams: Promise<{ a?: string; b?: string }>
}) {
  const params = await searchParams
  const a = (params.a ?? '').toUpperCase()
  const b = (params.b ?? '').toUpperCase()
  return (
    <SimpleShell title="Compare" subtitle={a && b ? `${a} against ${b}` : 'company against company'}>
      <ExperienceCompare a={a} b={b} mode="beginner" />
    </SimpleShell>
  )
}
