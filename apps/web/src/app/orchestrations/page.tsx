"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Network, Play, Plus, Square } from "lucide-react";
import type { Agent, Orchestration, OrchestrationStatus } from "@/lib/types";
import {
  cancelOrchestration,
  createOrchestration,
  executeOrchestration,
  fetchAgents,
  fetchOrchestrationTasks,
  fetchOrchestrations,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

const STATUS_OPTIONS: (OrchestrationStatus | "all")[] = [
  "all",
  "created",
  "planning",
  "planned",
  "assigning",
  "running",
  "synthesizing",
  "completed",
  "partially_completed",
  "failed",
  "cancelled",
];

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; items: Orchestration[]; total: number; agents: Agent[] }
  | { kind: "error"; message: string };

export default function OrchestrationsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [status, setStatus] = useState<OrchestrationStatus | "all">("all");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const params =
      status === "all" ? undefined : { status };
    Promise.all([fetchOrchestrations(params), fetchAgents()])
      .then(([data, agents]) => {
        if (!cancelled) setState({ kind: "ok", items: data.items, total: data.total, agents });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, [status]);

  function reload() {
    setState({ kind: "loading" });
    const params = status === "all" ? undefined : { status };
    Promise.all([fetchOrchestrations(params), fetchAgents()])
      .then(([data, agents]) => setState({ kind: "ok", items: data.items, total: data.total, agents }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function act(orchId: string, fn: () => Promise<unknown>) {
    setBusy(orchId);
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Orchestrations
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Multi-agent teams coordinated on a shared objective — planned,
            assigned, executed, and verified together. Create an orchestration
            and run it to see the team in action.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New orchestration
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Status
        </label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as typeof status)}
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "All" : s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {showForm && (
        <OrchestrationForm
          onCreated={(orch) => {
            setShowForm(false);
            reload();
            void act(orch.id, () =>
              executeOrchestration(orch.id).then(() => undefined),
            );
          }}
        />
      )}

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-20 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800"
            />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.items.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <Network className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No orchestrations yet. Create one with an objective like{" "}
            <span className="font-medium text-zinc-800 dark:text-zinc-200">
              &quot;analyze the competitive market and write a report&quot;
            </span>{" "}
            and watch a research team decompose and execute it.
          </p>
        </div>
      )}

      {state.kind === "ok" &&
        state.items.map((orch) => (
          <OrchestrationRow
            key={orch.id}
            orch={orch}
            busy={busy === orch.id}
            onExecute={() =>
              act(orch.id, () => executeOrchestration(orch.id).then(() => undefined))
            }
            onCancel={() =>
              act(orch.id, () =>
                cancelOrchestration(orch.id).then(() => undefined),
              )
            }
          />
        ))}
    </div>
  );
}

function OrchestrationRow({
  orch,
  busy,
  onExecute,
  onCancel,
}: {
  orch: Orchestration;
  busy: boolean;
  onExecute: () => void;
  onCancel: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [taskCount, setTaskCount] = useState<number | null>(null);
  const completed =
    orch.metrics && typeof orch.metrics.tasks_completed === "number"
      ? (orch.metrics.tasks_completed as number)
      : null;
  const total =
    orch.metrics && typeof orch.metrics.tasks_total === "number"
      ? (orch.metrics.tasks_total as number)
      : null;

  const canRun = ["created", "planned", "failed"].includes(orch.status);
  const canCancel = ["created", "planning", "planned", "assigning", "running"].includes(
    orch.status,
  );

  async function toggle() {
    const next = !expanded;
    setExpanded(next);
    if (next) {
      try {
        const tasks = await fetchOrchestrationTasks(orch.id);
        setTaskCount(tasks.length);
      } catch {
        /* leave null */
      }
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-3 p-4">
        <Link
          href={`/orchestrations/${orch.id}`}
          className="min-w-0 flex-1"
        >
          <p className="truncate font-medium text-zinc-900 hover:underline dark:text-zinc-100">
            {orch.objective}
          </p>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
            {orch.selected_agents?.length ?? 0} agents · {"strategy: "}
            {orch.strategy}
          </p>
          {total != null && (
            <div className="mt-1.5 h-1.5 w-44 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-emerald-500"
                style={{
                  width: `${total > 0 ? Math.round(((completed ?? 0) / total) * 100) : 0}%`,
                }}
              />
            </div>
          )}
        </Link>
        <StatusBadge status={orch.status} />
        <button
          onClick={() => void toggle()}
          className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          {expanded ? "Collapse" : "Details"}
        </button>
        {canCancel && (
          <button
            onClick={onCancel}
            disabled={busy}
            title="Cancel orchestration"
            className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <Square className="h-3.5 w-3.5" />
            Cancel
          </button>
        )}
        {canRun && (
          <button
            onClick={onExecute}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
          >
            <Play className="h-3.5 w-3.5" />
            {busy ? "Running…" : "Run"}
          </button>
        )}
      </div>

      {expanded && (
        <div className="grid gap-4 border-t border-zinc-100 bg-zinc-50/60 p-4 sm:grid-cols-2 dark:border-zinc-800 dark:bg-zinc-900/30">
          <Metric label="Tasks" value={taskCount ?? (total ?? "—")} />
          <Metric
            label="Duration"
            value={orch.duration_ms != null ? `${orch.duration_ms.toFixed(0)}ms` : "—"}
          />
          <Metric
            label="Started"
            value={orch.started_at ? new Date(orch.started_at).toLocaleString() : "—"}
          />
          <Metric
            label="Completed"
            value={
              orch.completed_at ? new Date(orch.completed_at).toLocaleString() : "—"
            }
          />
          {orch.error && (
            <p className="col-span-2 rounded-md bg-red-50 px-3 py-2 font-mono text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {orch.error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-0.5 text-sm text-zinc-800 dark:text-zinc-200">{value}</p>
    </div>
  );
}

function OrchestrationForm({
  onCreated,
}: {
  onCreated: (orch: Orchestration) => void;
}) {
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const orch = await createOrchestration({ objective });
      onCreated(orch);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create orchestration");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        Create orchestration
      </h2>
      <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
        Describe an objective in plain language. The planner decomposes it into
        tasks and assembles a team of matching agents. Try:{" "}
        <span className="text-zinc-700 dark:text-zinc-300">
          &quot;analyze the competitive market and write a report&quot;
        </span>
      </p>
      <textarea
        value={objective}
        onChange={(e) => setObjective(e.target.value)}
        required
        rows={3}
        placeholder="e.g. Research the AI infrastructure market, analyze growth, fact-check findings, and write a summary"
        className="mt-3 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      />
      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="mt-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create & run"}
        </button>
      </div>
    </form>
  );
}