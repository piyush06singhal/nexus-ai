import type {
  Agent,
  AgentExecution,
  AgentInput,
  HealthResponse,
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