import type { NextConfig } from 'next'

// Backend origin for the /api/* proxy. Deliberately NOT read from API_URL:
// the hosting env had a stale API_URL pinned to a dead Railway backend that
// silently overrode this. BACKEND_ORIGIN is a fresh name the host doesn't set,
// so production always resolves to the live Render service below. For local
// dev against a local backend, set BACKEND_ORIGIN in dashboard/.env.local.
const API_BASE = process.env.BACKEND_ORIGIN || 'https://minialaddin-d8oe.onrender.com'

const nextConfig: NextConfig = {
  // Explicit root: a stray lockfile higher up the tree otherwise makes
  // Turbopack guess the wrong workspace directory.
  turbopack: { root: __dirname },
  experimental: {
    // The proxy below defaults to a 30-second timeout and answers anything
    // slower with a plain-text "Internal Server Error" and no content type.
    // /api/research/:ticker fans out across every configured vendor and takes
    // between roughly 25 and 65 seconds whenever the backend cache is cold,
    // so the most substantial panel on the security page — fundamentals,
    // filings, coverage — failed for any name nobody had looked at recently.
    // Measured: a cold NVDA request returned 500 at exactly 30.0s while the
    // same request against the backend directly returned 200.
    //
    // This is a ceiling, not a target. The fan-out being slow is a separate
    // problem; a proxy that gives up before the work it is proxying can
    // finish is this one.
    proxyTimeout: 120_000,
  },
  async rewrites() {
    // Proxy analysis endpoints to the FastAPI backend on Railway.
    // App-router routes (e.g. /api/news) take precedence over these rewrites.
    return [
      {
        source: '/api/:path*',
        destination: `${API_BASE}/api/:path*`,
      },
    ]
  },
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
