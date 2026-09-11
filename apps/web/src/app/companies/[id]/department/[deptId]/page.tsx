"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Users } from "lucide-react";
import {
  fetchDepartmentBudget,
  fetchDepartmentEmployees,
  fetchDepartmentGoals,
  fetchDepartmentKpis,
  fetchDepartmentPerformance,
  fetchDepartmentRisks,
  getDepartment,
} from "@/lib/api";
import type {
  BudgetSnapshot,
  Department,
  DepartmentEmployee,
  EmployeeStatus,
  Kpi,
  OrgGoal,
  Risk,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      dept: Department;
      employees: DepartmentEmployee[];
      goals: OrgGoal[];
      kpis: Kpi[];
      performance: Record<string, unknown>;
      budget: BudgetSnapshot | null;
      risks: Risk[];
    }
  | { kind: "error"; message: string };

export default function DepartmentPage({ params }: { params: Promise<{ id: string; deptId: string }> }) {
  const [ids, setIds] = useState<{ companyId: string; deptId: string }>({ companyId: "", deptId: "" });
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [tab, setTab] = useState<"overview" | "goals" | "kpis" | "employees" | "risks">("overview");

  useEffect(() => {
    params.then((p) => setIds({ companyId: p.id, deptId: p.deptId }));
  }, [params]);

  useEffect(() => {
    if (!ids.companyId || !ids.deptId) return;
    let cancelled = false;
    Promise.all([
      getDepartment(ids.deptId),
      fetchDepartmentEmployees(ids.deptId),
      fetchDepartmentGoals(ids.deptId),
      fetchDepartmentKpis(ids.deptId),
      fetchDepartmentPerformance(ids.deptId),
      fetchDepartmentBudget(ids.deptId),
      fetchDepartmentRisks(ids.deptId),
    ])
      .then(([dept, employees, goals, kpis, performance, budget, risks]) => {
        if (!cancelled) setState({ kind: "ok", dept, employees, goals, kpis, performance, budget, risks });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message || "Failed to load department" });
      });
    return () => { cancelled = true; };
  }, [ids]);

  return (
    <div className="space-y-6">
      <Link href={`/companies/${ids.companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      {state.kind === "loading" && <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && (
        <>
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{state.dept.name}</h1>
                <StatusBadge status={state.dept.status} />
              </div>
              {state.dept.mission && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{state.dept.mission}</p>}
              {state.dept.description && <p className="mt-1 text-sm text-zinc-500">{state.dept.description}</p>}
            </div>
            <div className="inline-flex items-center gap-2 rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-900/50 dark:text-zinc-300">
              <Users className="h-4 w-4" /> {state.employees.length} employees
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-6 border-b border-zinc-200 text-sm dark:border-zinc-800">
            {(["overview", "goals", "kpis", "employees", "risks"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={tab === t ? "-mb-px border-b-2 border-zinc-900 pb-3 font-medium capitalize text-zinc-900 dark:border-white dark:text-zinc-100" : "pb-3 capitalize text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"}
              >
                {t}
              </button>
            ))}
          </div>

          {tab === "overview" && <OverviewTab state={state} />}
          {tab === "goals" && (
            <div className="grid gap-3 md:grid-cols-2">
              {state.goals.length === 0 ? <EmptyHint text="No department goals yet." /> : state.goals.map((g) => (
                <div key={g.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                  <div className="flex items-start justify-between">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{g.title}</p>
                    <StatusBadge status={g.status} />
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${Math.min(100, g.progress * 100)}%` }} />
                    </div>
                    <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{Math.round(g.progress * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {tab === "kpis" && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {state.kpis.length === 0 ? <EmptyHint text="No department KPIs yet." /> : state.kpis.map((k) => (
                <div key={k.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                  <p className="text-xs text-zinc-500">{k.name}</p>
                  <p className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                    {k.current_value ?? 0}{k.unit ? ` ${k.unit}` : ""}
                  </p>
                  {k.trend && <StatusBadge status={k.trend} />}
                  <p className="mt-1 text-xs text-zinc-500">target {k.target ?? "—"}</p>
                </div>
              ))}
            </div>
          )}
          {tab === "employees" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {state.employees.length === 0 ? <EmptyHint text="No employees assigned to this department." /> : state.employees.map((e) => (
                <div key={e.id} className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                  <div className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100 text-zinc-500 dark:bg-zinc-800">
                    <Users className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{e.display_name || e.name}</p>
                    <p className="text-xs text-zinc-500">{e.role}</p>
                  </div>
                  <StatusBadge status={e.status as EmployeeStatus} />
                </div>
              ))}
            </div>
          )}
          {tab === "risks" && (
            <div className="space-y-2">
              {state.risks.length === 0 ? <EmptyHint text="No department risks registered." /> : state.risks.map((r) => (
                <div key={r.id} className="flex items-start justify-between rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
                  <div>
                    <p className="text-sm text-zinc-700 dark:text-zinc-300">{r.title}</p>
                    <p className="text-xs text-zinc-500">{r.severity}</p>
                  </div>
                  <StatusBadge status={r.status} />
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function OverviewTab({ state }: { state: Extract<LoadState, { kind: "ok" }> }) {
  const p = state.performance as Record<string, unknown>;
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Task success" value={`${num(p.success_rate)}%`} />
        <Metric label="Verification" value={`${num(p.verification_rate)}%`} />
        <Metric label="Recovery" value={`${num(p.recovery_rate)}%`} />
        <Metric label="Utilization" value={`${num(p.employee_utilization)}%`} />
      </div>

      {state.budget && (
        <section>
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Budget</h2>
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-zinc-900 dark:text-zinc-100">Department budget</span>
              <span className="text-zinc-500">
                ${state.budget.spent.toFixed(2)} / ${state.budget.monthly_limit.toFixed(2)}
              </span>
            </div>
            <div className="mt-3 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className={`h-2 rounded-full ${state.budget.utilization_pct > 95 ? "bg-red-500" : state.budget.utilization_pct > 80 ? "bg-amber-500" : "bg-emerald-500"}`}
                style={{ width: `${Math.min(100, state.budget.utilization_pct)}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              {state.budget.utilization_pct}% utilized · ${state.budget.remaining.toFixed(2)} remaining
            </p>
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Goals</h2>
        {state.goals.length === 0 ? (
          <EmptyHint text="No department goals yet." />
        ) : (
          <div className="space-y-2">
            {state.goals.map((g) => (
              <div key={g.id} className="flex items-center justify-between rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
                <p className="text-sm text-zinc-700 dark:text-zinc-300">{g.title}</p>
                <div className="flex items-center gap-3">
                  <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{Math.round(g.progress * 100)}%</span>
                  <StatusBadge status={g.status} />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-6 text-center text-sm text-zinc-500 dark:border-zinc-700 dark:bg-zinc-900/30">
      {text}
    </div>
  );
}

function num(v: unknown): string {
  if (typeof v === "number") return Number(v.toFixed ? v.toFixed(2) : v.toPrecision(3)).toString();
  if (v == null) return "0";
  return String(v);
}