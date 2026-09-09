"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bot, ListChecks } from "lucide-react";
import { fetchAgents, fetchTasks } from "@/lib/api";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      agents: { total: number; active: number };
      tasks: { total: number; completed: number };
    }
  | { kind: "error"; message: string };

/** Live count of agents and tasks, linking to their management pages. */
export function WorkforceOverview() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  // Initial load — async callbacks only (avoids the set-state-in-effect rule).
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchAgents(), fetchTasks()])
      .then(([agents, tasks]) => {
        if (cancelled) return;
        setState({
          kind: "ok",
          agents: {
            total: agents.length,
            active: agents.filter((a) => a.status === "active").length,
          },
          tasks: {
            total: tasks.length,
            completed: tasks.filter((t) => t.status === "completed").length,
          },
        });
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
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {[0, 1].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
        ))}
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        Could not load workforce overview: {state.message}
      </p>
    );
  }

  const { agents, tasks } = state;
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Link
        href="/agents"
        className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-5 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700"
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800">
          <Bot className="h-5 w-5 text-zinc-500 dark:text-zinc-400" />
        </div>
        <div>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {agents.total}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Agents · {agents.active} active
          </p>
        </div>
      </Link>
      <Link
        href="/tasks"
        className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-5 hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700"
      >
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-zinc-100 dark:bg-zinc-800">
          <ListChecks className="h-5 w-5 text-zinc-500 dark:text-zinc-400" />
        </div>
        <div>
          <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {tasks.total}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Tasks · {tasks.completed} completed
          </p>
        </div>
      </Link>
    </div>
  );
}