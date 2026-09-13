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
  | "not_configured"
  // ── Phase 11: Security, Governance & Production Hardening ──
  | "investigating"
  | "contained"
  | "closed"
  | "applied"
  | "reverted"
  | "cleared"
  // ── Phase 12: Simulation, Optimization & Agent Marketplace ──
  // Sim statuses
  | "archived"
  // Sim scenario types
  | "baseline"
  | "what_if"
  | "stress_test"
  | "capacity_test"
  | "resource_test"
  | "strategy_test"
  | "workforce_test"
  | "agent_test"
  | "product_test"
  | "risk_test"
  | "custom"
  // Sim variable kinds
  | "integer"
  | "float"
  | "boolean"
  | "string"
  | "enum"
  | "duration"
  | "percentage"
  | "currency"
  | "rate"
  // Sim event kinds
  | "task_created"
  | "task_completed"
  | "task_failed"
  | "employee_unavailable"
  | "employee_overloaded"
  | "agent_failure"
  | "budget_change"
  | "project_delay"
  | "product_launch"
  | "kpi_threshold"
  | "resource_exhaustion"
  | "workflow_failure"
  | "department_change"
  | "priority_change"
  | "sandbox_refusal"
  // Output kind labels
  | "actual"
  | "simulated"
  | "forecast"
  // Checkpoint actions
  | "checkpoint"
  | "restore"
  | "resume"
  // Optimization
  | "minimize"
  | "maximize"
  | "proposed"
  | "pending_approval"
  // Experiment conclusions
  | "winner"
  | "loser"
  | "inconclusive"
  | "stopped"
  // Benchmark dimensions
  | "correctness"
  | "reliability"
  | "tool_usage"
  | "latency"
  | "cost"
  | "verification_success"
  | "recovery"
  | "consistency"
  // Package status
  | "published"
  | "deprecated"
  // Compatibility
  | "compatible"
  | "compatible_with_note"
  | "incompatible"
  // Installation status
  | "approval_required"
  | "installing"
  | "installed"
  | "uninstalled"
  // Reputation + security
  | "success"
  | "rating"
  | "public"
  | "internal"
  | "confidential"
  | "restricted"
  // Optimization cycles
  | "simulating"
  | "optimizing"
  | "proposing"
  | "learning";

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
  // ── Phase 11: Security, Governance & Production Hardening ──
  investigating: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  contained: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  closed: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  applied: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  reverted: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  cleared: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  // ── Phase 12: Simulation, Optimization & Agent Marketplace ──
  // Sim scenario types
  baseline: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  what_if: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  stress_test: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  capacity_test: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  resource_test: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  strategy_test: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  workforce_test: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300",
  agent_test: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-900/40 dark:text-fuchsia-300",
  product_test: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  risk_test: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  custom: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  // Sim variable kinds
  integer: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  float: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  boolean: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  string: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  enum: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  duration: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  percentage: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  currency: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  rate: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  // Sim event kinds
  task_created: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  task_completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  task_failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  employee_unavailable: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  employee_overloaded: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  agent_failure: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  budget_change: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  project_delay: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  product_launch: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  kpi_threshold: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  resource_exhaustion: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  workflow_failure: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  department_change: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  priority_change: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  sandbox_refusal: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  // Output kind labels
  actual: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  simulated: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  forecast: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  // Checkpoint actions
  checkpoint: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  restore: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  resume: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  // Optimization
  minimize: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  maximize: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  proposed: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  pending_approval: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  // Experiment conclusions
  winner: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  loser: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  inconclusive: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  stopped: "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  // Benchmark dimensions
  correctness: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  reliability: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  tool_usage: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  latency: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  cost: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  verification_success: "bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300",
  recovery: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  consistency: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  // Package status
  published: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  deprecated: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  // Compatibility
  compatible: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  compatible_with_note: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  incompatible: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  // Installation status
  approval_required: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  installing: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  installed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  uninstalled: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  // Reputation + security
  success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  rating: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  public: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  internal: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  confidential: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  restricted: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  // Optimization cycles
  simulating: "bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  optimizing: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300",
  proposing: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  learning: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
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