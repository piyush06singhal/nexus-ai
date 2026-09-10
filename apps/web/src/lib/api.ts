import type {
  Agent,
  AgentAssignment,
  AgentExecution,
  AgentInput,
  AgentMessage,
  AgentReview,
  HealthResponse,
  Memory,
  MemoryListResponse,
  MemorySearchResult,
  MemoryStatus,
  MemoryType,
  Orchestration,
  OrchestrationContextEntry,
  OrchestrationInput,
  OrchestrationListResponse,
  OrchestrationResult,
  OrchestrationStatus,
  OrchestrationTask,
  OrchestrationTimelineEvent,
  ReviewCompleteInput,
  ReviewInput,
  StepExecution,
  Task,
  Workflow,
  WorkflowExecution,
  WorkflowInput,
  WorkflowStep,
  WorkflowStepInput,
  WorkflowTrigger,
  WorkflowTriggerInput,
  WorkflowValidationResult,
} from "@/lib/types";

/**
 * API calls are made same-origin and proxied to the NEXUS backend by the
 * catch-all route in `src/app/api/[...path]/route.ts`. This keeps the browser
 * talking to one origin and avoids CORS in local dev and Docker alike.
 */
interface ApiError extends Error {
  status?: number;
  body?: unknown;
}

/** Thin wrapper around fetch with JSON handling and normalized errors. */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!response.ok) {
    const error: ApiError = new Error(
      `Request failed: ${response.status} ${response.statusText}`,
    );
    error.status = response.status;
    try {
      error.body = await response.json();
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw error;
  }

  return (await response.json()) as T;
}

function apiUrl(path: string): string {
  return `/api/v1${path}`;
}

/** Fetch the backend health status. */
export function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>(apiUrl("/health"));
}

// --- Agents ---

export function fetchAgents(): Promise<Agent[]> {
  return apiFetch<Agent[]>(apiUrl("/agents"));
}

export function createAgent(input: AgentInput): Promise<Agent> {
  return apiFetch<Agent>(apiUrl("/agents"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateAgent(
  id: string,
  input: Partial<AgentInput>,
): Promise<Agent> {
  return apiFetch<Agent>(apiUrl(`/agents/${id}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteAgent(id: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/agents/${id}`), { method: "DELETE" });
}

// --- Tools (Phase 2) ---

export function fetchTools(): Promise<import("@/lib/types").ToolDefinition[]> {
  return apiFetch<import("@/lib/types").ToolDefinition[]>(apiUrl("/tools"));
}

export function fetchToolCalls(
  executionId: string,
): Promise<import("@/lib/types").ToolCallRecord[]> {
  return apiFetch<import("@/lib/types").ToolCallRecord[]>(
    apiUrl(`/tools/calls/${executionId}`),
  );
}

// --- Tasks ---

export function fetchTasks(): Promise<Task[]> {
  return apiFetch<Task[]>(apiUrl("/tasks"));
}

export function createTask(input: {
  title: string;
  description?: string | null;
  input_data?: Record<string, unknown> | null;
}): Promise<Task> {
  return apiFetch<Task>(apiUrl("/tasks"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function assignTask(taskId: string, agentId: string): Promise<Task> {
  return apiFetch<Task>(apiUrl(`/tasks/${taskId}/assign`), {
    method: "POST",
    body: JSON.stringify({ agent_id: agentId }),
  });
}

export function executeTask(taskId: string): Promise<AgentExecution> {
  return apiFetch<AgentExecution>(apiUrl(`/tasks/${taskId}/execute`), {
    method: "POST",
  });
}

export function fetchTaskExecutions(taskId: string): Promise<AgentExecution[]> {
  return apiFetch<AgentExecution[]>(apiUrl(`/tasks/${taskId}/executions`));
}

/** Fetch the most recent executions across all tasks (activity feed). */
export function fetchExecutions(limit = 50): Promise<AgentExecution[]> {
  return apiFetch<AgentExecution[]>(apiUrl(`/executions?limit=${limit}`));
}

// --- Workflows (Phase 3) ---

export function fetchWorkflows(): Promise<Workflow[]> {
  return apiFetch<Workflow[]>(apiUrl("/workflows"));
}

export function createWorkflow(input: WorkflowInput): Promise<Workflow> {
  return apiFetch<Workflow>(apiUrl("/workflows"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getWorkflow(id: string): Promise<Workflow> {
  return apiFetch<Workflow>(apiUrl(`/workflows/${id}`));
}

export function updateWorkflow(
  id: string,
  input: Partial<WorkflowInput>,
): Promise<Workflow> {
  return apiFetch<Workflow>(apiUrl(`/workflows/${id}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteWorkflow(id: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/workflows/${id}`), { method: "DELETE" });
}

export function activateWorkflow(id: string): Promise<Workflow> {
  return apiFetch<Workflow>(apiUrl(`/workflows/${id}/activate`), {
    method: "POST",
  });
}

export function pauseWorkflow(id: string): Promise<Workflow> {
  return apiFetch<Workflow>(apiUrl(`/workflows/${id}/pause`), {
    method: "POST",
  });
}

export function validateWorkflow(id: string): Promise<WorkflowValidationResult> {
  return apiFetch<WorkflowValidationResult>(apiUrl(`/workflows/${id}/validate`));
}

// Steps

export function fetchWorkflowSteps(workflowId: string): Promise<WorkflowStep[]> {
  return apiFetch<WorkflowStep[]>(apiUrl(`/workflows/${workflowId}/steps`));
}

export function createWorkflowStep(
  workflowId: string,
  input: WorkflowStepInput,
): Promise<WorkflowStep> {
  return apiFetch<WorkflowStep>(apiUrl(`/workflows/${workflowId}/steps`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateWorkflowStep(
  stepId: string,
  input: Partial<WorkflowStepInput>,
): Promise<WorkflowStep> {
  return apiFetch<WorkflowStep>(apiUrl(`/workflows/steps/${stepId}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteWorkflowStep(stepId: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/workflows/steps/${stepId}`), {
    method: "DELETE",
  });
}

// Triggers

export function fetchWorkflowTriggers(
  workflowId: string,
): Promise<WorkflowTrigger[]> {
  return apiFetch<WorkflowTrigger[]>(apiUrl(`/workflows/${workflowId}/triggers`));
}

export function createWorkflowTrigger(
  workflowId: string,
  input: WorkflowTriggerInput,
): Promise<WorkflowTrigger> {
  return apiFetch<WorkflowTrigger>(apiUrl(`/workflows/${workflowId}/triggers`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteWorkflowTrigger(triggerId: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/workflows/triggers/${triggerId}`), {
    method: "DELETE",
  });
}

// Execute

export function executeWorkflow(
  workflowId: string,
  input?: Record<string, unknown> | null,
): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(apiUrl(`/workflows/${workflowId}/execute`), {
    method: "POST",
    body: input ? JSON.stringify({ input_data: input }) : "{}",
  });
}

// Executions

export function fetchWorkflowExecutions(
  workflowId: string,
): Promise<WorkflowExecution[]> {
  return apiFetch<WorkflowExecution[]>(
    apiUrl(`/workflows/${workflowId}/executions`),
  );
}

export function getWorkflowExecution(
  executionId: string,
): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(
    apiUrl(`/workflows/executions/${executionId}`),
  );
}

export function fetchStepExecutions(
  executionId: string,
): Promise<StepExecution[]> {
  return apiFetch<StepExecution[]>(
    apiUrl(`/workflows/executions/${executionId}/steps`),
  );
}

export function cancelWorkflowExecution(
  executionId: string,
): Promise<WorkflowExecution> {
  return apiFetch<WorkflowExecution>(
    apiUrl(`/workflows/executions/${executionId}/cancel`),
    { method: "POST" },
  );
}

// --- Memory (Phase 4) ---

export function fetchMemories(params: {
  namespace: string;
  owner_id?: string;
  type?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<MemoryListResponse> {
  const sp = new URLSearchParams({ namespace: params.namespace });
  if (params.owner_id) sp.set("owner_id", params.owner_id);
  if (params.type) sp.set("type", params.type);
  if (params.status) sp.set("status", params.status);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  return apiFetch<MemoryListResponse>(apiUrl(`/memories?${sp.toString()}`));
}

export function createMemory(input: {
  namespace: string;
  type: MemoryType;
  content: string;
  summary?: string;
  importance?: number;
  confidence?: number;
}): Promise<Memory> {
  return apiFetch<Memory>(apiUrl("/memories"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getMemory(id: string): Promise<Memory> {
  return apiFetch<Memory>(apiUrl(`/memories/${id}`));
}

export function updateMemory(
  id: string,
  input: Partial<{
    content: string;
    summary: string;
    status: MemoryStatus;
    importance: number;
    confidence: number;
  }>,
): Promise<Memory> {
  return apiFetch<Memory>(apiUrl(`/memories/${id}`), {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteMemory(id: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/memories/${id}`), { method: "DELETE" });
}

export function searchMemories(input: {
  query: string;
  namespace: string;
  owner_id?: string;
  memory_types?: MemoryType[];
  top_k?: number;
  min_score?: number;
}): Promise<MemorySearchResult[]> {
  return apiFetch<MemorySearchResult[]>(
    apiUrl("/memories/search"),
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function archiveMemory(id: string): Promise<Memory> {
  return apiFetch<Memory>(apiUrl(`/memories/${id}/archive`), {
    method: "POST",
  });
}

export function cleanupExpiredMemories(): Promise<{
  expired_count: number;
}> {
  return apiFetch<{ expired_count: number }>(apiUrl("/memories/cleanup"), {
    method: "POST",
  });
}

// --- Orchestrations (Phase 5) ---

export function fetchOrchestrations(input?: {
  status?: OrchestrationStatus;
  limit?: number;
  offset?: number;
}): Promise<OrchestrationListResponse> {
  const sp = new URLSearchParams();
  if (input?.status) sp.set("status", input.status);
  if (input?.limit) sp.set("limit", String(input.limit));
  if (input?.offset) sp.set("offset", String(input.offset));
  const query = sp.toString();
  return apiFetch<OrchestrationListResponse>(
    apiUrl(`/orchestrations${query ? `?${query}` : ""}`),
  );
}

export function createOrchestration(
  input: OrchestrationInput,
): Promise<Orchestration> {
  return apiFetch<Orchestration>(apiUrl("/orchestrations"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getOrchestration(id: string): Promise<Orchestration> {
  return apiFetch<Orchestration>(apiUrl(`/orchestrations/${id}`));
}

export function executeOrchestration(id: string): Promise<Orchestration> {
  return apiFetch<Orchestration>(apiUrl(`/orchestrations/${id}/execute`), {
    method: "POST",
  });
}

export function cancelOrchestration(id: string): Promise<Orchestration> {
  return apiFetch<Orchestration>(apiUrl(`/orchestrations/${id}/cancel`), {
    method: "POST",
  });
}

export function fetchOrchestrationTasks(
  id: string,
): Promise<OrchestrationTask[]> {
  return apiFetch<OrchestrationTask[]>(apiUrl(`/orchestrations/${id}/tasks`));
}

export function fetchOrchestrationAgents(
  id: string,
): Promise<AgentAssignment[]> {
  return apiFetch<AgentAssignment[]>(
    apiUrl(`/orchestrations/${id}/assignments`),
  );
}

export function fetchOrchestrationMessages(
  id: string,
): Promise<AgentMessage[]> {
  return apiFetch<AgentMessage[]>(apiUrl(`/orchestrations/${id}/messages`));
}

export function fetchOrchestrationResults(
  id: string,
): Promise<OrchestrationResult[]> {
  return apiFetch<OrchestrationResult[]>(apiUrl(`/orchestrations/${id}/results`));
}

export function fetchOrchestrationContext(
  id: string,
): Promise<OrchestrationContextEntry[]> {
  return apiFetch<OrchestrationContextEntry[]>(
    apiUrl(`/orchestrations/${id}/context`),
  );
}

export function fetchOrchestrationReviews(
  id: string,
): Promise<AgentReview[]> {
  return apiFetch<AgentReview[]>(apiUrl(`/orchestrations/${id}/reviews`));
}

export function fetchOrchestrationTimeline(
  id: string,
): Promise<OrchestrationTimelineEvent[]> {
  return apiFetch<OrchestrationTimelineEvent[]>(
    apiUrl(`/orchestrations/${id}/timeline`),
  );
}

export function createOrchestrationReview(
  id: string,
  input: ReviewInput,
): Promise<AgentReview> {
  return apiFetch<AgentReview>(apiUrl(`/orchestrations/${id}/reviews`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function completeOrchestrationReview(
  orchestrationId: string,
  reviewId: string,
  input: ReviewCompleteInput,
): Promise<AgentReview> {
  return apiFetch<AgentReview>(
    apiUrl(`/orchestrations/${orchestrationId}/reviews/${reviewId}/complete`),
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}