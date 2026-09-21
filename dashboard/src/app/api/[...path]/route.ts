import { proxyBackend } from '@/lib/backend-proxy'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'
export const maxDuration = 120

type Context = { params: Promise<{ path: string[] }> }

async function handle(request: Request, context: Context): Promise<Response> {
  try {
    const { path } = await context.params
    return await proxyBackend(request, path)
  } catch (error) {
    console.error('[backend-proxy] request failed', {
      error: error instanceof Error ? error.name : 'UnknownError',
    })
    const message = error instanceof Error && error.message.startsWith('Missing server configuration:')
      ? 'Backend proxy is not configured.'
      : 'Backend service is unavailable.'
    return Response.json(
      { status: 'unavailable', error: message },
      { status: 503, headers: { 'Cache-Control': 'no-store' } },
    )
  }
}

export const GET = handle
export const POST = handle
export const PUT = handle
export const PATCH = handle
export const DELETE = handle
export const OPTIONS = handle
