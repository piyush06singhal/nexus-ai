"use client";

import { useEffect, useState } from "react";
import { Target } from "lucide-react";
import { fetchEmployees, fetchEmployeeGoals } from "@/lib/api";
import type { EmployeeGoal } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type GoalWithEmployee = EmployeeGoal & { employee_name: string; employee_role: string };

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; goals: GoalWithEmployee[] }
  | { kind: "error"; message: string };

export default function EmployeeGoalsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    load();
    return () => { cancelled = true; };

    async function load() {
      try {
        const resp = await fetchEmployees();
        const allGoals: GoalWithEmployee[] = [];
        for (const emp of resp.items) {
          const goals = await fetchEmployeeGoals(emp.id);
          for (const g of goals) {
            allGoals.push({ ...g, employee_name: emp.display_name || emp.name, employee_role: emp.role });
          }
        }
        if (!cancelled) setState({ kind: "ok", goals: allGoals });
      } catch (err: unknown) {
        if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "Failed to load goals" });
      }
    }
  }, []);

  if (state.kind === "loading") {
    return <div className="space-y-4">{[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />)}</div>;
  }

  if (state.kind === "error") {
    return <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>;
  }

  const filtered = statusFilter
    ? state.goals.filter((g) => g.status === statusFilter)
    : state.goals;

  const active = filtered.filter((g) => g.status === "active");
  const completed = filtered.filter((g) => g.status === "completed");
  const other = filtered.filter((g) => !["active", "completed"].includes(g.status));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Employee Goals</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Track goal progress across all employees. Goals are driven by actual execution data.
        </p>
      </div>

      <div className="flex gap-3">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="not_started">Not started</option>
          <option value="at_risk">At risk</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      {filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Target className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">No goals found.</p>
        </div>
      )}

      {active.length > 0 && <GoalSection title="Active Goals" goals={active} />}
      {completed.length > 0 && <GoalSection title="Completed" goals={completed} />}
      {other.length > 0 && <GoalSection title="Other" goals={other} />}
    </div>
  );
}

function GoalSection({ title, goals }: { title: string; goals: GoalWithEmployee[] }) {
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold text-zinc-500 uppercase tracking-wide">{title}</h2>
      <div className="space-y-3">
        {goals.map((g) => (
          <div key={g.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-medium text-zinc-900 dark:text-zinc-100">{g.title}</p>
                <p className="text-xs text-zinc-500">{g.employee_name} · {g.employee_role}</p>
              </div>
              <StatusBadge status={g.status} />
            </div>
            {g.description && <p className="mt-1 text-sm text-zinc-500">{g.description}</p>}
            <div className="mt-3 h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div className="h-2 rounded-full bg-emerald-500 transition-all" style={{ width: `${g.progress * 100}%` }} />
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-zinc-400">
              <span>{Math.round(g.progress * 100)}% complete</span>
              {g.target && <span>Target: {g.target}</span>}
              <span>Priority: {g.priority}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
