/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // The page is fully client-side, so it builds to static files (web/out) that the
  // FastAPI server serves in production: one container, one origin.
  output: "export",
};

export default nextConfig;
