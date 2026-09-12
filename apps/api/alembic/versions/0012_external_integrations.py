"""0012 — External Integrations tables

Phase 10 — Computer Use & External Integrations.

Adds the governed external-interaction layer: company-scoped integration
instances, connections, capabilities, a *reference-only* credential record
(no plaintext column), the immutable external-action journal with attempt
traces, normalized external events (webhook ingest), the simulated browser
and computer-use sessions/actions/observations, and integration policies +
domain allowlists.

All enum columns are stored as plain String columns (project convention —
``native_enum=False``) so no native PostgreSQL enum types are created.

Tables only reference tables from migrations 0001–0011
(companies, ai_employees, agents, agent_executions, workflow_executions,
orchestrations, integration_connections, approval_gates).

Revision ID: 0012_external_integrations
Revises: 0011_autonomous_startup_engine
Create Date: 2026-09-12
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_external_integrations"
down_revision = "0011_autonomous_startup_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── external_integrations ─────────────────────────────────────────────────
    op.create_table(
        "external_integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="custom_api"),
        sa.Column("auth_type", sa.String(16), nullable=False, server_default="none"),
        sa.Column("status", sa.String(32), nullable=False, server_default="available"),
        sa.Column("configuration", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_external_integrations_company_slug", "external_integrations",
        ["company_id", "slug"],
    )
    op.create_index(
        "ix_external_integrations_company_provider", "external_integrations",
        ["company_id", "provider"],
    )
    op.create_index(
        "ix_external_integrations_company_status", "external_integrations",
        ["company_id", "status"],
    )

    # ── integration_connections ───────────────────────────────────────────────
    op.create_table(
        "integration_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="connected"),
        sa.Column("auth_method", sa.String(16), nullable=False, server_default="none"),
        sa.Column("credential_reference", sa.String(128), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("permissions", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_integration_connections_integration", "integration_connections", ["integration_id"]
    )
    op.create_index(
        "ix_integration_connections_company_status", "integration_connections",
        ["company_id", "status"],
    )

    # ── integration_capabilities ──────────────────────────────────────────────
    op.create_table(
        "integration_capabilities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capability_type", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("input_schema", sa.Text(), nullable=True),
        sa.Column("output_schema", sa.Text(), nullable=True),
        sa.Column("reversibility", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("supports_idempotency", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required_permissions", sa.Text(), nullable=True),
        sa.Column("required_scopes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_integration_capabilities_name", "integration_capabilities", ["integration_id", "name"]
    )
    op.create_index(
        "ix_integration_capabilities_integration", "integration_capabilities", ["integration_id"]
    )

    # ── external_credentials (reference-only — no plaintext column) ───────────
    op.create_table(
        "external_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("reference", sa.String(128), nullable=False),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="api_key"),
        sa.Column("masked_value", sa.String(128), nullable=False),
        sa.Column("env_var_hint", sa.String(128), nullable=True),
        sa.Column("scopes", sa.Text(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_external_credentials_reference", "external_credentials", ["reference"])
    op.create_index(
        "ix_external_credentials_company_provider", "external_credentials",
        ["company_id", "provider"],
    )
    op.create_index(
        "ix_external_credentials_connection", "external_credentials", ["connection_id"]
    )

    # ── external_actions (immutable journal) ──────────────────────────────────
    op.create_table(
        "external_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("integration_connections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("execution_id", sa.Uuid(), sa.ForeignKey("agent_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workflow_execution_id", sa.Uuid(), sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), sa.ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("capability", sa.String(128), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("reversibility", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("external_operation_id", sa.String(128), nullable=True),
        sa.Column("policy_result", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("approval_gate_id", sa.Uuid(), sa.ForeignKey("approval_gates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="requested"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("verification", sa.Text(), nullable=True),
        sa.Column("recovery", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_external_actions_company_status", "external_actions", ["company_id", "status"])
    op.create_index("ix_external_actions_company_integration", "external_actions", ["company_id", "integration_id"])
    op.create_index(
        "ix_external_actions_idem", "external_actions",
        ["company_id", "integration_id", "capability", "idempotency_key"],
    )
    op.create_index("ix_external_actions_gate", "external_actions", ["approval_gate_id"])

    # ── external_action_attempts (recovery trace) ─────────────────────────────
    op.create_table(
        "external_action_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("action_id", sa.Uuid(), sa.ForeignKey("external_actions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("strategy", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="executing"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_category", sa.String(40), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("external_operation_id", sa.String(128), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_external_attempts_number", "external_action_attempts", ["action_id", "attempt_number"])
    op.create_index("ix_external_action_attempts_action", "external_action_attempts", ["action_id"])

    # ── external_events (normalized webhook/other events — not commands) ──────
    op.create_table(
        "external_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="integration"),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("payload_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(16), nullable=False, server_default="not_verified"),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("signature_status", sa.String(16), nullable=False, server_default="not_required"),
        sa.Column("ingest_id", sa.String(128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_external_events_ingest", "external_events", ["source", "ingest_id"])
    op.create_index("ix_external_events_company_received", "external_events", ["company_id", "received_at"])
    op.create_index("ix_external_events_source_type", "external_events", ["source", "event_type"])

    # ── browser_sessions ──────────────────────────────────────────────────────
    op.create_table(
        "browser_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workflow_execution_id", sa.Uuid(), sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), sa.ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("current_url", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("allowed_domains", sa.Text(), nullable=True),
        sa.Column("policy", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("navigation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_browser_sessions_company_status", "browser_sessions", ["company_id", "status"])
    op.create_index("ix_browser_sessions_owner", "browser_sessions", ["employee_id"])

    # ── browser_actions ───────────────────────────────────────────────────────
    op.create_table(
        "browser_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("browser_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("verification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_browser_actions_session_created", "browser_actions", ["session_id", "created_at"])
    op.create_index("ix_browser_actions_company_created", "browser_actions", ["company_id", "created_at"])

    # ── browser_observations ──────────────────────────────────────────────────
    op.create_table(
        "browser_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("browser_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observation_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("screenshot_ref", sa.String(128), nullable=True),
        sa.Column("content_type", sa.String(40), nullable=False, server_default="external_untrusted_content"),
        sa.Column("page_state", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_browser_observations_number", "browser_observations", ["session_id", "observation_number"])

    # ── computer_sessions ─────────────────────────────────────────────────────
    op.create_table(
        "computer_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("workflow_execution_id", sa.Uuid(), sa.ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), sa.ForeignKey("orchestrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("screen", sa.Text(), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("policy", sa.Text(), nullable=True),
        sa.Column("action_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_computer_sessions_company_status", "computer_sessions", ["company_id", "status"])
    op.create_index("ix_computer_sessions_owner", "computer_sessions", ["employee_id"])

    # ── computer_actions ──────────────────────────────────────────────────────
    op.create_table(
        "computer_actions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("computer_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("verification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_computer_actions_session_created", "computer_actions", ["session_id", "created_at"])
    op.create_index("ix_computer_actions_company_created", "computer_actions", ["company_id", "created_at"])

    # ── computer_observations ─────────────────────────────────────────────────
    op.create_table(
        "computer_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("computer_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("observation_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("snapshot", sa.Text(), nullable=True),
        sa.Column("screenshot_ref", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_computer_observations_number", "computer_observations", ["session_id", "observation_number"])

    # ── integration_policies ──────────────────────────────────────────────────
    op.create_table(
        "integration_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("capability_pattern", sa.String(128), nullable=True),
        sa.Column("risk_level_override", sa.String(16), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rate_limit", sa.Text(), nullable=True),
        sa.Column("budget", sa.Text(), nullable=True),
        sa.Column("allowed_domains", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_integration_policies_company_integration", "integration_policies",
        ["company_id", "integration_id"],
    )
    op.create_index(
        "ix_integration_policies_scope", "integration_policies",
        ["company_id", "scope_type", "scope_id"],
    )

    # ── domain_allowlists ─────────────────────────────────────────────────────
    op.create_table(
        "domain_allowlists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("external_integrations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False, server_default="allow"),
        sa.Column("http_methods", sa.Text(), nullable=True),
        sa.Column("allowed_paths", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_domain_allowlists_company_domain", "domain_allowlists", ["company_id", "domain"])
    op.create_index(
        "ix_domain_allowlists_company_scope", "domain_allowlists",
        ["company_id", "scope_type", "scope_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_domain_allowlists_company_scope", table_name="domain_allowlists")
    op.drop_index("ix_domain_allowlists_company_domain", table_name="domain_allowlists")
    op.drop_table("domain_allowlists")
    op.drop_index("ix_integration_policies_scope", table_name="integration_policies")
    op.drop_index("ix_integration_policies_company_integration", table_name="integration_policies")
    op.drop_table("integration_policies")
    op.drop_table("computer_observations")
    op.drop_index("ix_computer_actions_company_created", table_name="computer_actions")
    op.drop_index("ix_computer_actions_session_created", table_name="computer_actions")
    op.drop_table("computer_actions")
    op.drop_index("ix_computer_sessions_owner", table_name="computer_sessions")
    op.drop_index("ix_computer_sessions_company_status", table_name="computer_sessions")
    op.drop_table("computer_sessions")
    op.drop_table("browser_observations")
    op.drop_index("ix_browser_actions_company_created", table_name="browser_actions")
    op.drop_index("ix_browser_actions_session_created", table_name="browser_actions")
    op.drop_table("browser_actions")
    op.drop_index("ix_browser_sessions_owner", table_name="browser_sessions")
    op.drop_index("ix_browser_sessions_company_status", table_name="browser_sessions")
    op.drop_table("browser_sessions")
    op.drop_index("ix_external_events_source_type", table_name="external_events")
    op.drop_index("ix_external_events_company_received", table_name="external_events")
    op.drop_table("external_events")
    op.drop_index("ix_external_action_attempts_action", table_name="external_action_attempts")
    op.drop_table("external_action_attempts")
    op.drop_index("ix_external_actions_gate", table_name="external_actions")
    op.drop_index("ix_external_actions_idem", table_name="external_actions")
    op.drop_index("ix_external_actions_company_integration", table_name="external_actions")
    op.drop_index("ix_external_actions_company_status", table_name="external_actions")
    op.drop_table("external_actions")
    op.drop_index("ix_external_credentials_connection", table_name="external_credentials")
    op.drop_index("ix_external_credentials_company_provider", table_name="external_credentials")
    op.drop_table("external_credentials")
    op.drop_index("ix_integration_capabilities_integration", table_name="integration_capabilities")
    op.drop_table("integration_capabilities")
    op.drop_index("ix_integration_connections_company_status", table_name="integration_connections")
    op.drop_index("ix_integration_connections_integration", table_name="integration_connections")
    op.drop_table("integration_connections")
    op.drop_index("ix_external_integrations_company_status", table_name="external_integrations")
    op.drop_index("ix_external_integrations_company_provider", table_name="external_integrations")
    op.drop_table("external_integrations")