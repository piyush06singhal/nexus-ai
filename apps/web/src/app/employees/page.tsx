"use client";

import { useEffect, useState } from "react";
import { Plus, Users } from "lucide-react";
import {
  activateEmployee,
  createEmployee,
  deleteEmployee,
  fetchEmployees,
  fetchEmployeeTemplates,
  createEmployeeFromTemplate,
} from "@/lib/api";
import type { Employee, EmployeeTemplate } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; employees: Employee[]; templates: EmployeeTemplate[] }
  | { kind: "error"; message: string };

export default function EmployeesPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchEmployees({ status: statusFilter || undefined, role: roleFilter || undefined }),
      fetchEmployeeTemplates(),
    ])
      .then(([empResp, templates]) => {
        if (!cancelled) setState({ kind: "ok", employees: empResp.items, templates });
      })
      .catch((err) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => { cancelled = true; };
  }, [statusFilter, roleFilter]);

  function reload() {
    setState({ kind: "loading" });
    Promise.all([
      fetchEmployees({ status: statusFilter || undefined, role: roleFilter || undefined }),
      fetchEmployeeTemplates(),
    ])
      .then(([empResp, templates]) => setState({ kind: "ok", employees: empResp.items, templates }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleDelete(id: string) {
    await deleteEmployee(id);
    reload();
  }

  async function handleActivate(id: string) {
    await activateEmployee(id);
    reload();
  }

  const roles = state.kind === "ok"
    ? [...new Set(state.employees.map((e) => e.role))].sort()
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            AI Employees
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Persistent AI workforce with roles, skills, goals, and performance
            tracking. Each employee wraps an agent with organizational identity.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New employee
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {showForm && (
        <EmployeeForm
          templates={state.kind === "ok" ? state.templates : []}
          onCreated={() => { setShowForm(false); reload(); }}
        />
      )}

      {/* Filters */}
      {state.kind === "ok" && state.employees.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All statuses</option>
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="busy">Busy</option>
            <option value="paused">Paused</option>
            <option value="suspended">Suspended</option>
            <option value="terminated">Terminated</option>
          </select>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="">All roles</option>
            {roles.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>
      )}

      {state.kind === "loading" && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.employees.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Users className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No employees yet. Create your first AI employee to give an agent a
            role, skills, goals, and organizational identity.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.employees.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {state.employees.map((emp) => (
            <a
              key={emp.id}
              href={`/employees/${emp.id}`}
              className="flex flex-col rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
                    {emp.display_name || emp.name}
                  </h3>
                  <p className="mt-0.5 text-xs uppercase tracking-wide text-zinc-500">
                    {emp.role}
                    {emp.department && ` · ${emp.department}`}
                  </p>
                </div>
                <StatusBadge status={emp.status} />
              </div>
              {emp.description && (
                <p className="mt-2 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {emp.description}
                </p>
              )}
              {emp.skills && emp.skills.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1">
                  {emp.skills.slice(0, 4).map((s) => (
                    <span key={s.skill_id} className="rounded-md bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                      {s.name}
                    </span>
                  ))}
                  {emp.skills.length > 4 && (
                    <span className="text-[11px] text-zinc-400">+{emp.skills.length - 4}</span>
                  )}
                </div>
              )}
              <div className="mt-auto flex items-center gap-2 border-t border-zinc-100 pt-3 dark:border-zinc-800">
                {emp.status === "draft" && (
                  <button
                    onClick={(e) => { e.preventDefault(); handleActivate(emp.id); }}
                    className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                  >
                    Activate
                  </button>
                )}
                <button
                  onClick={(e) => { e.preventDefault(); handleDelete(emp.id); }}
                  aria-label={`Delete ${emp.name}`}
                  className="ml-auto rounded-md p-1.5 text-zinc-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                >
                  <span className="text-xs">Delete</span>
                </button>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function EmployeeForm({
  templates,
  onCreated,
}: {
  templates: EmployeeTemplate[];
  onCreated: () => void;
}) {
  const [mode, setMode] = useState<"new" | "template">("new");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("general");
  const [department, setDepartment] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "template" && selectedTemplate) {
        await createEmployeeFromTemplate(selectedTemplate, {
          name,
          role,
          department: department || undefined,
          description: description || undefined,
        });
      } else {
        await createEmployee({
          name,
          role,
          department: department || undefined,
          description: description || undefined,
        });
      }
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create employee");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-4">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
          Create employee
        </h2>
        {templates.length > 0 && (
          <div className="flex gap-2 text-xs">
            <button type="button" onClick={() => setMode("new")} className={mode === "new" ? "font-semibold text-zinc-900 dark:text-zinc-100" : "text-zinc-500"}>New</button>
            <button type="button" onClick={() => setMode("template")} className={mode === "template" ? "font-semibold text-zinc-900 dark:text-zinc-100" : "text-zinc-500"}>From template</button>
          </div>
        )}
      </div>

      {mode === "template" && (
        <div className="mt-3">
          <label className="mb-1 block text-xs font-medium text-zinc-500">Template</label>
          <select value={selectedTemplate} onChange={(e) => setSelectedTemplate(e.target.value)} required className={inputCls}>
            <option value="">Select a template…</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name} — {t.role}</option>
            ))}
          </select>
        </div>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          <input value={name} onChange={(e) => setName(e.target.value)} required className={inputCls} placeholder="e.g. research-analyst" />
        </Field>
        <Field label="Role">
          <input value={role} onChange={(e) => setRole(e.target.value)} className={inputCls} placeholder="e.g. analyst" />
        </Field>
        <Field label="Department">
          <input value={department} onChange={(e) => setDepartment(e.target.value)} className={inputCls} placeholder="e.g. research" />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Description">
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} className={inputCls} rows={2} />
          </Field>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4 flex items-center gap-2">
        <button type="submit" disabled={busy} className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900">
          {busy ? "Creating…" : "Create employee"}
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
