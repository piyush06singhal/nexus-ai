"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Wallet } from "lucide-react";
import { fetchCompanyBudgets, fetchDepartments } from "@/lib/api";
import type { BudgetSnapshot, Department } from "@/lib/types";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; budgets: { company: BudgetSnapshot | null; departments: BudgetSnapshot[] }; departments: Department[] }
  | { kind: "error"; message: string };

export default function CompanyBudgetPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    Promise.all([fetchCompanyBudgets(companyId), fetchDepartments(companyId)])
      .then(([budgets, departments]) => {
        if (!cancelled) setState({ kind: "ok", budgets, departments });
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load budget",
          });
        }
      });
    return () => { cancelled = true; };
  }, [companyId]);

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div>
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Budget</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Company and department budget utilization, enforced by the resource governor.
        </p>
      </div>

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && (
        <div className="space-y-6">
          {state.budgets.company ? (
            <BudgetCard snap={state.budgets.company} isCompany companyId={companyId} />
          ) : (
            <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-8 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
              <Wallet className="mx-auto h-8 w-8 text-zinc-400" />
              <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
                No company budget configured. Budgets are seeded via the API or the demo seed script.
              </p>
            </div>
          )}

          <section>
            <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Department budgets</h2>
            {state.budgets.departments.length === 0 ? (
              <p className="text-sm text-zinc-500">No department budgets configured.</p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {state.budgets.departments.map((snap) => {
                  const dept = state.departments.find((d) => d.id === snap.scope_id);
                  return (
                    <BudgetCard
                      key={snap.scope_id}
                      snap={snap}
                      label={dept?.name ?? "Department"}
                      deptId={dept?.id}
                      companyId={companyId}
                    />
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function BudgetCard({ snap, isCompany, label, deptId, companyId }: { snap: BudgetSnapshot; isCompany?: boolean; label?: string; deptId?: string; companyId?: string }) {
  const pct = Math.min(100, snap.utilization_pct ?? 0);
  const barColor = snap.utilization_pct > 95 ? "bg-red-500" : snap.utilization_pct > 80 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {label ?? (isCompany ? "Company budget" : "Department budget")}
          </p>
          <p className="text-xs text-zinc-500">scope: {snap.scope_type}</p>
        </div>
        <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${snap.utilization_pct > 80 ? "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"}`}>
          {snap.utilization_pct}% used
        </span>
      </div>

      <div className="mt-4 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div className={`h-2 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">${snap.spent.toFixed(2)}</p>
          <p className="text-[11px] text-zinc-500">spent</p>
        </div>
        <div>
          <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">${snap.remaining.toFixed(2)}</p>
          <p className="text-[11px] text-zinc-500">remaining</p>
        </div>
        <div>
          <p className="text-base font-semibold text-zinc-900 dark:text-zinc-100">${snap.monthly_limit.toFixed(2)}</p>
          <p className="text-[11px] text-zinc-500">limit</p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-zinc-100 pt-3 text-xs text-zinc-500 dark:border-zinc-800">
        <span>{snap.tokens_used.toLocaleString()} tokens</span>
        <span>{snap.execution_count} executions</span>
        <span>${snap.cost_used.toFixed(2)} cost used</span>
        <span>{snap.tool_calls_used} tool calls</span>
      </div>

      {deptId && companyId && (
        <Link
          href={`/companies/${companyId}/department/${deptId}`}
          className="mt-3 inline-block text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
        >
          Open department →
        </Link>
      )}
    </div>
  );
}