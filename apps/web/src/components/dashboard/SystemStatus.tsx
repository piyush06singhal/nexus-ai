"use client";

import { useEffect, useState } from "react";
import { fetchHealth } from "@/lib/api";
import type { HealthResponse } from "@/lib/types";
import { cn } from "@/lib/cn";

type StatusState =
  | { kind: "loading" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "error"; message: string };

export function SystemStatus() {
  const [state, setState] = useState<StatusState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((data) => {
        if (!cancelled) setState({ kind: "ok", data });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.kind === "loading") {
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="h-4 w-32 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" />
        <div className="mt-3 h-3 w-48 animate-pulse rounded bg-zinc-100 dark:bg-zinc-900" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-900 dark:bg-red-950/30">
        <StatusDot tone="error" label="Backend unreachable" />
        <p className="mt-2 text-sm text-red-700 dark:text-red-400">
          Could not reach the API. Is it running on port 8000?
        </p>
        <p className="mt-1 font-mono text-xs text-red-500">{state.message}</p>
      </div>
    );
  }

  const { data } = state;
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
          System Status
        </h3>
        <StatusDot
          tone={data.status === "healthy" ? "ok" : "warn"}
          label={data.status}
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ServiceTile label="API" value={`v${data.version}`} ok />
        <ServiceTile
          label="Database"
          value={data.checks.database.status}
          ok={data.checks.database.status === "ok"}
        />
        <ServiceTile
          label="Redis"
          value={data.checks.redis.status}
          ok={data.checks.redis.status === "ok"}
        />
      </div>

      <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">{data.message}</p>
    </div>
  );
}

function StatusDot({ tone, label }: { tone: "ok" | "warn" | "error"; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium capitalize">
      <span
        className={cn(
          "h-2.5 w-2.5 rounded-full",
          tone === "ok" && "bg-emerald-500",
          tone === "warn" && "bg-amber-500",
          tone === "error" && "bg-red-500",
        )}
      />
      {label}
    </span>
  );
}

function ServiceTile({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p
        className={cn(
          "mt-1 text-sm font-medium capitalize",
          ok
            ? "text-emerald-600 dark:text-emerald-400"
            : "text-amber-600 dark:text-amber-400",
        )}
      >
        {value}
      </p>
    </div>
  );
}