import type { NextConfig } from 'next'

const API_BASE = process.env.API_URL || 'https://minialaddin-production.up.railway.app'

const nextConfig: NextConfig = {
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
