import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone", poweredByHeader: false, devIndicators: false,
  distDir: process.env.LAPI_BUILD_DIR || ".next",
  ...(process.env.LAPI_IN_PROCESS_WEB === "true" ? { experimental: { workerThreads: true } } : {}),
};
export default nextConfig;
