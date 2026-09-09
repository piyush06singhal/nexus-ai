"use client";

import { useEffect, useState } from "react";
import { Activity as ActivityIcon } from "lucide-react";
import { fetchExecutions } from "@/lib/api";
import type { AgentExecution } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; executions: AgentExecution[] }
  | { kind: "error"; message: string };

export default function ActivityPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  // Initial load — async callbacks only (avoids the set-state-in-effect rule).
  useEffect(() => {
    let cancelled = false;
    fetchExecutions()
      .then((executions) => {
        if (!cancelled) setState({ kind: "ok", executions });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
          Activity
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          A live feed of agent executions — every model call is recorded with
          its provider, tokens, cost, and latency.
        </p>
      </div>

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {state.kind === "ok" && state.executions.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <ActivityIcon className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No executions yet. Assign a task to an active agent and execute it
            to begin the activity feed.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.executions.length > 0 && (
        <div className="space-y-3">
          {state.executions.map((execution) => (
            <ActivityRow key={execution.id} execution={execution} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({ execution }: { execution: AgentExecution }) {
  const timestamp = execution.completed_at ?? execution.started_at ?? execution.created_at;
  return (
    <div className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-700" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-zinc-400">
            {execution.id.slice(0, 8)}
          </span>
          <StatusBadge status={execution.status} />
        </div>
        <p className="mt-1 truncate text-sm text-zinc-800 dark:text-zinc-200">
          {execution.status === "succeeded"
            ? String(
                execution.output_data?.summary ??
                  JSON.stringify(execution.output_data).slice(0, 120) ??
                  "Completed",
              )
            : execution.error?.slice(0, 140) ?? "Agent execution"}
        </p>
      </div>
      <div className="hidden shrink-0 text-right sm:block">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {execution.model_name ?? "—"}
        </p>
        <p className="text-[11px] text-zinc-400">{timestamp ? new Date(timestamp).toLocaleString() : "—"}</p>
      </div>
    </div>
  );
}