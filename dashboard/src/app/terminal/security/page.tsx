import { redirect } from 'next/navigation'

/**
 * The security page and the company report were two views of one company.
 * Both now live in the company workspace; this keeps old links working.
 */
export default async function SecurityRedirect({
  searchParams,
}: {
  searchParams: Promise<{ symbol?: string; paper?: string }>
}) {
  const params = await searchParams
  const symbol = (params.symbol ?? '').trim().toUpperCase()
  if (!symbol) redirect('/terminal/command')
  redirect(`/company/${encodeURIComponent(symbol)}${params.paper === '1' ? '?paper=1' : ''}`)
}
