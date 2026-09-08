import type { HealthResponse } from "@/lib/types";

/**
 * API calls are made same-origin and proxied to the NEXUS backend by the
 * Next.js rewrite configured in `next.config.ts`. This keeps the browser
 * talking to one origin and avoids CORS in local dev and Docker alike.
 */
interface ApiError extends Error {
  status?: number;
  body?: unknown;
}

/** Thin wrapper around fetch with JSON handling and normalized errors. */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    const error: ApiError = new Error(
      `Request failed: ${response.status} ${response.statusText}`,
    );
    error.status = response.status;
    try {
      error.body = await response.json();
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw error;
  }

  return (await response.json()) as T;
}

/** Fetch the backend health status. */
export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/v1/health");
}