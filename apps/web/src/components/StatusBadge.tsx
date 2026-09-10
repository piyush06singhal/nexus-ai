import type {
  AgentStatus,
  ExecutionStatus,
  MemoryType,
  StepExecutionStatus,
  TaskStatus,
  WorkflowExecutionStatus,
  WorkflowStatus,
} from "@/lib/types";
import { cn } from "@/lib/cn";

type BadgeStatus =
  | AgentStatus
  | TaskStatus
  | ExecutionStatus
  | WorkflowStatus
  | WorkflowExecutionStatus
  | StepExecutionStatus
  | MemoryType
  | "expired"
  | "created"
  | "planning"
  | "planned"
  | "assigning"
  | "running"
  | "synthesizing"
  | "completed"
  | "partially_completed"
  | "failed"
  | "cancelled"
  | "pending"
  | "ready"
  | "assigned"
  | "timed_out"
  | "approved"
  | "rejected"
  | "request_revision";

const COLORS: Record<BadgeStatus, string> = {
  draft: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  inactive: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  pending: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  queued: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  in_progress: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  succeeded: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  cancelled: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  archived: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  paused: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  ready: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  skipped: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  timed_out: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  expired: "bg-zinc-100 text-zinc-400 dark:bg-zinc-800 dark:text-zinc-500",
  working: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  episodic: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  semantic: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  procedural: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  structured: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/40 dark:text-fuchsia-300",
  created: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  planning: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  planned: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  assigning: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  synthesizing: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  partially_completed: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  assigned: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  approved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  request_revision: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
};

/** Small colored pill that renders a status value with normalized casing. */
export function StatusBadge({ status }: { status: BadgeStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium capitalize",
        COLORS[status],
      )}
    >
      {status.replace("_", " ")}
    </span>
  );
}