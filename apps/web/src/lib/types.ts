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