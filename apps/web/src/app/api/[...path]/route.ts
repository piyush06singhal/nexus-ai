import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

/**
 * Runtime API proxy (Backend-for-Frontend).
 *
 * Forwards any `/api/*` request to the NEXUS backend. The backend base URL is
 * resolved per-request from the `API_BASE_URL` env var (default localhost:8000),
 * so it works in local dev and in Docker without being baked at build time.
 */

const DEFAULT_API_BASE = "http://localhost:8000";

function resolveBackend(path: string[]): string {
  const base = (process.env.API_BASE_URL ?? DEFAULT_API_BASE).replace(/\/$/, "");
  return `${base}/api/${path.join("/")}`;
}

async function proxy(request: NextRequest, segments: string[]) {
  const backend = resolveBackend(segments);
  const url = new URL(backend);
  url.search = request.nextUrl.search;

  const body =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const response = await fetch(url, {
    method: request.method,
    headers: {
      ...Object.fromEntries(request.headers.entries()),
      host: new URL(backend).host,
    },
    body,
    cache: "no-store",
  });

  const responseBody = await response.arrayBuffer();
  const headers = new Headers(response.headers);
  headers.set(
    "content-type",
    response.headers.get("content-type") ?? "application/json",
  );
  headers.delete("content-length");

  return new NextResponse(Buffer.from(responseBody), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

type RouteCtx = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}

export async function POST(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}

export async function PUT(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}

export async function PATCH(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}

export async function DELETE(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}

export async function OPTIONS(request: NextRequest, { params }: RouteCtx) {
  const { path } = await params;
  return proxy(request, path);
}