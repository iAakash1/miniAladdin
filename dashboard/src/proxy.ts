import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

/**
 * Public surface: the marketing site, live news (page + API), the macro
 * readout used on the landing page, auth pages and SEO files.
 * Everything else — the terminal, research/chart APIs, payments — requires auth.
 */
const isPublic = createRouteMatcher([
  '/',
  '/news',
  '/api/news(.*)',
  '/api/macro',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/sitemap.xml',
  '/robots.txt',
])

export default clerkMiddleware(async (auth, req) => {
  if (!isPublic(req)) await auth.protect()
})

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
}
