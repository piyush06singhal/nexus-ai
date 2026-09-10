"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Bot, Target, TrendingUp, Wrench } from "lucide-react";
import {
  getEmployee,
  activateEmployee,
  pauseEmployee,
  resumeEmployee,
  suspendEmployee,
  terminateEmployee,
  fetchEmployeeSkills,
  fetchEmployeeGoals,
  fetchEmployeeWorkload,
  fetchEmployeePerformance,
  fetchEmployeeReviews,
  fetchEmployeeTimeline,
  fetchEmployeeAudit,
} from "@/lib/api";
import type {
  Employee,
  EmployeeSkill,
  EmployeeGoal,
  EmployeeWorkload,
  EmployeePerformance,
  EmployeeReview,
  EmployeeTimelineEvent,
  EmployeeAuditEntry,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; emp: Employee; skills: EmployeeSkill[]; goals: EmployeeGoal[]; workload: EmployeeWorkload; performance: EmployeePerformance; reviews: EmployeeReview[]; timeline: EmployeeTimelineEvent[]; audit: EmployeeAuditEntry[] }
  | { kind: "error"; message: string };

export default function EmployeeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const [employeeId, setEmployeeId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [tab, setTab] = useState<"overview" | "skills" | "goals" | "performance" | "timeline">("overview");

  useEffect(() => {
    params.then((p) => setEmployeeId(p.id));
  }, [params]);

  useEffect(() => {
    if (!employeeId) return;
    let cancelled = false;
    loadAll(employeeId, cancelled);
    return () => { cancelled = true; };
  }, [employeeId]);

  async function loadAll(id: string, cancelled: boolean) {
    try {
      const [emp, skills, goals, workload, performance, reviews, timeline, audit] = await Promise.all([
        getEmployee(id),
        fetchEmployeeSkills(id),
        fetchEmployeeGoals(id),
        fetchEmployeeWorkload(id),
        fetchEmployeePerformance(id),
        fetchEmployeeReviews(id),
        fetchEmployeeTimeline(id),
        fetchEmployeeAudit(id),
      ]);
      if (!cancelled) setState({ kind: "ok", emp, skills, goals, workload, performance, reviews, timeline, audit });
    } catch (err: unknown) {
      if (!cancelled) setState({ kind: "error", message: err instanceof Error ? err.message : "Failed to load employee" });
    }
  }

  function reload() {
    if (!employeeId) return;
    setState({ kind: "loading" });
    loadAll(employeeId, false);
  }

  async function lifecycle(action: string) {
    if (!employeeId) return;
    const fn = { activate: activateEmployee, pause: pauseEmployee, resume: resumeEmployee, suspend: suspendEmployee, terminate: terminateEmployee }[action];
    if (fn) { await fn(employeeId); reload(); }
  }

  return (
    <div className="space-y-6">
      <Link href="/employees" className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Employees
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
                <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{state.emp.display_name || state.emp.name}</h1>
                <StatusBadge status={state.emp.status} />
              </div>
              <p className="mt-1 text-sm text-zinc-500">{state.emp.role}{state.emp.department && ` · ${state.emp.department}`}</p>
              {state.emp.description && <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{state.emp.description}</p>}
            </div>
            <div className="flex gap-2">
              {state.emp.status === "draft" && <LifecycleBtn label="Activate" onClick={() => lifecycle("activate")} />}
              {state.emp.status === "active" && <LifecycleBtn label="Pause" onClick={() => lifecycle("pause")} />}
              {state.emp.status === "paused" && <LifecycleBtn label="Resume" onClick={() => lifecycle("resume")} />}
              {state.emp.status === "active" && <LifecycleBtn label="Suspend" onClick={() => lifecycle("suspend")} />}
              {(state.emp.status === "active" || state.emp.status === "paused" || state.emp.status === "suspended") && (
                <LifecycleBtn label="Terminate" onClick={() => lifecycle("terminate")} danger />
              )}
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
            {(["overview", "skills", "goals", "performance", "timeline"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm font-medium capitalize transition ${tab === t ? "border-b-2 border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100" : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"}`}>
                {t}
              </button>
            ))}
          </div>

          {/* Tab content */}
          {tab === "overview" && <OverviewTab state={state} />}
          {tab === "skills" && <SkillsTab skills={state.skills} />}
          {tab === "goals" && <GoalsTab goals={state.goals} />}
          {tab === "performance" && <PerformanceTab performance={state.performance} reviews={state.reviews} />}
          {tab === "timeline" && <TimelineTab timeline={state.timeline} audit={state.audit} />}
        </>
      )}
    </div>
  );
}

function OverviewTab({ state }: { state: Extract<LoadState, { kind: "ok" }> }) {
  const { emp, workload, performance } = state;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Identity */}
      <Card title="Identity" icon={<Bot className="h-4 w-4" />}>
        <Row label="Name" value={emp.display_name || emp.name} />
        <Row label="Role" value={emp.role} />
        {emp.department && <Row label="Department" value={emp.department} />}
        <Row label="Status" value={emp.status} />
        <Row label="Availability" value={emp.availability} />
        {emp.agent_id && <Row label="Agent ID" value={emp.agent_id.slice(0, 8)} />}
        {emp.memory_namespace && <Row label="Memory namespace" value={emp.memory_namespace} />}
      </Card>

      {/* Workload */}
      <Card title="Workload" icon={<Wrench className="h-4 w-4" />}>
        <Row label="Active tasks" value={String(workload.active_tasks)} />
        <Row label="Capacity" value={String(workload.capacity)} />
        <Row label="Utilization" value={`${Math.round(workload.utilization * 100)}%`} />
        <Row label="Available slots" value={String(workload.available_slots)} />
      </Card>

      {/* Performance */}
      <Card title="Performance" icon={<TrendingUp className="h-4 w-4" />}>
        <Row label="Tasks completed" value={String(performance.tasks_completed)} />
        <Row label="Success rate" value={`${Math.round(performance.success_rate * 100)}%`} />
        <Row label="Verification pass rate" value={`${Math.round(performance.verification_pass_rate * 100)}%`} />
        <Row label="Average quality" value={performance.average_quality.toFixed(2)} />
        <Row label="Total cost" value={`$${performance.total_cost.toFixed(2)}`} />
      </Card>

      {/* Tools & Permissions */}
      <Card title="Tools & Permissions" icon={<Wrench className="h-4 w-4" />}>
        {emp.tools && emp.tools.length > 0 ? emp.tools.map((t) => (
          <span key={t} className="mr-2 mb-1 inline-block rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">{t}</span>
        )) : <p className="text-sm text-zinc-400">No tools assigned</p>}
        {emp.permissions && emp.permissions.length > 0 && (
          <div className="mt-2">
            <p className="text-xs font-medium text-zinc-500 mb-1">Permissions</p>
            {emp.permissions.map((p) => (
              <span key={p} className="mr-2 mb-1 inline-block rounded-md bg-sky-100 px-2 py-0.5 text-xs text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">{p}</span>
            ))}
          </div>
        )}
      </Card>

      {/* Responsibilities */}
      {emp.responsibilities && emp.responsibilities.length > 0 && (
        <Card title="Responsibilities" icon={<Target className="h-4 w-4" />}>
          <ul className="list-disc pl-5 text-sm text-zinc-600 dark:text-zinc-400">
            {emp.responsibilities.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Card>
      )}

      {/* Budget */}
      <Card title="Budget" icon={<TrendingUp className="h-4 w-4" />}>
        <Row label="Tokens used" value={String(performance.total_tokens)} />
        <Row label="Cost" value={`$${performance.total_cost.toFixed(2)}`} />
        <Row label="Period" value={performance.period_start ? new Date(performance.period_start).toLocaleDateString() : "—"} />
      </Card>
    </div>
  );
}

function SkillsTab({ skills }: { skills: EmployeeSkill[] }) {
  if (skills.length === 0) return <p className="text-sm text-zinc-500">No skills recorded yet.</p>;
  return (
    <div className="space-y-3">
      {skills.map((s) => (
        <div key={s.skill_id} className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium text-zinc-900 dark:text-zinc-100">{s.name}</span>
              <span className="ml-2 text-xs text-zinc-500">{s.category}</span>
            </div>
            <span className="text-sm text-zinc-600 dark:text-zinc-400">{Math.round(s.proficiency * 100)}%</span>
          </div>
          <div className="mt-2 h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div className="h-1.5 rounded-full bg-zinc-900 dark:bg-zinc-100" style={{ width: `${s.proficiency * 100}%` }} />
          </div>
          <p className="mt-1 text-xs text-zinc-400">Confidence: {Math.round(s.confidence * 100)}% · Evidence: {s.evidence_count}</p>
        </div>
      ))}
    </div>
  );
}

function GoalsTab({ goals }: { goals: EmployeeGoal[] }) {
  if (goals.length === 0) return <p className="text-sm text-zinc-500">No goals set yet.</p>;
  return (
    <div className="space-y-3">
      {goals.map((g) => (
        <div key={g.id} className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between">
            <span className="font-medium text-zinc-900 dark:text-zinc-100">{g.title}</span>
            <StatusBadge status={g.status} />
          </div>
          {g.description && <p className="mt-1 text-sm text-zinc-500">{g.description}</p>}
          <div className="mt-2 h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-800">
            <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${g.progress * 100}%` }} />
          </div>
          <p className="mt-1 text-xs text-zinc-400">{Math.round(g.progress * 100)}% complete · Priority: {g.priority}</p>
        </div>
      ))}
    </div>
  );
}

function PerformanceTab({ performance, reviews }: { performance: EmployeePerformance; reviews: EmployeeReview[] }) {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Tasks completed" value={String(performance.tasks_completed)} />
        <StatCard label="Success rate" value={`${Math.round(performance.success_rate * 100)}%`} />
        <StatCard label="Avg quality" value={performance.average_quality.toFixed(2)} />
        <StatCard label="Total cost" value={`$${performance.total_cost.toFixed(2)}`} />
        <StatCard label="Avg latency" value={`${Math.round(performance.average_latency_ms)}ms`} />
        <StatCard label="Utilization" value={`${Math.round(performance.utilization * 100)}%`} />
        <StatCard label="Deadline adherence" value={`${Math.round(performance.deadline_adherence * 100)}%`} />
        <StatCard label="Recovery rate" value={`${Math.round(performance.recovery_rate * 100)}%`} />
      </div>
      {reviews.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Reviews</h3>
          <div className="space-y-3">
            {reviews.map((r) => (
              <div key={r.id} className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
                <p className="text-xs text-zinc-400">{new Date(r.created_at).toLocaleDateString()} · by {r.reviewer}</p>
                {r.strengths && r.strengths.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-emerald-600">Strengths</p>
                    <ul className="list-disc pl-5 text-sm text-zinc-600 dark:text-zinc-400">{r.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  </div>
                )}
                {r.recommendations && r.recommendations.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-zinc-500">Recommendations</p>
                    <ul className="list-disc pl-5 text-sm text-zinc-600 dark:text-zinc-400">{r.recommendations.map((s, i) => <li key={i}>{s}</li>)}</ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TimelineTab({ timeline, audit }: { timeline: EmployeeTimelineEvent[]; audit: EmployeeAuditEntry[] }) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Activity Timeline</h3>
        {timeline.length === 0 ? <p className="text-sm text-zinc-500">No activity yet.</p> : (
          <div className="space-y-2">
            {timeline.map((e) => (
              <div key={e.event_id} className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
                <div className="mt-1 h-2 w-2 rounded-full bg-zinc-400" />
                <div>
                  <p className="text-sm text-zinc-900 dark:text-zinc-100">{e.description}</p>
                  <p className="text-xs text-zinc-400">{e.timestamp ? new Date(e.timestamp).toLocaleString() : "—"}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 mb-3">Audit Log</h3>
        {audit.length === 0 ? <p className="text-sm text-zinc-500">No audit entries.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-zinc-200 dark:border-zinc-800 text-left text-xs text-zinc-500">
                <th className="pb-2 pr-4">Action</th><th className="pb-2 pr-4">Actor</th><th className="pb-2 pr-4">Target</th><th className="pb-2">Time</th>
              </tr></thead>
              <tbody>{audit.map((a) => (
                <tr key={a.id} className="border-b border-zinc-100 dark:border-zinc-800/50">
                  <td className="py-2 pr-4"><StatusBadge status={a.action as "active"} /></td>
                  <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{a.actor}</td>
                  <td className="py-2 pr-4 text-zinc-600 dark:text-zinc-400">{a.target_type}{a.target_id ? ` · ${a.target_id.slice(0, 8)}` : ""}</td>
                  <td className="py-2 text-zinc-400">{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Card({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">{icon}{title}</h3>
      <div className="mt-3 space-y-2">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="font-medium text-zinc-900 dark:text-zinc-100">{value}</span>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}

function LifecycleBtn({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button onClick={onClick} className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${danger ? "border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40" : "border-zinc-300 text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"}`}>
      {label}
    </button>
  );
}
