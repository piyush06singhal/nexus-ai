import { describe, it, expect } from "vitest";
import type { ServiceCheck, HealthResponse } from "@/lib/types";

describe("HealthResponse type", () => {
  it("accepts a valid healthy response", () => {
    const response: HealthResponse = {
      status: "healthy",
      message: "NEXUS API is running.",
      service: "NEXUS API",
      version: "0.1.0",
      environment: "development",
      checks: {
        database: { status: "ok" },
        redis: { status: "ok" },
      },
    };

    expect(response.status).toBe("healthy");
    expect(response.checks.database.status).toBe("ok");
  });

  it("accepts degraded status", () => {
    const check: ServiceCheck = { status: "degraded" };
    expect(check.status).toBe("degraded");
  });

  it("accepts unavailable status", () => {
    const check: ServiceCheck = { status: "unavailable" };
    expect(check.status).toBe("unavailable");
  });
});
