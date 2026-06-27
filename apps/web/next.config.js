/** @type {import('next').NextConfig} */
const API_PROXY_TARGET =
  process.env.API_PROXY_TARGET ?? "http://127.0.0.1:9000";

const nextConfig = {
  reactStrictMode: true,
  // Üretim sunucusu (scripts/start-dashboard.ps1, "next start") .next-prod
  // kullanır; platformun otomatik önizleme dev sunucusu (next dev, varsayılan
  // .next) ile aynı build klasörünü PAYLAŞMAZ. Aksi halde ikisi aynı anda
  // yazınca klasör bozulur (BUILD_ID kaybolur → tüm chunk'lar 400 döner →
  // "Yükleniyor..." ekranında sonsuz kalır).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  experimental: {
    optimizePackageImports: ["@react-three/drei", "framer-motion"],
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
