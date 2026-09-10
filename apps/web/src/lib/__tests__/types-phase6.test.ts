import { describe, it, expect } from "vitest";
import type {
  Escalation,
  EvaluationRun,
  FailureDiagnosis,
  RecoveryAttempt,
  VerificationResult,
  VerificationRun,
} from "@/lib/types";

describe("Phase 6 reliability types", () => {
  it("accepts a VerificationRun and VerificationResult", () => {
    const run: VerificationRun = {
      id: "v1",
      execution_id: "e1",
      task_id: null,
      orchestration_id: null,
      workflow_id: null,
      policy_id: null,
      strategy_used: "deterministic",
      status: "pass",
      score: 1.0,
      confidence: 0.95,
      created_at: "2026-01-01T00:00:00Z",
    };
    const result: VerificationResult = {
      id: "vr1",
      run_id: run.id,
      execution_id: "e1",
      verifier_type: "deterministic",
      verifier_id: null,
      status: "pass",
      score: 1.0,
      confidence: 0.95,
      reason: "all criteria met",
      failed_criteria: [],
      passed_criteria: ["answer"],
      evidence: [],
      recommendations: [],
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(run.status).toBe("pass");
    expect(result.passed_criteria).toContain("answer");
  });

  it("accepts alternative verification statuses", () => {
    const fail: VerificationRun = {
      id: "v2",
      execution_id: "e2",
      status: "fail",
      score: 0.2,
      confidence: 0.8,
      created_at: "2026-01-01T00:00:00Z",
    } as VerificationRun;
    const partial: VerificationRun = { ...fail, id: "v3", status: "partial" };
    const uncertain: VerificationRun = { ...fail, id: "v4", status: "uncertain" };
    expect([fail.status, partial.status, uncertain.status]).toEqual([
      "fail",
      "partial",
      "uncertain",
    ]);
  });

  it("accepts a RecoveryAttempt with a state and outcome", () => {
    const attempt: RecoveryAttempt = {
      id: "r1",
      execution_id: "e1",
      plan_id: "p1",
      attempt_number: 1,
      state: "recovered",
      strategy: "retry_with_backoff",
      verification_result_id: null,
      outcome: "recovered",
      reason: "retry succeeded",
      metadata: null,
      started_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:00:01Z",
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(attempt.state).toBe("recovered");
    expect(attempt.outcome).toBe("recovered");
  });

  it("accepts recovery failure and escalation states", () => {
    const escalated: RecoveryAttempt = {
      id: "r2",
      execution_id: "e2",
      state: "escalated",
      outcome: "escalated",
      created_at: "2026-01-01T00:00:00Z",
    } as RecoveryAttempt;
    const aborted: RecoveryAttempt = {
      id: "r3",
      execution_id: "e3",
      state: "aborted",
      outcome: "aborted",
      created_at: "2026-01-01T00:00:00Z",
    } as RecoveryAttempt;
    expect(escalated.state).toBe("escalated");
    expect(aborted.outcome).toBe("aborted");
  });

  it("accepts a FailureDiagnosis with a category and retryability", () => {
    const diagnosis: FailureDiagnosis = {
      id: "d1",
      execution_id: "e1",
      category: "timeout",
      severity: "medium",
      root_cause: "tool timed out",
      retryable: true,
      recommended_strategy: "retry_with_backoff",
      confidence: 0.9,
      evidence: { tool_call_status: "timeout" },
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(diagnosis.category).toBe("timeout");
    expect(diagnosis.retryable).toBe(true);
  });

  it("accepts an Escalation pending human review", () => {
    const escalation: Escalation = {
      id: "esc1",
      execution_id: "e1",
      orchestration_id: null,
      workflow_id: "w1",
      issue: "recovery requires a destructive tool",
      category: "permission_failure",
      severity: "high",
      state: "pending_human_review",
      context: null,
      decision_reason: null,
      reviewed_at: null,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(escalation.state).toBe("pending_human_review");
    expect(escalation.category).toBe("permission_failure");
  });

  it("accepts an EvaluationRun with metrics", () => {
    const run: EvaluationRun = {
      id: "er1",
      evaluation_id: "ev1",
      status: "completed",
      score: 0.875,
      metrics: { task_success_rate: 0.9, recovery_success_rate: 0.85 },
      summary: "Default suite",
      result_count: 8,
      created_at: "2026-01-01T00:00:00Z",
    };
    expect(run.metrics?.task_success_rate).toBeCloseTo(0.9);
    expect(run.result_count).toBe(8);
  });
});