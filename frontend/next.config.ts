import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/tomi/:path*",
        destination: "http://localhost:7860/:path*",
      },
    ];
  },
};

export default nextConfig;
