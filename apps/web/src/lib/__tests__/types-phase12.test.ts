import { describe, it, expect } from "vitest";
import type {
  AgentBenchmarkScorePublic,
  AgentPackageCreate,
  AgentPackagePublic,
  AgentPackageVersionPublic,
  AgentRecommendationPublic,
  BenchmarkCreate,
  BenchmarkPublic,
  BenchmarkResultsPublic,
  BenchmarkRunPublic,
  ExperimentCreate,
  ExperimentPublic,
  ExperimentResultPublic,
  InstallationPublic,
  OptimizationCyclePublic,
  OptimizationProblemCreate,
  OptimizationResultsPublic,
  OptimizationRunPublic,
  RecommendationPublic,
  ScenarioCreate,
  ScenarioPublic,
  SimulationComparisonPublic,
  SimulationPublic,
  SimulationResultsPublic,
  SimulationRunPublic,
  SimulationSnapshotPublic,
  SimulationStatePublic,
  SimulationUpdate,
} from "@/lib/types";

describe("Phase 12 Simulation types", () => {
  it("simulations are sandboxed modeled estimates, not actuals", () => {
    const sim: SimulationPublic = {
      id: "sim-1",
      company_id: "company-1",
      name: "What-if: 5→7 engineers",
      description: null,
      scenario_type: "what_if",
      status: "ready",
      model_name: "workforce",
      model_version: "1.0",
      assumptions_json: { growth: 0.4 },
      horizon_days: 90,
      clock_tick: "week",
      baseline_simulation_id: null,
      sandboxed: true,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(sim.sandboxed).toBe(true);
    expect(sim.scenario_type).toBe("what_if");
  });

  it("a run carries a modeled summary and honest failure message", () => {
    const run: SimulationRunPublic = {
      id: "run-1",
      simulation_id: "sim-1",
      scenario_id: "sc-1",
      company_id: "company-1",
      status: "completed",
      seed: "seed-42",
      model_name: "workforce",
      model_version: "1.0",
      tick_count: 12,
      started_at: "2026-09-01T00:00:00Z",
      completed_at: "2026-09-01T00:00:00Z",
      error_message: null,
      summary_json: { iterations: 1, output_kind: "simulated" },
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(run.summary_json?.output_kind).toBe("simulated");
    expect(run.tick_count).toBeGreaterThan(0);
  });

  it("scenarios reference a parent simulation and mark baselines", () => {
    const input: ScenarioCreate = {
      simulation_id: "sim-1",
      name: "Stress: churn spike",
      scenario_type: "stress_test",
      is_baseline: false,
    };
    const scenario: ScenarioPublic = {
      id: "sc-1",
      simulation_id: "sim-1",
      company_id: "company-1",
      name: "Stress: churn spike",
      scenario_type: "stress_test",
      description: null,
      assumptions_json: { churn: 0.3 },
      horizon_days: 90,
      is_baseline: false,
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(input.simulation_id).toBe("sim-1");
    expect(scenario.is_baseline).toBe(false);
  });

  it("comparisons expose baseline-vs-scenario deltas", () => {
    const comp: SimulationComparisonPublic = {
      id: "c-1",
      baseline_run_id: "run-1",
      scenario_run_id: "run-2",
      company_id: "company-1",
      metric_deltas_json: { revenue: "+0.12", on_time: "-0.04" },
      bottleneck_json: { entity: "engineering", pressure: 0.9 },
      summary: "Time-to-market improves at the cost of utilization.",
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(comp.metric_deltas_json?.revenue).toBe("+0.12");
    expect(comp.bottleneck_json?.pressure).toBe(0.9);
  });

  it("digital-twin snapshots name their source company", () => {
    const twin: SimulationSnapshotPublic = {
      id: "tw-1",
      company_id: "company-1",
      source_company_id: "company-1",
      name: "Company twin 2026-09-01",
      model_version: "1.0",
      snapshot_json: { departments: [] },
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(twin.source_company_id).toBe(twin.company_id);
  });

  it("live state carries tick, entities, and events (sim-only)", () => {
    const state: SimulationStatePublic = {
      run_id: "run-1",
      status: "running",
      tick: 5,
      simulation_id: "sim-1",
      scenario_id: null,
      entities: [{ kind: "department", name: "engineering", load: 0.7 }],
      events: [
        { tick: 3, kind: "kpi_threshold", entity_ref: "revenue", detail: { ok: true } },
        { tick: 4, kind: "sandbox_refusal", entity_ref: "http", detail: { refused: true } },
      ],
    };
    const refused = state.events.find((e) => e.kind === "sandbox_refusal");
    expect(refused && "detail" in refused ? (refused.detail as Record<string, unknown>)?.refused : undefined
    ).toBe(true);
    expect(state.tick).toBe(5);
  });

  it("multi-run aggregates are labeled modeled estimates", () => {
    const results: SimulationResultsPublic = {
      run_id: "run-multi",
      iterations: 200,
      summary_json: { min: 90, max: 120, mean: 104, p95: 115, kind: "forecast" },
      metrics: [],
      outcomes: [],
    };
    expect(results.iterations).toBeGreaterThan(1);
    expect(results.summary_json?.kind).toBe("forecast");
  });

  it("simulation updates are partial and non-destructive", () => {
    const update: SimulationUpdate = {
      description: "Extended horizon",
      horizon_days: 180,
    };
    expect(update.horizon_days).toBe(180);
  });
});

describe("Phase 12 Optimization types", () => {
  it("problems enumerate objectives and constraints", () => {
    const input: OptimizationProblemCreate = {
      name: "Hiring mix",
      objectives: [
        { metric: "throughput", direction: "maximize", weight: 0.7 },
        { metric: "cost", direction: "minimize", weight: 0.3 },
      ],
      variables: [{ name: "engineers", kind: "integer", low: 2, high: 8 }],
      constraints: [{ type: "budget", max_cost: 500_000 }],
    };
    expect(input.objectives).toHaveLength(2);
    expect(input.constraints?.[0]?.type).toBe("budget");
  });

  it("runs record the strategy and constraints applied", () => {
    const run: OptimizationRunPublic = {
      id: "or-1",
      problem_id: "op-1",
      company_id: "company-1",
      status: "completed",
      strategy: "greedy",
      constraints_json: { budget: 500_000 },
      started_at: "2026-09-01T00:00:00Z",
      completed_at: "2026-09-01T00:00:00Z",
      error_message: null,
      result_json: { best_score: 0.92 },
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(run.strategy).toBe("greedy");
  });

  it("results expose ranked candidates and a best candidate", () => {
    const results: OptimizationResultsPublic = {
      run_id: "or-1",
      candidates: [
        { name: "A", score: 0.92 },
        { name: "B", score: 0.81 },
      ],
      best_candidate: { name: "A", score: 0.92 },
    };
    expect((results.candidates[0].score as number)).toBeGreaterThan(
      results.candidates[1].score as number,
    );
    expect((results.best_candidate as Record<string, unknown>)?.name).toBe("A");
  });

  it("recommendations are explainable and approval-gated", () => {
    const rec: RecommendationPublic = {
      id: "rec-1",
      run_id: "or-1",
      company_id: "company-1",
      status: "pending_approval",
      title: "Hire 2 engineers to unblock engineering",
      candidate_values_json: { engineers: 7 },
      explanation_json: { what: "Grow engineering", why: "Bottleneck", alternatives: ["3"] },
      expected_benefit_json: { throughput: "+18%" },
      expected_cost_json: { annual: 240_000 },
      risk_json: { recruiting_delay: "medium" },
      assumptions_json: { ramp: "8 weeks" },
      approval_gate_id: "gate-1",
      approved_at: null,
      rejected_reason: null,
      applied_ref: null,
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(rec.explanation_json?.why).toBe("Bottleneck");
    expect(rec.approval_gate_id).toBeDefined();
    // A proposal is not applied until governed execution records a reference.
    expect(rec.applied_ref).toBeNull();
    expect(rec.status).toBe("pending_approval");
  });
});

describe("Phase 12 Experiment types", () => {
  it("experiments declare a hypothesis and bounded sample size", () => {
    const input: ExperimentCreate = {
      name: "Launch timing",
      hypothesis: "4-week launch lifts win rate",
      sample_size: 200,
      metrics: ["win_rate"],
      variants: [{ name: "4wk" }, { name: "6wk" }],
    };
    const experiment: ExperimentPublic = {
      id: "ex-1",
      company_id: "company-1",
      name: "Launch timing",
      description: null,
      status: "pending_approval",
      hypothesis: input.hypothesis ?? null,
      sample_size: 200,
      metrics_json: { win_rate: {} },
      baseline_json: { win_rate: 0.5 },
      approval_gate_id: "gate-2",
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(experiment.approval_gate_id).toBeDefined();
  });

  it("results bound significance with confidence + limitations", () => {
    const result: ExperimentResultPublic = {
      id: "er-1",
      experiment_id: "ex-1",
      conclusion: "winner",
      winning_variant_id: "var-4wk",
      sample_size: 200,
      metrics_json: { win_rate: { variant: 0.58, baseline: 0.5 } },
      confidence_json: { level: 0.95, ci: [0.51, 0.65] },
      assumptions_json: { traffic: "even split" },
      limitations_json: { seasonality: "north-hemisphere only" },
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(result.conclusion).toBe("winner");
    expect(result.limitations_json?.seasonality).toBeDefined();
  });
});

describe("Phase 12 Benchmark types", () => {
  it("benchmarks define dimensions and version", () => {
    const input: BenchmarkCreate = {
      name: "Customer support tasks",
      dimensions: ["correctness", "reliability", "latency", "cost"],
      version: "1.0",
    };
    const benchmark: BenchmarkPublic = {
      id: "b-1",
      company_id: "company-1",
      name: input.name,
      description: null,
      status: "ready",
      version: "1.0",
      dimensions_json: { correctness: {}, reliability: {}, latency: {}, cost: {} },
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(benchmark.version).toBe("1.0");
  });

  it("runs record case counts and per-dimension scores", () => {
    const run: BenchmarkRunPublic = {
      id: "br-1",
      benchmark_id: "b-1",
      agent_id: "ag-1",
      agent_version: "2.1.0",
      company_id: "company-1",
      status: "completed",
      case_count: 42,
      started_at: "2026-09-01T00:00:00Z",
      completed_at: "2026-09-01T00:00:00Z",
      created_at: "2026-09-01T00:00:00Z",
    };
    const score: AgentBenchmarkScorePublic = {
      id: "sc-1",
      agent_id: "ag-1",
      benchmark_id: "b-1",
      dimension: "correctness",
      score: 0.94,
      sample_cases: 42,
      created_at: "2026-09-01T00:00:00Z",
    };
    const results: BenchmarkResultsPublic = {
      run_id: "br-1",
      benchmark_id: "b-1",
      results: [{ case: 1, passed: true }],
      aggregate: { correctness: 0.94 },
    };
    expect(run.case_count).toBe(42);
    expect(score.score).toBe(0.94);
    expect(results.aggregate?.correctness).toBe(0.94);
  });
});

describe("Phase 12 Marketplace types", () => {
  it("packages are metadata-only with a security classification", () => {
    const input: AgentPackageCreate = {
      name: "research-analyst-pro",
      display_name: "Research Analyst Pro",
      description: "Evidence-gathering specialist",
      capabilities: ["web_search", "synthesis"],
      skills: ["research", "citation"],
      supported_task_types: ["research"],
      security: "internal",
      version: { version: "1.0.0", compatibility: "compatible" },
    };
    const pkg: AgentPackagePublic = {
      id: "pkg-1",
      company_id: "company-1",
      name: "research-analyst-pro",
      display_name: "Research Analyst Pro",
      description: null,
      status: "published",
      capabilities_json: { web_search: {}, synthesis: {} },
      skills_json: { research: {}, citation: {} },
      supported_task_types_json: { research: {} },
      requirements_json: { tools: ["web_search"], max_latency_s: 30 },
      security: "internal",
      published_at: "2026-09-01T00:00:00Z",
      deprecated_at: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(input.version?.version).toBe("1.0.0");
    expect(pkg.security).toBe("internal");
    expect(pkg).not.toHaveProperty("credentials");
    expect(pkg).not.toHaveProperty("memories");
  });

  it("versions track semver and compatibility", () => {
    const version: AgentPackageVersionPublic = {
      id: "v-1",
      package_id: "pkg-1",
      version: "1.0.0",
      changelog: "Initial release",
      compatibility: "compatible",
      metadata_json: { model: "sonnet-5" },
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(version.version.split(".")).toHaveLength(3);
  });

  it("installs are governed and approval-gated", () => {
    const inst: InstallationPublic = {
      id: "in-1",
      package_id: "pkg-1",
      version_id: "v-1",
      company_id: "company-2",
      employee_id: "emp-9",
      agent_id: "ag-9",
      status: "installed",
      approval_gate_id: "gate-3",
      config_json: { role: "research" },
      installed_at: "2026-09-01T00:00:00Z",
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(inst.approval_gate_id).toBeDefined();
    expect(inst.company_id).toBe("company-2");
  });

  it("recommendations expose ranking, reasoning, and policy status", () => {
    const rec: AgentRecommendationPublic = {
      id: "ar-1",
      company_id: "company-1",
      task_id: "task-1",
      agent_id: "ag-9",
      package_id: "pkg-1",
      request_json: { skills: ["research"] },
      rank: 1,
      score: 0.91,
      reasoning: "Highest benchmark correctness for this task type",
      tradeoffs_json: { cost: "higher than B", latency: "similar" },
      compatibility: "compatible",
      policy_status: "allowed",
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(rec.rank).toBe(1);
    expect(rec.policy_status).toBe("allowed");
  });
});

describe("Phase 12 Optimization cycle (closed-loop) types", () => {
  it("cycles trace observe→simulate→optimize→approve→measure→learn", () => {
    const cycle: OptimizationCyclePublic = {
      id: "cyc-1",
      company_id: "company-1",
      name: "Engineering bottleneck",
      status: "learning",
      observed_json: { kpi: { throughput: 0.4 } },
      scenario_ids_json: ["sc-1", "sc-2"],
      simulation_run_id: "run-1",
      optimization_run_id: "or-1",
      recommendation_id: "rec-1",
      approval_gate_id: "gate-4",
      execute_ref: "change-set/04",
      measures_json: { throughput: 0.62 },
      lesson_json: { kind: "simulation", note: "Growth from 5→7 engineers" },
      error_message: null,
      started_at: "2026-09-01T00:00:00Z",
      completed_at: null,
      updated_at: "2026-09-03T00:00:00Z",
    };
    expect(cycle.simulation_run_id).toBeDefined();
    expect(cycle.recommendation_id).toBeDefined();
    expect(cycle.execute_ref).toBeDefined();
    expect(cycle.lesson_json?.kind).toBe("simulation");
  });
});