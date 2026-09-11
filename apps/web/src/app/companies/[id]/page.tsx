"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Building2, RefreshCw, Users } from "lucide-react";
import {
  activateCompany,
  checkCompanyAlerts,
  getCompany,
  fetchCompanyAlerts,
  fetchCompanyBudgets,
  fetchCompanyEmployees,
  fetchCompanyGoals,
  fetchCompanyHealth,
  fetchCompanyKpis,
  fetchCompanyPerformance,
  fetchCompanyRisks,
  fetchDepartments,
  fetchTimeline,
  generateReport,
  pauseCompany,
  archiveCompany,
} from "@/lib/api";
import type {
  Alert,
  BudgetSnapshot,
  Company,
  CompanyEmployee,
  CompanyHealth,
  Department,
  EmployeeStatus,
  Kpi,
  OrgEvent,
  OrgGoal,
  Risk,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | {
      kind: "ok";
      company: Company;
      health: CompanyHealth;
      performance: Record<string, unknown>;
      goals: OrgGoal[];
      kpis: Kpi[];
      departments: Department[];
      employees: CompanyEmployee[];
      budgets: { company: BudgetSnapshot | null; departments: BudgetSnapshot[] };
      risks: Risk[];
      alerts: Alert[];
      timeline: OrgEvent[];
    }
  | { kind: "error"; message: string };

export default function CompanyOverviewPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [tab, setTab] = useState<"overview" | "timeline">("overview");
  const [reportMsg, setReportMsg] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    loadAll(companyId, cancelled);
    return () => { cancelled = true; };
  }, [companyId]);

  async function loadAll(id: string, cancelled: boolean) {
    try {
      const [
        company,
        health,
        performance,
        goals,
        kpis,
        departments,
        employees,
        budgets,
        risks,
        alerts,
        timeline,
      ] = await Promise.all([
        getCompany(id),
        fetchCompanyHealth(id),
        fetchCompanyPerformance(id),
        fetchCompanyGoals(id),
        fetchCompanyKpis(id),
        fetchDepartments(id),
        fetchCompanyEmployees(id),
        fetchCompanyBudgets(id),
        fetchCompanyRisks(id),
        fetchCompanyAlerts(id),
        fetchTimeline(id, 20),
      ]);
      if (!cancelled) {
        setState({
          kind: "ok",
          company,
          health,
          performance,
          goals,
          kpis,
          departments,
          employees,
          budgets,
          risks,
          alerts,
          timeline,
        });
      }
    } catch (err: unknown) {
      if (!cancelled) {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load company",
        });
      }
    }
  }

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    loadAll(companyId, false);
  }

  async function lifecycle(action: "activate" | "pause" | "archive") {
    if (!companyId) return;
    if (action === "activate") await activateCompany(companyId);
    else if (action === "pause") await pauseCompany(companyId);
    else await archiveCompany(companyId);
    reload();
  }

  async function handleCheckAlerts() {
    await checkCompanyAlerts(companyId);
    reload();
  }

  async function handleGenerateReport() {
    setReportMsg(null);
    try {
      const report = await generateReport(companyId, "weekly");
      setReportMsg(
        `Report created and ${report.verification_status === "verified" ? "verified" : "generated"} (${report.report_type}).`,
      );
    } catch (err) {
      setReportMsg(err instanceof Error ? err.message : "Failed to generate report");
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/companies" className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Companies
      </Link>

      {state.kind === "loading" && (
        <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
      )}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {state.kind === "ok" && (
        <>
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{state.company.name}</h1>
                <StatusBadge status={state.company.status} />
                <StatusBadge status={state.health.status} />
              </div>
              <p className="mt-1 text-sm text-zinc-500">{state.company.industry ?? "company"}{state.company.timezone && ` · ${state.company.timezone}`}</p>
              {state.company.mission && <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{state.company.mission}</p>}
            </div>
            <div className="flex gap-2">
              {state.company.status === "draft" && <LifecycleBtn label="Activate" onClick={() => lifecycle("activate")} />}
              {state.company.status === "active" && <LifecycleBtn label="Pause" onClick={() => lifecycle("pause")} />}
              {state.company.status === "paused" && <LifecycleBtn label="Archive" onClick={() => lifecycle("archive")} danger />}
            </div>
          </div>

          {/* Executive dashboard stat row */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Health score" value={`${state.health.overall_score}/100`} sub={`${state.health.status}`} />
            <StatCard label="Employees" value={String(state.employees.length)} sub={`${state.departments.length} departments`} />
            <StatCard label="Active goals" value={String(state.goals.filter((g) => g.status === "active" || g.status === "at_risk").length)} sub="company + department" />
            <StatCard label="Open risks" value={String(state.risks.filter((r) => r.status === "open" || r.status === "mitigating").length)} sub={`${state.alerts.filter((a) => a.severity === "critical").length} critical alerts`} />
          </div>

          {/* Quick navigation */}
          <div className="flex flex-wrap gap-2">
            {[
              ["Organization chart", `/companies/${companyId}/organization-chart`],
              ["Goals", `/companies/${companyId}/goals`],
              ["KPIs", `/companies/${companyId}/kpis`],
              ["Budget", `/companies/${companyId}/budget`],
              ["Decisions", `/companies/${companyId}/decisions`],
              ["Risks", `/companies/${companyId}/risks`],
              ["Alerts", `/companies/${companyId}/alerts`],
            ].map(([label, href]) => (
              <Link
                key={href}
                href={href}
                className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                {label}
              </Link>
            ))}
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleCheckAlerts}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Check alerts
            </button>
            <button
              onClick={handleGenerateReport}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              Generate weekly report
            </button>
            {reportMsg && <span className="text-xs text-zinc-500">{reportMsg}</span>}
          </div>

          {/* Tabs */}
          <div className="flex gap-6 border-b border-zinc-200 text-sm dark:border-zinc-800">
            {(["overview", "timeline"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={tab === t ? "-mb-px border-b-2 border-zinc-900 pb-3 font-medium text-zinc-900 dark:border-white dark:text-zinc-100" : "pb-3 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"}
              >
                {t === "overview" ? "Overview" : "Timeline"}
              </button>
            ))}
          </div>

          {tab === "overview" && <OverviewTab state={state} companyId={companyId} />}
          {tab === "timeline" && <TimelineTab events={state.timeline} />}
        </>
      )}
    </div>
  );
}

function OverviewTab({ state, companyId }: { state: Extract<LoadState, { kind: "ok" }>; companyId: string }) {
  const p = state.performance as Record<string, unknown>;
  return (
    <div className="space-y-6">
      {/* Health dimensions */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Health dimensions</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(state.health.dimensions).map(([dim, score]) => (
            <div key={dim} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
              <div className="flex items-center justify-between">
                <span className="text-xs capitalize text-zinc-500">{dim.replace("_", " ")}</span>
                <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{score}</span>
              </div>
              <div className="mt-2 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className={score >= 75 ? "h-1.5 rounded-full bg-emerald-500" : score >= 50 ? "h-1.5 rounded-full bg-amber-500" : "h-1.5 rounded-full bg-red-500"}
                  style={{ width: `${Math.min(100, score)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Performance row */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Task success" value={`${num(p.success_rate)}%`} />
        <Metric label="Verification" value={`${num(p.verification_rate)}%`} />
        <Metric label="Recovery" value={`${num(p.recovery_rate)}%`} />
        <Metric label="Total cost" value={`$${num(p.total_cost)}`} />
      </section>

      {/* Goals preview */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Goals</h2>
          <Link href={`/companies/${companyId}/goals`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            View all →
          </Link>
        </div>
        {state.goals.length === 0 ? (
          <EmptyHint text="No goals yet. Add company or department goals to track progress." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {state.goals.slice(0, 6).map((g) => (
              <div key={g.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{g.title}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">{g.scope_type} · prio {g.priority}</p>
                  </div>
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
      </section>

      {/* KPIs */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">KPIs</h2>
          <Link href={`/companies/${companyId}/kpis`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            View all →
          </Link>
        </div>
        {state.kpis.length === 0 ? (
          <EmptyHint text="No KPIs yet. KPIs are computed from authoritative data." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {state.kpis.map((k) => (
              <div key={k.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                <p className="text-xs text-zinc-500">{k.name}</p>
                <p className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
                  {k.current_value ?? 0}{k.unit ? ` ${k.unit}` : ""}
                </p>
                {k.trend && <StatusBadge status={k.trend} />}
                {k.current_value != null && k.target != null && (
                  <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
                    <span>target {k.target}{k.unit ? ` ${k.unit}` : ""}</span>
                    <span className={k.variance != null && k.variance < 0 ? "text-red-600" : "text-emerald-600"}>
                      {k.variance != null ? (k.variance >= 0 ? "+" : "") + k.variance : ""}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Budget */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Budget</h2>
          <Link href={`/companies/${companyId}/budget`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            View detail →
          </Link>
        </div>
        {state.budgets.company ? (
          <BudgetBar snap={state.budgets.company} />
        ) : (
          <EmptyHint text="No budget set. Configure a company budget in the budget dashboard." />
        )}
      </section>

      {/* Risks */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Top risks</h2>
          <Link href={`/companies/${companyId}/risks`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            Risk center →
          </Link>
        </div>
        {state.risks.length === 0 ? (
          <EmptyHint text="No risks registered." />
        ) : (
          <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
            {state.risks.slice(0, 5).map((r, i) => (
              <div key={r.id} className={`flex items-center justify-between px-4 py-3 ${i > 0 ? "border-t border-zinc-100 dark:border-zinc-800" : ""}`}>
                <div className="flex items-center gap-3">
                  <span className={`h-2 w-2 rounded-full ${sevColor(r.severity)}`} />
                  <span className="text-sm text-zinc-700 dark:text-zinc-300">{r.title}</span>
                </div>
                <StatusBadge status={r.status} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Departments */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Departments</h2>
          <span className="text-xs text-zinc-500">{state.departments.length} total</span>
        </div>
        {state.departments.length === 0 ? (
          <EmptyHint text="No departments yet. Add departments from this company dashboard." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {state.departments.map((d) => (
              <Link
                key={d.id}
                href={`/companies/${companyId}/department/${d.id}`}
                className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{d.name}</p>
                    {d.mission && <p className="mt-0.5 line-clamp-1 text-xs text-zinc-500">{d.mission}</p>}
                  </div>
                  <StatusBadge status={d.status} />
                </div>
                <p className="mt-2 text-xs text-zinc-500">
                  {state.employees.filter((e) => e.responsible_scope?.department_id === d.id).length} employees
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Employees */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Employees</h2>
          <span className="inline-flex items-center gap-1 text-xs text-zinc-500"><Users className="h-3.5 w-3.5" /> {state.employees.length}</span>
        </div>
        {state.employees.length === 0 ? (
          <EmptyHint text="No members yet. Add employee memberships from company settings." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {state.employees.slice(0, 9).map((e) => (
              <div key={e.id} className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                <div className="flex h-9 w-9 items-center justify-center rounded-full bg-zinc-100 text-zinc-500 dark:bg-zinc-800">
                  <Building2 className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{e.display_name || e.name}</p>
                  <p className="text-xs text-zinc-500">{e.role}{e.department && ` · ${e.department}`}</p>
                </div>
                <StatusBadge status={e.status as EmployeeStatus} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Alerts */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Active alerts</h2>
          <Link href={`/companies/${companyId}/alerts`} className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            Alert center →
          </Link>
        </div>
        {state.alerts.length === 0 ? (
          <EmptyHint text="No alerts. Run threshold checks to detect violations." />
        ) : (
          <div className="space-y-2">
            {state.alerts.filter((a) => a.status === "active").slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
                <div className="flex items-center gap-3">
                  <span className={`h-2 w-2 rounded-full ${a.severity === "critical" ? "bg-red-500" : a.severity === "warning" ? "bg-amber-500" : "bg-sky-500"}`} />
                  <div>
                    <p className="text-sm text-zinc-700 dark:text-zinc-300">{a.title}</p>
                    <p className="text-xs text-zinc-500">{a.category}</p>
                  </div>
                </div>
                <StatusBadge status={a.severity} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TimelineTab({ events }: { events: OrgEvent[] }) {
  if (events.length === 0) return <EmptyHint text="No events recorded yet." />;
  return (
    <div className="space-y-2">
      {events.map((e) => (
        <div key={e.id} className="flex items-start gap-3 rounded-lg border border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-zinc-400" />
          <div className="min-w-0">
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              <span className="font-medium">{e.action.replace(/_/g, " ")}</span>
              {e.target_type && <span className="text-zinc-500"> · {e.target_type.replace(/_/g, " ")}</span>}
            </p>
            {e.actor && <p className="text-xs text-zinc-500">by {e.actor}</p>}
          </div>
          {e.created_at && <span className="ml-auto text-xs text-zinc-400">{fmtDate(e.created_at)}</span>}
        </div>
      ))}
    </div>
  );
}

function BudgetBar({ snap }: { snap: BudgetSnapshot }) {
  const pct = Math.min(100, snap.utilization_pct ?? 0);
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-zinc-900 dark:text-zinc-100">Company budget</span>
        <span className="text-zinc-500">
          ${snap.spent.toFixed(2)} / ${snap.monthly_limit.toFixed(2)}
        </span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-zinc-100 dark:bg-zinc-800">
        <div className={`h-2 rounded-full ${snap.utilization_pct > 95 ? "bg-red-500" : snap.utilization_pct > 80 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        {snap.utilization_pct}% utilized · ${snap.remaining.toFixed(2)} remaining
      </p>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
      <p className="mt-0.5 text-xs capitalize text-zinc-400">{sub}</p>
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

function sevColor(severity: string): string {
  switch (severity) {
    case "critical": return "bg-red-500";
    case "high": return "bg-red-500";
    case "medium": return "bg-amber-500";
    case "low": return "bg-sky-500";
    default: return "bg-zinc-400";
  }
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function LifecycleBtn({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={danger
        ? "rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
        : "rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"}
    >
      {label}
    </button>
  );
}