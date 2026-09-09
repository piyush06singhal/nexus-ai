import { describe, it, expect } from "vitest";
import type { Agent, Task, AgentExecution } from "@/lib/types";

describe("Phase 1 agent runtime types", () => {
  it("accepts an Agent", () => {
    const agent: Agent = {
      id: "a1",
      name: "analyst",
      role: "analyst",
      description: null,
      status: "active",
      system_prompt: "Be precise.",
      provider: "openai",
      model_name: "gpt-4o",
      temperature: 0.5,
      max_tokens: 1024,
      model_params: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(agent.status).toBe("active");
    expect(agent.name).toBe("analyst");
  });

  it("accepts a Task", () => {
    const task: Task = {
      id: "t1",
      title: "Build report",
      description: null,
      input_data: { quarter: "Q1" },
      status: "queued",
      assigned_agent_id: "a1",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      executed_at: null,
    };
    expect(task.status).toBe("queued");
    expect(task.assigned_agent_id).toBe("a1");
  });

  it("accepts a completed execution result", () => {
    const execution: AgentExecution = {
      id: "e1",
      task_id: "t1",
      agent_id: "a1",
      status: "succeeded",
      input_data: { query: "x" },
      output_data: { summary: "done" },
      error: null,
      provider: "mock",
      model_name: "mock-model",
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
      estimated_cost: 0.0,
      latency_ms: 40.2,
      created_at: "2026-01-01T00:00:00Z",
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
    };
    expect(execution.status).toBe("succeeded");
    expect(execution.total_tokens).toBe(15);
  });
});