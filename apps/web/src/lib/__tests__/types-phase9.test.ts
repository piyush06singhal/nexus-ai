import { describe, it, expect } from "vitest";
import type {
  ApprovalGate,
  ApprovalGateStatus,
  ApprovalGateType,
  AutonomyLevel,
  AutonomyPolicy,
  CompanyStateSnapshot,
  CycleStage,
  ExecutionPlanStatus,
  Lesson,
  LessonType,
  Mission,
  MissionGraph,
  MissionGraphEdge,
  MissionGraphRelation,
  MissionStatus,
  OperatingCycle,
  OperatingCycleStatus,
  Product,
  ProductStatus,
  StartupFeedback,
  StartupPlan,
  StartupPlanStatus,
  StartupProject,
  StartupProjectStatus,
  StrategicPlanStatus,
} from "@/lib/types";

describe("Phase 9 Autonomous Startup Engine types", () => {
  it("accepts all MissionStatus values", () => {
    const statuses: MissionStatus[] = [
      "draft",
      "analyzing",
      "planned",
      "active",
      "paused",
      "blocked",
      "completed",
      "failed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(9);
    expect(statuses).toContain("analyzing");
    expect(statuses).toContain("blocked");
  });

  it("accepts all StrategicPlanStatus values", () => {
    const statuses: StrategicPlanStatus[] = [
      "draft",
      "active",
      "superseded",
      "cancelled",
    ];
    expect(statuses).toHaveLength(4);
    expect(statuses).toContain("superseded");
  });

  it("accepts all StartupPlanStatus values", () => {
    const statuses: StartupPlanStatus[] = [
      "draft",
      "under_review",
      "approved",
      "bootstrapping",
      "active",
      "paused",
      "completed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(8);
    expect(statuses).toContain("under_review");
    expect(statuses).toContain("bootstrapping");
  });

  it("accepts all ProductStatus values", () => {
    const statuses: ProductStatus[] = [
      "idea",
      "discovery",
      "validation",
      "planning",
      "building",
      "testing",
      "ready_for_launch",
      "launched",
      "measuring",
      "iterating",
      "paused",
      "retired",
    ];
    expect(statuses).toHaveLength(12);
    expect(statuses).toContain("ready_for_launch");
  });

  it("accepts all StartupProjectStatus values", () => {
    const statuses: StartupProjectStatus[] = [
      "planned",
      "active",
      "blocked",
      "completed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(5);
    expect(statuses).toContain("blocked");
  });

  it("accepts all ExecutionPlanStatus values", () => {
    const statuses: ExecutionPlanStatus[] = [
      "draft",
      "ready",
      "running",
      "blocked",
      "paused",
      "completed",
      "failed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(8);
    expect(statuses).toContain("running");
    expect(statuses).not.toContain("awaiting_approval");
  });

  it("accepts all OperatingCycleStatus values", () => {
    const statuses: OperatingCycleStatus[] = [
      "initializing",
      "observing",
      "assessing",
      "planning",
      "awaiting_approval",
      "executing",
      "verifying",
      "measuring",
      "replanning",
      "completed",
      "blocked",
      "failed",
      "cancelled",
    ];
    expect(statuses).toHaveLength(13);
    expect(statuses).toContain("awaiting_approval");
    expect(statuses).toContain("replanning");
  });

  it("accepts all LessonType values", () => {
    const types: LessonType[] = [
      "lesson",
      "decision_outcome",
      "failed_assumption",
      "success_pattern",
      "process_improvement",
      "strategic_insight",
    ];
    expect(types).toHaveLength(6);
    expect(types).toContain("failed_assumption");
  });

  it("accepts all ApprovalGateType values", () => {
    const types: ApprovalGateType[] = [
      "mission_approval",
      "strategy_approval",
      "company_bootstrap_approval",
      "workforce_approval",
      "budget_approval",
      "product_launch_approval",
      "high_risk_action_approval",
      "major_strategic_change_approval",
    ];
    expect(types).toHaveLength(8);
    expect(types).toContain("budget_approval");
  });

  it("accepts all ApprovalGateStatus values", () => {
    const statuses: ApprovalGateStatus[] = [
      "pending",
      "approved",
      "rejected",
      "expired",
      "cancelled",
    ];
    expect(statuses).toHaveLength(5);
  });

  it("accepts all MissionGraphRelation values", () => {
    const relations: MissionGraphRelation[] = [
      "derived_from",
      "depends_on",
      "assigned_to",
      "executed_by",
      "measured_by",
      "blocked_by",
      "generated_by",
      "improves",
      "triggers",
    ];
    expect(relations).toHaveLength(9);
    expect(relations).toContain("executed_by");
  });

  it("accepts all AutonomyLevel values", () => {
    const levels: AutonomyLevel[] = [
      "manual",
      "assisted",
      "bounded_autonomy",
      "high_autonomy",
    ];
    expect(levels).toHaveLength(4);
    expect(levels).toContain("bounded_autonomy");
  });

  it("accepts a full Mission fixture", () => {
    const mission: Mission = {
      id: "m1",
      company_id: "c1",
      title: "Build an AI developer productivity startup",
      description: null,
      mission_statement: "Ship an autonomous AI dev-tool company.",
      desired_outcome: "A self-sustaining AI software company",
      target_market: "small software teams",
      constraints: ["no external APIs", "deterministic by default"],
      assumptions: ["mock provider is available"],
      success_criteria: ["company bootstrapped", "cycle completed"],
      strategic_context: null,
      priority: 1,
      status: "active",
      analysis: {
        objectives: ["Stand up company", "Ship product"],
        target_market: "small software teams",
        problem: "Teams waste time on boilerplate",
        proposed_solution: "AI agent",
        constraints: ["deterministic by default"],
        timeline: "30 days",
        success_criteria: ["launched product"],
        assumptions: ["mock provider"],
        risks: ["model failure"],
        unknowns: ["market fit"],
        required_capabilities: ["agents", "workflows"],
        analyzer: "deterministic",
      },
      validation: null,
      owner_id: null,
      started_at: "2026-09-01T00:00:00Z",
      completed_at: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(mission.status).toBe("active");
    expect(mission.constraints).toHaveLength(2);
    expect(mission.analysis?.objectives).toContain("Ship product");
  });

  it("accepts a full StartupPlan fixture", () => {
    const plan: StartupPlan = {
      id: "sp1",
      mission_id: "m1",
      strategic_plan_id: null,
      business_objectives: ["Achieve gross margin"],
      product_objectives: ["Ship MVP"],
      market_objectives: ["Enter dev-tools market"],
      organization_objectives: ["Stand up 3 departments"],
      operational_objectives: ["Run 10 operating cycles"],
      milestones: ["Bootstrap by day 7"],
      departments: [{ name: "Engineering", roles: ["engineer"], mission: "Ship" }],
      roles: ["engineer", "researcher"],
      capabilities: ["orchestration"],
      initial_products: [{ name: "AI Dev Platform", description: "Dev tool" }],
      initial_projects: [{ name: "MVP project" }],
      kpi_targets: { test_pass_rate: 0.9 },
      budget_allocation: { engineering: 500, research: 300 },
      execution_priorities: ["bootstrap", "product"],
      approval_requirements: ["company_bootstrap_approval"],
      status: "approved",
      review: null,
      created_at: "2026-09-02T00:00:00Z",
      updated_at: "2026-09-02T00:00:00Z",
    };
    expect(plan.status).toBe("approved");
    expect(plan.initial_products).toHaveLength(1);
    expect(plan.approval_requirements).toContain("company_bootstrap_approval");
  });

  it("accepts a full Product fixture", () => {
    const product: Product = {
      id: "p1",
      company_id: "c1",
      name: "AI Developer Platform",
      description: "Autonomous dev-tools assistant",
      product_type: "saas",
      target_users: ["developers", "tech leads"],
      value_proposition: "Reduce boilerplate",
      status: "building",
      owner_id: "emp-1",
      strategic_priority: 1,
      budget: { monthly: 300 },
      success_metrics: ["activation_rate"],
      launch_criteria: ["test coverage"],
      validation: null,
      created_at: "2026-09-03T00:00:00Z",
      updated_at: "2026-09-03T00:00:00Z",
    };
    expect(product.status).toBe("building");
    expect(product.target_users).toHaveLength(2);
  });

  it("accepts a full StartupProject fixture", () => {
    const project: StartupProject = {
      id: "pr1",
      company_id: "c1",
      product_id: "p1",
      department_id: "d1",
      name: "MVP project",
      description: "Build the core loop",
      objective: "Ship a verified task execution",
      owner_id: "emp-1",
      status: "blocked",
      priority: 1,
      budget: { cap: 100 },
      milestones: ["design", "implement", "verify"],
      dependencies: ["assigned agent"],
      success_criteria: ["verification passes"],
      start_date: "2026-09-04T00:00:00Z",
      deadline: "2026-09-30T00:00:00Z",
      created_at: "2026-09-04T00:00:00Z",
      updated_at: "2026-09-05T00:00:00Z",
    };
    expect(project.status).toBe("blocked");
    expect(project.dependencies).toHaveLength(1);
  });

  it("accepts a full OperatingCycle fixture with stage timeline", () => {
    const stages: CycleStage[] = [
      {
        stage: "observe",
        status: "completed",
        started_at: "2026-09-05T00:00:00Z",
        ended_at: "2026-09-05T00:01:00Z",
        duration_ms: 60000,
        outputs: { goals: 3 },
      },
      {
        stage: "replan",
        status: "completed",
        outputs: { actions: ["reprioritize"] },
      },
    ];
    const cycle: OperatingCycle = {
      id: "cy1",
      company_id: "c1",
      mission_id: "m1",
      startup_plan_id: "sp1",
      cycle_number: 1,
      status: "completed",
      stages,
      state_snapshot_id: "snap1",
      decisions: [{ type: "reprioritize", reason: "kpi miss" }],
      actions: [{ type: "allocate", resource: "engineer" }],
      kpis: [{ name: "test_pass_rate", value: 0.9 }],
      failures: [{ stage: "execute", message: "task failed" }],
      recovery: [{ stage: "execute", outcome: "recovered" }],
      approvals: [],
      resource_usage: { tokens: 12000 },
      outcome: { overall_score: 0.82, replanning_executed: false },
      started_at: "2026-09-05T00:00:00Z",
      ended_at: "2026-09-05T00:02:00Z",
    };
    expect(cycle.cycle_number).toBe(1);
    expect(cycle.stages[0].stage).toBe("observe");
    expect(cycle.failures).toHaveLength(1);
    expect(cycle.recovery[0].outcome).toBe("recovered");
    expect(cycle.outcome.replanning_executed).toBe(false);
  });

  it("accepts a full CompanyStateSnapshot fixture", () => {
    const snapshot: CompanyStateSnapshot = {
      id: "snap1",
      company_id: "c1",
      overall_score: 0.82,
      dimensions: { execution: 0.85, quality: 0.9, cost: 0.7 },
      explanations: {
        execution: "task verification pass rate 95%",
        quality: "no verification failures",
        cost: "budget utilization below 40%",
      },
      computed_at: "2026-09-05T00:02:00Z",
      metrics: { tasks_verified: 12 },
    };
    expect(snapshot.dimensions.cost).toBeCloseTo(0.7);
    expect(Object.keys(snapshot.explanations)).toContain("execution");
  });

  it("accepts a full ApprovalGate fixture", () => {
    const gate: ApprovalGate = {
      id: "g1",
      company_id: "c1",
      gate_type: "budget_approval",
      risk_level: "medium",
      requested_action: { action: "increase_budget", amount: 120, pct: 20 },
      rationale: "Customer expansion requires more dev budget",
      affected_entities: ["department:engineering"],
      resource_impact: { monthly_budget: "+120" },
      requester_id: "emp-1",
      approver_id: "human-1",
      status: "approved",
      decided_at: "2026-09-06T00:00:00Z",
      expiration: null,
      created_at: "2026-09-06T00:00:00Z",
    };
    expect(gate.gate_type).toBe("budget_approval");
    expect(gate.status).toBe("approved");
    expect((gate.requested_action as { pct: number }).pct).toBe(20);
  });

  it("accepts a full AutonomyPolicy fixture", () => {
    const policy: AutonomyPolicy = {
      company_id: "c1",
      autonomy_level: "bounded_autonomy",
      allow_matrix: {
        run_cycle: "allow",
        increase_budget: "require_approval",
        hire: "block",
      },
      never_allowed: ["finance", "legal", "hire_human", "self_modify"],
      max_employees: 20,
      max_departments: 6,
      max_budget: 1000,
      max_concurrent_work: 5,
      max_provisioning_rate: 2,
      require_approval_for: ["budget_changes", "product_launch"],
    };
    expect(policy.autonomy_level).toBe("bounded_autonomy");
    expect(policy.allow_matrix.hire).toBe("block");
    expect(policy.require_approval_for).toContain("budget_changes");
  });

  it("accepts a full StartupFeedback fixture", () => {
    const feedback: StartupFeedback = {
      id: "f1",
      company_id: "c1",
      mission_id: "m1",
      objective_type: { scope: "company" },
      source: "performance aggregator",
      category: "efficiency",
      observation: "Verification pass rate dropped below target",
      impact: "negative",
      confidence: 0.8,
      recommendation: "Increase reviewer capacity",
      related_goal_id: "g1",
      related_project_id: null,
      related_product_id: null,
      created_at: "2026-09-06T00:00:00Z",
    };
    expect(feedback.category).toBe("efficiency");
    expect(feedback.confidence).toBeCloseTo(0.8);
  });

  it("accepts a full Lesson fixture", () => {
    const lesson: Lesson = {
      id: "l1",
      company_id: "c1",
      mission_id: "m1",
      lesson_type: "failed_assumption",
      title: "Researcher role needs a fallback agent",
      content: "Single-agent research failed; recovery used a fallback.",
      source: { edge: "task->execution", ref: "ex1" },
      created_at: "2026-09-06T00:01:00Z",
    };
    expect(lesson.lesson_type).toBe("failed_assumption");
  });

  it("accepts a MissionGraph fixture, edges chainable to a mission", () => {
    const edges: MissionGraphEdge[] = [
      {
        id: "e1",
        company_id: "c1",
        source_type: "mission",
        source_id: "m1",
        target_type: "startup_plan",
        target_id: "sp1",
        relation: "derived_from",
        metadata: { step: "plan" },
        created_at: "2026-09-02T00:00:00Z",
      },
      {
        id: "e2",
        company_id: "c1",
        source_type: "execution",
        source_id: "ex1",
        target_type: "task",
        target_id: "t1",
        relation: "generated_by",
        metadata: null,
        created_at: "2026-09-05T00:00:00Z",
      },
    ];
    const graph: MissionGraph = { edges, total: 2 };
    expect(graph.total).toBe(2);
    expect(graph.edges[0].relation).toBe("derived_from");
    const start: MissionGraphEdge | undefined = edges.find(
      (e) => e.source_type === "mission",
    );
    expect(start?.source_id).toBe("m1");
  });
});