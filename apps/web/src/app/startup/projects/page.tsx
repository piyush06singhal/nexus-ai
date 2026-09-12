"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bot, Plus } from "lucide-react";
import { createStartupProject, fetchStartupProjects } from "@/lib/api";
import type { StartupProject } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../_components/StartupShell";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; projects: StartupProject[] }
  | { kind: "error"; message: string };

export default function ProjectsPage() {
  const { companyId, href } = useStartup();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (!companyId) return;
    let cancelled = false;
    fetchStartupProjects(companyId)
      .then((projects) => !cancelled && setState({ kind: "ok", projects }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId]);

  function reload() {
    if (!companyId) return;
    fetchStartupProjects(companyId)
      .then((projects) => setState({ kind: "ok", projects }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            Startup projects
          </h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Projects carry objectives, dependencies, milestones, and success
            criteria; their work is executed through operating cycles.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New project
        </button>
      </div>

      {state.kind === "error" && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {state.message}
        </p>
      )}

      {showForm && companyId && (
        <ProjectForm
          companyId={companyId}
          onCreated={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {state.kind === "loading" && (
        <div className="h-48 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
      )}

      {state.kind === "ok" && state.projects.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Bot className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No startup projects yet. They are seeded when a startup plan is
            bootstrapped.
          </p>
        </div>
      )}

      {state.kind === "ok" && state.projects.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {state.projects.map((p) => (
            <div
              key={p.id}
              className="flex flex-col rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-600"
            >
              <Link
                href={href(`/startup/projects/${p.id}`)}
                className="flex items-start justify-between"
              >
                <h3 className="font-semibold text-zinc-900 dark:text-zinc-100">
                  {p.name}
                </h3>
                <StatusBadge status={p.status} />
              </Link>
              <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
                priority {p.priority}
              </p>
              {p.objective && (
                <p className="mt-2 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                  {p.objective}
                </p>
              )}
              <Link
                href={href(`/startup/projects/${p.id}`)}
                className="ml-auto mt-auto pt-3 text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
              >
                Open →
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectForm({
  companyId,
  onCreated,
}: {
  companyId: string;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createStartupProject({
        company_id: companyId,
        name,
        objective: objective || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setBusy(false);
    }
  }

  const base =
    "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Create project
      </h3>
      <div className="mt-4 grid gap-4">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className={base}
            placeholder="e.g. Research: validate problem/solution fit"
          />
        </Field>
        <Field label="Objective">
          <input
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className={base}
            placeholder="What the project must achieve"
          />
        </Field>
      </div>
      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create project"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
    </label>
  );
}