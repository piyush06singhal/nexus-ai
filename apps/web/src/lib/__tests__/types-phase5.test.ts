import { describe, it, expect } from "vitest";
import type {
  AgentAssignment,
  AgentMessage,
  Orchestration,
  OrchestrationTask,
} from "@/lib/types";

describe("Phase 5 orchestration types", () => {
  it("accepts an Orchestration", () => {
    const orch: Orchestration = {
      id: "o1",
      objective: "analyze the competitive market and write a report",
      status: "completed",
      strategy: "deterministic",
      selected_agents: ["a1", "a2", "a3", "a4"],
      execution_graph: { objective: "x", tasks: [] },
      final_result: {
        status: "completed",
        summary: "Market analysis with attribution.",
        findings: [],
        sources: [],
        conflicts: [],
        incomplete_tasks: [],
      },
      error: null,
      metrics: { tasks_total: 4, tasks_completed: 4 },
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:02Z",
      duration_ms: 2000,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:02Z",
    };
    expect(orch.status).toBe("completed");
    expect(orch.selected_agents?.length).toBe(4);
  });

  it("accepts an OrchestrationTask with capabilities and deps", () => {
    const task: OrchestrationTask = {
      id: "t1",
      orchestration_id: "o1",
      name: "research",
      description: "Compile market data",
      required_capabilities: ["research"],
      dependencies: [],
      status: "completed",
      agent_id: "a1",
      input_context: { objective: "x" },
      output_data: { market_size: 100 },
      result_summary: "compiled",
      attempt_number: 1,
      error: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
      duration_ms: 1000,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(task.required_capabilities).toEqual(["research"]);
    expect(task.status).toBe("completed");
  });

  it("accepts an AgentAssignment", () => {
    const assignment: AgentAssignment = {
      id: "as1",
      orchestration_id: "o1",
      task_id: "t1",
      agent_id: "a1",
      role: "researcher",
      instructions: "Gather data.",
      priority: 1,
      dependencies: [],
      status: "completed",
      input_context: null,
      output_data: { data: 1 },
      error: null,
      attempt_number: 1,
      agent_execution_id: "e1",
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
    };
    expect(assignment.role).toBe("researcher");
    expect(assignment.status).toBe("completed");
  });

  it("accepts an AgentMessage with correlation id", () => {
    const msg: AgentMessage = {
      id: "m1",
      orchestration_id: "o1",
      sender_agent_id: "a2",
      recipient_agent_id: "a4",
      message_type: "request_information",
      content: "Please share growth figures",
      metadata: null,
      correlation_id: "c1",
      task_id: "t2",
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(msg.message_type).toBe("request_information");
    expect(msg.correlation_id).toBe("c1");
  });
});