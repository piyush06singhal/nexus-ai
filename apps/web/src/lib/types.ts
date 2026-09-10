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