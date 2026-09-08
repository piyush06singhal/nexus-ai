import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API calls to `/api/*` are proxied to the NEXUS backend at *runtime* by the
  // catch-all route handler in `src/app/api/[...path]/route.ts`. We deliberately
  // avoid a `next.config` rewrite here: env vars referenced in config are baked
  // at build time, whereas the route handler resolves `API_BASE_URL` per request.
};

export default nextConfig;