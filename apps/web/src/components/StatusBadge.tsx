import type {
  AgentStatus,
  AlertSeverity,
  AlertStatus,
  ApprovalGateType,
  AutonomyLevel,
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
  MissionStatus,
  OperatingCycleStatus,
  ProductStatus,
  RiskStatus,
  StartupPlanStatus,
  StrategicPlanStatus,
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
  // ── Phase 9: Autonomous Startup Engine statuses ──
  | MissionStatus
  | StrategicPlanStatus
  | StartupPlanStatus
  | ProductStatus
  | OperatingCycleStatus
  | AutonomyLevel
  | ApprovalGateType
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
  | "unknown"
  // ── Phase 10: External Integrations & Computer Use ──
  | "connected"
  | "disconnected"
  | "revoked"
  | "expired"
  | "configuring"
  | "available"
  | "error"
  | "suspended"
  | "requested"
  | "authorized"
  | "not_required"
  | "low"
  | "medium"
  | "high"
  | "reversible"
  | "partially_reversible"
  | "irreversible"
  | "verified"
  | "unverified"
  | "processed"
  | "signature_ok"
  | "signature_invalid"
  | "authentication_failed"
  | "permission_failed"
  | "rate_limited"
  | "service_unavailable"
  | "invalid_configuration"
  | "not_configured";

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
  // ── Phase 9: Autonomous Startup Engine statuses ──
  blocked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  validation: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  analyzing: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  superseded: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  under_review: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  bootstrapping: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  idea: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  discovery: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  building: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  testing: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  ready_for_launch: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  launched: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  measuring: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  iterating: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
  retired: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  initializing: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  observing: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  assessing: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  awaiting_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  executing: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  verifying: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  high_autonomy: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  bounded_autonomy: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  assisted: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  manual: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  mission_approval: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  strategy_approval: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  company_bootstrap_approval: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  workforce_approval: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
  budget_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  product_launch_approval: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  high_risk_action_approval: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  major_strategic_change_approval: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  external_action_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  // ── Phase 10: External Integrations & Computer Use ──
  connected: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  disconnected: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  revoked: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  configuring: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  error: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  requested: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  authorized: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  not_required: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  low: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  reversible: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  partially_reversible: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  irreversible: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  verified: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  unverified: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  processed: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  signature_ok: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  signature_invalid: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  authentication_failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  permission_failed: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  rate_limited: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  service_unavailable: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  invalid_configuration: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  not_configured: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
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