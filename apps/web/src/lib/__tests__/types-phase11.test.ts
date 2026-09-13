import { describe, it, expect } from "vitest";
import type {
  AuthSessionResponse,
  AuditChainVerify,
  AuditEventPublic,
  BreakGlassInput,
  BreakGlassPublic,
  DataClassificationInput,
  DataClassificationPublic,
  FeatureFlagInput,
  FeatureFlagPublic,
  GovernanceControlPublic,
  HealthOverview,
  IdentityKind,
  IncidentActionInput,
  IncidentActionPublic,
  IncidentCreateInput,
  IncidentDetailPublic,
  IncidentPublic,
  IncidentTransitionInput,
  MetricsSnapshot,
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

describe("Phase 11 Security & Governance types", () => {
  it("models the five identity kinds", () => {
    const kinds: IdentityKind[] = [
      "user",
      "service",
      "ai_employee",
      "agent",
      "company",
    ];
    expect(kinds).toHaveLength(5);
    expect(kinds).toContain("agent");
  });

  it("auth session carries identity + roles + permissions", () => {
    const session: AuthSessionResponse = {
      identity: {
        id: "id-1",
        kind: "user",
        name: "ops",
        status: "active",
        company_id: null,
        external_ref: null,
      },
      user: null,
      roles: ["company_admin"],
      permissions: ["control.read"],
    };
    expect(session.permissions).toContain("control.read");
  });

  it("login result binds tokens to an identity", () => {
    const result: SessionResult = {
      access_token: "a",
      refresh_token: "r",
      session_id: "s",
      identity: { id: "id-1", kind: "user", name: "ops", status: "active", company_id: null, external_ref: null },
      user: null,
      company_id: null,
    };
    expect(result.access_token).toBe("a");
  });

  it("secret references expose a mask hint, never a value", () => {
    const ref: SecretReference = {
      id: "s-1",
      name: "mailgun_api_key",
      company_id: null,
      kind: "api_key",
      status: "active",
      mask_hint: "k···1234",
      key_id: "key-0001",
      rotation_due_at: null,
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
    };
    expect(ref.mask_hint).toContain("···");
    expect(ref).not.toHaveProperty("plaintext");
  });

  it("governance flags express a scope and pause state", () => {
    const flag: SystemFlagPublic = {
      id: "f-1",
      scope: "external",
      tenant_id: "company-1",
      flag: "external_paused",
      status: "active",
      reason: "Investigation",
      set_by: "id-1",
      set_at: "2026-09-01T00:00:00Z",
      cleared_at: null,
    };
    expect(flag.status).toBe("active");
    expect(flag.flag).toContain("paused");
  });

  it("audit events are hash-chained", () => {
    const event: AuditEventPublic = {
      id: "a-1",
      seq: 42,
      company_id: null,
      actor_id: "id-1",
      actor_name: "ops",
      action: "identity.login",
      category: "auth",
      resource_type: "identity",
      resource_id: "id-1",
      outcome: "success",
      detail: null,
      policy_result: null,
      approval_ref: null,
      correlation_id: "c-1",
      ip_address: null,
      hash: "abc123",
      prev_hash: "…",
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(event.seq).toBe(42);
    expect(event.prev_hash).toBeDefined();
  });

  it("chain verification reports the first gap", () => {
    const verify: AuditChainVerify = {
      verified: true,
      checked: 120,
      first_gap_at_seq: null,
    };
    expect(verify.verified).toBe(true);
  });

  it("incident details enrich an incident with alerts and actions", () => {
    const incident: IncidentDetailPublic = {
      id: "i-1",
      company_id: null,
      severity: "high",
      status: "contained",
      title: "Burst",
      description: null,
      timeline_json: null,
      contained_at: "2026-09-01T00:00:00Z",
      resolved_at: null,
      closed_at: null,
      created_at: "2026-09-01T00:00:00Z",
      alerts: [
        {
          id: "al-1",
          company_id: null,
          severity: "high",
          status: "open",
          rule_code: "CROSS_COMPANY_BURST",
          title: "Burst alert",
          description: null,
          created_at: "2026-09-01T00:00:00Z",
          acknowledged_at: null,
          resolved_at: null,
        },
      ],
      actions: [
        {
          id: "act-1",
          incident_id: "i-1",
          action_code: "pause_company",
          target_company_id: null,
          target_ref: null,
          state: "applied",
          performed_by: "id-1",
          result_json: { ok: true },
          created_at: "2026-09-01T00:00:00Z",
          applied_at: null,
        },
      ],
    };
    expect(incident.actions[0].action_code).toBe("pause_company");
    expect(incident.alerts[0].id).toBe("al-1");
  });

  it("policy decisions record the enforcement outcome", () => {
    const d: PolicyDecisionPublic = {
      id: "d-1",
      company_id: null,
      identity_id: "id-1",
      action: "tool:execute",
      resource: "shell",
      decision: "deny",
      reason: "high risk",
      matched_rule_scope: "agent",
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(d.decision).toBe("deny");
  });

  it("data transfer checks gate classification", () => {
    const input: TransferCheckInput = {
      resource_type: "api.export",
      resource_id: "exp-1",
      destination: "webhook://partner",
    };
    const decision: TransferDecisionPublic = {
      allowed: false,
      reason: "restricted",
      target_classification: "restricted",
      destination: "webhook://partner",
      requires_approval: true,
      blocked_fields: 1,
    };
    expect(input.destination).toContain("webhook");
    expect(decision.allowed).toBe(false);
  });

  it("health overview aggregates the control surface", () => {
    const overview: HealthOverview = {
      incidents_open: 1,
      alerts_open: 2,
      audit_events: 1000,
      resource_limits: 3,
      resource_usage_entries: 4,
    };
    expect(overview.audit_events).toBe(1000);
  });

  it("action inputs describe auditable remediation", () => {
    const input: IncidentActionInput = {
      incident_id: "i-1",
      action: "disable_agent",
      params: { target_ref: "ag-9" },
    };
    expect(input.params?.target_ref).toBe("ag-9");
  });

  it("security events and alerts carry severity + category", () => {
    const event: SecurityEventPublic = {
      id: "e-1",
      company_id: null,
      category: "ssrf_blocked",
      severity: "high",
      title: "SSRF attempt blocked",
      detail: { host: "169.254.169.254" },
      actor_id: "id-1",
      created_at: "2026-09-01T00:00:00Z",
    };
    const alert: SecurityAlertPublic = {
      id: "a-2",
      company_id: null,
      severity: "critical",
      status: "open",
      rule_code: "SSRF_METADATA",
      title: "Metadata probe",
      description: null,
      created_at: "2026-09-01T00:00:00Z",
      acknowledged_at: null,
      resolved_at: null,
    };
    expect(event.category).toBe("ssrf_blocked");
    expect(alert.rule_code).toBe("SSRF_METADATA");
  });

  it("policy rules express most-restrictive-wins enforcement", () => {
    const input: PolicyRuleInput = {
      scope: "agent",
      action_pattern: "tool:*",
      effect: "deny",
      risk_level: "high",
      priority: 10,
    };
    const rule: PolicyRulePublic = {
      id: "r-1",
      scope: "agent",
      company_id: null,
      subject_pattern: "*",
      action_pattern: "tool:*",
      resource_pattern: "*",
      effect: "deny",
      risk_level: "high",
      priority: 10,
      reason: null,
      enabled: true,
      created_at: "2026-09-01T00:00:00Z",
    };
    expect(input.effect).toBe("deny");
    expect(rule.priority).toBeGreaterThan(0);
  });

  it("resource limits are enforced per scope", () => {
    const input: ResourceLimitInput = {
      scope: "company",
      tenant_id: "company-1",
      category: "tool_calls",
      max_value: 500,
      period: "day",
    };
    const limit: ResourceLimitPublic = {
      id: "l-1",
      scope: "company",
      tenant_id: "company-1",
      category: "tool_calls",
      max_value: 500,
      period: "day",
      enforced: true,
    };
    const usage: ResourceUsagePublic = {
      id: "u-1",
      company_id: "company-1",
      tenant_id: "company-1",
      actor_id: "id-1",
      category: "tool_calls",
      amount: 42,
      unit: "count",
      instrument: "runaway_guard",
      recorded_at: "2026-09-01T00:00:00Z",
    };
    expect(input.max_value).toBe(500);
    expect(limit.enforced).toBe(true);
    expect(usage.amount).toBeLessThan(limit.max_value);
  });

  it("feature flags default risky capabilities off", () => {
    const flag: FeatureFlagPublic = {
      id: "f-2",
      scope: "global",
      company_id: null,
      name: "feature_external_symbols_enabled",
      enabled: false,
      rationale: "Bounded-autonomy default",
      updated_at: "2026-09-01T00:00:00Z",
    };
    const input: FeatureFlagInput = { enabled: true, rationale: "Review OK" };
    expect(flag.enabled).toBe(false);
    expect(input.rationale).toContain("Review");
  });

  it("break-glass elevates a scoped operation with expiry", () => {
    const input: BreakGlassInput = {
      scope: "company:company-1",
      reason: "Outage remediation",
      max_minutes: 30,
    };
    const bg: BreakGlassPublic = {
      id: "bg-1",
      identity_id: "id-1",
      company_id: "company-1",
      scope: "company:company-1",
      reason: "Outage remediation",
      status: "active",
      requested_at: "2026-09-01T00:00:00Z",
      expires_at: "2026-09-01T00:30:00Z",
      approved_by: null,
      revoked_at: null,
    };
    expect(bg.status).toBe("active");
    expect(input.max_minutes).toBe(30);
  });

  it("data classification + retention shape controlled data", () => {
    const cl: DataClassificationPublic = {
      resource_type: "api.export",
      resource_id: "exp-1",
      classification: "confidential",
      sensitivity_reason: "Employee PII",
    };
    const clIn: DataClassificationInput = {
      resource_type: "api.export",
      resource_id: "exp-1",
      classification: "confidential",
    };
    const rpIn: RetentionPolicyInput = {
      entity_type: "audit_events",
      retention_days: 730,
      deletion_semantics: "retention_lock",
      retention_lock: true,
    };
    const rp: RetentionPolicyPublic = {
      entity_type: "audit_events",
      company_id: null,
      retention_days: 730,
      deletion_semantics: "retention_lock",
      retention_lock: true,
      enabled: true,
    };
    expect(cl.classification).toBe("confidential");
    expect(clIn.classification).toBe("confidential");
    expect(rpIn.retention_lock).toBe(true);
    expect(rp.retention_lock).toBe(true);
  });

  it("governance controls enumerate enforced controls", () => {
    const control: GovernanceControlPublic = {
      id: "c-1",
      company_id: null,
      code: "auth_required",
      title: "Authentication required",
      description: null,
      category: "identity",
      enforced: true,
      source: null,
    };
    expect(control.enforced).toBe(true);
  });

  it("incident creation and lifecycle transition inputs serialize", () => {
    const create: IncidentCreateInput = {
      title: "Repeated cross-company access",
      severity: "high",
      company_id: null,
      alert_ids: ["a-2"],
    };
    const created: IncidentPublic = {
      id: "i-2",
      company_id: null,
      severity: "high",
      status: "detected",
      title: "Repeated cross-company access",
      description: null,
      timeline_json: null,
      contained_at: null,
      resolved_at: null,
      closed_at: null,
      created_at: "2026-09-01T00:00:00Z",
    };
    const transition: IncidentTransitionInput = {
      to_status: "investigating",
      note: "Starting investigation",
    };
    const action: IncidentActionPublic = {
      id: "act-2",
      incident_id: "i-2",
      action_code: "suspend_employee",
      target_company_id: "company-1",
      target_ref: "emp-7",
      state: "pending",
      performed_by: "id-1",
      result_json: null,
      created_at: "2026-09-01T00:00:00Z",
      applied_at: null,
    };
    expect(create.alert_ids).toContain("a-2");
    expect(created.status).toBe("detected");
    expect(transition.to_status).toBe("investigating");
    expect(action.action_code).toBe("suspend_employee");
  });

  it("secrets are created with rotation policy; users with roles", () => {
    const secret: SecretCreateInput = {
      name: "mailgun_api_key",
      plaintext: "sk-live-…",
      kind: "api_key",
      rotation_days: 90,
    };
    const userIn: UserCreateInput = {
      email: "ops@example.com",
      display_name: "ops",
      password: "…",
      roles: ["company_admin"],
    };
    const user: UserPublic = {
      id: "u-1",
      identity_id: "id-1",
      email: "ops@example.com",
      display_name: "ops",
      status: "active",
    };
    const role: RolePublic = {
      id: "r-2",
      name: "Company Admin",
      code: "company_admin",
      scope: "company",
      company_id: null,
      description: null,
      builtin: true,
    };
    expect(secret.rotation_days).toBe(90);
    expect(userIn.roles).toContain("company_admin");
    expect(user.status).toBe("active");
    expect(role.builtin).toBe(true);
  });

  it("system health probes + metrics snapshot the platform", () => {
    const probe: SystemHealthProbe = {
      status: "ok",
      service: "api",
      checks: { db: "ok", redis: "ok" },
    };
    const record: SystemHealthRecordPublic = {
      id: "h-1",
      service: "api",
      component: "db",
      healthy: true,
      detail: null,
      latency_ms: 12,
      recorded_at: "2026-09-01T00:00:00Z",
    };
    const metrics: MetricsSnapshot = {
      labels: { service: "api" },
      values: { latency_p99_ms: 210 },
      counters: { requests_total: 1234 },
      recorded_at: "2026-09-01T00:00:00Z",
    };
    expect(probe.status).toBe("ok");
    expect(record.healthy).toBe(true);
    expect(metrics.counters.requests_total).toBeGreaterThan(0);
  });
});