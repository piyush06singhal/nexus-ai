"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, GitFork } from "lucide-react";
import type {
  AgentAssignment,
  OrchestrationTask,
} from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

const CAPABILITY_LABELS: Record<string, string> = {
  research: "Research",
  analysis: "Analysis",
  fact_checking: "Fact-check",
  writing: "Writing",
  data_processing: "Data processing",
  summarization: "Summarization",
  general: "General",
};

/** Markers colored by the task status, used for the dependency timeline. */
const DOT_COLOR: Record<string, string> = {
  pending: "bg-zinc-300 dark:bg-zinc-600",
  ready: "bg-sky-400",
  running: "bg-amber-400 animate-pulse",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
  skipped: "bg-zinc-400 dark:bg-zinc-500",
  cancelled: "bg-zinc-400 dark:bg-zinc-600",
};

function formatJSON(value: unknown): string {
  if (value == null) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Stable topological order: dependencies before dependents, by id tiebreak. */
function topoOrder(tasks: OrchestrationTask[]): OrchestrationTask[] {
  const byName = new Map(tasks.map((t) => [t.name, t]));
  const visited = new Set<string>();
  const visiting = new Set<string>();
  const ordered: OrchestrationTask[] = [];

  const visit = (task: OrchestrationTask) => {
    if (visited.has(task.name)) return;
    if (visiting.has(task.name)) return; // cycle guard
    visiting.add(task.name);
    for (const dep of task.dependencies ?? []) {
      const depTask = byName.get(dep);
      if (depTask) visit(depTask);
    }
    visiting.delete(task.name);
    visited.add(task.name);
    ordered.push(task);
  };

  for (const task of tasks.slice().sort((a, b) => a.name.localeCompare(b.name))) {
    visit(task);
  }
  return ordered;
}

/**
 * Dependency graph of an orchestration's tasks: Objective → task nodes → the
 * assigned agent, each colored by its task/assignment status. Uses plain divs
 * and the StatusBadge, matching WorkflowVisualization — no extra deps.
 */
export function ExecutionGraph({
  tasks,
  assignments,
  agentNames = {},
}: {
  tasks: OrchestrationTask[];
  assignments: AgentAssignment[];
  agentNames?: Record<string, string>;
}) {
  if (tasks.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        This orchestration has not been planned yet. Run it to decompose the
        objective into tasks.
      </p>
    );
  }

  // Map task id → its assignment (later assignments win).
  const assignmentByTask = new Map<string, AgentAssignment>();
  for (const a of assignments) {
    assignmentByTask.set(a.task_id, a);
  }

  return (
    <ol className="relative border-l border-zinc-200 dark:border-zinc-800">
      {/* Topologically order tasks so dependencies appear before dependents,
          mirroring how the planner emits them; preserves relative order within
          the same dependency level. */}
      {topoOrder(tasks).map((task) => (
        <TaskRow
          key={task.id}
          task={task}
          assignment={assignmentByTask.get(task.id)}
          agentNames={agentNames}
        />
      ))}
    </ol>
  );
}

function TaskRow({
  task,
  assignment,
  agentNames,
}: {
  task: OrchestrationTask;
  assignment?: AgentAssignment;
  agentNames: Record<string, string>;
}) {
  const [expanded, setExpanded] = useState(false);
  const status = task.status;
  const agentName = task.agent_id
    ? agentNames[task.agent_id] ?? `agent ${task.agent_id.slice(0, 8)}`
    : null;

  return (
    <li className="pl-6 pb-6 last:pb-0">
      <span
        className={`absolute left-[-4.5px] mt-1.5 h-2.5 w-2.5 rounded-full ${
          DOT_COLOR[status] ?? DOT_COLOR.pending
        }`}
      />
      <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
            aria-label={expanded ? "Collapse task" : "Expand task"}
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium capitalize text-zinc-900 dark:text-zinc-100">
                {task.name.replace(/_/g, " ")}
              </span>
              {task.dependencies && task.dependencies.length > 0 && (
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  title={`Depends on: ${task.dependencies.join(", ")}`}
                >
                  <GitFork className="h-3 w-3" />
                  {task.dependencies.length}
                </span>
              )}
            </div>
            {task.description && (
              <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
                {task.description}
              </p>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              {(task.required_capabilities ?? []).map((cap) => (
                <span
                  key={cap}
                  className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700 dark:bg-sky-900/40 dark:text-sky-300"
                >
                  {CAPABILITY_LABELS[cap] ?? cap}
                </span>
              ))}
              {agentName && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                  → {agentName}
                </span>
              )}
            </div>
          </div>
          <StatusBadge status={status} />
        </div>

        {task.duration_ms != null && (
          <p className="mt-1 text-[11px] text-zinc-400">
            Duration: {task.duration_ms.toFixed(1)}ms · attempt{" "}
            {task.attempt_number}
          </p>
        )}

        {task.error && (
          <p className="mt-2 rounded-md bg-red-50 px-3 py-2 font-mono text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {task.error}
          </p>
        )}

        {expanded && (
          <div className="mt-3 grid gap-3 border-t border-zinc-100 pt-3 sm:grid-cols-2 dark:border-zinc-800">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Input context
              </p>
              <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {task.input_context ? formatJSON(task.input_context) : "—"}
              </pre>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Output
              </p>
              <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {task.output_data ? formatJSON(task.output_data) : "—"}
              </pre>
            </div>
          </div>
        )}

        {assignment && assignment.output_data && (
          <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
            <p className="text-[11px] uppercase tracking-wide text-zinc-400">
              {assignment.role ?? "Agent"} result
            </p>
            <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
              {formatJSON(assignment.output_data)}
            </pre>
          </div>
        )}
      </div>
    </li>
  );
}