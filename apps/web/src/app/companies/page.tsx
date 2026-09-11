"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Building2, Plus } from "lucide-react";
import {
  activateCompany,
  createCompany,
  fetchCompanies,
  fetchCompanyHealth,
} from "@/lib/api";
import type { Company, CompanyHealth } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; companies: Company[]; health: Record<string, CompanyHealth> }
  | { kind: "error"; message: string };

export default function CompaniesPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchCompanies()
      .then(async (companies) => {
        const healthEntries = await Promise.all(
          companies.map(async (c) => {
            try {
              return [c.id, await fetchCompanyHealth(c.id)] as const;
            } catch {
              return [c.id, null] as const;
            }
          }),
        );
        const health: Record<string, CompanyHealth> = {};
        for (const [id, h] of healthEntries) {
          if (h) health[id] = h;
        }
        if (!cancelled) setState({ kind: "ok", companies, health });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => { cancelled = true; };
  }, []);

  function reload() {
    setState({ kind: "loading" });
    fetchCompanies()
      .then(async (companies) => {
        const healthEntries = await Promise.all(
          companies.map(async (c) => {
            try {
              return [c.id, await fetchCompanyHealth(c.id)] as const;
            } catch {
              return [c.id, null] as const;
            }
          }),
        );
        const health: Record<string, CompanyHealth> = {};
        for (const [id, h] of healthEntries) {
          if (h) health[id] = h;
        }
        setState({ kind: "ok", companies, health });
      })
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleActivate(id: string) {
    await activateCompany(id);
    reload();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            AI Companies
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            The organizational layer — companies, departments, goals, KPIs,
            budgets, policies, decisions, risks, and health, sourced from real
            operations data.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New company
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {showForm && (
        <CompanyForm
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {state.kind === "loading" && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.companies.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Building2 className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No companies yet. Create your first AI company to organize
            departments, employees, goals, and budgets above the workforce.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.companies.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {state.companies.map((c) => {
            const health = state.health[c.id];
            return (
              <div
                key={c.id}
                className="flex flex-col rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
              >
                <Link href={`/companies/${c.id}`} className="flex items-start justify-between">
                  <div>
                    <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
                      {c.name}
                    </h3>
                    <p className="mt-0.5 text-xs uppercase tracking-wide text-zinc-500">
                      {c.industry ?? "company"}
                    </p>
                  </div>
                  <StatusBadge status={c.status} />
                </Link>
                {c.mission && (
                  <p className="mt-2 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                    {c.mission}
                  </p>
                )}
                {health && (
                  <div className="mt-3 flex items-center justify-between rounded-lg bg-zinc-50 px-3 py-2 dark:bg-zinc-900/50">
                    <span className="text-xs text-zinc-500">Health</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={health.status} />
                      <span className="text-xs font-medium text-zinc-600 dark:text-zinc-300">
                        {health.overall_score}/100
                      </span>
                    </div>
                  </div>
                )}
                <div className="mt-auto flex items-center gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                  {c.status === "draft" && (
                    <button
                      onClick={() => handleActivate(c.id)}
                      className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    >
                      Activate
                    </button>
                  )}
                  <Link
                    href={`/companies/${c.id}`}
                    className="ml-auto text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                  >
                    Open dashboard →
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CompanyForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [mission, setMission] = useState("");
  const [vision, setVision] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCompany({
        name,
        industry: industry || undefined,
        mission: mission || undefined,
        vision: vision || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create company");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Create company
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          <input value={name} onChange={(e) => setName(e.target.value)} required className={inputCls} placeholder="e.g. NEXUS Labs" />
        </Field>
        <Field label="Industry">
          <input value={industry} onChange={(e) => setIndustry(e.target.value)} className={inputCls} placeholder="e.g. ai" />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Mission">
            <input value={mission} onChange={(e) => setMission(e.target.value)} className={inputCls} placeholder="What the company is trying to accomplish" />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Vision">
            <input value={vision} onChange={(e) => setVision(e.target.value)} className={inputCls} placeholder="Where the company is headed" />
          </Field>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create company"}
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