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