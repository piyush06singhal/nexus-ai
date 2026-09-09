"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Play } from "lucide-react";
import type {
  StepExecution,
  Workflow,
  WorkflowStep,
  WorkflowTrigger,
} from "@/lib/types";
import {
  activateWorkflow,
  executeWorkflow,
  fetchStepExecutions,
  fetchWorkflowExecutions,
  fetchWorkflowSteps,
  fetchWorkflowTriggers,
  getWorkflow,
  pauseWorkflow,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { WorkflowVisualization } from "@/components/workflow/WorkflowVisualization";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; workflow: Workflow }
  | { kind: "error"; message: string };

export default function WorkflowDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [triggers, setTriggers] = useState<WorkflowTrigger[]>([]);
  const [latestExec, setLatestExec] = useState<string | null>(null);
  const [stepExecs, setStepExecs] = useState<StepExecution[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const workflow = await getWorkflow(id);
        if (cancelled) return;
        setState({ kind: "ok", workflow });
        const [s, t, e] = await Promise.all([
          fetchWorkflowSteps(id),
          fetchWorkflowTriggers(id),
          fetchWorkflowExecutions(id),
        ]);
        if (cancelled) return;
        setSteps(s);
        setTriggers(t);
        if (e.length > 0) setLatestExec(e[0].id);
      } catch (err) {
        if (!cancelled)
          setState({ kind: "error", message: (err as Error).message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // When the latest execution changes, load its step executions.
  useEffect(() => {
    if (!latestExec) return;
    let cancelled = false;
    fetchStepExecutions(latestExec)
      .then((ses) => {
        if (!cancelled) setStepExecs(ses);
      })
      .catch(() => {
        /* leave empty */
      });
    return () => {
      cancelled = true;
    };
  }, [latestExec]);

  async function run() {
    if (state.kind !== "ok") return;
    setBusy(true);
    setError(null);
    try {
      await executeWorkflow(state.workflow.id);
      const e = await fetchWorkflowExecutions(id);
      if (e.length > 0) setLatestExec(e[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggleStatus() {
    if (state.kind !== "ok") return;
    setBusy(true);
    setError(null);
    try {
      const next =
        state.workflow.status === "active"
          ? await pauseWorkflow(state.workflow.id)
          : await activateWorkflow(state.workflow.id);
      setState({ kind: "ok", workflow: next });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status change failed");
    } finally {
      setBusy(false);
    }
  }

  if (state.kind === "loading") {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800"
          />
        ))}
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
        {state.message}
      </p>
    );
  }

  const workflow = state.workflow;
  const isActive = workflow.status === "active";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {workflow.name}
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {workflow.description || "—"} · v{workflow.version}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={workflow.status} />
          <button
            onClick={() => void toggleStatus()}
            disabled={busy}
            className="inline-flex items-center rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            {isActive ? "Pause" : "Activate"}
          </button>
          {isActive && (
            <button
              onClick={() => void run()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
            >
              <Play className="h-3.5 w-3.5" />
              {busy ? "Running…" : "Execute"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            Latest execution
          </h2>
          {latestExec ? (
            <div className="mt-4">
              <WorkflowVisualization steps={steps} stepExecutions={stepExecs} />
            </div>
          ) : (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              No executions yet. Activate and run this workflow to see a
              step-by-step trace.
            </p>
          )}
        </section>

        <div className="space-y-6">
          <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Steps
            </h2>
            {steps.length === 0 ? (
              <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
                No steps defined.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {steps
                  .slice()
                  .sort((a, b) => a.order - b.order)
                  .map((s) => (
                    <li
                      key={s.id}
                      className="rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-zinc-900 dark:text-zinc-100">
                          {s.name}
                        </span>
                        <span className="ml-auto text-[11px] text-zinc-400">
                          {s.idempotency}
                        </span>
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px] text-zinc-400">
                        {s.configuration
                          ? JSON.stringify(s.configuration)
                          : "—"}
                      </p>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              Triggers
            </h2>
            {triggers.length === 0 ? (
              <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
                No triggers configured.
              </p>
            ) : (
              <ul className="mt-3 space-y-2">
                {triggers.map((t) => (
                  <li
                    key={t.id}
                    className="flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800"
                  >
                    <span className="font-medium capitalize text-zinc-900 dark:text-zinc-100">
                      {t.trigger_type}
                    </span>
                    <span className="ml-auto font-mono text-[11px] text-zinc-400">
                      {t.configuration ? JSON.stringify(t.configuration) : "—"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}