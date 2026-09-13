import type {
  Agent,
  AgentAssignment,
  AgentExecution,
  AgentInput,
  AgentMessage,
  AgentReview,
  Alert,
  ApprovalGate,
  AssignmentInput,
  AssignmentResult,
  AutonomyPolicy,
  AutonomyPolicyInput,
  BudgetSnapshot,
  Company,
  CompanyAnalytics,
  CompanyBudgets,
  CompanyEmployee,
  CompanyHealth,
  CompanyInput,
  CompanyPerformance,
  CompanyReport,
  CompanyStateSnapshot,
  CompanyUpdateInput,
  Decision,
  DecisionInput,
  DecisionReviewEntry,
  Department,
  DepartmentEmployee,
  DepartmentInput,
  EffectivePolicy,
  Employee,
  EmployeeAuditEntry,
  EmployeeGoal,
  EmployeeInput,
  EmployeeListResponse,
  EmployeePerformance,
  EmployeeReview,
  EmployeeSkill,
  EmployeeTemplate,
  EmployeeTemplateInput,
  EmployeeTimelineEvent,
  EmployeeWorkload,
  Escalation,
  EscalationListResponse,
  EscalationState,
  Evaluation,
  EvaluationComparison,
  EvaluationInput,
  EvaluationListResponse,
  EvaluationResult,
  EvaluationRun,
  EvaluationRunListResponse,
  FailureDiagnosis,
  GoalInput,
  GoalScopeType,
  HealthResponse,
  Kpi,
  KpiInput,
  Membership,
  MembershipInput,
  Memory,
  MemoryListResponse,
  MemorySearchResult,
  MemoryStatus,
  MemoryType,
  Mission,
  MissionAnalysisResult,
  MissionGraph,
  MissionInput,
  MissionPlanResult,
  MissionTrace,
  NextActions,
  OperatingCycle,
  Orchestration,
  OrchestrationContextEntry,
  OrchestrationInput,
  OrchestrationListResponse,
  OrchestrationResult,
  OrchestrationStatus,
  OrchestrationTask,
  OrchestrationTimelineEvent,
  OrgChartNode,
  OrgEvent,
  OrgGoal,
  OrgGoalInput,
  OrgRole,
  OrgRoleInput,
  Policy,
  PolicyInput,
  Product,
  ProductInput,
  ProductStatus,
  RecoveryAttempt,
  RecoveryPlan,
  RegressionReport,
  ReplanAction,
  ReviewCompleteInput,
  ReviewInput,
  Risk,
  RiskInput,
  StartupFeedback,
  StartupFeedbackInput,
  StartupPlan,
  StartupPlanInput,
  StartupProject,
  StartupProjectInput,
  StartupProjectStatus,
  StepExecution,
  Task,
  VerifyRequest,
  VerificationListResponse,
  VerificationPolicy,
  VerificationResult,
  VerificationRun,
  VerificationStatus,
  ValidationResult,
  Workflow,
  WorkflowExecution,
  WorkflowInput,
  WorkflowStep,
  WorkflowStepInput,
  WorkflowTrigger,
  WorkflowTriggerInput,
  WorkflowValidationResult,
  WorkforceOverview,
  // ── Phase 10: External Integrations & Computer Use ──
  BrowserAction,
  BrowserObservation,
  BrowserSession,
  ComputerAction,
  ComputerObservation,
  ComputerSession,
  ConnectionTestResponse,
  ExternalAction,
  ExternalDashboard,
  ExternalDomainRule,
  ExternalEvent,
  ExternalIntegration,
  ExternalIntegrationPolicy,
  IntegrationCapability,
  IntegrationConnection,
  // ── Phase 11: Security, Governance & Production Hardening ──
  AuditChainVerify,
  AuditEventPublic,
  AuthSessionResponse,
  BreakGlassInput,
  BreakGlassPublic,
  DataClassificationInput,
  DataClassificationPublic,
  FeatureFlagInput,
  FeatureFlagPublic,
  GovernanceControlPublic,
  HealthOverview,
  IncidentActionInput,
  IncidentActionPublic,
  IncidentCreateInput,
  IncidentDetailPublic,
  IncidentPublic,
  IncidentTransitionInput,
  MetricsSnapshot,
  PermissionPublic,
  PolicyDecisionPublic,
  PolicyRuleInput,
  PolicyRulePublic,
  ResourceLimitInput,
  ResourceLimitPublic,
  ResourceUsagePublic,
  RetentionPolicyInput,
  RetentionPolicyPublic,
  RolePublic,
  SecretCreateInput,
  SecretReference,
  SecurityAlertPublic,
  SecurityEventPublic,
  SessionResult,
  SystemFlagPublic,
  SystemHealthProbe,
  SystemHealthRecordPublic,
  TransferCheckInput,
  TransferDecisionPublic,
  UserCreateInput,
  UserPublic,
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

// --- Verification (Phase 6) ---

/** List verification runs, optionally filtered by status. */
export function fetchVerifications(
  status?: VerificationStatus,
  limit = 50,
): Promise<VerificationListResponse> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (status) qs.set("status", status);
  return apiFetch<VerificationListResponse>(
    apiUrl(`/verifications?${qs.toString()}`),
  );
}

/** Trigger verification of an execution or raw result data. */
export function verifyExecution(input: VerifyRequest): Promise<VerificationResult> {
  return apiFetch<VerificationResult>(apiUrl("/verifications"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Fetch a single verification result by id. */
export function getVerification(id: string): Promise<VerificationResult> {
  return apiFetch<VerificationResult>(apiUrl(`/verifications/${id}`));
}

/** Fetch a verification run (its status/score meta) by id. */
export function getVerificationRun(id: string): Promise<VerificationRun> {
  return apiFetch<VerificationRun>(apiUrl(`/verifications/runs/${id}`));
}

/** Create a verification policy. */
export function createVerificationPolicy(input: {
  name: string;
  config: Record<string, unknown>;
  scope_type?: string;
  scope_id?: string;
}): Promise<VerificationPolicy> {
  return apiFetch<VerificationPolicy>(apiUrl("/verifications/policies"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// --- Recovery (Phase 6) ---

/** Trigger recovery for a failed execution. */
export function recoverExecution(
  executionId: string,
  input?: {
    error_text?: string;
    exception_type?: string;
    tool_call_status?: string;
    tool_call_result?: Record<string, unknown>;
    original_plan?: Record<string, unknown>;
  },
): Promise<RecoveryAttempt> {
  return apiFetch<RecoveryAttempt>(
    apiUrl(`/recoveries/executions/${executionId}/recover`),
    {
      method: "POST",
      body: JSON.stringify(input ?? { execution_id: executionId }),
    },
  );
}

/** Fetch a single recovery attempt by id. */
export function getRecovery(id: string): Promise<RecoveryAttempt> {
  return apiFetch<RecoveryAttempt>(apiUrl(`/recoveries/attempts/${id}`));
}

/** List recovery attempts for an execution. */
export function fetchExecutionRecoveries(executionId: string): Promise<RecoveryAttempt[]> {
  return apiFetch<RecoveryAttempt[]>(
    apiUrl(`/recoveries/executions/${executionId}`),
  );
}

/** Fetch the latest failure diagnosis for an execution. */
export function fetchExecutionDiagnosis(executionId: string): Promise<FailureDiagnosis> {
  return apiFetch<FailureDiagnosis>(
    apiUrl(`/recoveries/diagnoses/executions/${executionId}`),
  );
}

/** Fetch the latest recovery plan for an execution. */
export function fetchExecutionPlan(executionId: string): Promise<RecoveryPlan> {
  return apiFetch<RecoveryPlan>(
    apiUrl(`/recoveries/plans/executions/${executionId}`),
  );
}

// --- Escalations (Phase 6) ---

/** List escalations, optionally filtered by state. */
export function fetchEscalations(
  state?: EscalationState,
  limit = 50,
): Promise<EscalationListResponse> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (state) qs.set("state", state);
  return apiFetch<EscalationListResponse>(
    apiUrl(`/escalations?${qs.toString()}`),
  );
}

/** Approve an escalation (human-in-the-loop). */
export function approveEscalation(
  id: string,
  decision_reason?: string,
): Promise<Escalation> {
  return apiFetch<Escalation>(apiUrl(`/escalations/${id}/approve`), {
    method: "POST",
    body: JSON.stringify({ decision_reason }),
  });
}

/** Reject an escalation (human-in-the-loop). */
export function rejectEscalation(
  id: string,
  decision_reason?: string,
): Promise<Escalation> {
  return apiFetch<Escalation>(apiUrl(`/escalations/${id}/reject`), {
    method: "POST",
    body: JSON.stringify({ decision_reason }),
  });
}

// --- Evaluation (Phase 6) ---

/** List evaluations. */
export function fetchEvaluations(limit = 50): Promise<EvaluationListResponse> {
  return apiFetch<EvaluationListResponse>(
    apiUrl(`/evaluations?limit=${limit}`),
  );
}

/** List evaluation runs (optionally for one evaluation). */
export function fetchEvaluationRuns(
  evaluationId?: string,
  limit = 50,
): Promise<EvaluationRunListResponse> {
  const qs = new URLSearchParams({ limit: String(limit) });
  if (evaluationId) qs.set("evaluation_id", evaluationId);
  return apiFetch<EvaluationRunListResponse>(
    apiUrl(`/evaluations/runs?${qs.toString()}`),
  );
}

/** Run an evaluation suite (or the default dataset). */
export function runEvaluation(input: EvaluationInput): Promise<EvaluationRun> {
  return apiFetch<EvaluationRun>(apiUrl("/evaluations/runs"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** Fetch a single evaluation run. */
export function fetchEvaluationRun(id: string): Promise<EvaluationRun> {
  return apiFetch<EvaluationRun>(apiUrl(`/evaluations/runs/${id}`));
}

/** Fetch the per-case results for an evaluation run. */
export function fetchEvaluationResults(id: string): Promise<EvaluationResult[]> {
  return apiFetch<EvaluationResult[]>(
    apiUrl(`/evaluations/runs/${id}/results`),
  );
}

/** Compare two evaluation runs. */
export function compareEvaluationRuns(
  runA: string,
  runB: string,
): Promise<EvaluationComparison> {
  const qs = new URLSearchParams({ run_a: runA, run_b: runB });
  return apiFetch<EvaluationComparison>(
    apiUrl(`/evaluations/runs/compare?${qs.toString()}`),
  );
}

/** Check for regression between two scores. */
export function checkRegression(
  previous: number,
  current: number,
): Promise<RegressionReport> {
  const qs = new URLSearchParams({
    previous: String(previous),
    current: String(current),
  });
  return apiFetch<RegressionReport>(
    apiUrl(`/evaluations/regression/check?${qs.toString()}`),
  );
}

/** Fetch a single evaluation by id. */
export function getEvaluation(id: string): Promise<Evaluation> {
  return apiFetch<Evaluation>(apiUrl(`/evaluations/${id}`));
}

// --- AI Employee OS (Phase 7) ---

export function fetchEmployees(params?: {
  status?: string;
  role?: string;
  limit?: number;
  offset?: number;
}): Promise<EmployeeListResponse> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.role) sp.set("role", params.role);
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  const query = sp.toString();
  return apiFetch<EmployeeListResponse>(
    apiUrl(`/employees${query ? `?${query}` : ""}`),
  );
}

export function createEmployee(input: EmployeeInput): Promise<Employee> {
  return apiFetch<Employee>(apiUrl("/employees"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}`));
}

export function updateEmployee(
  id: string,
  input: Partial<EmployeeInput>,
): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function deleteEmployee(id: string): Promise<void> {
  return apiFetch<void>(apiUrl(`/employees/${id}`), { method: "DELETE" });
}

// Lifecycle actions

export function activateEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}/activate`), {
    method: "POST",
  });
}

export function pauseEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}/pause`), {
    method: "POST",
  });
}

export function resumeEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}/resume`), {
    method: "POST",
  });
}

export function suspendEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}/suspend`), {
    method: "POST",
  });
}

export function terminateEmployee(id: string): Promise<Employee> {
  return apiFetch<Employee>(apiUrl(`/employees/${id}/terminate`), {
    method: "POST",
  });
}

// Assignment

export function assignEmployeeTask(
  employeeId: string,
  input: AssignmentInput,
): Promise<AssignmentResult> {
  return apiFetch<AssignmentResult>(apiUrl(`/employees/${employeeId}/tasks`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function autoAssignEmployeeTask(
  input: AssignmentInput,
): Promise<AssignmentResult> {
  return apiFetch<AssignmentResult>(apiUrl("/employees/assign"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Workload / Skills / Goals / Performance

export function fetchEmployeeWorkload(
  id: string,
): Promise<EmployeeWorkload> {
  return apiFetch<EmployeeWorkload>(apiUrl(`/employees/${id}/workload`));
}

export function fetchEmployeeSkills(id: string): Promise<EmployeeSkill[]> {
  return apiFetch<EmployeeSkill[]>(apiUrl(`/employees/${id}/skills`));
}

export function fetchEmployeeGoals(id: string): Promise<EmployeeGoal[]> {
  return apiFetch<EmployeeGoal[]>(apiUrl(`/employees/${id}/goals`));
}

export function createEmployeeGoal(
  employeeId: string,
  input: GoalInput,
): Promise<EmployeeGoal> {
  return apiFetch<EmployeeGoal>(apiUrl(`/employees/${employeeId}/goals`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchEmployeePerformance(
  id: string,
): Promise<EmployeePerformance> {
  return apiFetch<EmployeePerformance>(
    apiUrl(`/employees/${id}/performance`),
  );
}

export function fetchEmployeeReviews(id: string): Promise<EmployeeReview[]> {
  return apiFetch<EmployeeReview[]>(apiUrl(`/employees/${id}/reviews`));
}

// Timeline / Audit

export function fetchEmployeeTimeline(
  id: string,
): Promise<EmployeeTimelineEvent[]> {
  return apiFetch<EmployeeTimelineEvent[]>(
    apiUrl(`/employees/${id}/timeline`),
  );
}

export function fetchEmployeeAudit(
  id: string,
): Promise<EmployeeAuditEntry[]> {
  return apiFetch<EmployeeAuditEntry[]>(apiUrl(`/employees/${id}/audit`));
}

// Templates

export function fetchEmployeeTemplates(): Promise<EmployeeTemplate[]> {
  return apiFetch<EmployeeTemplate[]>(apiUrl("/employee-templates"));
}

export function createEmployeeTemplate(
  input: EmployeeTemplateInput,
): Promise<EmployeeTemplate> {
  return apiFetch<EmployeeTemplate>(apiUrl("/employee-templates"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getEmployeeTemplate(id: string): Promise<EmployeeTemplate> {
  return apiFetch<EmployeeTemplate>(apiUrl(`/employee-templates/${id}`));
}

export function createEmployeeFromTemplate(
  templateId: string,
  overrides?: Partial<EmployeeInput>,
): Promise<Employee> {
  return apiFetch<Employee>(
    apiUrl(`/employee-templates/${templateId}/create`),
    {
      method: "POST",
      body: JSON.stringify(overrides ?? {}),
    },
  );
}

// Workforce overview

export function fetchWorkforceOverview(): Promise<WorkforceOverview> {
  return apiFetch<WorkforceOverview>(apiUrl("/employees/workforce"));
}

// ── Companies (Phase 8: AI Company Layer) ──

export function fetchCompanies(): Promise<Company[]> {
  return apiFetch<Company[]>(apiUrl("/companies"));
}

export function createCompany(input: CompanyInput): Promise<Company> {
  return apiFetch<Company>(apiUrl("/companies"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getCompany(id: string): Promise<Company> {
  return apiFetch<Company>(apiUrl(`/companies/${id}`));
}

export function updateCompany(
  id: string,
  input: CompanyUpdateInput,
): Promise<Company> {
  return apiFetch<Company>(apiUrl(`/companies/${id}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

// Lifecycle

export function activateCompany(id: string): Promise<Company> {
  return apiFetch<Company>(apiUrl(`/companies/${id}/activate`), {
    method: "POST",
  });
}

export function pauseCompany(id: string): Promise<Company> {
  return apiFetch<Company>(apiUrl(`/companies/${id}/pause`), {
    method: "POST",
  });
}

export function archiveCompany(id: string): Promise<Company> {
  return apiFetch<Company>(apiUrl(`/companies/${id}/archive`), {
    method: "POST",
  });
}

// Departments

export function fetchDepartments(companyId: string): Promise<Department[]> {
  return apiFetch<Department[]>(apiUrl(`/companies/${companyId}/departments`));
}

export function createDepartment(
  companyId: string,
  input: DepartmentInput,
): Promise<Department> {
  return apiFetch<Department>(apiUrl(`/companies/${companyId}/departments`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getDepartment(id: string): Promise<Department> {
  return apiFetch<Department>(apiUrl(`/departments/${id}`));
}

export function updateDepartment(
  id: string,
  input: Partial<DepartmentInput>,
): Promise<Department> {
  return apiFetch<Department>(apiUrl(`/departments/${id}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function fetchDepartmentEmployees(
  id: string,
  includeSubtree = false,
): Promise<DepartmentEmployee[]> {
  return apiFetch<DepartmentEmployee[]>(
    apiUrl(`/departments/${id}/employees${includeSubtree ? "?include_subtree=true" : ""}`),
  );
}

export function fetchDepartmentGoals(id: string): Promise<OrgGoal[]> {
  return apiFetch<OrgGoal[]>(apiUrl(`/departments/${id}/goals`));
}

export function fetchDepartmentKpis(id: string): Promise<Kpi[]> {
  return apiFetch<Kpi[]>(apiUrl(`/departments/${id}/kpis`));
}

export function fetchDepartmentPerformance(
  id: string,
): Promise<CompanyPerformance> {
  return apiFetch<CompanyPerformance>(apiUrl(`/departments/${id}/performance`));
}

export function fetchDepartmentRisks(id: string): Promise<Risk[]> {
  return apiFetch<Risk[]>(apiUrl(`/departments/${id}/risks`));
}

export function fetchDepartmentBudget(id: string): Promise<BudgetSnapshot> {
  return apiFetch<BudgetSnapshot>(apiUrl(`/departments/${id}/budget`));
}

export function fetchDepartmentTimeline(id: string): Promise<OrgEvent[]> {
  return apiFetch<OrgEvent[]>(apiUrl(`/departments/${id}/timeline`));
}

// Memberships

export function fetchMemberships(companyId: string): Promise<Membership[]> {
  return apiFetch<Membership[]>(apiUrl(`/companies/${companyId}/memberships`));
}

export function addMembership(
  companyId: string,
  input: MembershipInput,
): Promise<Membership> {
  return apiFetch<Membership>(apiUrl(`/companies/${companyId}/memberships`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Employees + org chart

export function fetchCompanyEmployees(companyId: string): Promise<CompanyEmployee[]> {
  return apiFetch<CompanyEmployee[]>(apiUrl(`/companies/${companyId}/employees`));
}

export function fetchOrgChart(companyId: string): Promise<OrgChartNode> {
  return apiFetch<OrgChartNode>(
    apiUrl(`/companies/${companyId}/organization-chart`),
  );
}

// Goals

export function fetchCompanyGoals(
  companyId: string,
  scopeType?: GoalScopeType,
): Promise<OrgGoal[]> {
  return apiFetch<OrgGoal[]>(
    apiUrl(
      `/companies/${companyId}/goals${scopeType ? `?scope_type=${scopeType}` : ""}`,
    ),
  );
}

export function createCompanyGoal(
  companyId: string,
  input: OrgGoalInput,
): Promise<OrgGoal> {
  return apiFetch<OrgGoal>(apiUrl(`/companies/${companyId}/goals`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchGoalTree(companyId: string): Promise<OrgGoal[]> {
  return apiFetch<OrgGoal[]>(apiUrl(`/companies/${companyId}/goals/tree`));
}

export function getGoal(id: string): Promise<OrgGoal> {
  return apiFetch<OrgGoal>(apiUrl(`/goals/${id}`));
}

export function updateGoal(
  id: string,
  input: Partial<OrgGoalInput>,
): Promise<OrgGoal> {
  return apiFetch<OrgGoal>(apiUrl(`/goals/${id}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function recomputeGoalProgress(id: string): Promise<OrgGoal> {
  return apiFetch<OrgGoal>(apiUrl(`/goals/${id}/progress`));
}

// KPIs

export function fetchCompanyKpis(
  companyId: string,
  scopeType?: GoalScopeType,
): Promise<Kpi[]> {
  return apiFetch<Kpi[]>(
    apiUrl(
      `/companies/${companyId}/kpis${scopeType ? `?scope_type=${scopeType}` : ""}`,
    ),
  );
}

export function createCompanyKpi(
  companyId: string,
  input: KpiInput,
): Promise<Kpi> {
  return apiFetch<Kpi>(apiUrl(`/companies/${companyId}/kpis`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function recomputeCompanyKpis(companyId: string): Promise<{
  recomputed: number;
}> {
  return apiFetch<{ recomputed: number }>(
    apiUrl(`/companies/${companyId}/kpis/recompute`),
    { method: "POST" },
  );
}

// Budgets

export function fetchCompanyBudgets(companyId: string): Promise<CompanyBudgets> {
  return apiFetch<CompanyBudgets>(apiUrl(`/companies/${companyId}/budgets`));
}

// Performance + reports

export function fetchCompanyPerformance(
  companyId: string,
): Promise<CompanyPerformance> {
  return apiFetch<CompanyPerformance>(
    apiUrl(`/companies/${companyId}/performance`),
  );
}

export function fetchReports(
  companyId: string,
  reportType?: string,
): Promise<CompanyReport[]> {
  return apiFetch<CompanyReport[]>(
    apiUrl(
      `/companies/${companyId}/reports${reportType ? `?report_type=${reportType}` : ""}`,
    ),
  );
}

export function generateReport(
  companyId: string,
  reportType = "weekly",
): Promise<CompanyReport> {
  return apiFetch<CompanyReport>(
    apiUrl(`/companies/${companyId}/reports/generate?report_type=${reportType}`),
    { method: "POST" },
  );
}

// Risks

export function fetchCompanyRisks(
  companyId: string,
  severity?: string,
): Promise<Risk[]> {
  return apiFetch<Risk[]>(
    apiUrl(
      `/companies/${companyId}/risks${severity ? `?severity=${severity}` : ""}`,
    ),
  );
}

export function createCompanyRisk(
  companyId: string,
  input: RiskInput,
): Promise<Risk> {
  return apiFetch<Risk>(apiUrl(`/companies/${companyId}/risks`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateRisk(
  id: string,
  input: Partial<RiskInput>,
): Promise<Risk> {
  return apiFetch<Risk>(apiUrl(`/risks/${id}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

// Alerts

export function fetchCompanyAlerts(
  companyId: string,
  severity?: string,
): Promise<Alert[]> {
  return apiFetch<Alert[]>(
    apiUrl(
      `/companies/${companyId}/alerts${severity ? `?severity=${severity}` : ""}`,
    ),
  );
}

export function checkCompanyAlerts(companyId: string): Promise<{
  generated: number;
  alerts: Alert[];
}> {
  return apiFetch<{ generated: number; alerts: Alert[] }>(
    apiUrl(`/companies/${companyId}/alerts/check`),
    { method: "POST" },
  );
}

export function acknowledgeAlert(id: string): Promise<Alert> {
  return apiFetch<Alert>(apiUrl(`/alerts/${id}/acknowledge`), {
    method: "POST",
  });
}

export function resolveAlert(id: string): Promise<Alert> {
  return apiFetch<Alert>(apiUrl(`/alerts/${id}/resolve`), {
    method: "POST",
  });
}

// Decisions

export function fetchCompanyDecisions(
  companyId: string,
  decisionStatus?: string,
): Promise<Decision[]> {
  return apiFetch<Decision[]>(
    apiUrl(
      `/companies/${companyId}/decisions${decisionStatus ? `?status=${decisionStatus}` : ""}`,
    ),
  );
}

export function createCompanyDecision(
  companyId: string,
  input: DecisionInput,
): Promise<Decision> {
  return apiFetch<Decision>(apiUrl(`/decisions?company_id=${companyId}`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getDecision(id: string): Promise<Decision> {
  return apiFetch<Decision>(apiUrl(`/decisions/${id}`));
}

export function fetchDecisionReviews(id: string): Promise<DecisionReviewEntry[]> {
  return apiFetch<DecisionReviewEntry[]>(apiUrl(`/decisions/${id}/reviews`));
}

export function submitDecision(
  id: string,
  actorId?: string,
): Promise<Decision> {
  return apiFetch<Decision>(
    apiUrl(`/decisions/${id}/submit${actorId ? `?actor_id=${actorId}` : ""}`),
    { method: "POST" },
  );
}

export function approveDecision(
  id: string,
  reviewerId: string,
  rationale?: string,
): Promise<Decision> {
  return apiFetch<Decision>(
    apiUrl(`/decisions/${id}/approve?reviewer_id=${reviewerId}`),
    {
      method: "POST",
      body: JSON.stringify({ rationale: rationale ?? null }),
    },
  );
}

export function rejectDecision(
  id: string,
  reviewerId: string,
  rationale?: string,
): Promise<Decision> {
  return apiFetch<Decision>(
    apiUrl(`/decisions/${id}/reject?reviewer_id=${reviewerId}`),
    {
      method: "POST",
      body: JSON.stringify({ rationale: rationale ?? null }),
    },
  );
}

export function implementDecision(
  id: string,
  actorId: string,
): Promise<Decision> {
  return apiFetch<Decision>(
    apiUrl(`/decisions/${id}/implement?actor_id=${actorId}`),
    { method: "POST" },
  );
}

// Policies

export function fetchCompanyPolicies(companyId: string): Promise<Policy[]> {
  return apiFetch<Policy[]>(apiUrl(`/companies/${companyId}/policies`));
}

export function createCompanyPolicy(
  companyId: string,
  input: PolicyInput,
): Promise<Policy> {
  return apiFetch<Policy>(apiUrl(`/companies/${companyId}/policies`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchEffectivePolicy(
  companyId: string,
  key: string,
  departmentId?: string,
): Promise<EffectivePolicy> {
  const sp = new URLSearchParams({ key });
  if (departmentId) sp.set("department_id", departmentId);
  return apiFetch<EffectivePolicy>(
    apiUrl(`/companies/${companyId}/policies/effective?${sp.toString()}`),
  );
}

// Roles

export function fetchCompanyRoles(companyId: string): Promise<OrgRole[]> {
  return apiFetch<OrgRole[]>(apiUrl(`/companies/${companyId}/roles`));
}

export function fetchRoles(options?: {
  companyId?: string;
  authorityLevel?: string;
}): Promise<OrgRole[]> {
  const sp = new URLSearchParams();
  if (options?.companyId) sp.set("company_id", options.companyId);
  if (options?.authorityLevel) sp.set("authority_level", options.authorityLevel);
  const query = sp.toString();
  return apiFetch<OrgRole[]>(apiUrl(`/roles${query ? `?${query}` : ""}`));
}

export function createRole(input: OrgRoleInput): Promise<OrgRole> {
  return apiFetch<OrgRole>(apiUrl("/roles"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Analytics + health + timeline

export function fetchCompanyAnalytics(
  companyId: string,
): Promise<CompanyAnalytics> {
  return apiFetch<CompanyAnalytics>(apiUrl(`/companies/${companyId}/analytics`));
}

export function fetchCompanyHealth(companyId: string): Promise<CompanyHealth> {
  return apiFetch<CompanyHealth>(apiUrl(`/companies/${companyId}/health`));
}

export function fetchTimeline(companyId: string, limit = 50): Promise<OrgEvent[]> {
  return apiFetch<OrgEvent[]>(
    apiUrl(`/companies/${companyId}/timeline?limit=${limit}`),
  );
}

// ── Autonomous Startup Engine (Phase 9) ──

// Missions

export function fetchMissions(companyId: string): Promise<Mission[]> {
  return apiFetch<Mission[]>(apiUrl(`/missions?company_id=${companyId}`));
}

export function createMission(
  input: Omit<MissionInput, "company_id"> & { company_id: string },
): Promise<Mission> {
  return apiFetch<Mission>(apiUrl("/missions"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getMission(companyId: string, id: string): Promise<Mission> {
  return apiFetch<Mission>(apiUrl(`/missions/${id}?company_id=${companyId}`));
}

export function analyzeMission(companyId: string, id: string): Promise<MissionAnalysisResult> {
  return apiFetch<MissionAnalysisResult>(
    apiUrl(`/missions/${id}/analyze?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function validateMission(
  companyId: string,
  id: string,
): Promise<ValidationResult> {
  return apiFetch<ValidationResult>(
    apiUrl(`/missions/${id}/validate?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function planMission(companyId: string, id: string): Promise<MissionPlanResult> {
  return apiFetch<MissionPlanResult>(
    apiUrl(`/missions/${id}/plan?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function activateMission(companyId: string, id: string): Promise<Mission> {
  return apiFetch<Mission>(
    apiUrl(`/missions/${id}/activate?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function pauseMission(companyId: string, id: string): Promise<Mission> {
  return apiFetch<Mission>(
    apiUrl(`/missions/${id}/pause?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function cancelMission(companyId: string, id: string): Promise<Mission> {
  return apiFetch<Mission>(
    apiUrl(`/missions/${id}/cancel?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function fetchMissionGraph(
  companyId: string,
  missionId?: string,
  relation?: string,
): Promise<MissionGraph> {
  const base = missionId
    ? `/missions/${missionId}/graph`
    : `/missions/graph`;
  const sp = new URLSearchParams({ company_id: companyId });
  if (relation) sp.set("relation", relation);
  return apiFetch<MissionGraph>(apiUrl(`${base}?${sp.toString()}`));
}

export function traceMissionNode(
  companyId: string,
  missionId: string,
  nodeType: string,
  nodeId: string,
): Promise<MissionTrace> {
  const sp = new URLSearchParams({
    company_id: companyId,
    node_type: nodeType,
    node_id: nodeId,
  });
  return apiFetch<MissionTrace>(
    apiUrl(`/missions/${missionId}/graph/trace?${sp.toString()}`),
  );
}

// Startup plans

export function fetchStartupPlans(
  companyId: string,
  missionId: string,
): Promise<StartupPlan[]> {
  return apiFetch<StartupPlan[]>(
    apiUrl(`/startup-plans?company_id=${companyId}&mission_id=${missionId}`),
  );
}

export function createStartupPlan(
  companyId: string,
  input: StartupPlanInput,
): Promise<StartupPlan> {
  return apiFetch<StartupPlan>(apiUrl(`/startup-plans?company_id=${companyId}`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getStartupPlan(
  companyId: string,
  missionId: string,
  id: string,
): Promise<StartupPlan> {
  return apiFetch<StartupPlan>(
    apiUrl(`/startup-plans/${id}?company_id=${companyId}&mission_id=${missionId}`),
  );
}

export function validateStartupPlan(
  companyId: string,
  missionId: string,
  planId: string,
): Promise<ValidationResult> {
  return apiFetch<ValidationResult>(
    apiUrl(
      `/startup-plans/${planId}/validate?company_id=${companyId}&mission_id=${missionId}`,
    ),
    { method: "POST" },
  );
}

export function approveStartupPlan(
  companyId: string,
  missionId: string,
  planId: string,
  approvedGateId?: string,
): Promise<StartupPlan> {
  const sp = new URLSearchParams({ company_id: companyId, mission_id: missionId });
  if (approvedGateId) sp.set("approved_gate_id", approvedGateId);
  return apiFetch<StartupPlan>(
    apiUrl(`/startup-plans/${planId}/approve?${sp.toString()}`),
    { method: "POST" },
  );
}

export function bootstrapStartupPlan(
  companyId: string,
  missionId: string,
  planId: string,
  approvedGateId?: string,
): Promise<Record<string, unknown>> {
  const sp = new URLSearchParams({ company_id: companyId, mission_id: missionId });
  if (approvedGateId) sp.set("approved_gate_id", approvedGateId);
  return apiFetch<Record<string, unknown>>(
    apiUrl(`/startup-plans/${planId}/bootstrap?${sp.toString()}`),
    { method: "POST" },
  );
}

export function executeStartupPlan(
  companyId: string,
  missionId: string,
  planId: string,
  approvedGateId?: string,
): Promise<OperatingCycle> {
  const sp = new URLSearchParams({ company_id: companyId, mission_id: missionId });
  if (approvedGateId) sp.set("approved_gate_id", approvedGateId);
  return apiFetch<OperatingCycle>(
    apiUrl(`/startup-plans/${planId}/execute?${sp.toString()}`),
    { method: "POST" },
  );
}

// Products

export function fetchProducts(companyId: string): Promise<Product[]> {
  return apiFetch<Product[]>(apiUrl(`/products?company_id=${companyId}`));
}

export function createProduct(input: ProductInput): Promise<Product> {
  return apiFetch<Product>(apiUrl("/products"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getProduct(companyId: string, id: string): Promise<Product> {
  return apiFetch<Product>(apiUrl(`/products/${id}?company_id=${companyId}`));
}

export function updateProduct(
  companyId: string,
  id: string,
  input: Partial<ProductInput>,
): Promise<Product> {
  return apiFetch<Product>(apiUrl(`/products/${id}?company_id=${companyId}`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function moveProductStatus(
  companyId: string,
  id: string,
  target: ProductStatus,
): Promise<Product> {
  return apiFetch<Product>(
    apiUrl(`/products/${id}/status?company_id=${companyId}`),
    { method: "POST", body: JSON.stringify({ target }) },
  );
}

export function validateProduct(
  companyId: string,
  id: string,
): Promise<ValidationResult> {
  return apiFetch<ValidationResult>(
    apiUrl(`/products/${id}/validate?company_id=${companyId}`),
    { method: "POST" },
  );
}

export function launchProduct(
  companyId: string,
  id: string,
  approvedGateId?: string,
): Promise<Product> {
  const sp = new URLSearchParams({ company_id: companyId });
  if (approvedGateId) sp.set("approved_gate_id", approvedGateId);
  return apiFetch<Product>(
    apiUrl(`/products/${id}/launch?${sp.toString()}`),
    { method: "POST" },
  );
}

// Startup projects

export function fetchStartupProjects(
  companyId: string,
  status?: string,
  productId?: string,
): Promise<StartupProject[]> {
  const sp = new URLSearchParams({ company_id: companyId });
  if (status) sp.set("status", status);
  if (productId) sp.set("product_id", productId);
  return apiFetch<StartupProject[]>(apiUrl(`/startup-projects?${sp.toString()}`));
}

export function createStartupProject(
  input: StartupProjectInput,
): Promise<StartupProject> {
  return apiFetch<StartupProject>(apiUrl("/startup-projects"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getStartupProject(
  companyId: string,
  id: string,
): Promise<StartupProject> {
  return apiFetch<StartupProject>(
    apiUrl(`/startup-projects/${id}?company_id=${companyId}`),
  );
}

export function moveStartupProjectStatus(
  companyId: string,
  id: string,
  target: StartupProjectStatus,
): Promise<StartupProject> {
  return apiFetch<StartupProject>(
    apiUrl(`/startup-projects/${id}/status?company_id=${companyId}`),
    { method: "POST", body: JSON.stringify({ target }) },
  );
}

// Operating cycles

export function runCycle(
  companyId: string,
  input: { mission_id: string; startup_plan_id?: string | null; approved_gate_id?: string | null },
): Promise<OperatingCycle> {
  return apiFetch<OperatingCycle>(apiUrl(`/startup/${companyId}/cycles`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchCycles(companyId: string, limit = 20): Promise<OperatingCycle[]> {
  return apiFetch<OperatingCycle[]>(
    apiUrl(`/startup/${companyId}/cycles?limit=${limit}`),
  );
}

export function getCycle(companyId: string, cycleId: string): Promise<OperatingCycle> {
  return apiFetch<OperatingCycle>(
    apiUrl(`/startup/${companyId}/cycles/${cycleId}`),
  );
}

export function resumeCycle(
  companyId: string,
  cycleId: string,
  approvedGateId?: string,
): Promise<OperatingCycle> {
  return apiFetch<OperatingCycle>(
    apiUrl(`/startup/${companyId}/cycles/${cycleId}/execute`),
    { method: "POST", body: JSON.stringify({ approved_gate_id: approvedGateId ?? null }) },
  );
}

export function approveCycleGate(
  companyId: string,
  cycleId: string,
): Promise<OperatingCycle> {
  return apiFetch<OperatingCycle>(
    apiUrl(`/startup/${companyId}/cycles/${cycleId}/approve`),
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function cancelCycle(companyId: string, cycleId: string): Promise<OperatingCycle> {
  return apiFetch<OperatingCycle>(
    apiUrl(`/startup/${companyId}/cycles/${cycleId}/cancel`),
    { method: "POST" },
  );
}

// State / replan / next actions

export function fetchCompanyState(
  companyId: string,
  persist = false,
): Promise<CompanyStateSnapshot> {
  return apiFetch<CompanyStateSnapshot>(
    apiUrl(`/startup/${companyId}/state?persist=${persist}`),
  );
}

export function fetchStateHistory(
  companyId: string,
  limit = 20,
): Promise<CompanyStateSnapshot[]> {
  return apiFetch<CompanyStateSnapshot[]>(
    apiUrl(`/startup/${companyId}/state/history?limit=${limit}`),
  );
}

export function replanCompany(
  companyId: string,
  opts?: { trigger?: string; apply?: boolean; approvedGateId?: string },
): Promise<ReplanAction> {
  const sp = new URLSearchParams();
  if (opts?.trigger) sp.set("trigger", opts.trigger);
  if (opts?.apply) sp.set("apply", "true");
  if (opts?.approvedGateId) sp.set("approved_gate_id", opts.approvedGateId);
  const query = sp.toString();
  return apiFetch<ReplanAction>(
    apiUrl(`/startup/${companyId}/replan${query ? `?${query}` : ""}`),
    { method: "POST" },
  );
}

export function fetchNextActions(companyId: string): Promise<NextActions> {
  return apiFetch<NextActions>(apiUrl(`/startup/${companyId}/next-actions`));
}

// Feedback

export function fetchFeedback(
  companyId: string,
  category?: string,
  limit = 50,
): Promise<StartupFeedback[]> {
  const sp = new URLSearchParams({ limit: String(limit) });
  if (category) sp.set("category", category);
  return apiFetch<StartupFeedback[]>(
    apiUrl(`/startup/${companyId}/feedback?${sp.toString()}`),
  );
}

export function createFeedback(
  companyId: string,
  input: StartupFeedbackInput,
): Promise<StartupFeedback> {
  return apiFetch<StartupFeedback>(apiUrl(`/startup/${companyId}/feedback`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// Autonomy + approval gates

export function fetchAutonomyPolicy(companyId: string): Promise<AutonomyPolicy> {
  return apiFetch<AutonomyPolicy>(apiUrl(`/autonomy/${companyId}/policy`));
}

export function updateAutonomyPolicy(
  companyId: string,
  input: AutonomyPolicyInput,
): Promise<AutonomyPolicy> {
  return apiFetch<AutonomyPolicy>(apiUrl(`/autonomy/${companyId}/policy`), {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function fetchApprovalGates(
  companyId: string,
  status?: string,
): Promise<ApprovalGate[]> {
  const sp = new URLSearchParams();
  if (status) sp.set("status", status);
  const query = sp.toString();
  return apiFetch<ApprovalGate[]>(
    apiUrl(`/autonomy/${companyId}/approval-gates${query ? `?${query}` : ""}`),
  );
}

export function fetchPendingApprovalGates(companyId: string): Promise<ApprovalGate[]> {
  return apiFetch<ApprovalGate[]>(
    apiUrl(`/autonomy/${companyId}/approval-gates/pending`),
  );
}

export function approveApprovalGate(
  companyId: string,
  gateId: string,
  approverId?: string,
  rationale?: string,
): Promise<ApprovalGate> {
  return apiFetch<ApprovalGate>(
    apiUrl(`/autonomy/${companyId}/approval-gates/${gateId}/approve`),
    { method: "POST", body: JSON.stringify({ approver_id: approverId ?? null, rationale: rationale ?? null }) },
  );
}

export function rejectApprovalGate(
  companyId: string,
  gateId: string,
  approverId?: string,
  rationale?: string,
): Promise<ApprovalGate> {
  return apiFetch<ApprovalGate>(
    apiUrl(`/autonomy/${companyId}/approval-gates/${gateId}/reject`),
    { method: "POST", body: JSON.stringify({ approver_id: approverId ?? null, rationale: rationale ?? null }) },
  );
}
// ── Phase 10: External Integrations ------------------------------

export function fetchIntegrations(
  companyId: string,
): Promise<ExternalIntegration[]> {
  return apiFetch<ExternalIntegration[]>(apiUrl(`/integrations/${companyId}`));
}

export function createIntegration(
  companyId: string,
  input: { provider: string; name: string; description?: string },
): Promise<ExternalIntegration> {
  return apiFetch<ExternalIntegration>(apiUrl(`/integrations/${companyId}`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchIntegration(
  companyId: string,
  integrationId: string,
): Promise<ExternalIntegration> {
  return apiFetch<ExternalIntegration>(
    apiUrl(`/integrations/${companyId}/${integrationId}`),
  );
}

export function deleteIntegration(
  companyId: string,
  integrationId: string,
): Promise<void> {
  return apiFetch<void>(apiUrl(`/integrations/${companyId}/${integrationId}`), {
    method: "DELETE",
  });
}

export function fetchCapabilities(
  companyId: string,
  integrationId: string,
): Promise<IntegrationCapability[]> {
  return apiFetch<IntegrationCapability[]>(
    apiUrl(`/integrations/${companyId}/${integrationId}/capabilities`),
  );
}

export function createConnection(
  companyId: string,
  integrationId: string,
  input: {
    auth_method?: string;
    secret_value?: string;
    env_var_hint?: string;
    scopes?: string[];
    permissions?: string[];
  },
): Promise<IntegrationConnection> {
  return apiFetch<IntegrationConnection>(
    apiUrl(`/integrations/${companyId}/${integrationId}/connections`),
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function fetchConnections(
  companyId: string,
  integrationId: string,
): Promise<IntegrationConnection[]> {
  return apiFetch<IntegrationConnection[]>(
    apiUrl(`/integrations/${companyId}/${integrationId}/connections`),
  );
}

export function testConnection(
  companyId: string,
  integrationId: string,
  connectionId: string,
): Promise<ConnectionTestResponse> {
  return apiFetch<ConnectionTestResponse>(
    apiUrl(
      `/integrations/${companyId}/${integrationId}/connections/${connectionId}/test`,
    ),
    { method: "POST" },
  );
}

export function revokeConnection(
  companyId: string,
  integrationId: string,
  connectionId: string,
): Promise<IntegrationConnection> {
  return apiFetch<IntegrationConnection>(
    apiUrl(
      `/integrations/${companyId}/${integrationId}/connections/${connectionId}/revoke`,
    ),
    { method: "POST" },
  );
}

export function fetchIntegrationPolicies(
  companyId: string,
): Promise<ExternalIntegrationPolicy[]> {
  return apiFetch<ExternalIntegrationPolicy[]>(
    apiUrl(`/integrations/${companyId}/policies`),
  );
}

export function fetchDomainRules(
  companyId: string,
): Promise<ExternalDomainRule[]> {
  return apiFetch<ExternalDomainRule[]>(
    apiUrl(`/integrations/${companyId}/domains`),
  );
}

// ── External actions journal ------------------------------

export function createExternalAction(
  companyId: string,
  input: {
    integration_id: string;
    capability: string;
    action_type?: string;
    payload?: Record<string, unknown>;
    connection_id?: string;
    idempotency_key?: string;
    employee_id?: string;
    approved_gate_id?: string;
  },
): Promise<ExternalAction> {
  return apiFetch<ExternalAction>(apiUrl(`/external-actions/${companyId}`), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchExternalActions(
  companyId: string,
): Promise<ExternalAction[]> {
  return apiFetch<ExternalAction[]>(apiUrl(`/external-actions/${companyId}`));
}

export function fetchExternalAction(
  companyId: string,
  actionId: string,
): Promise<ExternalAction> {
  return apiFetch<ExternalAction>(
    apiUrl(`/external-actions/${companyId}/${actionId}`),
  );
}

export function cancelExternalAction(
  companyId: string,
  actionId: string,
): Promise<ExternalAction> {
  return apiFetch<ExternalAction>(
    apiUrl(`/external-actions/${companyId}/${actionId}/cancel`),
    { method: "POST" },
  );
}

export function fetchExternalDashboard(
  companyId: string,
): Promise<ExternalDashboard> {
  return apiFetch<ExternalDashboard>(
    apiUrl(`/external-actions/${companyId}/dashboard`),
  );
}

// ── External events ------------------------------

export function fetchExternalEvents(
  companyId: string,
): Promise<ExternalEvent[]> {
  return apiFetch<ExternalEvent[]>(apiUrl(`/external-events/${companyId}`));
}

// ── Browser sessions ------------------------------

export function fetchBrowserSessions(
  companyId: string,
): Promise<BrowserSession[]> {
  return apiFetch<BrowserSession[]>(
    apiUrl(`/browser/sessions/${companyId}`),
  );
}

export function createBrowserSession(
  companyId: string,
  input?: { allowed_domains?: string[] },
): Promise<BrowserSession> {
  return apiFetch<BrowserSession>(apiUrl(`/browser/sessions/${companyId}`), {
    method: "POST",
    body: JSON.stringify(input ?? {}),
  });
}

export function fetchBrowserSession(
  companyId: string,
  sessionId: string,
): Promise<BrowserSession> {
  return apiFetch<BrowserSession>(
    apiUrl(`/browser/sessions/${companyId}/${sessionId}`),
  );
}

export function runBrowserAction(
  companyId: string,
  sessionId: string,
  input: {
    action_type: string;
    target?: Record<string, unknown>;
    input?: Record<string, unknown>;
    approved_gate_id?: string;
  },
): Promise<BrowserAction> {
  return apiFetch<BrowserAction>(
    apiUrl(`/browser/sessions/${companyId}/${sessionId}/actions`),
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function pauseBrowserSession(
  companyId: string,
  sessionId: string,
): Promise<BrowserSession> {
  return apiFetch<BrowserSession>(
    apiUrl(`/browser/sessions/${companyId}/${sessionId}/pause`),
    { method: "POST" },
  );
}

export function terminateBrowserSession(
  companyId: string,
  sessionId: string,
): Promise<BrowserSession> {
  return apiFetch<BrowserSession>(
    apiUrl(`/browser/sessions/${companyId}/${sessionId}/terminate`),
    { method: "POST" },
  );
}

export function fetchBrowserObservations(
  companyId: string,
  sessionId: string,
): Promise<BrowserObservation[]> {
  return apiFetch<BrowserObservation[]>(
    apiUrl(`/browser/sessions/${companyId}/${sessionId}/observations`),
  );
}

// ── Computer sessions ------------------------------

export function fetchComputerSessions(
  companyId: string,
): Promise<ComputerSession[]> {
  return apiFetch<ComputerSession[]>(
    apiUrl(`/computer/sessions/${companyId}`),
  );
}

export function createComputerSession(
  companyId: string,
): Promise<ComputerSession> {
  return apiFetch<ComputerSession>(apiUrl(`/computer/sessions/${companyId}`), {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function fetchComputerSession(
  companyId: string,
  sessionId: string,
): Promise<ComputerSession> {
  return apiFetch<ComputerSession>(
    apiUrl(`/computer/sessions/${companyId}/${sessionId}`),
  );
}

export function runComputerAction(
  companyId: string,
  sessionId: string,
  input: {
    action_type: string;
    input?: Record<string, unknown>;
    approved_gate_id?: string;
  },
): Promise<ComputerAction> {
  return apiFetch<ComputerAction>(
    apiUrl(`/computer/sessions/${companyId}/${sessionId}/actions`),
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function pauseComputerSession(
  companyId: string,
  sessionId: string,
): Promise<ComputerSession> {
  return apiFetch<ComputerSession>(
    apiUrl(`/computer/sessions/${companyId}/${sessionId}/pause`),
    { method: "POST" },
  );
}

export function terminateComputerSession(
  companyId: string,
  sessionId: string,
): Promise<ComputerSession> {
  return apiFetch<ComputerSession>(
    apiUrl(`/computer/sessions/${companyId}/${sessionId}/terminate`),
    { method: "POST" },
  );
}

export function fetchComputerObservations(
  companyId: string,
  sessionId: string,
): Promise<ComputerObservation[]> {
  return apiFetch<ComputerObservation[]>(
    apiUrl(`/computer/sessions/${companyId}/${sessionId}/observations`),
  );
}

// ── Phase 11: Security, Governance & Production Hardening ───────────────────

/** apiFetch variant that attaches the stored bearer token when one exists. */
async function apiFetchAuthorized<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const { getAccessToken } = await import("@/lib/auth");
  const token = getAccessToken();
  return apiFetch<T>(path, {
    ...init,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
}

function qs(params: Record<string, string | number | null | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

// --- Auth (login is the only token-free call; session requires a token) ---

export function login(input: {
  email: string;
  password: string;
}): Promise<SessionResult> {
  return apiFetch<SessionResult>(apiUrl("/auth/login"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function logout(refreshToken: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(apiUrl("/auth/logout"), {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function refreshSession(refreshToken: string): Promise<SessionResult> {
  return apiFetch<SessionResult>(apiUrl("/auth/refresh"), {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function fetchAuthSession(): Promise<AuthSessionResponse> {
  return apiFetchAuthorized<AuthSessionResponse>(apiUrl("/auth/session"));
}

// --- Access: users, roles, permissions, secrets (refs only) ---

export function fetchAccessUsers(): Promise<UserPublic[]> {
  return apiFetchAuthorized<UserPublic[]>(apiUrl("/access/users"));
}

export function createAccessUser(input: UserCreateInput): Promise<UserPublic> {
  return apiFetchAuthorized<UserPublic>(apiUrl("/access/users"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function assignUserRoles(userId: string, roles: string[]): Promise<UserPublic> {
  return apiFetchAuthorized<UserPublic>(
    apiUrl(`/access/users/${userId}/roles`),
    { method: "POST", body: JSON.stringify({ roles }) },
  );
}

export function fetchAccessRoles(): Promise<RolePublic[]> {
  return apiFetchAuthorized<RolePublic[]>(apiUrl("/access/roles"));
}

export function fetchAccessPermissions(): Promise<PermissionPublic[]> {
  return apiFetchAuthorized<PermissionPublic[]>(apiUrl("/access/permissions"));
}

export function fetchSecrets(): Promise<SecretReference[]> {
  return apiFetchAuthorized<SecretReference[]>(apiUrl("/access/secrets"));
}

export function createSecret(input: SecretCreateInput): Promise<SecretReference> {
  return apiFetchAuthorized<SecretReference>(apiUrl("/access/secrets"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function revokeSecret(secretId: string): Promise<void> {
  return apiFetchAuthorized<void>(apiUrl(`/access/secrets/${secretId}`), {
    method: "DELETE",
  });
}

// --- Security events, alerts, audit ---

export function fetchSecurityEvents(params: {
  category?: string | null;
  companyId?: string | null;
  limit?: number;
} = {}): Promise<SecurityEventPublic[]> {
  return apiFetchAuthorized<SecurityEventPublic[]>(
    apiUrl(`/security/events${qs({ category: params.category, company_id: params.companyId, limit: params.limit })}`),
  );
}

export function fetchSecurityAlerts(params: {
  companyId?: string | null;
} = {}): Promise<SecurityAlertPublic[]> {
  return apiFetchAuthorized<SecurityAlertPublic[]>(
    apiUrl(`/security/alerts${qs({ company_id: params.companyId })}`),
  );
}

export function acknowledgeSecurityAlert(
  alertId: string,
): Promise<SecurityAlertPublic> {
  return apiFetchAuthorized<SecurityAlertPublic>(
    apiUrl(`/security/alerts/${alertId}/acknowledge`),
    { method: "POST" },
  );
}

export function resolveSecurityAlert(
  alertId: string,
  resolution?: string,
): Promise<SecurityAlertPublic> {
  return apiFetchAuthorized<SecurityAlertPublic>(
    apiUrl(`/security/alerts/${alertId}/resolve`),
    {
      method: "POST",
      body: JSON.stringify(resolution ? { resolution } : {}),
    },
  );
}

export function fetchAuditEvents(params: {
  companyId?: string | null;
  limit?: number;
} = {}): Promise<AuditEventPublic[]> {
  return apiFetchAuthorized<AuditEventPublic[]>(
    apiUrl(`/security/audit${qs({ company_id: params.companyId, limit: params.limit })}`),
  );
}

export function verifyAuditChain(): Promise<AuditChainVerify> {
  return apiFetchAuthorized<AuditChainVerify>(apiUrl("/security/audit/verify"));
}

// --- Incidents ---

export function fetchIncidents(params: {
  status?: string | null;
  companyId?: string | null;
  limit?: number;
} = {}): Promise<IncidentPublic[]> {
  return apiFetchAuthorized<IncidentPublic[]>(
    apiUrl(`/security/incidents${qs({ status: params.status, company_id: params.companyId, limit: params.limit })}`),
  );
}

export function fetchIncident(id: string): Promise<IncidentDetailPublic> {
  return apiFetchAuthorized<IncidentDetailPublic>(
    apiUrl(`/security/incidents/${id}`),
  );
}

export function createIncident(input: IncidentCreateInput): Promise<IncidentPublic> {
  return apiFetchAuthorized<IncidentPublic>(apiUrl("/security/incidents"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function transitionIncident(
  incidentId: string,
  input: IncidentTransitionInput,
): Promise<IncidentPublic> {
  return apiFetchAuthorized<IncidentPublic>(
    apiUrl(`/security/incidents/${incidentId}/transition`),
    { method: "POST", body: JSON.stringify(input) },
  );
}

export function executeIncidentAction(
  incidentId: string,
  input: IncidentActionInput,
): Promise<IncidentActionPublic> {
  return apiFetchAuthorized<IncidentActionPublic>(
    apiUrl(`/security/incidents/${incidentId}/actions`),
    { method: "POST", body: JSON.stringify(input) },
  );
}

// --- Governance: kill switch, policies, limits, resources, break-glass ---

export function fetchSystemFlags(): Promise<SystemFlagPublic[]> {
  return apiFetchAuthorized<SystemFlagPublic[]>(apiUrl("/governance/flags"));
}

export function pauseScope(
  scope: string,
  reason?: string | null,
  companyId?: string | null,
): Promise<SystemFlagPublic> {
  return apiFetchAuthorized<SystemFlagPublic>(
    apiUrl(`/governance/flags/${scope}/pause`),
    {
      method: "POST",
      body: JSON.stringify({
        flag: `${scope}_paused`,
        reason,
        tenant_id: companyId ?? undefined,
      }),
    },
  );
}

export function resumeScope(scope: string): Promise<SystemFlagPublic> {
  return apiFetchAuthorized<SystemFlagPublic>(
    apiUrl(`/governance/flags/${scope}/resume`),
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function fetchPolicyRules(): Promise<PolicyRulePublic[]> {
  return apiFetchAuthorized<PolicyRulePublic[]>(apiUrl("/governance/policies"));
}

export function createPolicyRule(input: PolicyRuleInput): Promise<PolicyRulePublic> {
  return apiFetchAuthorized<PolicyRulePublic>(apiUrl("/governance/policies"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchPolicyDecisions(): Promise<PolicyDecisionPublic[]> {
  return apiFetchAuthorized<PolicyDecisionPublic[]>(apiUrl("/governance/policy-decisions"));
}

export function fetchResourceLimits(): Promise<ResourceLimitPublic[]> {
  return apiFetchAuthorized<ResourceLimitPublic[]>(apiUrl("/governance/limits"));
}

export function setResourceLimit(input: ResourceLimitInput): Promise<ResourceLimitPublic> {
  return apiFetchAuthorized<ResourceLimitPublic>(apiUrl("/governance/limits"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchResourceUsage(): Promise<ResourceUsagePublic[]> {
  return apiFetchAuthorized<ResourceUsagePublic[]>(apiUrl("/governance/resources/usage"));
}

export function fetchGovernanceControls(): Promise<GovernanceControlPublic[]> {
  return apiFetchAuthorized<GovernanceControlPublic[]>(apiUrl("/governance/controls"));
}

export function activateBreakGlass(input: BreakGlassInput): Promise<BreakGlassPublic> {
  return apiFetchAuthorized<BreakGlassPublic>(apiUrl("/governance/break-glass"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchBreakGlass(): Promise<BreakGlassPublic[]> {
  return apiFetchAuthorized<BreakGlassPublic[]>(apiUrl("/governance/break-glass"));
}

// --- Data governance: classification, transfer check, retention ---

export function fetchClassifications(): Promise<DataClassificationPublic[]> {
  return apiFetchAuthorized<DataClassificationPublic[]>(apiUrl("/data/classifications"));
}

export function setClassification(input: DataClassificationInput): Promise<DataClassificationPublic> {
  return apiFetchAuthorized<DataClassificationPublic>(apiUrl("/data/classifications"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function checkTransfer(input: TransferCheckInput): Promise<TransferDecisionPublic> {
  return apiFetchAuthorized<TransferDecisionPublic>(apiUrl("/data/transfer-check"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchRetentionPolicies(): Promise<RetentionPolicyPublic[]> {
  return apiFetchAuthorized<RetentionPolicyPublic[]>(apiUrl("/data/retention"));
}

export function setRetentionPolicy(input: RetentionPolicyInput): Promise<RetentionPolicyPublic> {
  return apiFetchAuthorized<RetentionPolicyPublic>(apiUrl("/data/retention"), {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// --- System: health, metrics, feature flags ---

export async function fetchHealthProbe(kind: "live" | "ready" | "dependencies"): Promise<SystemHealthProbe> {
  return apiFetchAuthorized<SystemHealthProbe>(
    apiUrl(`/system/health/${kind}`),
  );
}

export async function fetchHealthOverview(): Promise<HealthOverview> {
  return apiFetchAuthorized<HealthOverview>(apiUrl("/system/health/overview"));
}

export async function fetchMetricSnapshot(): Promise<MetricsSnapshot> {
  return apiFetchAuthorized<MetricsSnapshot>(apiUrl("/system/metrics"));
}

export function fetchFeatureFlags(): Promise<FeatureFlagPublic[]> {
  return apiFetchAuthorized<FeatureFlagPublic[]>(apiUrl("/system/feature-flags"));
}

export function setFeatureFlag(
  name: string,
  input: FeatureFlagInput,
): Promise<FeatureFlagPublic> {
  return apiFetchAuthorized<FeatureFlagPublic>(apiUrl("/system/feature-flags"), {
    method: "POST",
    body: JSON.stringify({ name, ...input }),
  });
}

export function fetchHealthRecords(): Promise<SystemHealthRecordPublic[]> {
  return apiFetchAuthorized<SystemHealthRecordPublic[]>(apiUrl("/system/health-records"));
}
