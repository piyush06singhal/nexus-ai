"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, BarChart3, Plus, RefreshCw } from "lucide-react";
import {
  createCompanyKpi,
  fetchCompanyKpis,
  fetchDepartments,
  recomputeCompanyKpis,
} from "@/lib/api";
import type { Department, GoalScopeType, Kpi, KpiCategory } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; kpis: Kpi[]; departments: Department[] }
  | { kind: "error"; message: string };

const CATEGORIES: KpiCategory[] = [
  "quality",
  "productivity",
  "reliability",
  "cost",
  "speed",
  "goal_progress",
  "resource_utilization",
  "customer",
  "operational",
];

export default function CompanyKpisPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [recomputeMsg, setRecomputeMsg] = useState<string | null>(null);

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
      const [kpis, departments] = await Promise.all([
        fetchCompanyKpis(id),
        fetchDepartments(id),
      ]);
      if (!cancelled) setState({ kind: "ok", kpis, departments });
    } catch (err) {
      if (!cancelled) {
        setState({
          kind: "error",
          message: err instanceof Error ? err.message : "Failed to load KPIs",
        });
      }
    }
  }

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    loadAll(companyId, false);
  }

  async function handleRecompute() {
    setRecomputeMsg(null);
    const res = await recomputeCompanyKpis(companyId);
    setRecomputeMsg(`Recomputed ${res.recomputed} KPI values from authoritative data.`);
    reload();
  }

  const filtered =
    state.kind === "ok"
      ? state.kpis.filter((k) => !categoryFilter || k.category === categoryFilter)
      : [];

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">KPIs</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Key performance indicators computed server-side from authoritative data — never user-submitted.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleRecompute}
            className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <RefreshCw className="h-4 w-4" /> Recompute
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
          >
            <Plus className="h-4 w-4" />
            New KPI
          </button>
        </div>
      </div>

      {recomputeMsg && <p className="text-sm text-zinc-600 dark:text-zinc-400">{recomputeMsg}</p>}

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {showForm && state.kind === "ok" && (
        <KpiForm
          companyId={companyId}
          departments={state.departments}
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {state.kind === "ok" && filtered.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c.replace("_", " ")}</option>
            ))}
          </select>
        </div>
      )}

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "ok" && state.kpis.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <BarChart3 className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No KPIs yet. Define a KPI with a source metric and recompute to populate values.
          </p>
        </div>
      )}

      {state.kind === "ok" && filtered.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {filtered.map((k) => <KpiCard key={k.id} kpi={k} />)}
        </div>
      )}

      {state.kind === "ok" && filtered.length === 0 && state.kpis.length > 0 && (
        <p className="text-sm text-zinc-500">No KPIs in this category.</p>
      )}
    </div>
  );
}

function KpiCard({ kpi }: { kpi: Kpi }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{kpi.name}</p>
          <p className="mt-0.5 text-xs text-zinc-500">{kpi.category.replace("_", " ")} · {kpi.scope_type}</p>
        </div>
        {kpi.trend && <StatusBadge status={kpi.trend} />}
      </div>
      <p className="mt-3 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
        {kpi.current_value ?? 0}{kpi.unit ? <span className="text-base text-zinc-500"> {kpi.unit}</span> : null}
      </p>
      <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
        <span>target {kpi.target ?? "—"}</span>
        {kpi.variance != null && (
          <span className={kpi.variance < 0 ? "font-medium text-red-600" : "font-medium text-emerald-600"}>
            {kpi.variance >= 0 ? "+" : ""}{kpi.variance} vs target
          </span>
        )}
      </div>
      <p className="mt-1 text-[11px] text-zinc-400">source: {kpi.source_metric}</p>
      <div className="mt-3 h-10 rounded-lg bg-zinc-50 dark:bg-zinc-900/50">
        <Sparkline
          values={kpi.history.map((h) => h.value)}
          target={kpi.target ?? undefined}
        />
      </div>
    </div>
  );
}

function Sparkline({ values, target }: { values: number[]; target?: number }) {
  if (values.length === 0) return <div className="h-10" />;
  const max = Math.max(...values, target ?? 0);
  const min = Math.min(...values, target ?? 0, 0);
  const range = max - min || 1;
  const w = 100;
  const h = 40;
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-10 w-full">
      {target != null && (
        <line x1="0" y1={h - ((target - min) / range) * h} x2={w} y2={h - ((target - min) / range) * h} stroke="currentColor" strokeDasharray="4 4" className="text-zinc-300 dark:text-zinc-600" strokeWidth="1" />
      )}
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="2" className="text-emerald-500" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function KpiForm({ companyId, departments, onCreated }: { companyId: string; departments: Department[]; onCreated: () => void }) {
  const [scopeType, setScopeType] = useState<GoalScopeType>("company");
  const [scopeId, setScopeId] = useState("");
  const [name, setName] = useState("");
  const [sourceMetric, setSourceMetric] = useState("");
  const [category, setCategory] = useState<KpiCategory>("productivity");
  const [target, setTarget] = useState("");
  const [unit, setUnit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCompanyKpi(companyId, {
        scope_type: scopeType,
        scope_id: scopeType === "company" ? companyId : scopeId,
        name,
        source_metric: sourceMetric,
        category,
        target: target ? Number(target) : undefined,
        unit: unit || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create KPI");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Create KPI</h2>
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
          <Field label="Name" required>
            <input value={name} onChange={(e) => setName(e.target.value)} required className={inputCls} placeholder="e.g. Verification Rate" />
          </Field>
        </div>
        <Field label="Source metric" required>
          <input value={sourceMetric} onChange={(e) => setSourceMetric(e.target.value)} required className={inputCls} placeholder="e.g. verification_rate" />
        </Field>
        <Field label="Category">
          <select value={category} onChange={(e) => setCategory(e.target.value as KpiCategory)} className={inputCls}>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c.replace("_", " ")}</option>
            ))}
          </select>
        </Field>
        <Field label="Target">
          <input value={target} onChange={(e) => setTarget(e.target.value)} type="number" className={inputCls} placeholder="e.g. 90" />
        </Field>
        <Field label="Unit">
          <input value={unit} onChange={(e) => setUnit(e.target.value)} className={inputCls} placeholder="e.g. %" />
        </Field>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create KPI"}
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