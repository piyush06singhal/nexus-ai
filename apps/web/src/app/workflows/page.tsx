"use client";

import { useEffect, useState } from "react";
import { GitBranch, Play, Plus, Power, Square } from "lucide-react";
import type {
  Agent,
  StepExecution,
  Workflow,
  WorkflowExecution,
  WorkflowStep,
  WorkflowTrigger,
} from "@/lib/types";
import {
  activateWorkflow,
  createWorkflowStep,
  createWorkflowTrigger,
  createWorkflow,
  deleteWorkflowStep,
  deleteWorkflowTrigger,
  executeWorkflow,
  fetchAgents,
  fetchStepExecutions,
  fetchWorkflowExecutions,
  fetchWorkflowSteps,
  fetchWorkflowTriggers,
  fetchWorkflows,
  pauseWorkflow,
  validateWorkflow,
} from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { WorkflowVisualization } from "@/components/workflow/WorkflowVisualization";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; workflows: Workflow[]; agents: Agent[] }
  | { kind: "error"; message: string };

export default function WorkflowsPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchWorkflows(), fetchAgents()])
      .then(([workflows, agents]) => {
        if (!cancelled) setState({ kind: "ok", workflows, agents });
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
    Promise.all([fetchWorkflows(), fetchAgents()])
      .then(([workflows, agents]) => setState({ kind: "ok", workflows, agents }))
      .catch((err: Error) => setState({ kind: "error", message: err.message }));
  }

  async function run(wfId: string, fn: () => Promise<unknown>) {
    setBusy(wfId);
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
            Workflows
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Multi-step orchestrated pipelines with input/output, conditions,
            retries, and triggers. Activate a workflow, then execute it.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-2 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          <Plus className="h-4 w-4" />
          New workflow
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </p>
      )}

      {showForm && (
        <WorkflowForm onCreated={() => { setShowForm(false); reload(); }} />
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

      {state.kind === "ok" && state.workflows.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-zinc-50 p-10 text-center dark:border-zinc-700 dark:bg-zinc-900/30">
          <GitBranch className="mx-auto h-8 w-8 text-zinc-400" />
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            No workflows yet. Create a workflow, add steps, then activate and
            execute it.
          </p>
        </div>
      )}

      {state.kind === "ok" &&
        state.workflows.map((wf) => (
          <WorkflowRow
            key={wf.id}
            workflow={wf}
            busy={busy === wf.id}
            onExecute={() =>
              run(wf.id, () => executeWorkflow(wf.id).then(() => undefined))
            }
            onToggleStatus={() =>
              run(wf.id, () =>
                wf.status === "active"
                  ? pauseWorkflow(wf.id).then(() => undefined)
                  : activateWorkflow(wf.id).then(() => undefined),
              )
            }
          />
        ))}
    </div>
  );
}

/** A single expandable workflow card with steps, triggers, and executions. */
function WorkflowRow({
  workflow,
  busy,
  onExecute,
  onToggleStatus,
}: {
  workflow: Workflow;
  busy: boolean;
  onExecute: () => void;
  onToggleStatus: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [steps, setSteps] = useState<WorkflowStep[] | null>(null);
  const [triggers, setTriggers] = useState<WorkflowTrigger[] | null>(null);
  const [executions, setExecutions] = useState<WorkflowExecution[] | null>(null);
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const [s, t, e, v] = await Promise.all([
        fetchWorkflowSteps(workflow.id),
        fetchWorkflowTriggers(workflow.id),
        fetchWorkflowExecutions(workflow.id),
        validateWorkflow(workflow.id),
      ]);
      setSteps(s);
      setTriggers(t);
      setExecutions(e);
      setValidation(v);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load workflow detail");
    }
  }

  function toggle() {
    setExpanded((v) => !v);
    if (!expanded) void load();
  }

  const isActive = workflow.status === "active";

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-zinc-900 dark:text-zinc-100">
            {workflow.name}
          </p>
          <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
            {workflow.description || "—"} · v{workflow.version}
          </p>
        </div>
        <StatusBadge status={workflow.status} />
        <button
          onClick={toggle}
          className="text-xs font-medium text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          {expanded ? "Collapse" : "Details"}
        </button>
        <button
          onClick={onToggleStatus}
          disabled={busy}
          title={isActive ? "Pause workflow" : "Activate workflow"}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          {isActive ? (
            <Power className="h-3.5 w-3.5" />
          ) : (
            <Square className="h-3.5 w-3.5" />
          )}
          {isActive ? "Pause" : "Activate"}
        </button>
        {isActive && (
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
        <div className="border-t border-zinc-100 bg-zinc-50/60 p-4 space-y-6 dark:border-zinc-800 dark:bg-zinc-900/30">
          {err && <p className="text-sm text-red-600 dark:text-red-400">{err}</p>}

          {validation && !validation.valid && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
              <p className="font-semibold">Validation failed:</p>
              <ul className="mt-1 list-inside list-disc">
                {validation.errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            </div>
          )}

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Steps
            </h3>
            <StepList
              workflowId={workflow.id}
              steps={steps}
              onChange={() => void load()}
            />
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Triggers
            </h3>
            <TriggerList
              workflowId={workflow.id}
              triggers={triggers}
              onChange={() => void load()}
            />
          </section>

          <section>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Execution history
            </h3>
            <ExecutionList
              executions={executions}
              steps={steps ?? []}
            />
          </section>
        </div>
      )}
    </div>
  );
}

function StepList({
  workflowId,
  steps,
  onChange,
}: {
  workflowId: string;
  steps: WorkflowStep[] | null;
  onChange: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [stepType, setStepType] = useState("delay");
  const [config, setConfig] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let parsed: Record<string, unknown> | null = null;
    if (config.trim()) {
      try {
        parsed = JSON.parse(config) as Record<string, unknown>;
      } catch {
        setError("Configuration must be valid JSON.");
        setBusy(false);
        return;
      }
    }
    try {
      await createWorkflowStep(workflowId, {
        name,
        step_type: stepType as "agent_task" | "tool_action" | "condition" | "delay",
        configuration: parsed,
      });
      setName("");
      setConfig("");
      setShowForm(false);
      onChange();
    } catch (f) {
      setError(f instanceof Error ? f.message : "Failed to add step");
    } finally {
      setBusy(false);
    }
  }

  async function remove(stepId: string) {
    setError(null);
    try {
      await deleteWorkflowStep(stepId);
      onChange();
    } catch (f) {
      setError(f instanceof Error ? f.message : "Failed to delete step");
    }
  }

  if (steps === null) {
    return <p className="mt-2 text-sm text-zinc-500">Loading steps…</p>;
  }

  return (
    <div className="mt-2">
      {error && <p className="mb-2 text-xs text-red-600 dark:text-red-400">{error}</p>}
      {steps.length === 0 ? (
        <p className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
          No steps yet. Add a delay, agent task, tool action, or condition.
        </p>
      ) : (
        <ul className="space-y-2">
          {steps
            .slice()
            .sort((a, b) => a.order - b.order)
            .map((step) => (
              <li
                key={step.id}
                className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-950"
              >
                <span className="font-medium text-zinc-900 dark:text-zinc-100">
                  {step.name}
                </span>
                <StepTypeTag type={step.step_type} />
                <span className="ml-auto max-w-[40%] truncate font-mono text-[11px] text-zinc-400">
                  {step.configuration
                    ? JSON.stringify(step.configuration)
                    : "—"}
                </span>
                <button
                  onClick={() => void remove(step.id)}
                  className="text-xs text-red-500 hover:text-red-700"
                >
                  Remove
                </button>
              </li>
            ))}
        </ul>
      )}

      {showForm ? (
        <form
          onSubmit={submit}
          className="mt-3 rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <div className="grid gap-2 sm:grid-cols-3">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Step name"
              className={inputCls}
            />
            <select
              value={stepType}
              onChange={(e) => setStepType(e.target.value)}
              className={inputCls}
            >
              <option value="delay">Delay</option>
              <option value="agent_task">Agent task</option>
              <option value="tool_action">Tool action</option>
              <option value="condition">Condition</option>
            </select>
            <input
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              placeholder='{"duration": 5}'
              className={`${inputCls} font-mono text-xs`}
            />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
            >
              {busy ? "Adding…" : "Add step"}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="text-xs text-zinc-500 hover:text-zinc-700"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200"
        >
          <Plus className="h-3.5 w-3.5" /> Add step
        </button>
      )}
    </div>
  );
}

const TYPE_LABELS: Record<string, string> = {
  agent_task: "Agent task",
  tool_action: "Tool action",
  condition: "Condition",
  delay: "Delay",
};

function StepTypeTag({ type }: { type: string }) {
  const color: Record<string, string> = {
    agent_task: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
    tool_action: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
    condition: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    delay: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${color[type] ?? "bg-zinc-100 text-zinc-600"}`}>
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

function TriggerList({
  workflowId,
  triggers,
  onChange,
}: {
  workflowId: string;
  triggers: WorkflowTrigger[] | null;
  onChange: () => void;
}) {
  const [type, setType] = useState<"schedule" | "event" | "webhook">("schedule");
  const [config, setConfig] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    let parsed: Record<string, unknown> | null = null;
    if (config.trim()) {
      try {
        parsed = JSON.parse(config) as Record<string, unknown>;
      } catch {
        setError("Trigger configuration must be valid JSON.");
        setBusy(false);
        return;
      }
    }
    try {
      await createWorkflowTrigger(workflowId, {
        trigger_type: type,
        configuration: parsed,
      });
      setConfig("");
      onChange();
    } catch (f) {
      setError(f instanceof Error ? f.message : "Failed to add trigger");
    } finally {
      setBusy(false);
    }
  }

  async function remove(triggerId: string) {
    try {
      await deleteWorkflowTrigger(triggerId);
      onChange();
    } catch (f) {
      setError(f instanceof Error ? f.message : "Failed to delete trigger");
    }
  }

  return (
    <div className="mt-2">
      {triggers === null ? (
        <p className="text-sm text-zinc-500">Loading triggers…</p>
      ) : (
        <>
          {error && <p className="mb-2 text-xs text-red-600 dark:text-red-400">{error}</p>}
          {triggers.length === 0 ? (
            <p className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
              No triggers. Add a schedule (interval or cron), event, or webhook
              trigger.
            </p>
          ) : (
            <ul className="space-y-2">
              {triggers.map((t) => (
                <li
                  key={t.id}
                  className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-950"
                >
                  <span className="font-medium capitalize text-zinc-900 dark:text-zinc-100">
                    {t.trigger_type}
                  </span>
                  <span className="ml-auto max-w-[40%] truncate font-mono text-[11px] text-zinc-400">
                    {t.configuration
                      ? JSON.stringify(t.configuration)
                      : "—"}
                  </span>
                  <StatusBadge status={t.enabled ? "active" : "paused"} />
                  <button
                    onClick={() => void remove(t.id)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={add} className="mt-3 flex items-center gap-2">
            <select
              value={type}
              onChange={(e) => setType(e.target.value as typeof type)}
              className={inputCls}
            >
              <option value="schedule">Schedule</option>
              <option value="event">Event</option>
              <option value="webhook">Webhook</option>
            </select>
            <input
              value={config}
              onChange={(e) => setConfig(e.target.value)}
              placeholder='{"interval": 60}'
              className={`${inputCls} font-mono text-xs`}
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-zinc-900"
            >
              {busy ? "Adding…" : "Add"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}

function ExecutionList({
  executions,
  steps,
}: {
  executions: WorkflowExecution[] | null;
  steps: WorkflowStep[];
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [stepExecs, setStepExecs] = useState<StepExecution[] | null>(null);

  function showExecution(executionId: string) {
    setSelected((v) => {
      if (v === executionId) {
        setStepExecs(null);
        return null;
      }
      setStepExecs(null);
      fetchStepExecutions(executionId)
        .then(setStepExecs)
        .catch(() => setStepExecs([]));
      return executionId;
    });
  }

  return (
    <div className="mt-2">
      {executions === null ? (
        <p className="text-sm text-zinc-500">Loading executions…</p>
      ) : executions.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No executions yet for this workflow.
        </p>
      ) : (
        <ul className="space-y-2">
          {executions.map((execution) => (
            <li
              key={execution.id}
              className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950"
            >
              <button
                onClick={() => showExecution(execution.id)}
                className="flex w-full items-center gap-3 px-3 py-2 text-left"
              >
                <span className="font-mono text-[11px] text-zinc-400">
                  {execution.id.slice(0, 8)}
                </span>
                <StatusBadge status={execution.status} />
                <span className="text-[11px] capitalize text-zinc-400">
                  {execution.trigger_type ?? "manual"}
                </span>
                {execution.duration_ms != null && (
                  <span className="ml-auto text-[11px] text-zinc-400">
                    {execution.duration_ms.toFixed(0)}ms
                  </span>
                )}
              </button>
              {selected === execution.id && (
                <div className="border-t border-zinc-100 p-3 dark:border-zinc-800">
                  {execution.error && (
                    <p className="mb-2 rounded-md bg-red-50 px-3 py-2 font-mono text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
                      {execution.error}
                    </p>
                  )}
                  {stepExecs === null ? (
                    <p className="text-xs text-zinc-500">Loading steps…</p>
                  ) : (
                    <WorkflowVisualization
                      steps={steps}
                      stepExecutions={stepExecs}
                    />
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function WorkflowForm({
  onCreated,
}: {
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createWorkflow({ name, description: description || null });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workflow");
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
        Create workflow
      </h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label="Name" required>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className={inputCls}
            placeholder="e.g. Daily research digest"
          />
        </Field>
        <Field label="Description">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={inputCls}
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
          {busy ? "Creating…" : "Create workflow"}
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