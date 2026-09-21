import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // Vercel exposes its git SHA only during the build. Copy it into a public,
  // non-secret value so the operator diagnostics can compare all three tiers.
  env: {
    NEXT_PUBLIC_BUILD_SHA:
      process.env.VERCEL_GIT_COMMIT_SHA || process.env.GIT_COMMIT || 'unknown',
  },
  // Explicit root: a stray lockfile higher up the tree otherwise makes
  // Turbopack guess the wrong workspace directory.
  turbopack: { root: __dirname },
  // `/api/[...path]` is an App Router server proxy.  It can attach a
  // short-lived Google-signed token for private Cloud Run while preserving the
  // browser's Clerk bearer token for application authorization.  Render uses
  // the same path with BACKEND_AUTH_MODE=none for one-variable rollback.
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ]
  },
}

export default nextConfig
