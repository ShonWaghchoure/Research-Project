import path from "node:path";
import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enables the slim production image in frontend/Dockerfile.
  output: "standalone",
  // Pin the tracing root to this folder; a stray lockfile higher up (e.g. in $HOME) would
  // otherwise be picked as the workspace root and break the standalone Docker output.
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  // The app uses no next/image. Disabling the optimizer removes the /_next/image endpoint,
  // which is where Next's image RCE / DoS advisories live.
  images: { unoptimized: true },
  // Security headers. frame-ancestors/X-Frame-Options stop clickjacking: with demo
  // wallets there is no confirmation popup, so a framed page could trick a click into
  // "Commit" or "Deposit". A full script CSP is left out because wallet extensions and
  // the dev server inject scripts; these directives are safe everywhere.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  webpack: (config) => {
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
      net: false,
      tls: false,
      crypto: false,
    };
    return config;
  },
};

export default nextConfig;
