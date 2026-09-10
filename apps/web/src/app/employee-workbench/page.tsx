"use client";

import { useEffect, useState } from "react";
import { ClipboardList } from "lucide-react";
import { fetchEmployees, fetchEmployeeWorkload } from "@/lib/api";
import type { Employee, EmployeeWorkload } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; employees: (Employee & { workload: EmployeeWorkload })[] }
  | { kind: "error"; message: string };

export default function EmployeeWorkbenchPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    load();
    return () => { cancelled = true; };

    async function load() {
      try {
        const resp = await fetchEmployees();
        const employees = await Promise.all(
          resp.items.map(async (emp) => {
            const workload = await fetchEmployeeWorkload(emp.id);
            return { ...emp, workload };
          }),
        );
        if (!cancelled) setState({ kind: "ok", employees });
      } catch (err: unknown) {
        if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "Failed to load workbench" });
      }
    }
  }, []);

  if (state.kind === "loading") {
    return <div className="space-y-6"><div className="h-8 w-48 animate-pulse rounded bg-zinc-200 dark:bg-zinc-800" /><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="h-40 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />)}</div></div>;
  }

  if (state.kind === "error") {
    return <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>;
  }

  const active = state.employees.filter((e) => e.status === "active" || e.status === "busy");
  const draft = state.employees.filter((e) => e.status === "draft");
  const paused = state.employees.filter((e) => e.status === "paused" || e.status === "suspended");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Employee Workbench</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Overview of all employees grouped by their current status. View workload, availability, and capacity at a glance.
        </p>
      </div>

      {state.employees.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <ClipboardList className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">No employees to display.</p>
        </div>
      )}

      <Section title="Active & Busy" employees={active} />
      <Section title="Draft" employees={draft} />
      <Section title="Paused & Suspended" employees={paused} />
    </div>
  );
}

function Section({ title, employees }: { title: string; employees: (Employee & { workload: EmployeeWorkload })[] }) {
  if (employees.length === 0) return null;
  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold text-zinc-500 uppercase tracking-wide">{title}</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {employees.map((emp) => (
          <a
            key={emp.id}
            href={`/employees/${emp.id}`}
            className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium text-zinc-900 dark:text-zinc-100">{emp.display_name || emp.name}</p>
                <p className="text-xs text-zinc-500">{emp.role}</p>
              </div>
              <StatusBadge status={emp.status} />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <MiniStat label="Active" value={emp.workload.active_tasks} />
              <MiniStat label="Capacity" value={emp.workload.capacity} />
              <MiniStat label="Util" value={`${Math.round(emp.workload.utilization * 100)}%`} />
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-[11px] text-zinc-400">{label}</p>
      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}
