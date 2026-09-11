"""0010 — AI Company layer tables

Phase 8 — the organizational layer above the AI Employee OS. Adds the company,
department, organizational role/membership, and organizational-intelligence
tables (goals, KPIs, budgets, policies, decisions, risks, alerts, reports,
audit/timeline events).

Every enum is stored as a plain String column (project convention —
``native_enum=False``) so PostgreSQL does not create native enum types and the
ORM's ``create_constraint=False`` ``Enum`` columns map cleanly without a
``DuplicateObject`` on fresh databases.

Revision ID: 0010_company_layer
Revises: 0009_ai_employee_os
Create Date: 2026-09-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_company_layer"
down_revision = "0009_ai_employee_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── companies ─────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("slug", sa.String(160), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mission", sa.Text(), nullable=True),
        sa.Column("vision", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("values", sa.Text(), nullable=True),
        sa.Column("strategic_priorities", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("policies", sa.Text(), nullable=True),
        sa.Column("resource_limits", sa.Text(), nullable=True),
        sa.Column("budget_config", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── departments ───────────────────────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mission", sa.Text(), nullable=True),
        sa.Column("manager_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("parent_department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_departments_company_parent", "departments", ["company_id", "parent_department_id"])
    op.create_index("ix_departments_status", "departments", ["status"])

    # ── organizational_roles ──────────────────────────────────────────────────
    op.create_table(
        "organizational_roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("required_skills", sa.Text(), nullable=True),
        sa.Column("authority_level", sa.String(32), nullable=False, server_default="individual_contributor"),
        sa.Column("authority_scope", sa.Text(), nullable=True),
        sa.Column("default_policies", sa.Text(), nullable=True),
        sa.Column("kpis", sa.Text(), nullable=True),
        sa.Column("compatible_departments", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── organizational_memberships ────────────────────────────────────────────
    op.create_table(
        "organizational_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("organizational_roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("responsibility", sa.String(16), nullable=False, server_default="ic"),
        sa.Column("manager_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "employee_id", name="uq_org_memberships_company_employee"),
    )
    op.create_index("ix_org_memberships_company", "organizational_memberships", ["company_id"])
    op.create_index("ix_org_memberships_department", "organizational_memberships", ["department_id"])
    op.create_index("ix_org_memberships_manager", "organizational_memberships", ["manager_id"])

    # ── org_goals ─────────────────────────────────────────────────────────────
    op.create_table(
        "org_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("parent_goal_id", sa.Uuid(), sa.ForeignKey("org_goals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target", sa.String(256), nullable=True),
        sa.Column("metric", sa.String(128), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_goals_company_scope", "org_goals", ["company_id", "scope_type", "scope_id"])
    op.create_index("ix_org_goals_parent", "org_goals", ["parent_goal_id"])

    # ── kpis / kpi_values ─────────────────────────────────────────────────────
    op.create_table(
        "kpis",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="operational"),
        sa.Column("source_metric", sa.String(64), nullable=False),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("frequency", sa.String(16), nullable=True),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kpis_company_scope", "kpis", ["company_id", "scope_type", "scope_id"])
    op.create_index("ix_kpis_category", "kpis", ["category"])

    op.create_table(
        "kpi_values",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kpi_id", sa.Uuid(), sa.ForeignKey("kpis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("variance", sa.Float(), nullable=True),
        sa.Column("trend", sa.String(16), nullable=True),
        sa.Column("period_label", sa.String(32), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_kpi_values_kpi_recorded", "kpi_values", ["kpi_id", "recorded_at"])

    # ── budgets ───────────────────────────────────────────────────────────────
    op.create_table(
        "budgets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_limit", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("allocated", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reserved", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("spent", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_used", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_budgets_company_scope", "budgets", ["company_id", "scope_type", "scope_id"])

    # ── policies ──────────────────────────────────────────────────────────────
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope_type", sa.String(16), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_policies_scope", "policies", ["company_id", "scope_type", "scope_id", "key"])

    # ── decisions / decision_reviews ──────────────────────────────────────────
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_maker_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("options", sa.Text(), nullable=False),
        sa.Column("selected_option", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("risk", sa.Text(), nullable=True),
        sa.Column("budget_impact", sa.Text(), nullable=True),
        sa.Column("required_authority", sa.String(32), nullable=False, server_default="executive"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_decisions_company_status", "decisions", ["company_id", "status"])

    op.create_table(
        "decision_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("decision_id", sa.Uuid(), sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(32), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("previous_status", sa.String(32), nullable=True),
        sa.Column("next_status", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_decision_reviews_decision", "decision_reviews", ["decision_id"])

    # ── risks ─────────────────────────────────────────────────────────────────
    op.create_table(
        "risks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("impact", sa.String(256), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_risks_company_scope", "risks", ["company_id", "scope_type", "scope_id"])
    op.create_index("ix_risks_severity", "risks", ["severity"])

    # ── alerts ────────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="company"),
        sa.Column("scope_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="warning"),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alerts_company_severity", "alerts", ["company_id", "severity", "status"])

    # ── company_reports ───────────────────────────────────────────────────────
    op.create_table(
        "company_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(32), nullable=False, server_default="weekly"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("highlights", sa.Text(), nullable=True),
        sa.Column("risks", sa.Text(), nullable=True),
        sa.Column("blockers", sa.Text(), nullable=True),
        sa.Column("goal_progress", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("verification_status", sa.String(16), nullable=False, server_default="unverified"),
        sa.Column("verification_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_reports_company_created", "company_reports", ["company_id", "created_at"])

    # ── organizational_events ─────────────────────────────────────────────────
    op.create_table(
        "organizational_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_org_events_company_created", "organizational_events", ["company_id", "created_at"])
    op.create_index("ix_org_events_action", "organizational_events", ["action"])


def downgrade() -> None:
    op.drop_index("ix_org_events_action", table_name="organizational_events")
    op.drop_index("ix_org_events_company_created", table_name="organizational_events")
    op.drop_table("organizational_events")
    op.drop_index("ix_company_reports_company_created", table_name="company_reports")
    op.drop_table("company_reports")
    op.drop_index("ix_alerts_company_severity", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_risks_severity", table_name="risks")
    op.drop_index("ix_risks_company_scope", table_name="risks")
    op.drop_table("risks")
    op.drop_index("ix_decision_reviews_decision", table_name="decision_reviews")
    op.drop_table("decision_reviews")
    op.drop_index("ix_decisions_company_status", table_name="decisions")
    op.drop_table("decisions")
    op.drop_index("ix_policies_scope", table_name="policies")
    op.drop_table("policies")
    op.drop_index("ix_budgets_company_scope", table_name="budgets")
    op.drop_table("budgets")
    op.drop_index("ix_kpi_values_kpi_recorded", table_name="kpi_values")
    op.drop_table("kpi_values")
    op.drop_index("ix_kpis_category", table_name="kpis")
    op.drop_index("ix_kpis_company_scope", table_name="kpis")
    op.drop_table("kpis")
    op.drop_index("ix_org_goals_parent", table_name="org_goals")
    op.drop_index("ix_org_goals_company_scope", table_name="org_goals")
    op.drop_table("org_goals")
    op.drop_index("ix_org_memberships_manager", table_name="organizational_memberships")
    op.drop_index("ix_org_memberships_department", table_name="organizational_memberships")
    op.drop_index("ix_org_memberships_company", table_name="organizational_memberships")
    op.drop_table("organizational_memberships")
    op.drop_table("organizational_roles")
    op.drop_index("ix_departments_status", table_name="departments")
    op.drop_index("ix_departments_company_parent", table_name="departments")
    op.drop_table("departments")
    op.drop_table("companies")