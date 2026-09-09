"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, ListChecks, Play, Plus } from "lucide-react";
import {
  assignTask,
  createTask,
  executeTask,
  fetchAgents,
  fetchTaskExecutions,
  fetchTasks,
} from "@/lib/api";
import type { Agent, AgentExecution, Task } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";
import { ToolCallsSection } from "@/components/ToolCallsSection";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; tasks: Task[]; agents: Agent[] }
  | { kind: "error"; message: string };

export default function TasksPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Initial load — async callbacks only (avoids the set-state-in-effect rule).
  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchTasks(), fetchAgents()])
      .then(([tasks, agents]) => {
        if (!cancelled) setState({ kind: "ok", tasks, agents });
      })
      .catch((err: Error) => {
        if (!cancelled) setState({ kind: "error", message: err.message });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function reload() {
    setState({ kind: "loading" });
    Promise.all([fetchTasks(), fetchAgents()])
      .then(([tasks, agents]) => setState({ kind: "ok", tasks, agents }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function handleAssign(taskId: string, agentId: string) {
    setBusy(taskId);
    setError(null);
    try {
      await assignTask(taskId, agentId);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assignment failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleExecute(taskId: string) {
    setBusy(taskId);
    setError(null);
    try {
      await executeTask(taskId);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setBusy(null);
    }
  }

  const agents = state.kind === "ok" ? state.agents : [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            Tasks
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Discrete units of work assigned to agents. Assign a task to an
            active agent, then execute it through the runtime.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New task
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {showForm && <TaskForm agents={agents} onCreated={() => { setShowForm(false); reload(); }} />}

      {state.kind === "loading" && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-zinc-200 dark:bg-zinc-800" />
          ))}
        </div>
      )}

      {state.kind === "ok" && state.tasks.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <ListChecks className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No tasks yet. Create a task, assign it to an agent, and execute it.
          </p>
        </div>
      )}

      {state.kind === "ok" &&
        state.tasks.map((task) => (
          <TaskRow
            key={task.id}
            task={task}
            agents={agents}
            busy={busy === task.id}
            onAssign={(agentId) => handleAssign(task.id, agentId)}
            onExecute={() => handleExecute(task.id)}
          />
        ))}
    </div>
  );
}

function TaskRow({
  task,
  agents,
  busy,
  onAssign,
  onExecute,
}: {
  task: Task;
  agents: Agent[];
  busy: boolean;
  onAssign: (agentId: string) => void;
  onExecute: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [executions, setExecutions] = useState<AgentExecution[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const assignedAgent = agents.find((a) => a.id === task.assigned_agent_id);

  async function toggle() {
    setExpanded((v) => !v);
    if (!expanded) {
      try {
        setExecutions(await fetchTaskExecutions(task.id));
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load executions");
      }
    }
  }

  const canExecute =
    task.assigned_agent_id && !["completed", "failed", "in_progress"].includes(task.status);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-3 p-4">
        <button
          onClick={toggle}
          className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
          aria-label="Toggle executions"
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-zinc-900 dark:text-zinc-100">
            {task.title}
          </p>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
            {assignedAgent ? `Assigned to ${assignedAgent.name}` : "Unassigned"}
          </p>
        </div>
        <StatusBadge status={task.status} />
        <select
          value={task.assigned_agent_id ?? ""}
          onChange={(e) => e.target.value && onAssign(e.target.value)}
          className="rounded-md border border-zinc-300 px-2 py-1.5 text-xs text-zinc-700 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
        >
          <option value="" disabled>
            Assign…
          </option>
          {agents.filter((a) => a.status === "active").map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        {canExecute && (
          <button
            onClick={onExecute}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
          >
            <Play className="h-3.5 w-3.5" />
            {busy ? "Running…" : "Execute"}
          </button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/30">
          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}
          {executions && executions.length === 0 ? (
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              No executions yet for this task.
            </p>
          ) : (
            <div className="space-y-3">
              {executions?.map((execution) => (
                <ExecutionCard key={execution.id} execution={execution} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ExecutionCard({ execution }: { execution: AgentExecution }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-zinc-400">
            {execution.id.slice(0, 8)}
          </span>
          <StatusBadge status={execution.status} />
        </div>
        <span className="text-[11px] text-zinc-400">
          {execution.model_name ?? "—"} · {execution.latency_ms?.toFixed(1) ?? "–"}ms
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Meta label="Provider" value={execution.provider ?? "—"} />
        <Meta label="Tokens" value={execution.total_tokens?.toLocaleString() ?? "—"} />
        <Meta label="Cost" value={`$${execution.estimated_cost?.toFixed(6) ?? "—"}`} />
        <Meta label="Status time" value={completionLabel(execution)} />
      </div>

      {execution.error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 font-mono text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
          {execution.error}
        </p>
      )}

      {execution.output_data && (
        <pre className="mt-3 max-h-48 overflow-auto rounded-md bg-zinc-100 p-3 text-xs text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
          {JSON.stringify(execution.output_data, null, 2)}
        </pre>
      )}

      <ToolCallsSection executionId={execution.id} />
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-zinc-800 dark:text-zinc-200">{value}</p>
    </div>
  );
}

function completionLabel(execution: AgentExecution): string {
  const t = execution.completed_at ?? execution.started_at ?? execution.created_at;
  return t ? new Date(t).toLocaleTimeString() : "—";
}

function TaskForm({
  agents,
  onCreated,
}: {
  agents: Agent[];
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [inputData, setInputData] = useState("");
  const [assigned, setAssigned] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let parsed: Record<string, unknown> | null = null;
    if (inputData.trim()) {
      try {
        parsed = JSON.parse(inputData) as Record<string, unknown>;
      } catch {
        setError("Input payload must be valid JSON.");
        setBusy(false);
        return;
      }
    }
    try {
      const task = await createTask({
        title,
        description: description || null,
        input_data: parsed,
      });
      if (assigned) await assignTask(task.id, assigned);
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
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
        Create task
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Title" required>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className={inputCls}
            placeholder="e.g. Summarize Q1 sales"
          />
        </Field>
        <Field label="Assigned agent">
          <select
            value={assigned}
            onChange={(e) => setAssigned(e.target.value)}
            className={inputCls}
          >
            <option value="">Unassigned</option>
            {agents.filter((a) => a.status === "active").map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Description">
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={inputCls}
              rows={2}
            />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Field label="Input payload (JSON)">
            <textarea
              value={inputData}
              onChange={(e) => setInputData(e.target.value)}
              className={`${inputCls} font-mono text-xs`}
              rows={3}
              placeholder='{"quarter": "Q1", "region": "APAC"}'
            />
          </Field>
        </div>
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-4">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
        >
          {busy ? "Creating…" : "Create task"}
        </button>
      </div>
    </form>
  );
}

const inputCls =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

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