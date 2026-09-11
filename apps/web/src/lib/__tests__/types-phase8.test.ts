import { describe, it, expect } from "vitest";
import type {
  Alert,
  AlertSeverity,
  AlertStatus,
  AuthorityLevel,
  BudgetSnapshot,
  Company,
  CompanyHealth,
  CompanyReport,
  CompanyStatus,
  Decision,
  DecisionOption,
  DecisionReviewEntry,
  DecisionStatus,
  Department,
  DepartmentStatus,
  EffectivePolicy,
  GoalScopeType,
  GoalStatusOrg,
  Kpi,
  KpiCategory,
  KpiTrend,
  KpiValueEntry,
  Membership,
  OrgChartNode,
  OrgEvent,
  OrgGoal,
  OrgRole,
  Policy,
  PolicyScopeType,
  Risk,
  RiskStatus,
} from "@/lib/types";

describe("Phase 8 AI Company Layer types", () => {
  it("accepts all CompanyStatus values", () => {
    const statuses: CompanyStatus[] = [
      "draft",
      "active",
      "paused",
      "suspended",
      "archived",
    ];
    expect(statuses).toHaveLength(5);
    expect(statuses).toContain("active");
    expect(statuses).toContain("archived");
  });

  it("accepts all DepartmentStatus values", () => {
    const statuses: DepartmentStatus[] = [
      "draft",
      "active",
      "paused",
      "archived",
    ];
    expect(statuses).toHaveLength(4);
  });

  it("accepts all AuthorityLevel values", () => {
    const levels: AuthorityLevel[] = [
      "individual_contributor",
      "team_lead",
      "manager",
      "executive",
      "company_admin",
    ];
    expect(levels).toHaveLength(5);
    expect(levels).toContain("executive");
  });

  it("accepts all GoalScopeType values", () => {
    const scopes: GoalScopeType[] = ["company", "department", "employee"];
    expect(scopes).toHaveLength(3);
  });

  it("accepts all GoalStatusOrg values", () => {
    const statuses: GoalStatusOrg[] = [
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

  it("accepts all PolicyScopeType values", () => {
    const scopes: PolicyScopeType[] = ["system", "company", "department"];
    expect(scopes).toHaveLength(3);
  });

  it("accepts all DecisionStatus values", () => {
    const statuses: DecisionStatus[] = [
      "draft",
      "pending_review",
      "approved",
      "rejected",
      "implemented",
      "expired",
      "cancelled",
    ];
    expect(statuses).toHaveLength(7);
    expect(statuses).toContain("pending_review");
  });

  it("accepts all RiskStatus values", () => {
    const statuses: RiskStatus[] = [
      "open",
      "mitigating",
      "monitored",
      "resolved",
      "accepted",
    ];
    expect(statuses).toHaveLength(5);
  });

  it("accepts all AlertSeverity values", () => {
    const severities: AlertSeverity[] = [
      "critical",
      "warning",
      "informational",
    ];
    expect(severities).toHaveLength(3);
  });

  it("accepts all AlertStatus values", () => {
    const statuses: AlertStatus[] = ["active", "acknowledged", "resolved"];
    expect(statuses).toHaveLength(3);
  });

  it("accepts all KpiCategory values", () => {
    const cats: KpiCategory[] = [
      "quality",
      "productivity",
      "reliability",
      "cost",
      "speed",
      "goal_progress",
      "resource_utilization",
      "customer",
      "operational",
    ];
    expect(cats).toHaveLength(9);
    expect(cats).toContain("goal_progress");
  });

  it("accepts all KpiTrend values", () => {
    const trends: KpiTrend[] = ["declining", "flat", "improving"];
    expect(trends).toHaveLength(3);
  });

  it("accepts a full Company fixture", () => {
    const company: Company = {
      id: "c1",
      name: "NEXUS Labs",
      slug: "nexus-labs",
      description: "AI software company",
      mission: "Build the future",
      vision: "AGI by 2030",
      industry: "ai",
      timezone: "UTC",
      currency: "USD",
      values: ["innovation", "integrity"],
      strategic_priorities: ["ship", "hire"],
      status: "active",
      owner_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
    };
    expect(company.status).toBe("active");
    expect(company.values).toHaveLength(2);
  });

  it("accepts a full Department fixture", () => {
    const dept: Department = {
      id: "d1",
      company_id: "c1",
      name: "Engineering",
      description: "Product engineering",
      mission: "Ship quality software",
      manager_id: null,
      parent_department_id: null,
      status: "active",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(dept.status).toBe("active");
    expect(dept.company_id).toBe("c1");
  });

  it("accepts a full OrgGoal fixture", () => {
    const goal: OrgGoal = {
      id: "g1",
      company_id: "c1",
      scope_type: "company",
      scope_id: "c1",
      parent_goal_id: null,
      title: "Ship v1.0",
      description: "Launch product",
      priority: 1,
      target: "2026-06-01",
      metric: "release_date",
      deadline: "2026-06-01T00:00:00Z",
      status: "active",
      progress: 0.45,
      owner_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
    };
    expect(goal.scope_type).toBe("company");
    expect(goal.progress).toBeCloseTo(0.45);
  });

  it("accepts a full OrgGoal with parent cascade", () => {
    const goal: OrgGoal = {
      id: "g2",
      company_id: "c1",
      scope_type: "department",
      scope_id: "d1",
      parent_goal_id: "g1",
      title: "Ship API v1.0",
      description: null,
      priority: 2,
      target: null,
      metric: null,
      deadline: null,
      status: "at_risk",
      progress: 0.2,
      owner_id: "emp-1",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-15T00:00:00Z",
    };
    expect(goal.parent_goal_id).toBe("g1");
    expect(goal.status).toBe("at_risk");
  });

  it("accepts a full Kpi fixture with history", () => {
    const history: KpiValueEntry[] = [
      {
        value: 0.82,
        variance: -0.03,
        trend: "declining",
        period_label: "2026-01",
        recorded_at: "2026-01-31T00:00:00Z",
      },
      {
        value: 0.88,
        variance: 0.0,
        trend: "flat",
        period_label: "2026-02",
        recorded_at: "2026-02-28T00:00:00Z",
      },
    ];
    const kpi: Kpi = {
      id: "k1",
      company_id: "c1",
      scope_type: "department",
      scope_id: "d1",
      name: "Test pass rate",
      description: "Percentage of passing tests",
      category: "reliability",
      source_metric: "verification_results.pass_rate",
      target: 0.95,
      unit: "%",
      owner_id: "emp-1",
      frequency: "daily",
      current_value: 0.88,
      variance: -0.07,
      trend: "improving",
      recorded_at: "2026-03-01T00:00:00Z",
      history,
    };
    expect(kpi.source_metric).toBe("verification_results.pass_rate");
    expect(kpi.history).toHaveLength(2);
    expect(kpi.history[0].trend).toBe("declining");
  });

  it("accepts a full BudgetSnapshot fixture", () => {
    const snap: BudgetSnapshot = {
      company_id: "c1",
      scope_type: "company",
      scope_id: "c1",
      monthly_limit: 1000,
      allocated: 400,
      reserved: 50,
      spent: 350,
      tokens_used: 1500000,
      cost_used: 320,
      tool_calls_used: 4200,
      execution_count: 180,
      period_start: "2026-03-01T00:00:00Z",
      period_end: "2026-03-31T00:00:00Z",
      utilization_pct: 35,
      remaining: 650,
    };
    expect(snap.utilization_pct).toBe(35);
    expect(snap.remaining).toBe(650);
  });

  it("accepts a full Decision fixture", () => {
    const options: DecisionOption[] = [
      { id: "opt1", label: "Approve migration" },
      { id: "opt2", label: "Defer" },
    ];
    const decision: Decision = {
      id: "dc1",
      company_id: "c1",
      requester_id: "emp-1",
      decision_maker_id: null,
      question: "Should we migrate to new infra?",
      context: { urgency: "high" },
      options,
      selected_option: null,
      evidence: { cost_analysis: "saves 20%" },
      rationale: null,
      risk_level: "medium",
      risk: { downtime: "possible" },
      budget_impact: { cost: 5000 },
      required_authority: "executive",
      status: "pending_review",
      created_at: "2026-03-01T00:00:00Z",
      updated_at: "2026-03-01T00:00:00Z",
    };
    expect(decision.options).toHaveLength(2);
    expect(decision.status).toBe("pending_review");
    expect(decision.required_authority).toBe("executive");
  });

  it("accepts a full DecisionReviewEntry fixture", () => {
    const review: DecisionReviewEntry = {
      id: "rev1",
      decision_id: "dc1",
      reviewer_id: "emp-2",
      action: "approve",
      verdict: "approve",
      rationale: "Cost savings justified",
      previous_status: "pending_review",
      next_status: "approved",
      created_at: "2026-03-02T00:00:00Z",
    };
    expect(review.verdict).toBe("approve");
  });

  it("accepts a full Risk fixture", () => {
    const risk: Risk = {
      id: "r1",
      company_id: "c1",
      scope_type: "company",
      scope_id: "c1",
      title: "Budget overrun risk",
      description: "Monthly costs exceeding limits",
      severity: "high",
      probability: 0.6,
      impact: "financial",
      owner_id: "emp-1",
      status: "mitigating",
      mitigation: "Implement cost alerts",
      created_at: "2026-03-01T00:00:00Z",
      updated_at: "2026-03-01T00:00:00Z",
    };
    expect(risk.severity).toBe("high");
    expect(risk.probability).toBe(0.6);
  });

  it("accepts a full Alert fixture", () => {
    const alert: Alert = {
      id: "a1",
      company_id: "c1",
      scope_type: "company",
      scope_id: "c1",
      title: "Budget threshold exceeded",
      severity: "critical",
      category: "budget",
      message: "Spend is at 92% of monthly limit",
      status: "active",
      payload: { utilization_pct: 92, monthly_limit: 1000 },
      created_at: "2026-03-01T00:00:00Z",
      resolved_at: null,
    };
    expect(alert.severity).toBe("critical");
    expect(alert.payload?.utilization_pct).toBe(92);
  });

  it("accepts a full CompanyReport fixture", () => {
    const report: CompanyReport = {
      id: "rp1",
      company_id: "c1",
      report_type: "weekly",
      period_start: "2026-02-24T00:00:00Z",
      period_end: "2026-03-02T00:00:00Z",
      created_at: "2026-03-02T12:00:00Z",
      metrics: { tasks_completed: 42 },
      highlights: ["Goal progress 45%"],
      risks: [{ title: "Budget risk", severity: "high" }],
      blockers: ["Slow verification"],
      goal_progress: { g1: 0.45 },
      recommendations: ["Increase reviewer capacity"],
      evidence: { verified: true },
      verification_status: "verified",
      verification_summary: "All metrics cross-checked",
    };
    expect(report.report_type).toBe("weekly");
    expect(report.verification_status).toBe("verified");
    expect(report.recommendations).toHaveLength(1);
  });

  it("accepts a full OrgEvent fixture", () => {
    const evt: OrgEvent = {
      id: "evt1",
      company_id: "c1",
      actor: "CEO",
      action: "decision_approved",
      target_type: "decision",
      target_id: "dc1",
      details: { approved_option: "Approve migration" },
      outcome: "success",
      created_at: "2026-03-02T00:00:00Z",
    };
    expect(evt.action).toBe("decision_approved");
  });

  it("accepts a recursive OrgChartNode fixture", () => {
    const node: OrgChartNode = {
      id: "c1",
      type: "company",
      name: "NEXUS Labs",
      status: "active",
      children: [
        {
          id: "d1",
          type: "department",
          name: "Engineering",
          status: "active",
          children: [
            {
              id: "emp-1",
              type: "employee",
              name: "Alex",
              status: "active",
              children: [],
            },
          ],
        },
      ],
    };
    expect(node.type).toBe("company");
    expect(node.children[0].type).toBe("department");
    expect(node.children[0].children[0].type).toBe("employee");
  });

  it("accepts a full CompanyHealth fixture", () => {
    const health: CompanyHealth = {
      company_id: "c1",
      overall_score: 78,
      status: "degraded",
      dimensions: {
        execution: 85,
        quality: 80,
        reliability: 70,
        cost: 75,
        goal_progress: 65,
        risk_posture: 82,
      },
      weights: {
        execution: 0.2,
        quality: 0.2,
        reliability: 0.2,
        cost: 0.15,
        goal_progress: 0.15,
        risk_posture: 0.1,
      },
      computed_at: "2026-03-01T00:00:00Z",
    };
    expect(health.status).toBe("degraded");
    expect(health.overall_score).toBe(78);
    expect(health.dimensions.reliability).toBe(70);
  });

  it("accepts a full Policy fixture", () => {
    const policy: Policy = {
      id: "pol1",
      company_id: "c1",
      scope_type: "company",
      scope_id: "c1",
      name: "Budget limit policy",
      key: "max_monthly_cost",
      value: 500,
      priority: 10,
      enabled: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(policy.key).toBe("max_monthly_cost");
    expect(policy.enabled).toBe(true);
  });

  it("accepts an EffectivePolicy fixture", () => {
    const ep: EffectivePolicy = {
      key: "max_retries",
      value: 3,
      source_scope: "company",
      source_name: "Budget limit policy",
      candidates_checked: 3,
    };
    expect(ep.candidates_checked).toBe(3);
  });

  it("accepts a Membership fixture", () => {
    const mem: Membership = {
      id: "mem1",
      company_id: "c1",
      employee_id: "emp-1",
      employee_name: "Alex",
      role: "engineer",
      department_id: "d1",
      role_id: "role1",
      role_title: "Senior Engineer",
      authority_level: "team_lead",
      responsibility: "tech lead",
      manager_id: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(mem.authority_level).toBe("team_lead");
  });

  it("accepts an OrgRole fixture", () => {
    const role: OrgRole = {
      id: "role1",
      company_id: "c1",
      name: "senior-engineer",
      title: "Senior Engineer",
      description: "Senior technical contributor",
      responsibilities: ["Architecture", "Code review"],
      required_skills: ["python", "system_design"],
      authority_level: "team_lead",
      authority_scope: ["d1"],
      default_policies: ["max_retries:3"],
      kpis: ["test_pass_rate"],
      compatible_departments: ["d1"],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    expect(role.authority_level).toBe("team_lead");
    expect(role.required_skills).toHaveLength(2);
  });
});
