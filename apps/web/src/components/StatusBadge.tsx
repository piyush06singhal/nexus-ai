import type {
  AgentStatus,
  ExecutionStatus,
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
  | StepExecutionStatus;

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