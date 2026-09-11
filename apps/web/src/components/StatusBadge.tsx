import type {
  AgentStatus,
  AlertSeverity,
  AlertStatus,
  CompanyStatus,
  DecisionStatus,
  DepartmentStatus,
  EmployeeAvailability,
  EmployeeStatus,
  ExecutionStatus,
  GoalStatus,
  GoalStatusOrg,
  HealthStatus,
  KpiTrend,
  MemoryType,
  RiskStatus,
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
  | EmployeeStatus
  | EmployeeAvailability
  | GoalStatus
  // ── Phase 8: AI Company Layer statuses ──
  | CompanyStatus
  | DepartmentStatus
  | GoalStatusOrg
  | DecisionStatus
  | RiskStatus
  | AlertSeverity
  | AlertStatus
  | KpiTrend
  | HealthStatus
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
  | "request_revision"
  | "pass"
  | "fail"
  | "partial"
  | "uncertain"
  | "skipped"
  | "detected"
  | "classified"
  | "recovery_planned"
  | "recovering"
  | "retrying"
  | "replanning"
  | "fallback"
  | "reverified"
  | "recovered"
  | "escalated"
  | "aborted"
  | "partially_recovered"
  | "pending_human_review"
  | "validation_failure"
  | "model_failure"
  | "tool_failure"
  | "timeout"
  | "permission_failure"
  | "invalid_input"
  | "invalid_output"
  | "dependency_failure"
  | "memory_failure"
  | "communication_failure"
  | "resource_limit"
  | "verification_failure"
  | "system_failure"
  | "unknown";

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
  // ── Phase 6: Verification & Recovery statuses ──
  pass: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  fail: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  partial: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  uncertain: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  skipped: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  validation_failure: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  model_failure: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  tool_failure: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  timeout: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  permission_failure: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  invalid_input: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  invalid_output: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  dependency_failure: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  memory_failure: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/40 dark:text-fuchsia-300",
  communication_failure: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  resource_limit: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  verification_failure: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  system_failure: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  unknown: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  detected: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  classified: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  recovery_planned: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  recovering: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  retrying: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  replanning: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  fallback: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  reverified: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  recovered: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  escalated: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  aborted: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  partially_recovered: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  pending_human_review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  // ── Phase 7: AI Employee OS ──
  available: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  unavailable: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  busy: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  on_leave: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  suspended: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  terminated: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  not_started: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  at_risk: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  // ── Phase 8: AI Company Layer statuses ──
  pending_review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  implemented: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  open: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  mitigating: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  monitored: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  resolved: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  accepted: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  acknowledged: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  warning: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  informational: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  healthy: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  degraded: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  declining: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  flat: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  improving: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
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