/** Shared frontend type definitions mirroring the backend API responses. */

export interface ServiceCheck {
  status: "ok" | "degraded" | "unavailable";
}

export interface HealthResponse {
  status: string;
  message: string;
  service: string;
  version: string;
  environment: string;
  checks: {
    database: ServiceCheck;
    redis: ServiceCheck;
  };
}

// --- Phase 1: Agent Runtime ---

export type AgentStatus = "draft" | "active" | "inactive";

export interface Agent {
  id: string;
  name: string;
  role: string | null;
  description: string | null;
  status: AgentStatus;
  system_prompt: string | null;
  provider: string;
  model_name: string;
  temperature: number | null;
  max_tokens: number | null;
  model_params: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

/** Payload for creating an agent. */
export interface AgentInput {
  name: string;
  role?: string | null;
  description?: string | null;
  status?: AgentStatus;
  system_prompt?: string | null;
  provider?: string;
  model_name?: string;
  temperature?: number | null;
  max_tokens?: number | null;
  model_params?: Record<string, unknown> | null;
}

export type TaskStatus =
  | "pending"
  | "queued"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  input_data: Record<string, unknown> | null;
  status: TaskStatus;
  assigned_agent_id: string | null;
  created_at: string;
  updated_at: string;
  executed_at: string | null;
}

export type ExecutionStatus = "running" | "succeeded" | "failed" | "cancelled";

export interface AgentExecution {
  id: string;
  task_id: string;
  agent_id: string;
  status: ExecutionStatus;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  provider: string | null;
  model_name: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated_cost: number | null;
  latency_ms: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// --- Phase 2: Tool & Action System ---

export interface ToolParameter {
  name: string;
  type: string;
  description: string;
  required: boolean;
  default: unknown;
  enum: unknown[] | null;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameter[];
  dangerous: boolean;
  timeout_seconds: number;
  tags: string[];
}

export interface ToolCallRecord {
  id: string;
  execution_id: string;
  tool_name: string;
  arguments: Record<string, unknown> | null;
  result_status: "success" | "error" | "timeout" | "denied";
  result_data: unknown;
  result_error: string | null;
  execution_time_ms: number | null;
  iteration: number;
  created_at: string;
}

// --- Phase 3: Workflow Orchestration ---

export type WorkflowStatus = "draft" | "active" | "paused" | "archived";
export type WorkflowStepType =
  | "agent_task"
  | "tool_action"
  | "condition"
  | "delay"
  | "orchestration";
export type WorkflowTriggerType = "schedule" | "event" | "webhook";
export type WorkflowExecutionStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";
export type StepExecutionStatus =
  | "pending"
  | "ready"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "cancelled"
  | "timed_out";

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  status: WorkflowStatus;
  version: number;
  configuration: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStep {
  id: string;
  workflow_id: string;
  name: string;
  description: string | null;
  step_type: WorkflowStepType;
  configuration: Record<string, unknown> | null;
  order: number;
  dependencies: string[] | null;
  timeout_seconds: number | null;
  retry_policy: Record<string, unknown> | null;
  idempotency: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowTrigger {
  id: string;
  workflow_id: string;
  trigger_type: WorkflowTriggerType;
  configuration: Record<string, unknown> | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowExecution {
  id: string;
  workflow_id: string;
  status: WorkflowExecutionStatus;
  trigger_type: string | null;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface StepExecution {
  id: string;
  workflow_execution_id: string;
  workflow_step_id: string;
  status: StepExecutionStatus;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  attempt_number: number;
  created_at: string;
}

export interface WorkflowValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

/** Payload for creating a workflow. */
export interface WorkflowInput {
  name: string;
  description?: string | null;
  configuration?: Record<string, unknown> | null;
}

/** Payload for creating a workflow step. */
export interface WorkflowStepInput {
  name: string;
  step_type: WorkflowStepType;
  description?: string | null;
  order?: number;
  dependencies?: string[] | null;
  configuration?: Record<string, unknown> | null;
  timeout_seconds?: number | null;
  retry_policy?: Record<string, unknown> | null;
  idempotency?: string;
}

/** Payload for creating a workflow trigger. */
export interface WorkflowTriggerInput {
  trigger_type: WorkflowTriggerType;
  configuration?: Record<string, unknown> | null;
  enabled?: boolean;
}

// --- Phase 4: Memory System ---

export type MemoryType =
  | "working"
  | "episodic"
  | "semantic"
  | "procedural"
  | "structured";

export type MemoryStatus = "active" | "archived" | "expired";
export type MemoryOwnerType = "agent" | "system";
export type MemorySourceType =
  | "execution"
  | "user_input"
  | "tool_output"
  | "imported";

export interface Memory {
  id: string;
  namespace: string;
  type: MemoryType;
  owner_type: MemoryOwnerType;
  owner_id: string | null;
  status: MemoryStatus;
  source_type: MemorySourceType | null;
  source_id: string | null;
  content: string;
  summary: string | null;
  metadata_json: Record<string, unknown> | null;
  confidence: number;
  importance: number;
  access_count: number;
  last_accessed_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemorySearchResult {
  memory: Memory;
  score: number;
  breakdown: Record<string, number>;
}

export interface MemoryListResponse {
  memories: Memory[];
  total: number;
}

// --- Phase 5: Multi-Agent Orchestration ---

export type OrchestrationStatus =
  | "created"
  | "planning"
  | "planned"
  | "assigning"
  | "running"
  | "synthesizing"
  | "completed"
  | "partially_completed"
  | "failed"
  | "cancelled";

export type OrchestrationTaskStatus =
  | "pending"
  | "ready"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "cancelled";

export type AssignmentStatus =
  | "pending"
  | "assigned"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "timed_out";

export type AgentMessageType =
  | "task_assignment"
  | "task_result"
  | "request_information"
  | "information_response"
  | "status_update"
  | "error"
  | "review_request"
  | "review_result";

export type ReviewVerdict =
  | "pending"
  | "approved"
  | "rejected"
  | "request_revision";

export interface Orchestration {
  id: string;
  objective: string;
  status: OrchestrationStatus;
  strategy: string;
  selected_agents: string[] | null;
  execution_graph: Record<string, unknown> | null;
  final_result: Record<string, unknown> | null;
  error: string | null;
  metrics: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
}

export interface OrchestrationListResponse {
  items: Orchestration[];
  total: number;
}

export interface OrchestrationTask {
  id: string;
  orchestration_id: string;
  name: string;
  description: string | null;
  required_capabilities: string[] | null;
  dependencies: string[] | null;
  status: OrchestrationTaskStatus;
  agent_id: string | null;
  input_context: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  result_summary: string | null;
  attempt_number: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface AgentAssignment {
  id: string;
  orchestration_id: string;
  task_id: string;
  agent_id: string;
  role: string | null;
  instructions: string | null;
  priority: number;
  dependencies: string[] | null;
  status: AssignmentStatus;
  input_context: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  attempt_number: number;
  agent_execution_id: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentMessage {
  id: string;
  orchestration_id: string;
  sender_agent_id: string | null;
  recipient_agent_id: string | null;
  message_type: AgentMessageType;
  content: string;
  metadata: Record<string, unknown> | null;
  correlation_id: string | null;
  task_id: string | null;
  created_at: string;
}

export interface OrchestrationResult {
  id: string;
  orchestration_id: string;
  task_id: string | null;
  assignment_id: string | null;
  agent_id: string | null;
  content: string | null;
  structured_data: Record<string, unknown> | null;
  confidence: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface OrchestrationContextEntry {
  id: string;
  orchestration_id: string;
  key: string;
  value: unknown;
  kind: string;
  agent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentReview {
  id: string;
  orchestration_id: string;
  task_id: string | null;
  reviewer_agent_id: string;
  reviewee_agent_id: string | null;
  request_content: string | null;
  response_content: string | null;
  verdict: ReviewVerdict;
  iteration: number;
  created_at: string;
  completed_at: string | null;
}

export interface OrchestrationTimelineEvent {
  timestamp: string;
  event_type: string;
  status: string | null;
  description: string;
  entity_id: string | null;
}

/** Payload for creating an orchestration run. */
export interface OrchestrationInput {
  objective: string;
  strategy?: string | null;
}

/** Payload for requesting an agent review. */
export interface ReviewInput {
  reviewer_agent_id: string;
  task_id?: string | null;
  reviewee_agent_id?: string | null;
  content?: string | null;
}

/** Target of a review-completion action. */
export interface ReviewCompleteInput {
  verdict: ReviewVerdict;
  response_content?: string | null;
}

// --- Phase 6: Verification, Recovery & Evaluation ---

export type VerificationStatus = "pass" | "fail" | "partial" | "uncertain" | "skipped";

export interface VerificationRun {
  id: string;
  execution_id: string | null;
  task_id: string | null;
  orchestration_id: string | null;
  workflow_id: string | null;
  policy_id: string | null;
  strategy_used: string | null;
  status: VerificationStatus;
  score: number | null;
  confidence: number | null;
  created_at: string;
}

export interface VerificationResult {
  id: string;
  run_id: string | null;
  execution_id: string | null;
  verifier_type: string | null;
  verifier_id: string | null;
  status: VerificationStatus;
  score: number;
  confidence: number;
  reason: string | null;
  failed_criteria: string[] | null;
  passed_criteria: string[] | null;
  evidence: unknown[] | null;
  recommendations: string[] | null;
  created_at: string;
}

export interface VerificationListResponse {
  runs: VerificationRun[];
  total: number;
}

export interface VerificationPolicy {
  id: string;
  name: string;
  config: Record<string, unknown> | null;
  scope_type: string | null;
  scope_id: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

/** Payload for triggering verification of an execution or raw result data. */
export interface VerifyRequest {
  execution_id?: string;
  result_data?: Record<string, unknown>;
  risk_level?: "low" | "medium" | "high";
  policy_override?: Record<string, unknown>;
}

export type FailureCategory =
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

export type RecoveryState =
  | "detected"
  | "classified"
  | "recovery_planned"
  | "recovering"
  | "retrying"
  | "replanning"
  | "fallback"
  | "reverified"
  | "recovered"
  | "failed"
  | "escalated"
  | "aborted"
  | "partially_recovered";

export type RecoveryOutcome =
  | "recovered"
  | "failed"
  | "escalated"
  | "aborted"
  | "partially_recovered"
  | "in_progress";

export interface RecoveryAttempt {
  id: string;
  execution_id: string | null;
  plan_id: string | null;
  attempt_number: number;
  state: RecoveryState;
  strategy: string | null;
  verification_result_id: string | null;
  outcome: RecoveryOutcome | null;
  reason: string | null;
  metadata: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface FailureDiagnosis {
  id: string;
  execution_id: string | null;
  category: FailureCategory;
  severity: string;
  root_cause: string | null;
  retryable: boolean;
  recommended_strategy: string | null;
  confidence: number;
  evidence: unknown;
  created_at: string;
}

export interface RecoveryPlan {
  id: string;
  execution_id: string | null;
  orchestration_id: string | null;
  workflow_id: string | null;
  category: FailureCategory;
  severity: string;
  strategy: string | null;
  original_plan: Record<string, unknown> | null;
  revised_plan: Record<string, unknown> | null;
  reason: string | null;
  affected_tasks: string[] | null;
  safety_check: Record<string, unknown> | null;
  created_at: string;
}

export type EscalationState = "pending_human_review" | "approved" | "rejected";

export interface Escalation {
  id: string;
  execution_id: string | null;
  orchestration_id: string | null;
  workflow_id: string | null;
  issue: string;
  category: FailureCategory;
  severity: string;
  state: EscalationState;
  context: Record<string, unknown> | null;
  decision_reason: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface EscalationListResponse {
  escalations: Escalation[];
  total: number;
}

export interface Evaluation {
  id: string;
  name: string;
  target_type: string | null;
  target_id: string | null;
  description: string | null;
  case_count: number | null;
  created_at: string;
}

export interface EvaluationRun {
  id: string;
  evaluation_id: string | null;
  status: string;
  score: number | null;
  metrics: Record<string, number> | null;
  summary: string | null;
  result_count: number | null;
  created_at: string;
}

export interface EvaluationResult {
  id: string;
  run_id: string;
  case_id: string | null;
  passed: boolean;
  score: number | null;
  actual_outcome: Record<string, unknown> | null;
  metrics: Record<string, number> | null;
  error: string | null;
  created_at: string;
}

export interface EvaluationListResponse {
  evaluations: Evaluation[];
  total: number;
}

export interface EvaluationRunListResponse {
  runs: EvaluationRun[];
  total: number;
}

export interface EvaluationComparison {
  run_a_id: string;
  run_b_id: string;
  score_a: number;
  score_b: number;
  delta: number;
  per_metric_deltas: Record<string, number>;
  regression: boolean;
  regression_threshold: number;
}

export interface RegressionReport {
  status: string;
  previous_score: number;
  current_score: number;
  threshold: number;
  delta: number;
  message: string;
}

/** Payload for running an evaluation. */
export interface EvaluationInput {
  name?: string;
  target_type?: string;
  target_id?: string;
  description?: string;
  use_default_dataset?: boolean;
  cases?: Array<Record<string, unknown>>;
}

// --- Phase 7: AI Employee OS ---

export type EmployeeStatus =
  | "draft"
  | "active"
  | "paused"
  | "busy"
  | "on_leave"
  | "suspended"
  | "terminated";

export type EmployeeAvailability =
  | "available"
  | "busy"
  | "unavailable"
  | "paused"
  | "on_leave"
  | "suspended"
  | "terminated";

export type GoalStatus =
  | "not_started"
  | "active"
  | "at_risk"
  | "completed"
  | "failed"
  | "cancelled";

export interface Employee {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  role: string;
  department: string | null;
  status: EmployeeStatus;
  availability: EmployeeAvailability;
  agent_id: string | null;
  skills: EmployeeSkill[] | null;
  responsibilities: string[] | null;
  goals: Record<string, unknown>[] | null;
  tools: string[] | null;
  permissions: string[] | null;
  memory_namespace: string | null;
  work_preferences: Record<string, unknown> | null;
  workload_config: Record<string, unknown> | null;
  performance_profile: Record<string, unknown> | null;
  policies: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeSkill {
  skill_id: string;
  name: string;
  category: string;
  proficiency: number;
  confidence: number;
  evidence_count: number;
}

export interface EmployeeGoal {
  id: string;
  employee_id: string;
  title: string;
  description: string | null;
  priority: number;
  target: string | null;
  metric: string | null;
  deadline: string | null;
  status: GoalStatus;
  progress: number;
  parent_goal_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeBudget {
  id: string;
  employee_id: string;
  monthly_limit: number;
  task_limit: number | null;
  tokens_used: number;
  cost_used: number;
  tool_calls_used: number;
  period_start: string;
  period_end: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeReview {
  id: string;
  employee_id: string;
  period_start: string;
  period_end: string | null;
  metrics: Record<string, unknown> | null;
  strengths: string[] | null;
  weaknesses: string[] | null;
  skill_changes: Record<string, unknown>[] | null;
  recommendations: string[] | null;
  reviewer: string;
  created_at: string;
}

export interface EmployeeTemplate {
  id: string;
  name: string;
  description: string | null;
  role: string;
  skills: Record<string, unknown>[] | null;
  responsibilities: string[] | null;
  tools: string[] | null;
  policies: Record<string, unknown> | null;
  verification_policy: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeWorkload {
  employee_id: string;
  active_tasks: number;
  queued_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  capacity: number;
  utilization: number;
  available_slots: number;
}

export interface EmployeePerformance {
  employee_id: string;
  tasks_completed: number;
  tasks_failed: number;
  success_rate: number;
  verification_pass_rate: number;
  average_quality: number;
  recovery_rate: number;
  average_latency_ms: number;
  total_cost: number;
  total_tokens: number;
  utilization: number;
  deadline_adherence: number;
  period_start: string;
  period_end: string | null;
}

export interface EmployeeTimelineEvent {
  event_id: string;
  employee_id: string | null;
  event_type: string;
  description: string;
  timestamp: string | null;
  outcome: string | null;
}

export interface EmployeeAuditEntry {
  id: string;
  actor: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  outcome: string | null;
  created_at: string | null;
}

export interface WorkforceOverview {
  total_employees: number;
  active_employees: number;
  by_status: Record<string, number>;
}

export interface EmployeeListResponse {
  items: Employee[];
  total: number;
}

export interface AssignmentResult {
  success: boolean;
  employee_id: string | null;
  employee_name: string | null;
  score: number;
  reasoning: string;
  candidates_evaluated: number;
}

/** Payload for creating an employee. */
export interface EmployeeInput {
  name: string;
  display_name?: string | null;
  description?: string | null;
  role?: string;
  department?: string | null;
  agent_id?: string | null;
  skills?: EmployeeSkill[];
  responsibilities?: string[];
  tools?: string[];
  permissions?: string[];
  policies?: Record<string, unknown>;
  workload_config?: Record<string, unknown>;
}

/** Payload for assigning a task to an employee. */
export interface AssignmentInput {
  task_id: string;
  task_title: string;
  task_description: string;
  required_skills?: string[];
  preferred_role?: string;
  priority?: number;
}

/** Payload for creating a goal. */
export interface GoalInput {
  title: string;
  description?: string | null;
  priority?: number;
  target?: string | null;
  metric?: string | null;
}

/** Payload for creating an employee template. */
export interface EmployeeTemplateInput {
  name: string;
  description?: string | null;
  role: string;
  skills?: Record<string, unknown>[];
  responsibilities?: string[];
  tools?: string[];
  policies?: Record<string, unknown>;
  verification_policy?: Record<string, unknown>;
}

// ── Phase 8: AI Company Layer ──

export type CompanyStatus = "draft" | "active" | "paused" | "suspended" | "archived";
export type DepartmentStatus = "draft" | "active" | "paused" | "archived";
export type AuthorityLevel =
  | "individual_contributor"
  | "team_lead"
  | "manager"
  | "executive"
  | "company_admin";
export type GoalScopeType = "company" | "department" | "employee";
export type GoalStatusOrg =
  | "not_started"
  | "active"
  | "at_risk"
  | "completed"
  | "failed"
  | "cancelled";
export type PolicyScopeType = "system" | "company" | "department";
export type DecisionStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "rejected"
  | "implemented"
  | "expired"
  | "cancelled";
export type RiskStatus = "open" | "mitigating" | "monitored" | "resolved" | "accepted";
export type AlertSeverity = "critical" | "warning" | "informational";
export type AlertStatus = "active" | "acknowledged" | "resolved";
export type KpiCategory =
  | "quality"
  | "productivity"
  | "reliability"
  | "cost"
  | "speed"
  | "goal_progress"
  | "resource_utilization"
  | "customer"
  | "operational";
export type HealthStatus = "healthy" | "degraded" | "critical";

export interface Company {
  id: string;
  name: string;
  slug: string | null;
  description: string | null;
  mission: string | null;
  vision: string | null;
  industry: string | null;
  timezone: string | null;
  currency: string | null;
  values: string[] | null;
  strategic_priorities: string[] | null;
  status: CompanyStatus;
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface CompanyInput {
  name: string;
  description?: string | null;
  mission?: string | null;
  vision?: string | null;
  industry?: string | null;
  timezone?: string | null;
  currency?: string | null;
}

export interface CompanyUpdateInput {
  name?: string;
  description?: string | null;
  mission?: string | null;
  vision?: string | null;
  industry?: string | null;
  values?: string[] | null;
  strategic_priorities?: string[] | null;
}

export interface Department {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  mission: string | null;
  manager_id: string | null;
  parent_department_id: string | null;
  status: DepartmentStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface DepartmentInput {
  name: string;
  description?: string | null;
  mission?: string | null;
  manager_id?: string | null;
  parent_department_id?: string | null;
}

export interface DepartmentEmployee {
  id: string;
  name: string;
  display_name: string | null;
  role: string;
  department: string | null;
  status: string;
  agent_id: string | null;
}

export interface CompanyEmployee {
  id: string;
  name: string;
  display_name: string | null;
  role: string;
  department: string | null;
  status: string;
  agent_id: string | null;
  skills: string[] | null;
  responsible_scope: {
    department_id: string | null;
    role_id: string | null;
    authority_level: string | null;
    manager_id: string | null;
  } | null;
}

export interface Membership {
  id: string;
  company_id: string;
  employee_id: string;
  employee_name: string | null;
  role: string | null;
  department_id: string | null;
  role_id: string | null;
  role_title: string | null;
  authority_level: string | null;
  responsibility: string | null;
  manager_id: string | null;
  created_at: string | null;
}

export interface MembershipInput {
  employee_id: string;
  department_id?: string | null;
  role_id?: string | null;
  manager_id?: string | null;
  responsibility?: string;
}

export interface OrgRole {
  id: string;
  company_id: string | null;
  name: string;
  title: string | null;
  description: string | null;
  responsibilities: string[] | null;
  required_skills: string[] | null;
  authority_level: AuthorityLevel;
  authority_scope: string[] | null;
  default_policies: string[] | null;
  kpis: string[] | null;
  compatible_departments: string[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OrgRoleInput {
  name: string;
  title?: string | null;
  authority_level?: AuthorityLevel;
  responsibilities?: string[] | null;
  required_skills?: string[] | null;
  default_policies?: string[] | null;
}

export interface OrgGoal {
  id: string;
  company_id: string;
  scope_type: GoalScopeType;
  scope_id: string;
  parent_goal_id: string | null;
  title: string;
  description: string | null;
  priority: number;
  target: string | null;
  metric: string | null;
  deadline: string | null;
  status: GoalStatusOrg;
  progress: number;
  owner_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OrgGoalInput {
  scope_type: GoalScopeType;
  scope_id: string;
  title: string;
  description?: string | null;
  parent_goal_id?: string | null;
  priority?: number | null;
  target?: number | null;
  metric?: string | null;
  deadline?: string | null;
  owner_id?: string | null;
}

export type KpiTrend = "declining" | "flat" | "improving";

export interface KpiValueEntry {
  value: number;
  variance: number | null;
  trend: KpiTrend;
  period_label: string | null;
  recorded_at: string | null;
}

export interface Kpi {
  id: string;
  company_id: string;
  scope_type: GoalScopeType;
  scope_id: string;
  name: string;
  description: string | null;
  category: KpiCategory;
  source_metric: string;
  target: number | null;
  unit: string | null;
  owner_id: string | null;
  frequency: string | null;
  current_value: number | null;
  variance: number | null;
  trend: KpiTrend | null;
  recorded_at: string | null;
  history: KpiValueEntry[];
}

export interface KpiInput {
  scope_type: GoalScopeType;
  scope_id: string;
  name: string;
  source_metric: string;
  description?: string | null;
  category?: KpiCategory | null;
  target?: number | null;
  unit?: string | null;
  owner_id?: string | null;
  frequency?: string | null;
}

export interface BudgetSnapshot {
  company_id: string;
  scope_type: string;
  scope_id: string;
  monthly_limit: number;
  allocated: number;
  reserved: number;
  spent: number;
  tokens_used: number;
  cost_used: number;
  tool_calls_used: number;
  execution_count: number;
  period_start: string | null;
  period_end: string | null;
  utilization_pct: number;
  remaining: number;
}

export interface CompanyBudgets {
  company: BudgetSnapshot | null;
  departments: BudgetSnapshot[];
}

export interface Policy {
  id: string;
  company_id: string | null;
  scope_type: PolicyScopeType;
  scope_id: string | null;
  name: string;
  key: string;
  value: unknown;
  priority: number;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface PolicyInput {
  scope_type: PolicyScopeType;
  scope_id?: string | null;
  name: string;
  key: string;
  value: unknown;
  priority?: number;
  enabled?: boolean;
}

export interface EffectivePolicy {
  key: string;
  value: unknown;
  source_scope: string;
  source_name: string | null;
  candidates_checked: number;
}

export interface DecisionOption {
  id: string;
  label: string;
}

export interface Decision {
  id: string;
  company_id: string;
  requester_id: string | null;
  decision_maker_id: string | null;
  question: string;
  context: Record<string, unknown> | null;
  options: DecisionOption[];
  selected_option: DecisionOption | null;
  evidence: Record<string, unknown> | null;
  rationale: string | null;
  risk_level: string;
  risk: Record<string, unknown> | null;
  budget_impact: Record<string, unknown> | null;
  required_authority: AuthorityLevel;
  status: DecisionStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface DecisionInput {
  question: string;
  options: DecisionOption[];
  context?: Record<string, unknown> | null;
  evidence?: Record<string, unknown> | null;
  rationale?: string | null;
  risk_level?: string;
  risk?: Record<string, unknown> | null;
  budget_impact?: Record<string, unknown> | null;
  required_authority?: AuthorityLevel;
  requester_id?: string | null;
}

export interface DecisionReviewEntry {
  id: string;
  decision_id: string;
  reviewer_id: string | null;
  action: string;
  verdict: string | null;
  rationale: string | null;
  previous_status: string | null;
  next_status: string | null;
  created_at: string | null;
}

export interface Risk {
  id: string;
  company_id: string;
  scope_type: GoalScopeType;
  scope_id: string;
  title: string;
  description: string | null;
  severity: string;
  probability: number | null;
  impact: string | null;
  owner_id: string | null;
  status: RiskStatus;
  mitigation: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RiskInput {
  scope_type: GoalScopeType;
  scope_id: string;
  title: string;
  description?: string | null;
  severity?: string;
  probability?: number | null;
  impact?: string | null;
  owner_id?: string | null;
  mitigation?: string | null;
}

export interface Alert {
  id: string;
  company_id: string;
  scope_type: GoalScopeType;
  scope_id: string;
  title: string;
  severity: AlertSeverity;
  category: string;
  message: string;
  status: AlertStatus;
  payload: Record<string, unknown> | null;
  created_at: string | null;
  resolved_at: string | null;
}

export interface CompanyReport {
  id: string;
  company_id: string;
  report_type: string;
  period_start: string | null;
  period_end: string | null;
  created_at: string | null;
  metrics: Record<string, unknown> | null;
  highlights: string[] | null;
  risks: Record<string, unknown>[] | null;
  blockers: string[] | null;
  goal_progress: Record<string, unknown> | null;
  recommendations: string[] | null;
  evidence: Record<string, unknown> | null;
  verification_status: string;
  verification_summary: string | null;
}

export interface OrgEvent {
  id: string;
  company_id: string | null;
  actor: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown> | null;
  outcome: string | null;
  created_at: string | null;
}

export interface OrgChartNode {
  id: string;
  type: string;
  name: string;
  status: string | null;
  children: OrgChartNode[];
}

export interface CompanyHealth {
  company_id: string;
  overall_score: number;
  status: HealthStatus;
  dimensions: Record<string, number>;
  weights: Record<string, number>;
  computed_at: string | null;
}

export type CompanyPerformance = Record<string, unknown>;

export type CompanyAnalytics = Record<string, unknown>;

// ── Phase 9: Autonomous Startup Engine ──

export type MissionStatus =
  | "draft"
  | "analyzing"
  | "planned"
  | "active"
  | "paused"
  | "blocked"
  | "completed"
  | "failed"
  | "cancelled";
export type StrategicPlanStatus = "draft" | "active" | "superseded" | "cancelled";
export type StartupPlanStatus =
  | "draft"
  | "under_review"
  | "approved"
  | "bootstrapping"
  | "active"
  | "paused"
  | "completed"
  | "cancelled";
export type ProductStatus =
  | "idea"
  | "discovery"
  | "validation"
  | "planning"
  | "building"
  | "testing"
  | "ready_for_launch"
  | "launched"
  | "measuring"
  | "iterating"
  | "paused"
  | "retired";
export type StartupProjectStatus =
  | "planned"
  | "active"
  | "blocked"
  | "completed"
  | "cancelled";
export type ExecutionPlanStatus =
  | "draft"
  | "ready"
  | "running"
  | "blocked"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";
export type OperatingCycleStatus =
  | "initializing"
  | "observing"
  | "assessing"
  | "planning"
  | "awaiting_approval"
  | "executing"
  | "verifying"
  | "measuring"
  | "replanning"
  | "completed"
  | "blocked"
  | "failed"
  | "cancelled";
export type LessonType =
  | "lesson"
  | "decision_outcome"
  | "failed_assumption"
  | "success_pattern"
  | "process_improvement"
  | "strategic_insight";
export type ApprovalGateType =
  | "mission_approval"
  | "strategy_approval"
  | "company_bootstrap_approval"
  | "workforce_approval"
  | "budget_approval"
  | "product_launch_approval"
  | "high_risk_action_approval"
  | "major_strategic_change_approval"
  | "external_action_approval";
export type ApprovalGateStatus = "pending" | "approved" | "rejected" | "expired" | "cancelled";
export type MissionGraphRelation =
  | "derived_from"
  | "depends_on"
  | "assigned_to"
  | "executed_by"
  | "measured_by"
  | "blocked_by"
  | "generated_by"
  | "improves"
  | "triggers";
export type AutonomyLevel =
  | "manual"
  | "assisted"
  | "bounded_autonomy"
  | "high_autonomy";

/** A startup mission — the top of the traceability graph. */
export interface Mission {
  id: string;
  company_id: string;
  title: string;
  description: string | null;
  mission_statement: string;
  desired_outcome: string | null;
  target_market: string | null;
  constraints: unknown;
  assumptions: unknown;
  success_criteria: unknown;
  strategic_context: unknown;
  priority: number;
  status: MissionStatus;
  analysis: MissionAnalysisResult | null;
  validation: ValidationResult | null;
  owner_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface MissionInput {
  company_id: string;
  title: string;
  description?: string | null;
  mission_statement: string;
  desired_outcome?: string | null;
  target_market?: string | null;
  constraints?: string[];
  assumptions?: string[];
  success_criteria?: string[];
  strategic_context?: Record<string, unknown> | null;
  priority?: number;
  owner_id?: string | null;
}

export interface MissionAnalysisResult {
  objectives: string[];
  target_market: string | null;
  problem: string | null;
  proposed_solution: string | null;
  constraints: string[];
  timeline: string | null;
  success_criteria: string[];
  assumptions: string[];
  risks: string[];
  unknowns: string[];
  required_capabilities: string[];
  analyzer: string;
}

export interface ValidationIssue {
  code: string;
  message: string;
  severity: string;
}

export interface ValidationResult {
  ok: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

/** Strategic plan — vision, objectives, and the "how". */
export interface StrategicPlan {
  id: string;
  mission_id: string;
  vision: string | null;
  objectives: unknown;
  priorities: unknown;
  expected_outcomes: unknown;
  assumptions: unknown;
  risks: unknown;
  milestones: unknown;
  dependencies: unknown;
  capabilities: unknown;
  resource_estimates: unknown;
  success_metrics: unknown;
  status: StrategicPlanStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface StartupPlanInput {
  mission_id: string;
  strategic_plan_id?: string | null;
  business_objectives?: unknown[];
  product_objectives?: unknown[];
  market_objectives?: unknown[];
  organization_objectives?: unknown[];
  operational_objectives?: unknown[];
  milestones?: unknown[];
  departments?: unknown[];
  roles?: unknown[];
  capabilities?: string[];
  initial_products?: Record<string, unknown>[];
  initial_projects?: Record<string, unknown>[];
  kpi_targets?: Record<string, unknown>;
  budget_allocation?: Record<string, unknown>;
  execution_priorities?: string[];
  approval_requirements?: unknown[];
}

export interface StartupPlan {
  id: string;
  mission_id: string;
  strategic_plan_id: string | null;
  business_objectives: unknown;
  product_objectives: unknown;
  market_objectives: unknown;
  organization_objectives: unknown;
  operational_objectives: unknown;
  milestones: unknown;
  departments: unknown;
  roles: unknown;
  capabilities: unknown;
  initial_products: unknown;
  initial_projects: unknown;
  kpi_targets: unknown;
  budget_allocation: unknown;
  execution_priorities: unknown;
  approval_requirements: unknown;
  status: StartupPlanStatus;
  review: unknown;
  created_at: string | null;
  updated_at: string | null;
}

export interface Product {
  id: string;
  company_id: string;
  name: string;
  description: string | null;
  product_type: string | null;
  target_users: unknown;
  value_proposition: string | null;
  status: ProductStatus;
  owner_id: string | null;
  strategic_priority: number;
  budget: unknown;
  success_metrics: unknown;
  launch_criteria: unknown;
  validation: unknown;
  created_at: string | null;
  updated_at: string | null;
}

export interface ProductInput {
  company_id: string;
  name: string;
  description?: string | null;
  product_type?: string | null;
  target_users?: string[];
  value_proposition?: string | null;
  owner_id?: string | null;
  strategic_priority?: number;
  budget?: Record<string, unknown> | null;
  success_metrics?: string[];
  launch_criteria?: string[];
}

export interface StartupProject {
  id: string;
  company_id: string;
  product_id: string | null;
  department_id: string | null;
  name: string;
  description: string | null;
  objective: string | null;
  owner_id: string | null;
  status: StartupProjectStatus;
  priority: number;
  budget: unknown;
  milestones: unknown;
  dependencies: unknown;
  success_criteria: unknown;
  start_date: string | null;
  deadline: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface StartupProjectInput {
  company_id: string;
  name: string;
  description?: string | null;
  objective?: string | null;
  product_id?: string | null;
  department_id?: string | null;
  owner_id?: string | null;
  status?: StartupProjectStatus;
  priority?: number;
  budget?: Record<string, unknown> | null;
  milestones?: Record<string, unknown>[];
  dependencies?: Record<string, unknown>[];
  success_criteria?: string[];
  start_date?: string | null;
  deadline?: string | null;
  goal_id?: string | null;
}

export interface OperatingCycle {
  id: string;
  company_id: string;
  mission_id: string | null;
  startup_plan_id: string | null;
  cycle_number: number;
  status: OperatingCycleStatus;
  stages: CycleStage[];
  state_snapshot_id: string | null;
  decisions: Record<string, unknown>[];
  actions: Record<string, unknown>[];
  kpis: Record<string, unknown>[];
  failures: Record<string, unknown>[];
  recovery: Record<string, unknown>[];
  approvals: Record<string, unknown>[];
  resource_usage: unknown;
  outcome: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
}

export interface CycleStage {
  stage: string;
  status?: string;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  inputs?: unknown;
  outputs?: unknown;
  details?: Record<string, unknown>;
}

export interface CompanyStateSnapshot {
  id: string | null;
  company_id: string;
  overall_score: number;
  dimensions: Record<string, number>;
  explanations: Record<string, string>;
  computed_at: string | null;
  metrics?: Record<string, unknown>;
}

export interface ApprovalGate {
  id: string;
  company_id: string;
  gate_type: ApprovalGateType;
  risk_level: string;
  requested_action: unknown;
  rationale: string | null;
  affected_entities: unknown;
  resource_impact: unknown;
  requester_id: string | null;
  approver_id: string | null;
  status: ApprovalGateStatus;
  decided_at: string | null;
  expiration: string | null;
  created_at: string | null;
}

export interface StartupFeedback {
  id: string;
  company_id: string;
  mission_id: string | null;
  objective_type: unknown;
  source: string | null;
  category: string;
  observation: string;
  impact: string | null;
  confidence: number;
  recommendation: string | null;
  related_goal_id: string | null;
  related_project_id: string | null;
  related_product_id: string | null;
  created_at: string | null;
}

export interface StartupFeedbackInput {
  category: string;
  observation: string;
  mission_id?: string | null;
  source?: string | null;
  impact?: string | null;
  confidence?: number;
  recommendation?: string | null;
  objective_type?: Record<string, unknown> | null;
  related_goal_id?: string | null;
  related_project_id?: string | null;
  related_product_id?: string | null;
}

export interface Lesson {
  id: string;
  company_id: string;
  mission_id: string | null;
  lesson_type: LessonType;
  title: string;
  content: string;
  source: unknown;
  created_at: string | null;
}

export interface MissionGraphEdge {
  id: string;
  company_id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  relation: MissionGraphRelation;
  metadata: unknown;
  created_at: string | null;
}

export interface MissionGraph {
  edges: MissionGraphEdge[];
  total: number;
}

export interface MissionTrace {
  origin: { type: string; id: string };
  chain: Array<{
    from: { type: string; id: string };
    to: { type: string; id: string };
    relation: string;
    metadata: unknown;
  }>;
  reached_mission: boolean;
}

export interface AutonomyPolicy {
  company_id: string;
  autonomy_level: AutonomyLevel;
  allow_matrix: Record<string, string>;
  never_allowed: string[];
  max_employees: number | null;
  max_departments: number | null;
  max_budget: number | null;
  max_concurrent_work: number | null;
  max_provisioning_rate: number | null;
  require_approval_for: string[];
}

export interface AutonomyPolicyInput {
  autonomy_level?: AutonomyLevel;
  allow_matrix?: Record<string, string>;
  max_employees?: number;
  max_departments?: number;
  max_budget?: number;
  max_concurrent_work?: number;
  max_provisioning_rate?: number;
  require_approval_for?: string[];
  approved_gate_id?: string | null;
}

export interface ResourceAllocation {
  id: string;
  company_id: string;
  target_type: string;
  target_id: string;
  resource_type: string;
  amount: number;
  unit: string | null;
  purpose: unknown;
  actor: string;
  created_at: string | null;
}

export interface PriorityDecision {
  id: string;
  company_id: string;
  target_type: string;
  target_id: string;
  score: unknown;
  factors: unknown;
  reason: string | null;
  created_at: string | null;
}

export interface ReplanDecision {
  trigger: string;
  response: string;
  reason: string;
  actions: Record<string, unknown>[];
  requires_approval: boolean;
}

export interface ReplanAction {
  decision: ReplanDecision;
  applied: Record<string, unknown>[];
}

/** Composed next-actions view for the startup overview. */
export interface NextActions {
  company_id: string;
  state: CompanyStateSnapshot;
  pending_approvals: ApprovalGate[];
  pending_approval_count: number;
  latest_cycle: OperatingCycle | null;
  recent_feedback: StartupFeedback[];
  needs_attention: boolean;
}

/** Result of `plan_mission` — the derived strategic + startup plan ids. */
export interface MissionPlanResult {
  mission_id: string;
  status: string;
  strategic_plan_id: string;
  startup_plan_id: string;
}
// ── Phase 10: External Integrations & Computer Use ────────────────────────────

export type ExternalRiskLevel = "low" | "medium" | "high" | "critical";
export type Approvability = "not_required" | "required" | "pending" | "approved" | "rejected";

export interface ExternalIntegration {
  id: string;
  company_id: string;
  provider: string;
  name: string;
  slug: string;
  description: string | null;
  category: string;
  auth_type: string;
  status: string;
  configuration: unknown;
  owner_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface IntegrationCapability {
  id: string;
  integration_id: string;
  name: string;
  description: string | null;
  capability_type: string;
  risk_level: ExternalRiskLevel;
  input_schema: unknown;
  output_schema: unknown;
  reversibility: string;
  supports_idempotency: boolean;
  approval_required: boolean;
  required_permissions: unknown;
  required_scopes: unknown;
}

export interface IntegrationConnection {
  id: string;
  integration_id: string;
  company_id: string;
  status: string;
  auth_method: string;
  credential_reference: string | null;
  scopes: unknown;
  permissions: unknown;
  metadata: unknown;
  last_used_at: string | null;
  last_tested_at: string | null;
  last_error_at: string | null;
  revoked_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ConnectionTestResponse {
  result: string;
  message: string | null;
  tested_at: string;
}

export interface CredentialRef {
  id: string;
  reference: string;
  integration_id: string | null;
  connection_id: string | null;
  company_id: string;
  provider: string;
  kind: string;
  masked_value: string;
  env_var_hint: string | null;
  scopes: unknown;
  last_used_at: string | null;
  created_at: string;
}

export interface ExternalActionAttempt {
  id: string;
  action_id: string;
  attempt_number: number;
  strategy: string | null;
  status: string;
  retryable: boolean;
  error_category: string | null;
  error: string | null;
  request_id: string | null;
  external_operation_id: string | null;
  duration_ms: number | null;
  created_at: string;
}

export interface ExternalAction {
  id: string;
  company_id: string;
  integration_id: string;
  connection_id: string | null;
  employee_id: string | null;
  agent_id: string | null;
  execution_id: string | null;
  workflow_execution_id: string | null;
  orchestration_id: string | null;
  capability: string;
  action_type: string;
  input: unknown;
  risk_level: ExternalRiskLevel;
  reversibility: string;
  idempotency_key: string | null;
  external_operation_id: string | null;
  policy_result: unknown;
  approval_status: Approvability | null;
  approval_gate_id: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  result: unknown;
  error: string | null;
  verification: unknown;
  recovery: unknown;
  correlation_id: string | null;
  created_at: string;
  updated_at: string | null;
  attempts: ExternalActionAttempt[];
}

export interface ExternalEvent {
  id: string;
  source: string;
  integration_id: string | null;
  company_id: string | null;
  event_type: string;
  payload: unknown;
  payload_size: number;
  timestamp: string | null;
  verification_status: string;
  correlation_id: string | null;
  signature_status: string;
  ingest_id: string | null;
  received_at: string;
}

export interface BrowserSession {
  id: string;
  company_id: string;
  employee_id: string | null;
  agent_id: string | null;
  workflow_execution_id: string | null;
  orchestration_id: string | null;
  status: string;
  current_url: string | null;
  domain: string | null;
  allowed_domains: unknown;
  policy: unknown;
  metadata: unknown;
  action_count: number;
  navigation_count: number;
  started_at: string | null;
  last_activity_at: string | null;
  terminated_at: string | null;
  created_at: string;
}

export interface BrowserAction {
  id: string;
  session_id: string;
  company_id: string;
  action_type: string;
  target: unknown;
  input: unknown;
  status: string;
  risk_level: ExternalRiskLevel;
  approval_status: string;
  result: unknown;
  error: string | null;
  duration_ms: number | null;
  verification: unknown;
  created_at: string;
}

export interface BrowserObservation {
  id: string;
  session_id: string;
  company_id: string;
  observation_number: number;
  url: string | null;
  title: string | null;
  snapshot: unknown;
  screenshot_ref: string | null;
  content_type: string;
  page_state: unknown;
  created_at: string;
}

export interface ComputerSession {
  id: string;
  company_id: string;
  employee_id: string | null;
  agent_id: string | null;
  workflow_execution_id: string | null;
  orchestration_id: string | null;
  status: string;
  screen: unknown;
  cursor: unknown;
  policy: unknown;
  action_count: number;
  started_at: string | null;
  last_activity_at: string | null;
  terminated_at: string | null;
  created_at: string;
}

export interface ComputerAction {
  id: string;
  session_id: string;
  company_id: string;
  action_type: string;
  input: unknown;
  status: string;
  risk_level: ExternalRiskLevel;
  approval_status: string;
  result: unknown;
  error: string | null;
  duration_ms: number | null;
  verification: unknown;
  created_at: string;
}

export interface ComputerObservation {
  id: string;
  session_id: string;
  company_id: string;
  observation_number: number;
  snapshot: unknown;
  screenshot_ref: string | null;
  created_at: string;
}

export interface ExternalIntegrationPolicy {
  id: string;
  company_id: string;
  integration_id: string | null;
  scope_type: string;
  scope_id: string | null;
  capability_pattern: string | null;
  risk_level_override: ExternalRiskLevel | null;
  allowed: boolean;
  require_approval: boolean;
  rate_limit: unknown;
  budget: unknown;
  allowed_domains: unknown;
  enabled: boolean;
  created_at: string;
}

export interface ExternalDomainRule {
  id: string;
  company_id: string;
  integration_id: string | null;
  scope_type: string;
  scope_id: string | null;
  domain: string;
  decision: string;
  http_methods: unknown;
  allowed_paths: unknown;
  enabled: boolean;
  created_at: string;
}

export interface ExternalDashboard {
  company_id: string;
  total_actions: number;
  by_status: Record<string, number>;
  success_rate: number;
  failure_rate: number;
  pending_approvals: {
    id: string;
    capability: string;
    gate_id: string | null;
    risk_level: string | null;
    created_at: string | null;
  }[];
  pending_approval_count: number;
}

// ── Phase 11: Security, Governance & Production Hardening ───────────────────

export type IdentityKind =
  | "user"
  | "service"
  | "ai_employee"
  | "agent"
  | "company";

export interface IdentityPublic {
  id: string | null;
  kind: IdentityKind;
  name: string;
  status: string;
  company_id: string | null;
  external_ref: string | null;
}

export interface UserPublic {
  id: string;
  identity_id: string;
  email: string;
  display_name: string;
  status: string;
}

export interface UserCreateInput {
  email: string;
  display_name: string;
  password: string;
  company_id?: string | null;
  roles?: string[];
}

export interface RoleAssignInput {
  roles: string[];
  company_id?: string | null;
}

export interface RolePublic {
  id: string;
  name: string;
  code: string;
  scope: string;
  company_id: string | null;
  description: string | null;
  builtin: boolean;
}

export interface PermissionPublic {
  id: string;
  code: string;
  description: string | null;
  category: string | null;
  builtin: boolean;
}

export interface SecretCreateInput {
  name: string;
  plaintext: string;
  company_id?: string | null;
  kind?: string;
  rotation_days?: number | null;
}

/** A secret rendered as a reference + hint — never its value. */
export interface SecretReference {
  id: string;
  name: string;
  company_id: string | null;
  kind: string;
  status: string;
  mask_hint: string | null;
  key_id: string;
  rotation_due_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionResult {
  access_token: string;
  refresh_token: string;
  session_id: string;
  identity: IdentityPublic;
  user: UserPublic | null;
  company_id: string | null;
}

export interface AuthSessionResponse {
  identity: IdentityPublic;
  user: UserPublic | null;
  roles: string[];
  permissions: string[];
}

export interface SystemFlagPublic {
  id: string;
  scope: string;
  tenant_id: string | null;
  flag: string;
  status: string;
  reason: string | null;
  set_by: string | null;
  set_at: string;
  cleared_at: string | null;
}

export interface FlagSetInput {
  flag: string;
  reason?: string | null;
  tenant_id?: string | null;
}

export interface PolicyRuleInput {
  scope?: string;
  company_id?: string | null;
  subject_pattern?: string;
  action_pattern: string;
  resource_pattern?: string;
  effect: string;
  risk_level?: string;
  priority?: number;
  reason?: string | null;
  enabled?: boolean;
}

export interface PolicyRulePublic {
  id: string;
  scope: string;
  company_id: string | null;
  subject_pattern: string;
  action_pattern: string;
  resource_pattern: string;
  effect: string;
  risk_level: string;
  priority: number;
  reason: string | null;
  enabled: boolean;
  created_at: string;
}

export interface PolicyDecisionPublic {
  id: string;
  company_id: string | null;
  identity_id: string | null;
  action: string;
  resource: string | null;
  decision: string;
  reason: string | null;
  matched_rule_scope: string | null;
  created_at: string;
}

export interface ResourceLimitInput {
  scope?: string;
  tenant_id?: string | null;
  category: string;
  max_value: number;
  period?: string;
  enforced?: boolean;
}

export interface ResourceLimitPublic {
  id: string;
  scope: string;
  tenant_id: string | null;
  category: string;
  max_value: number;
  period: string | null;
  enforced: boolean;
}

export interface ResourceUsagePublic {
  id: string;
  company_id: string | null;
  tenant_id: string | null;
  actor_id: string | null;
  category: string;
  amount: number;
  unit: string | null;
  instrument: string | null;
  recorded_at: string;
}

export interface BreakGlassInput {
  scope?: string;
  reason: string;
  max_minutes?: number | null;
}

export interface BreakGlassPublic {
  id: string;
  identity_id: string;
  company_id: string | null;
  scope: string;
  reason: string;
  status: string;
  requested_at: string;
  expires_at: string;
  approved_by: string | null;
  revoked_at: string | null;
}

export interface FeatureFlagInput {
  enabled: boolean;
  rationale?: string | null;
}

export interface FeatureFlagPublic {
  id: string;
  scope: string;
  company_id: string | null;
  name: string;
  enabled: boolean;
  rationale: string | null;
  updated_at: string;
}

export interface GovernanceControlPublic {
  id: string;
  company_id: string | null;
  code: string;
  title: string;
  description: string | null;
  category: string;
  enforced: boolean;
  source: string | null;
}

export interface SecurityEventPublic {
  id: string;
  company_id: string | null;
  category: string;
  severity: string;
  title: string;
  detail: Record<string, unknown> | null;
  actor_id: string | null;
  created_at: string;
}

export interface SecurityAlertPublic {
  id: string;
  company_id: string | null;
  severity: string;
  status: string;
  rule_code: string | null;
  title: string;
  description: string | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
}

export interface IncidentCreateInput {
  company_id?: string | null;
  severity?: string;
  title: string;
  description?: string | null;
  alert_ids?: string[];
}

export interface IncidentPublic {
  id: string;
  company_id: string | null;
  severity: string;
  status: string;
  title: string;
  description: string | null;
  timeline_json: Record<string, unknown> | null;
  contained_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  created_at: string;
}

export interface IncidentTransitionInput {
  to_status: string;
  note?: string | null;
}

export interface IncidentActionInput {
  incident_id: string;
  action: string;
  params?: Record<string, unknown> | null;
}

export interface IncidentActionPublic {
  id: string;
  incident_id: string;
  action_code: string;
  target_company_id: string | null;
  target_ref: string | null;
  state: string;
  performed_by: string | null;
  result_json: Record<string, unknown> | null;
  created_at: string;
  applied_at: string | null;
}

/** Incident response enriched with linked alerts and containment actions. */
export interface IncidentDetailPublic extends IncidentPublic {
  alerts: SecurityAlertPublic[];
  actions: IncidentActionPublic[];
}

export interface AuditEventPublic {
  id: string;
  seq: number;
  company_id: string | null;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  category: string | null;
  resource_type: string | null;
  resource_id: string | null;
  outcome: string;
  detail: Record<string, unknown> | null;
  policy_result: string | null;
  approval_ref: string | null;
  correlation_id: string | null;
  ip_address: string | null;
  hash: string;
  prev_hash: string | null;
  created_at: string;
}

export interface AuditChainVerify {
  verified: boolean;
  checked: number;
  first_gap_at_seq: number | null;
}

export interface DataClassificationPublic {
  resource_type: string;
  resource_id: string;
  classification: string;
  sensitivity_reason: string | null;
}

export interface DataClassificationInput {
  resource_type: string;
  resource_id: string;
  classification: string;
  sensitivity_reason?: string | null;
}

export interface TransferCheckInput {
  resource_type: string;
  resource_id: string;
  destination: string;
  payload?: Record<string, unknown> | null;
  max_outbound?: string | null;
}

export interface TransferDecisionPublic {
  allowed: boolean;
  reason: string;
  target_classification: string;
  destination: string | null;
  requires_approval: boolean;
  blocked_fields: number;
}

export interface RetentionPolicyInput {
  entity_type: string;
  retention_days: number;
  deletion_semantics?: string;
  retention_lock?: boolean;
}

export interface RetentionPolicyPublic {
  entity_type: string;
  company_id: string | null;
  retention_days: number;
  deletion_semantics: string;
  retention_lock: boolean;
  enabled: boolean;
}

export interface SystemHealthProbe {
  status: string;
  service: string;
  checks: Record<string, string> | null;
}

export interface HealthOverview {
  incidents_open: number;
  alerts_open: number;
  audit_events: number;
  resource_limits: number;
  resource_usage_entries: number;
}

export interface MetricsSnapshot {
  labels: Record<string, string>;
  values: Record<string, number>;
  counters: Record<string, number>;
  recorded_at: string;
}

export interface SystemHealthRecordPublic {
  id: string;
  service: string;
  component: string;
  healthy: boolean;
  detail: Record<string, unknown> | null;
  latency_ms: number | null;
  recorded_at: string;
}

// ── Phase 12: Simulation, Optimization & Agent Marketplace ─────────────────

export interface SimulationVariableInput {
  name: string;
  kind: string;
  value?: string | null;
  min_value?: string | null;
  max_value?: string | null;
  default_value?: string | null;
  description?: string | null;
  source?: string | null;
  confidence?: number | null;
}

export interface SimulationCreate {
  name: string;
  description?: string | null;
  company_id?: string | null;
  scenario_type?: string;
  assumptions?: Record<string, unknown> | null;
  horizon_days?: number | null;
  clock_tick?: string | null;
  variables?: SimulationVariableInput[];
  baseline_simulation_id?: string | null;
}

export interface SimulationPublic {
  id: string;
  company_id: string | null;
  name: string;
  description: string | null;
  scenario_type: string;
  status: string;
  model_name: string | null;
  model_version: string | null;
  assumptions_json: Record<string, unknown> | null;
  horizon_days: number | null;
  clock_tick: string | null;
  baseline_simulation_id: string | null;
  sandboxed: boolean;
  created_at: string;
  updated_at: string;
}

export interface SimulationUpdate {
  name?: string | null;
  description?: string | null;
  assumptions?: Record<string, unknown> | null;
  horizon_days?: number | null;
  clock_tick?: string | null;
}

export interface SimulationRunCreate {
  scenario_id?: string | null;
  seed?: string | null;
  iterations?: number | null;
}

export interface SimulationRunPublic {
  id: string;
  simulation_id: string;
  scenario_id: string | null;
  company_id: string | null;
  status: string;
  seed: string | null;
  model_name: string | null;
  model_version: string | null;
  tick_count: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  summary_json: Record<string, unknown> | null;
  created_at: string;
}

export interface ScenarioCreate {
  simulation_id: string;
  name: string;
  scenario_type?: string;
  description?: string | null;
  company_id?: string | null;
  assumptions?: Record<string, unknown> | null;
  horizon_days?: number | null;
  objective?: Record<string, unknown> | null;
  is_baseline?: boolean;
  variables?: SimulationVariableInput[];
}

export interface ScenarioPublic {
  id: string;
  simulation_id: string;
  company_id: string | null;
  name: string;
  scenario_type: string;
  description: string | null;
  assumptions_json: Record<string, unknown> | null;
  horizon_days: number | null;
  is_baseline: boolean;
  created_at: string;
}

export interface SimulationComparisonPublic {
  id: string;
  baseline_run_id: string;
  scenario_run_id: string | null;
  company_id: string | null;
  metric_deltas_json: Record<string, unknown> | null;
  bottleneck_json: Record<string, unknown> | null;
  summary: string | null;
  created_at: string;
}

export interface SimulationSnapshotPublic {
  id: string;
  company_id: string | null;
  source_company_id: string;
  name: string;
  model_version: string | null;
  snapshot_json: Record<string, unknown> | null;
  created_at: string;
}

export interface SimulationStatePublic {
  run_id: string;
  status: string;
  tick: number;
  simulation_id: string;
  scenario_id: string | null;
  entities: Record<string, unknown>[];
  events: Record<string, unknown>[];
}

export interface SimulationEventPublic {
  id: string;
  run_id: string;
  tick: number;
  event_kind: string;
  entity_ref: string | null;
  detail_json: Record<string, unknown> | null;
}

export interface SimulationMetricsPublic {
  run_id: string;
  metrics: Record<string, unknown>[];
}

export interface SimulationResultsPublic {
  run_id: string;
  iterations: number;
  summary_json: Record<string, unknown> | null;
  metrics: Record<string, unknown>[];
  outcomes: Record<string, unknown>[];
}

export interface OptimizationObjectiveInput {
  metric: string;
  direction?: string;
  weight?: number;
}

export interface OptimizationVariableInput {
  name: string;
  kind?: string;
  low?: number | null;
  high?: number | null;
  default?: number | null;
  options?: unknown[] | null;
}

export interface OptimizationProblemCreate {
  name: string;
  description?: string | null;
  company_id?: string | null;
  strategy?: string | null;
  objectives?: OptimizationObjectiveInput[];
  variables?: OptimizationVariableInput[];
  constraints?: Record<string, unknown>[] | null;
}

export interface OptimizationProblemPublic {
  id: string;
  company_id: string | null;
  name: string;
  description: string | null;
  status: string;
  objective_json: Record<string, unknown> | null;
  strategy: string | null;
  created_at: string;
  updated_at: string;
}

export interface OptimizationRunPublic {
  id: string;
  problem_id: string;
  company_id: string | null;
  status: string;
  strategy: string | null;
  constraints_json: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  result_json: Record<string, unknown> | null;
  created_at: string;
}

export interface OptimizationResultsPublic {
  run_id: string;
  candidates: Record<string, unknown>[];
  best_candidate: Record<string, unknown> | null;
}

export interface RecommendationPublic {
  id: string;
  run_id: string;
  company_id: string | null;
  status: string;
  title: string;
  candidate_values_json: Record<string, unknown> | null;
  explanation_json: Record<string, unknown> | null;
  expected_benefit_json: Record<string, unknown> | null;
  expected_cost_json: Record<string, unknown> | null;
  risk_json: Record<string, unknown> | null;
  assumptions_json: Record<string, unknown> | null;
  approval_gate_id: string | null;
  approved_at: string | null;
  rejected_reason: string | null;
  applied_ref: string | null;
  created_at: string;
}

export interface RecommendationReject {
  reason?: string | null;
}

export interface ExperimentCreate {
  name: string;
  description?: string | null;
  company_id?: string | null;
  hypothesis?: string | null;
  sample_size?: number | null;
  metrics?: string[] | null;
  baseline?: Record<string, unknown> | null;
  variants?: Record<string, unknown>[];
}

export interface ExperimentPublic {
  id: string;
  company_id: string | null;
  name: string;
  description: string | null;
  status: string;
  hypothesis: string | null;
  sample_size: number | null;
  metrics_json: Record<string, unknown> | null;
  baseline_json: Record<string, unknown> | null;
  approval_gate_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExperimentResultPublic {
  id: string;
  experiment_id: string;
  conclusion: string;
  winning_variant_id: string | null;
  sample_size: number | null;
  metrics_json: Record<string, unknown> | null;
  confidence_json: Record<string, unknown> | null;
  assumptions_json: Record<string, unknown> | null;
  limitations_json: Record<string, unknown> | null;
  created_at: string;
}

export interface BenchmarkCreate {
  name: string;
  description?: string | null;
  company_id?: string | null;
  version?: string | null;
  dimensions?: string[] | null;
  cases?: Record<string, unknown>[] | null;
}

export interface BenchmarkPublic {
  id: string;
  company_id: string | null;
  name: string;
  description: string | null;
  status: string;
  version: string | null;
  dimensions_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface BenchmarkRunPublic {
  id: string;
  benchmark_id: string;
  agent_id: string | null;
  agent_version: string | null;
  company_id: string | null;
  status: string;
  case_count: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface BenchmarkResultsPublic {
  run_id: string;
  benchmark_id: string;
  results: Record<string, unknown>[];
  aggregate: Record<string, unknown> | null;
}

export interface AgentBenchmarkScorePublic {
  id: string;
  agent_id: string | null;
  benchmark_id: string;
  dimension: string;
  score: number;
  sample_cases: number;
  created_at: string;
}

export interface PackageVersionInput {
  version: string;
  changelog?: string | null;
  compatibility?: string;
  metadata?: Record<string, unknown> | null;
  capabilities?: string[];
  dependencies?: Record<string, string>[];
}

export interface AgentPackageCreate {
  name: string;
  display_name?: string | null;
  description?: string | null;
  company_id?: string | null;
  capabilities?: string[];
  skills?: string[];
  supported_task_types?: string[];
  requirements?: Record<string, unknown> | null;
  security?: string;
  version?: PackageVersionInput | null;
}

export interface AgentPackagePublic {
  id: string;
  company_id: string | null;
  name: string;
  display_name: string | null;
  description: string | null;
  status: string;
  capabilities_json: Record<string, unknown> | null;
  skills_json: Record<string, unknown> | null;
  supported_task_types_json: Record<string, unknown> | null;
  requirements_json: Record<string, unknown> | null;
  security: string;
  published_at: string | null;
  deprecated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentPackageVersionPublic {
  id: string;
  package_id: string;
  version: string;
  changelog: string | null;
  compatibility: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface InstallRequest {
  package_id: string;
  company_id: string;
  version_id?: string | null;
  config?: Record<string, unknown> | null;
  require_approval?: boolean;
}

export interface InstallationPublic {
  id: string;
  package_id: string;
  version_id: string | null;
  company_id: string;
  employee_id: string | null;
  agent_id: string | null;
  status: string;
  approval_gate_id: string | null;
  config_json: Record<string, unknown> | null;
  installed_at: string | null;
  created_at: string;
}

export interface AgentRecommendationPublic {
  id: string;
  company_id: string | null;
  task_id: string | null;
  agent_id: string | null;
  package_id: string | null;
  request_json: Record<string, unknown> | null;
  rank: number;
  score: number;
  reasoning: string | null;
  tradeoffs_json: Record<string, unknown> | null;
  compatibility: string;
  policy_status: string | null;
  created_at: string;
}

export interface ReputationPublic {
  id: string;
  agent_id: string | null;
  company_id: string | null;
  source: string;
  score: number;
  sample_size: number;
  recorded_at: string;
}

export interface OptimizationCyclePublic {
  id: string;
  company_id: string | null;
  name: string;
  status: string;
  observed_json: Record<string, unknown> | null;
  scenario_ids_json: unknown[] | null;
  simulation_run_id: string | null;
  optimization_run_id: string | null;
  recommendation_id: string | null;
  approval_gate_id: string | null;
  execute_ref: string | null;
  measures_json: Record<string, unknown> | null;
  lesson_json: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
  updated_at: string;
}

export interface OptimizationCycleCreate {
  company_id: string;
  name: string;
  observe?: boolean;
}
