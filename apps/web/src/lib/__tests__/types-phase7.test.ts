import { describe, it, expect } from "vitest";
import type {
  AssignmentResult,
  Employee,
  EmployeeAuditEntry,
  EmployeeAvailability,
  EmployeeBudget,
  EmployeeGoal,
  EmployeePerformance,
  EmployeeReview,
  EmployeeSkill,
  EmployeeStatus,
  EmployeeTemplate,
  EmployeeTimelineEvent,
  EmployeeWorkload,
  GoalStatus,
  WorkforceOverview,
} from "@/lib/types";

describe("Phase 7 AI Employee OS types", () => {
  it("accepts EmployeeStatus union values", () => {
    const statuses: EmployeeStatus[] = [
      "draft",
      "active",
      "paused",
      "busy",
      "on_leave",
      "suspended",
      "terminated",
    ];
    expect(statuses).toHaveLength(7);
    expect(statuses).toContain("active");
    expect(statuses).toContain("terminated");
  });

  it("accepts EmployeeAvailability union values", () => {
    const avail: EmployeeAvailability[] = [
      "available",
      "busy",
      "unavailable",
      "paused",
      "on_leave",
      "suspended",
      "terminated",
    ];
    expect(avail).toHaveLength(7);
    expect(avail).toContain("available");
  });

  it("accepts GoalStatus union values", () => {
    const statuses: GoalStatus[] = [
      "not_started",
      "active",
      "at_risk",
      "completed",
      "failed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(6);
    expect(statuses).toContain("at_risk");
  });

  it("accepts an Employee with full profile", () => {
    const emp: Employee = {
      id: "emp-1",
      name: "research-analyst",
      display_name: "Alex",
      description: "Senior research analyst",
      role: "analyst",
      department: "research",
      status: "active",
      availability: "available",
      agent_id: "agent-1",
      skills: [
        {
          skill_id: "s1",
          name: "research",
          category: "core",
          proficiency: 0.85,
          confidence: 0.9,
          evidence_count: 12,
        },
      ],
      responsibilities: ["Analyze data", "Write reports"],
      goals: [],
      tools: ["web_search", "calculator"],
      permissions: ["read_files"],
      memory_namespace: "employee:research-analyst",
      work_preferences: null,
      workload_config: { max_concurrent: 3 },
      performance_profile: null,
      policies: { max_retries: 3 },
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(emp.status).toBe("active");
    expect(emp.skills).toHaveLength(1);
    expect(emp.skills![0].proficiency).toBeCloseTo(0.85);
  });

  it("accepts an Employee with null optional fields", () => {
    const emp: Employee = {
      id: "emp-2",
      name: "minimal",
      display_name: "Minimal",
      description: null,
      role: "general",
      department: null,
      status: "draft",
      availability: "unavailable",
      agent_id: null,
      skills: null,
      responsibilities: null,
      goals: null,
      tools: null,
      permissions: null,
      memory_namespace: null,
      work_preferences: null,
      workload_config: null,
      performance_profile: null,
      policies: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(emp.status).toBe("draft");
    expect(emp.skills).toBeNull();
  });

  it("accepts an EmployeeGoal", () => {
    const goal: EmployeeGoal = {
      id: "g1",
      employee_id: "emp-1",
      title: "Improve response quality",
      description: "Reach 95% quality score",
      priority: 1,
      target: "95% quality",
      metric: "average_quality",
      deadline: "2026-06-01T00:00:00Z",
      status: "active",
      progress: 0.6,
      parent_goal_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(goal.status).toBe("active");
    expect(goal.progress).toBe(0.6);
  });

  it("accepts EmployeeWorkload", () => {
    const wl: EmployeeWorkload = {
      employee_id: "emp-1",
      active_tasks: 2,
      queued_tasks: 1,
      completed_tasks: 10,
      failed_tasks: 1,
      capacity: 5,
      utilization: 0.4,
      available_slots: 3,
    };
    expect(wl.utilization).toBe(0.4);
    expect(wl.available_slots).toBe(3);
  });

  it("accepts EmployeePerformance", () => {
    const perf: EmployeePerformance = {
      employee_id: "emp-1",
      tasks_completed: 42,
      tasks_failed: 3,
      success_rate: 0.933,
      verification_pass_rate: 0.85,
      average_quality: 0.87,
      recovery_rate: 0.5,
      average_latency_ms: 1200,
      total_cost: 15.5,
      total_tokens: 125000,
      utilization: 0.65,
      deadline_adherence: 0.9,
      period_start: "2026-01-01T00:00:00Z",
      period_end: null,
    };
    expect(perf.tasks_completed).toBe(42);
    expect(perf.success_rate).toBeCloseTo(0.933);
  });

  it("accepts EmployeeTemplate", () => {
    const tpl: EmployeeTemplate = {
      id: "t1",
      name: "research-analyst",
      description: "Standard research analyst template",
      role: "analyst",
      skills: [{ name: "research", proficiency: 0.7 }],
      responsibilities: ["Research", "Report"],
      tools: ["web_search"],
      policies: null,
      verification_policy: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(tpl.role).toBe("analyst");
    expect(tpl.skills).toHaveLength(1);
  });

  it("accepts EmployeeTimelineEvent", () => {
    const evt: EmployeeTimelineEvent = {
      event_id: "evt-1",
      employee_id: "emp-1",
      event_type: "activated",
      description: "activated by system",
      timestamp: "2026-01-01T00:00:00Z",
      outcome: "success",
    };
    expect(evt.event_type).toBe("activated");
  });

  it("accepts EmployeeAuditEntry", () => {
    const entry: EmployeeAuditEntry = {
      id: "audit-1",
      actor: "system",
      action: "task_assigned",
      target_type: "task",
      target_id: "task-1",
      details: { score: 0.85 },
      outcome: "success",
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(entry.action).toBe("task_assigned");
    expect(entry.details?.score).toBe(0.85);
  });

  it("accepts WorkforceOverview", () => {
    const overview: WorkforceOverview = {
      total_employees: 5,
      active_employees: 3,
      by_status: { active: 2, busy: 1, draft: 1, terminated: 1 },
    };
    expect(overview.total_employees).toBe(5);
    expect(overview.by_status.active).toBe(2);
  });

  it("accepts AssignmentResult", () => {
    const result: AssignmentResult = {
      success: true,
      employee_id: "emp-1",
      employee_name: "Alex",
      score: 0.87,
      reasoning: "skill_match=0.95(research); workload=0.80; role=1.00; perf=0.50",
      candidates_evaluated: 3,
    };
    expect(result.success).toBe(true);
    expect(result.score).toBeCloseTo(0.87);
  });

  it("accepts EmployeeReview", () => {
    const review: EmployeeReview = {
      id: "rev-1",
      employee_id: "emp-1",
      period_start: "2026-01-01T00:00:00Z",
      period_end: "2026-01-31T00:00:00Z",
      metrics: { quality: 0.9, latency: 1200 },
      strengths: ["Fast response", "High quality"],
      weaknesses: ["High cost"],
      skill_changes: [],
      recommendations: ["Reduce token usage"],
      reviewer: "system",
      created_at: "2026-02-01T00:00:00Z",
    };
    expect(review.strengths).toHaveLength(2);
    expect(review.reviewer).toBe("system");
  });

  it("accepts EmployeeBudget", () => {
    const budget: EmployeeBudget = {
      id: "b1",
      employee_id: "emp-1",
      monthly_limit: 50.0,
      task_limit: null,
      tokens_used: 25000,
      cost_used: 12.5,
      tool_calls_used: 45,
      period_start: "2026-01-01T00:00:00Z",
      period_end: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(budget.monthly_limit).toBe(50.0);
    expect(budget.cost_used).toBe(12.5);
  });

  it("accepts EmployeeSkill", () => {
    const skill: EmployeeSkill = {
      skill_id: "s1",
      name: "python",
      category: "technical",
      proficiency: 0.9,
      confidence: 0.85,
      evidence_count: 15,
    };
    expect(skill.proficiency).toBe(0.9);
    expect(skill.evidence_count).toBe(15);
  });
});
