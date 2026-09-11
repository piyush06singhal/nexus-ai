"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, Target } from "lucide-react";
import {
  createCompanyGoal,
  fetchCompanyGoals,
  fetchDepartments,
  fetchGoalTree,
  recomputeGoalProgress,
} from "@/lib/api";
import type { Department, GoalScopeType, OrgGoal } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; goals: OrgGoal[]; departments: Department[]; tree: OrgGoal[] }
  | { kind: "error"; message: string };

export default function CompanyGoalsPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [scopeFilter, setScopeFilter] = useState<string>("");

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    loadAll(companyId, cancelled, scopeFilter || undefined);
    return () => { cancelled = true; };
  }, [companyId, scopeFilter]);

  async function loadAll(id: string, cancelled: boolean, scope?: string) {
    try {
      const [goals, departments, tree] = await Promise.all([
        fetchCompanyGoals(id, scope as GoalScopeType | undefined),
        fetchDepartments(id),
        fetchGoalTree(id),
      ]);
      if (!cancelled) setState({ kind: "ok", goals, departments, tree });
    } catch (err) {
      if (!cancelled) {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load goals",
        });
      }
    }
  }

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    loadAll(companyId, false, scopeFilter || undefined);
  }

  async function handleRecompute(id: string) {
    await recomputeGoalProgress(id);
    reload();
  }

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Goals</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Company and department goal tree with progress recomputed from real evidence.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New goal
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {showForm && state.kind === "ok" && (
        <GoalForm
          companyId={companyId}
          departments={state.departments}
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {state.kind === "ok" && state.goals.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <select
            value={scopeFilter}
            onChange={(e) => setScopeFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All scopes</option>
            <option value="company">Company</option>
            <option value="department">Department</option>
            <option value="employee">Employee</option>
          </select>
        </div>
      )}

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "ok" && state.goals.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Target className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No goals yet. Create a company or department goal to start tracking progress.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.goals.length > 0 && (
        <div className="space-y-6">
          <section>
            <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">Goal tree</h2>
            <div className="space-y-2">
              {buildTree(state.tree).map((g) => <GoalRow key={g.id} goal={g} onRecompute={handleRecompute} />)}
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold text-zinc-900 dark:text-zinc-100">All goals</h2>
            <div className="grid gap-3 md:grid-cols-2">
              {state.goals.map((g) => (
                <GoalCard key={g.id} goal={g} onRecompute={handleRecompute} />
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function GoalRow({ goal, depth = 0, onRecompute }: { goal: OrgGoal & { children?: OrgGoal[] }; depth?: number; onRecompute: (id: string) => void }) {
  return (
    <div className="space-y-2">
      <div
        className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-950"
        style={{ marginLeft: `${depth * 20}px` }}
      >
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-xs text-zinc-400">{depth > 0 ? "└" : "●"}</span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">{goal.title}</p>
            <p className="text-xs text-zinc-500">{goal.scope_type} · prio {goal.priority}{goal.target ? ` · target ${goal.target}` : ""}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div className="flex w-24 items-center gap-1.5">
            <div className="h-1.5 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${Math.min(100, goal.progress * 100)}%` }} />
            </div>
            <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{Math.round(goal.progress * 100)}%</span>
          </div>
          <StatusBadge status={goal.status} />
          <button
            onClick={() => onRecompute(goal.id)}
            className="rounded-md border border-zinc-300 px-2 py-1 text-[11px] text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            Recompute
          </button>
        </div>
      </div>
      {goal.children && goal.children.length > 0 && (
        <div className="space-y-2">
          {goal.children.map((c) => <GoalRow key={c.id} goal={c} depth={depth + 1} onRecompute={onRecompute} />)}
        </div>
      )}
    </div>
  );
}

function GoalCard({ goal, onRecompute }: { goal: OrgGoal; onRecompute: (id: string) => void }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{goal.title}</p>
          <p className="mt-0.5 text-xs text-zinc-500">{goal.scope_type} · prio {goal.priority}</p>
          {goal.deadline && <p className="mt-0.5 text-xs text-zinc-500">deadline {goal.deadline}</p>}
        </div>
        <StatusBadge status={goal.status} />
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 rounded-full bg-zinc-100 dark:bg-zinc-800">
          <div className="h-1.5 rounded-full bg-emerald-500" style={{ width: `${Math.min(100, goal.progress * 100)}%` }} />
        </div>
        <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">{Math.round(goal.progress * 100)}%</span>
      </div>
      <button
        onClick={() => onRecompute(goal.id)}
        className="mt-3 rounded-md border border-zinc-300 px-2 py-1 text-[11px] text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
      >
        Recompute progress
      </button>
    </div>
  );
}

/** Convert a flat goal list (parent_goal_id) into a tree. */
function buildTree(goals: OrgGoal[]): Array<OrgGoal & { children?: Array<OrgGoal & { children?: OrgGoal[] }> }> {
  const byId = new Map<string, OrgGoal & { children?: unknown[] }>();
  for (const g of goals) byId.set(g.id, { ...g });
  const roots: Array<OrgGoal & { children?: OrgGoal[] }> = [];
  for (const g of byId.values()) {
    const node = g as OrgGoal & { children?: OrgGoal[] };
    if (g.parent_goal_id && byId.has(g.parent_goal_id)) {
      const parent = byId.get(g.parent_goal_id) as OrgGoal & { children?: OrgGoal[] };
      (parent.children ??= []).push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function GoalForm({ companyId, departments, onCreated }: { companyId: string; departments: Department[]; onCreated: () => void }) {
  const [scopeType, setScopeType] = useState<GoalScopeType>("company");
  const [scopeId, setScopeId] = useState("");
  const [title, setTitle] = useState("");
  const [metric, setMetric] = useState("");
  const [target, setTarget] = useState("");
  const [priority, setPriority] = useState("10");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCompanyGoal(companyId, {
        scope_type: scopeType,
        scope_id: scopeType === "company" ? companyId : scopeId,
        title,
        metric: metric || undefined,
        target: target ? Number(target) : undefined,
        priority: Number(priority),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create goal");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Create goal</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Scope">
          <select value={scopeType} onChange={(e) => setScopeType(e.target.value as GoalScopeType)} className={inputCls}>
            <option value="company">Company</option>
            <option value="department">Department</option>
          </select>
        </Field>
        <Field label="Department">
          <select
            value={scopeId}
            onChange={(e) => setScopeId(e.target.value)}
            disabled={scopeType !== "department"}
            required={scopeType === "department"}
            className={inputCls}
          >
            <option value="">Select department…</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Title" required>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required className={inputCls} placeholder="e.g. Ship Q3 release" />
          </Field>
        </div>
        <Field label="Metric">
          <input value={metric} onChange={(e) => setMetric(e.target.value)} className={inputCls} placeholder="e.g. verification_rate" />
        </Field>
        <Field label="Target">
          <input value={target} onChange={(e) => setTarget(e.target.value)} type="number" className={inputCls} placeholder="e.g. 90" />
        </Field>
        <Field label="Priority">
          <input value={priority} onChange={(e) => setPriority(e.target.value)} type="number" className={inputCls} />
        </Field>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create goal"}
        </button>
      </div>
    </form>
  );
}

const inputCls = "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}{required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}