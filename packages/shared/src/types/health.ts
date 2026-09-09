/**
 * Shared health check types.
 *
 * These types mirror the backend's Pydantic models in
 * `app/api/v1/endpoints/health.py`. When the backend schema changes,
 * update these types to match (or automate via OpenAPI codegen in Phase 1).
 */

export interface ServiceCheck {
  status: "ok" | "degraded" | "unavailable";
}

export interface HealthResponse {
  status: "healthy" | "degraded";
  message: string;
  service: string;
  version: string;
  environment: string;
  checks: {
    database: ServiceCheck;
    redis: ServiceCheck;
  };
}
