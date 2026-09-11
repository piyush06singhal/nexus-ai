"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, Plus, ShieldAlert } from "lucide-react";
import { createCompanyRisk, fetchCompanyRisks } from "@/lib/api";
import type { GoalScopeType, Risk } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; risks: Risk[] }
  | { kind: "error"; message: string };

const SEV_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export default function CompanyRisksPage({ params }: { params: Promise<{ id: string }> }) {
  const [companyId, setCompanyId] = useState<string>("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    params.then((p) => setCompanyId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchCompanyRisks(companyId)
      .then((risks) => {
        if (!cancelled) {
          setState({ kind: "ok", risks: [...risks].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)) });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setState({
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load risks",
          });
        }
      });
    return () => { cancelled = true; };
  }, [companyId]);

  function reload() {
    if (!companyId) return;
    setState({ kind: "loading" });
    fetchCompanyRisks(companyId)
      .then((risks) => setState({ kind: "ok", risks: [...risks].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)) }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  return (
    <div className="space-y-6">
      <Link href={`/companies/${companyId}`} className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
        <ArrowLeft className="h-4 w-4" /> Company
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Risk Center</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Company risks sorted by severity, with mitigation status tracking.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New risk
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{state.message}</p>
      )}

      {showForm && (
        <RiskForm
          companyId={companyId}
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {state.kind === "loading" && <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />}

      {state.kind === "ok" && state.risks.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <ShieldAlert className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No risks registered yet. Register a risk to track it through mitigation.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.risks.length > 0 && (
        <div className="space-y-2">
          {state.risks.map((r) => (
            <div key={r.id} className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${sevColor(r.severity)}`} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{r.title}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {r.severity} · scope {r.scope_type}
                      {r.probability != null && ` · probability ${r.probability}`}
                      {r.probability == null && " · probability unknown"}
                    </p>
                    {r.description && <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{r.description}</p>}
                    {r.mitigation && <p className="mt-1 text-xs text-zinc-500">mitigation: {r.mitigation}</p>}
                  </div>
                </div>
                <StatusBadge status={r.status} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RiskForm({ companyId, onCreated }: { companyId: string; onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("medium");
  const [mitigation, setMitigation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCompanyRisk(companyId, {
        scope_type: "company" as GoalScopeType,
        scope_id: companyId,
        title,
        description: description || undefined,
        severity,
        mitigation: mitigation || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create risk");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Create risk</h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Title" required>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required className={inputCls} placeholder="e.g. Infrastructure cost overrun" />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Description">
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} className={inputCls} />
          </Field>
        </div>
        <Field label="Severity">
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className={inputCls}>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Mitigation">
            <input value={mitigation} onChange={(e) => setMitigation(e.target.value)} className={inputCls} placeholder="Planned mitigation" />
          </Field>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create risk"}
        </button>
      </div>
    </form>
  );
}

function sevColor(severity: string): string {
  switch (severity) {
    case "critical":
    case "high": return "bg-red-500";
    case "medium": return "bg-amber-500";
    case "low": return "bg-sky-500";
    default: return "bg-zinc-400";
  }
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