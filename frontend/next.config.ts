import type { NextConfig } from "next";

// Browser traffic goes to /api/* on this origin and is proxied to FastAPI, so the
// httpOnly refresh cookie is first-party (Vercel and Render are different sites).
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";
if (process.env.VERCEL && !process.env.API_ORIGIN) {
  throw new Error("API_ORIGIN must be set on Vercel (e.g. https://<service>.onrender.com)");
}

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiOrigin}/api/:path*` }];
  },
};

export default nextConfig;
