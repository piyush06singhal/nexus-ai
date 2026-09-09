import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiFetch, fetchHealth } from "@/lib/api";

describe("apiFetch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed JSON on success", async () => {
    const mockData = { status: "ok" };
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockData), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiFetch<typeof mockData>("/api/v1/test");
    expect(result).toEqual(mockData);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/v1/test",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it("throws ApiError on non-OK response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "not found" }), {
        status: 404,
        statusText: "Not Found",
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(apiFetch("/api/v1/missing")).rejects.toThrow(
      "Request failed: 404 Not Found",
    );
  });

  it("attaches status and body to error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        statusText: "Forbidden",
        headers: { "Content-Type": "application/json" },
      }),
    );

    try {
      await apiFetch("/api/v1/secret");
      expect.fail("should have thrown");
    } catch (err: unknown) {
      const e = err as { status?: number; body?: unknown };
      expect(e.status).toBe(403);
      expect(e.body).toEqual({ detail: "forbidden" });
    }
  });

  it("handles non-JSON error body gracefully", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("Internal Server Error", {
        status: 500,
        statusText: "Internal Server Error",
        headers: { "Content-Type": "text/plain" },
      }),
    );

    await expect(apiFetch("/api/v1/crash")).rejects.toThrow(
      "Request failed: 500 Internal Server Error",
    );
  });
});

describe("fetchHealth", () => {
  it("calls the correct endpoint and returns HealthResponse", async () => {
    const mockHealth = {
      status: "healthy",
      message: "ok",
      service: "NEXUS API",
      version: "0.1.0",
      environment: "development",
      checks: { database: { status: "ok" }, redis: { status: "ok" } },
    };

    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(JSON.stringify(mockHealth), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await fetchHealth();
    expect(result.status).toBe("healthy");
    expect(result.checks.database.status).toBe("ok");
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.any(Object),
    );
  });
});
