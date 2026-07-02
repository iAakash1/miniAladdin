import { NextRequest, NextResponse } from 'next/server'
import { queryNews } from '@/lib/news'
import type { NewsCategory } from '@/lib/types'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const VALID_CATEGORIES = new Set(['all', 'markets', 'economy', 'companies', 'technology', 'crypto'])

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams
  const rawCategory = params.get('category') ?? 'all'
  const category = (VALID_CATEGORIES.has(rawCategory) ? rawCategory : 'all') as NewsCategory | 'all'

  try {
    const data = await queryNews({
      q: params.get('q') ?? undefined,
      category,
      page: parseInt(params.get('page') ?? '1', 10) || 1,
      pageSize: parseInt(params.get('pageSize') ?? '20', 10) || 20,
    })

    return NextResponse.json(data, {
      headers: {
        // CDN cache: fresh 5 min, serve stale while revalidating for 10 more.
        'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600',
      },
    })
  } catch {
    return NextResponse.json(
      { error: 'News sources are unreachable right now. Please try again shortly.' },
      { status: 503 },
    )
  }
}
