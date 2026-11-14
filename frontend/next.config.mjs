/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Enables the slim production image in frontend/Dockerfile.
  output: "standalone",
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
