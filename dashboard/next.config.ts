import type { NextConfig } from 'next'

const API_BASE = process.env.API_URL || 'https://minialaddin-d8oe.onrender.com'

const nextConfig: NextConfig = {
  // Explicit root: a stray lockfile higher up the tree otherwise makes
  // Turbopack guess the wrong workspace directory.
  turbopack: { root: __dirname },
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
