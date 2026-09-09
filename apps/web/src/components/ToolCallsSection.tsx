"use client";

import { useEffect, useState } from "react";
import { Wrench } from "lucide-react";
import { fetchToolCalls } from "@/lib/api";
import type { ToolCallRecord } from "@/lib/types";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; calls: ToolCallRecord[] }
  | { kind: "error"; message: string };

const STATUS_COLORS: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  timeout: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  denied: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
};

export function ToolCallsSection({ executionId }: { executionId: string }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (state.kind !== "loading") return;
    fetchToolCalls(executionId)
      .then((calls) => setState({ kind: "ok", calls }))
      .catch((err: Error) =>
        setState({ kind: "error", message: err.message }),
      );
  }, [executionId, state.kind]);

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => {
          if (!expanded) setState({ kind: "loading" });
          setExpanded((v) => !v);
        }}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
      >
        <Wrench className="h-3.5 w-3.5" />
        {expanded ? "Hide" : "Show"} tool calls
      </button>

      {expanded && state.kind === "loading" && (
        <p className="mt-2 text-xs text-zinc-500">Loading tool calls…</p>
      )}

      {expanded && state.kind === "error" && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">
          {state.message}
        </p>
      )}

      {expanded && state.kind === "ok" && state.calls.length === 0 && (
        <p className="mt-2 text-xs italic text-zinc-500">
          No tool calls for this execution.
        </p>
      )}

      {expanded && state.kind === "ok" && state.calls.length > 0 && (
        <ul className="mt-2 space-y-2">
          {state.calls.map((call) => (
            <li
              key={call.id}
              className="rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/40"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-semibold text-zinc-900 dark:text-zinc-100">
                  {call.tool_name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_COLORS[call.result_status] ?? "bg-zinc-100 text-zinc-600"}`}
                >
                  {call.result_status}
                </span>
                <span className="text-[11px] text-zinc-400">
                  iter {call.iteration}
                </span>
                {call.execution_time_ms != null && (
                  <span className="text-[11px] text-zinc-400">
                    {call.execution_time_ms.toFixed(1)}ms
                  </span>
                )}
              </div>
              <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                    Arguments
                  </p>
                  <pre className="mt-0.5 overflow-auto rounded bg-white p-1.5 font-mono text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    {JSON.stringify(call.arguments, null, 2) ?? "{}"}
                  </pre>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                    Result
                  </p>
                  {call.result_error ? (
                    <p className="mt-0.5 rounded bg-red-50 p-1.5 font-mono text-[11px] text-red-700 dark:bg-red-950/40 dark:text-red-300">
                      {call.result_error}
                    </p>
                  ) : (
                    <pre className="mt-0.5 overflow-auto rounded bg-white p-1.5 font-mono text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                      {JSON.stringify(call.result_data, null, 2) ?? "—"}
                    </pre>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
