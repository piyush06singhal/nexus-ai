"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { StepExecution, WorkflowStep } from "@/lib/types";
import { StatusBadge } from "@/components/StatusBadge";

const STEP_TYPE_LABELS: Record<string, string> = {
  agent_task: "Agent task",
  tool_action: "Tool action",
  condition: "Condition",
  delay: "Delay",
};

function formatJSON(value: unknown): string {
  if (value == null) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function WorkflowVisualization({
  steps,
  stepExecutions,
}: {
  steps: WorkflowStep[];
  stepExecutions: StepExecution[];
}) {
  // Build a map from step id -> step execution (later executions win).
  const execByStep = new Map<string, StepExecution>();
  for (const se of stepExecutions) {
    execByStep.set(se.workflow_step_id, se);
  }

  if (steps.length === 0) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        No steps defined for this workflow.
      </p>
    );
  }

  return (
    <ol className="relative border-l border-zinc-200 dark:border-zinc-800">
      {steps
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((step) => (
          <StepRow
            key={step.id}
            step={step}
            execution={execByStep.get(step.id)}
          />
        ))}
    </ol>
  );
}

function StepRow({
  step,
  execution,
}: {
  step: WorkflowStep;
  execution?: StepExecution;
}) {
  const [expanded, setExpanded] = useState(false);
  const status = execution?.status ?? "pending";

  // Timeline marker: dots in a color keyed to the current status.
  const dotColor: Record<string, string> = {
    pending: "bg-zinc-300 dark:bg-zinc-600",
    ready: "bg-sky-400",
    running: "bg-amber-400 animate-pulse",
    completed: "bg-emerald-500",
    failed: "bg-red-500",
    skipped: "bg-zinc-400 dark:bg-zinc-500",
    cancelled: "bg-zinc-400 dark:bg-zinc-600",
    timed_out: "bg-orange-500",
  };

  return (
    <li className="pl-6 pb-6 last:pb-0">
      <span
        className={`absolute left-[-4.5px] mt-1.5 h-2.5 w-2.5 rounded-full ${dotColor[status] ?? dotColor.pending}`}
      />
      <div className="rounded-lg border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300"
            aria-label={expanded ? "Collapse step" : "Expand step"}
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </button>
          <div className="min-w-0 flex-1">
            <span className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
              {step.name}
            </span>
            <span className="ml-2 text-xs text-zinc-400">
              {STEP_TYPE_LABELS[step.step_type] ?? step.step_type}
            </span>
          </div>
          <StatusBadge status={status} />
        </div>

        {execution?.duration_ms != null && (
          <p className="mt-1 text-[11px] text-zinc-400">
            Duration: {execution.duration_ms.toFixed(1)}ms · attempt{" "}
            {execution.attempt_number}
          </p>
        )}

        {execution?.error && (
          <p className="mt-2 rounded-md bg-red-50 px-3 py-2 font-mono text-xs text-red-700 dark:bg-red-950/40 dark:text-red-300">
            {execution.error}
          </p>
        )}

        {expanded && (
          <div className="mt-3 grid gap-3 border-t border-zinc-100 pt-3 sm:grid-cols-2 dark:border-zinc-800">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Input
              </p>
              <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {execution?.input_data
                  ? formatJSON(execution.input_data)
                  : "—"}
              </pre>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-400">
                Output
              </p>
              <pre className="mt-0.5 max-h-40 overflow-auto rounded bg-zinc-50 p-2 font-mono text-[11px] text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {execution?.output_data
                  ? formatJSON(execution.output_data)
                  : "—"}
              </pre>
            </div>
          </div>
        )}
      </div>
    </li>
  );
}