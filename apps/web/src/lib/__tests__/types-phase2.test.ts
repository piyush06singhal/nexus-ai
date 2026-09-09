import { describe, it, expect } from "vitest";
import type { ToolDefinition, ToolCallRecord } from "@/lib/types";

describe("Phase 2: tool types", () => {
  it("accepts a ToolDefinition", () => {
    const tool: ToolDefinition = {
      name: "calculator",
      description: "Evaluates math expressions.",
      parameters: [
        {
          name: "expression",
          type: "string",
          description: "Math expression to evaluate.",
          required: true,
          default: null,
          enum: null,
        },
      ],
      dangerous: false,
      timeout_seconds: 5,
      tags: ["math"],
    };
    expect(tool.name).toBe("calculator");
    expect(tool.parameters.length).toBe(1);
  });

  it("accepts a ToolCallRecord", () => {
    const call: ToolCallRecord = {
      id: "c1",
      execution_id: "e1",
      tool_name: "calculator",
      arguments: { expression: "2 + 2" },
      result_status: "success",
      result_data: { result: 4 },
      result_error: null,
      execution_time_ms: 12.3,
      iteration: 1,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(call.result_status).toBe("success");
  });
});
