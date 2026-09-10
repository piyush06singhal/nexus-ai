"use client";

import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";
import { fetchEmployees, fetchEmployeePerformance } from "@/lib/api";
import type { EmployeePerformance } from "@/lib/types";

type PerfWithEmployee = EmployeePerformance & { employee_name: string; employee_role: string };

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; metrics: PerfWithEmployee[] }
  | { kind: "error"; message: string };

export default function EmployeePerformancePage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    load();
    return () => { cancelled = true; };

    async function load() {
      try {
        const resp = await fetchEmployees();
        const metrics = await Promise.all(
          resp.items
            .filter((e) => e.status === "active" || e.status === "busy")
            .map(async (emp) => {
              const perf = await fetchEmployeePerformance(emp.id);
              return { ...perf, employee_name: emp.display_name || emp.name, employee_role: emp.role };
            }),
        );
        if (!cancelled) setState({ kind: "ok", metrics });
      } catch (err: unknown) {
        if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "Failed to load performance" });
      }
    }
  }, []);

  if (state.kind === "loading") {
    return <div className="space-y-4"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />)}</div></div>;
  }

  if (state.kind === "error") {
    return <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>;
  }

  const metrics = state.metrics;
  const totalCompleted = metrics.reduce((s, m) => s + m.tasks_completed, 0);
  const totalFailed = metrics.reduce((s, m) => s + m.tasks_failed, 0);
  const avgSuccess = metrics.length > 0 ? metrics.reduce((s, m) => s + m.success_rate, 0) / metrics.length : 0;
  const totalCost = metrics.reduce((s, m) => s + m.total_cost, 0);
  const avgQuality = metrics.length > 0 ? metrics.reduce((s, m) => s + m.average_quality, 0) / metrics.length : 0;
  const avgUtil = metrics.length > 0 ? metrics.reduce((s, m) => s + m.utilization, 0) / metrics.length : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Employee Performance</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Aggregate and per-employee performance metrics across active employees.
        </p>
      </div>

      {metrics.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <TrendingUp className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">No active employees to display performance for.</p>
        </div>
      )}

      {/* Aggregate stats */}
      {metrics.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total completed" value={String(totalCompleted)} />
          <StatCard label="Total failed" value={String(totalFailed)} />
          <StatCard label="Avg success rate" value={`${Math.round(avgSuccess * 100)}%`} />
          <StatCard label="Avg quality" value={avgQuality.toFixed(2)} />
          <StatCard label="Total cost" value={`$${totalCost.toFixed(2)}`} />
          <StatCard label="Avg utilization" value={`${Math.round(avgUtil * 100)}%`} />
          <StatCard label="Employees" value={String(metrics.length)} />
        </div>
      )}

      {/* Per-employee comparison */}
      {metrics.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-zinc-500 uppercase tracking-wide">Per-Employee Breakdown</h2>
          <div className="overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50 text-left text-xs text-zinc-500">
                  <th className="px-4 py-3">Employee</th>
                  <th className="px-4 py-3 text-right">Completed</th>
                  <th className="px-4 py-3 text-right">Success</th>
                  <th className="px-4 py-3 text-right">Quality</th>
                  <th className="px-4 py-3 text-right">Cost</th>
                  <th className="px-4 py-3 text-right">Utilization</th>
                  <th className="px-4 py-3 text-right">Latency</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map((m) => (
                  <tr key={m.employee_id} className="border-b border-zinc-100 dark:border-zinc-800/50">
                    <td className="px-4 py-3">
                      <a href={`/employees/${m.employee_id}`} className="font-medium text-zinc-900 hover:underline dark:text-zinc-100">{m.employee_name}</a>
                      <span className="ml-2 text-xs text-zinc-400">{m.employee_role}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">{m.tasks_completed}</td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">{Math.round(m.success_rate * 100)}%</td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">{m.average_quality.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">${m.total_cost.toFixed(2)}</td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">{Math.round(m.utilization * 100)}%</td>
                    <td className="px-4 py-3 text-right text-zinc-600 dark:text-zinc-400">{Math.round(m.average_latency_ms)}ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}
