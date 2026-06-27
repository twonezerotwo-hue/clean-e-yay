/** @type {import('next').NextConfig} */
const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1:9000";

const nextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["@react-three/drei", "framer-motion"],
  },
  async headers() {
    if (process.env.NODE_ENV !== "development") return [];
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "no-store, max-age=0, must-revalidate",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
