"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { getStartupProject, moveStartupProjectStatus } from "@/lib/api";
import type {
  StartupProject,
  StartupProjectStatus,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { useStartup } from "../../_components/StartupShell";
import { ActionButton, Dash, SectionCard, StringList } from "../../_components/ui";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; project: StartupProject }
  | { kind: "error"; message: string };

const NEXT: Record<StartupProjectStatus, StartupProjectStatus[]> = {
  planned: ["active", "cancelled"],
  active: ["blocked", "completed", "cancelled"],
  blocked: ["active", "cancelled"],
  completed: [],
  cancelled: [],
};

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { companyId, href } = useStartup();
  const [projectId, setProjectId] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    params.then((p) => setProjectId(p.id));
  }, [params]);

  useEffect(() => {
    if (!companyId || !projectId) return;
    let cancelled = false;
    getStartupProject(companyId, projectId)
      .then((project) => !cancelled && setState({ kind: "ok", project }))
      .catch((err: Error) =>
        !cancelled && setState({ kind: "error", message: err.message }),
      );
    return () => {
      cancelled = true;
    };
  }, [companyId, projectId]);

  async function move(target: StartupProjectStatus) {
    if (!companyId || !projectId) return;
    setBusy(true);
    setMsg(null);
    try {
      const p = await moveStartupProjectStatus(companyId, projectId, target);
      setState({ kind: "ok", project: p });
      setMsg(`Moved to ${p.status}.`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Lifecycle move failed");
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return <div className="h-64 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />;
  }
  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const { project } = state;
  const next = NEXT[project.status] ?? [];
  const milestones = project.milestones as Record<string, unknown>[] | null;

  return (
    <div className="space-y-6">
      <Link
        href={href("/startup/projects")}
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Projects
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              {project.name}
            </h1>
            <StatusBadge status={project.status} />
          </div>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            priority {project.priority} · {project.deadline ? `due ${new Date(project.deadline).toLocaleDateString()}` : "no deadline"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {next.map((t) => (
            <ActionButton key={t} onClick={() => move(t)} busy={busy}>
              → {t.replace("_", " ")}
            </ActionButton>
          ))}
        </div>
      </div>

      {project.objective && (
        <p className="max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          {project.objective}
        </p>
      )}

      {msg && (
        <p className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
          {msg}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Success criteria">
          <StringList value={project.success_criteria} />
        </SectionCard>
        <SectionCard title="Milestones">
          {milestones && milestones.length > 0 ? (
            <ul className="space-y-1">
              {milestones.map((m, i) => (
                <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                  · {String(m.title ?? m.name ?? JSON.stringify(m))}
                </li>
              ))}
            </ul>
          ) : (
            <Dash value={null} />
          )}
        </SectionCard>
        <SectionCard title="Dependencies">
          {Array.isArray(project.dependencies) && project.dependencies.length > 0 ? (
            <ul className="space-y-1">
              {project.dependencies.map((d, i) => (
                <li key={i} className="text-sm text-zinc-700 dark:text-zinc-300">
                  · {String(typeof d === "string" ? d : JSON.stringify(d))}
                </li>
              ))}
            </ul>
          ) : (
            <Dash value={null} />
          )}
        </SectionCard>
        <SectionCard title="Budget">
          {project.budget ? (
            <pre className="whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
              {JSON.stringify(project.budget, null, 2)}
            </pre>
          ) : (
            <Dash value={null} />
          )}
        </SectionCard>
      </div>
    </div>
  );
}