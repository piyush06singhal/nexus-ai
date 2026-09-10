"""0009 — AI Employee OS tables

Revision ID: 0009_ai_employee_os
Revises: 0008_integration_verification
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_ai_employee_os"
down_revision = "0008_integration_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ai_employees ───────────────────────────────────────────────────
    op.create_table(
        "ai_employees",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("display_name", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(64), nullable=False, server_default="general"),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("availability", sa.String(32), nullable=False, server_default="unavailable"),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        # Structured JSON fields
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column("tools", sa.Text(), nullable=True),
        sa.Column("permissions", sa.Text(), nullable=True),
        sa.Column("memory_namespace", sa.String(128), nullable=True),
        sa.Column("work_preferences", sa.Text(), nullable=True),
        sa.Column("workload_config", sa.Text(), nullable=True),
        sa.Column("performance_profile", sa.Text(), nullable=True),
        sa.Column("policies", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_employees_agent_id", "ai_employees", ["agent_id"])
    op.create_index("ix_ai_employees_status", "ai_employees", ["status"])
    op.create_index("ix_ai_employees_role", "ai_employees", ["role"])

    # ── employee_goals ─────────────────────────────────────────────────
    op.create_table(
        "employee_goals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target", sa.String(256), nullable=True),
        sa.Column("metric", sa.String(128), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="not_started"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("parent_goal_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_employee_goals_employee_id", "employee_goals", ["employee_id"])
    op.create_index("ix_employee_goals_emp_status", "employee_goals", ["employee_id", "status"])

    # ── employee_budgets ───────────────────────────────────────────────
    op.create_table(
        "employee_budgets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("monthly_limit", sa.Float(), nullable=False, server_default="50.0"),
        sa.Column("task_limit", sa.Float(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_used", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("tool_calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── employee_reviews ───────────────────────────────────────────────
    op.create_table(
        "employee_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("strengths", sa.Text(), nullable=True),
        sa.Column("weaknesses", sa.Text(), nullable=True),
        sa.Column("skill_changes", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(64), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_reviews_employee_id", "employee_reviews", ["employee_id"])
    op.create_index("ix_employee_reviews_emp_created", "employee_reviews", ["employee_id", "created_at"])

    # ── employee_templates ─────────────────────────────────────────────
    op.create_table(
        "employee_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(64), nullable=False, server_default="general"),
        sa.Column("skills", sa.Text(), nullable=True),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("tools", sa.Text(), nullable=True),
        sa.Column("policies", sa.Text(), nullable=True),
        sa.Column("verification_policy", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── employee_audit_log ─────────────────────────────────────────────
    op.create_table(
        "employee_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_audit_emp_created", "employee_audit_log", ["employee_id", "created_at"])
    op.create_index("ix_employee_audit_action", "employee_audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("employee_audit_log")
    op.drop_table("employee_templates")
    op.drop_table("employee_reviews")
    op.drop_table("employee_budgets")
    op.drop_table("employee_goals")
    op.drop_table("ai_employees")