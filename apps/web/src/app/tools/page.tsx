"use client";

import { useEffect, useState } from "react";
import { Clock, Shield, Wrench } from "lucide-react";
import { fetchTools } from "@/lib/api";
import type { ToolDefinition } from "@/lib/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; tools: ToolDefinition[] }
  | { kind: "error"; message: string };

export default function ToolsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchTools()
      .then((tools) => {
        if (!cancelled) setState({ kind: "ok", tools });
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
          Tools
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Tools that agents can call during execution — from math and text
          processing to structured data operations.
        </p>
      </div>

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-28 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800"
            />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {state.kind === "ok" && (
        <div className="grid gap-4 sm:grid-cols-2">
          {state.tools.map((tool) => (
            <ToolCard key={tool.name} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCard({ tool }: { tool: ToolDefinition }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start gap-3">
        <div
          className={
            tool.dangerous
              ? "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-900/40"
              : "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800"
          }
        >
          <Wrench
            className={
              tool.dangerous
                ? "h-4 w-4 text-amber-600 dark:text-amber-400"
                : "h-4 w-4 text-zinc-500 dark:text-zinc-400"
            }
          />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {tool.name}
            </span>
            {tool.dangerous && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                <Shield className="h-3 w-3" />
                dangerous
              </span>
            )}
          </div>
          <p className="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            {tool.description}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 text-[11px] text-zinc-400">
        <Clock className="h-3 w-3" />
        Timeout {tool.timeout_seconds}s
        {tool.tags.length > 0 && (
          <span className="ml-2">
            {tool.tags.map((t) => (
              <span
                key={t}
                className="mr-1 rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
              >
                {t}
              </span>
            ))}
          </span>
        )}
      </div>

      {tool.parameters.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
            Parameters
          </p>
          <ul className="mt-1 space-y-1">
            {tool.parameters.map((p) => (
              <li
                key={p.name}
                className="flex items-baseline gap-2 font-mono text-xs text-zinc-600 dark:text-zinc-400"
              >
                <span className="font-medium text-zinc-800 dark:text-zinc-200">
                  {p.name}
                </span>
                <span className="text-zinc-400">{p.type}</span>
                {p.required ? (
                  <span className="text-red-500">*</span>
                ) : (
                  <span className="text-zinc-400">optional</span>
                )}
                {p.enum && (
                  <span className="text-zinc-400">
                    ∈ {"{"}
                    {p.enum.join(", ")}
                    {"}"}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
