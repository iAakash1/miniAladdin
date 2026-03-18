import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Proxy API calls to local FastAPI during development
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
