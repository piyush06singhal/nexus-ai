"""phase1_agent_runtime

Revision ID: 0002_agent_runtime
Revises: 0001_baseline
Create Date: 2026-09-09

Expands the ``agents`` table with role, status, and model configuration,
and adds the ``tasks`` and ``agent_executions`` tables for Phase 1 (Agent
Runtime).
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_agent_runtime"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- agents: add role, status, system prompt, and model configuration --
    op.add_column("agents", sa.Column("role", sa.String(length=64), nullable=True))
    op.add_column("agents", sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"))
    op.add_column("agents", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("provider", sa.String(length=64), nullable=False, server_default="openai"))
    op.add_column("agents", sa.Column("model_name", sa.String(length=128), nullable=False, server_default="gpt-4o"))
    op.add_column("agents", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("agents", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("model_params", sa.Text(), nullable=True))

    # -- tasks --
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "assigned_agent_id",
            sa.Uuid(),
            sa.ForeignKey("agents.id", name=op.f("fk_tasks_assigned_agent_id_agents"), ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index(op.f("ix_tasks_assigned_agent_id"), "tasks", ["assigned_agent_id"])

    # -- agent_executions --
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_executions")),
    )
    op.create_index(op.f("ix_agent_executions_task_id"), "agent_executions", ["task_id"])
    op.create_index(op.f("ix_agent_executions_agent_id"), "agent_executions", ["agent_id"])


def downgrade() -> None:
    op.drop_table("agent_executions")
    op.drop_table("tasks")
    op.drop_column("agents", "model_params")
    op.drop_column("agents", "max_tokens")
    op.drop_column("agents", "temperature")
    op.drop_column("agents", "model_name")
    op.drop_column("agents", "provider")
    op.drop_column("agents", "system_prompt")
    op.drop_column("agents", "status")
    op.drop_column("agents", "role")