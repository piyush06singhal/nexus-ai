"""Add workflow orchestration tables.

Phase 3 — Workflow Orchestration:
  - ``workflows`` — durable, versioned orchestration definitions.
  - ``workflow_steps`` — a single operation within a workflow's graph.
  - ``workflow_triggers`` — schedule/event/webhook triggers.
  - ``workflow_executions`` — a single run of a workflow.
  - ``step_executions`` — per-step records within an execution.

Revision ID: 0004
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workflows — the durable orchestration definition.
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration", sa.Text(), nullable=True),  # JSON blob
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_workflows_name"),
    )

    # workflow_steps — single operations within a workflow graph.
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Uuid(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "step_type",
            sa.String(16),
            nullable=False,
        ),
        sa.Column("configuration", sa.Text(), nullable=True),  # JSON blob
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dependencies", sa.Text(), nullable=True),  # JSON list
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("retry_policy", sa.Text(), nullable=True),  # JSON blob
        sa.Column(
            "idempotency",
            sa.String(32),
            nullable=False,
            server_default="non_idempotent",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_workflow_steps_workflow_id", "workflow_id"),
        sa.Index("ix_workflow_steps_workflow_name", "workflow_id", "name"),
    )

    # workflow_triggers — schedule/event/webhook triggers.
    op.create_table(
        "workflow_triggers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Uuid(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(16), nullable=False),
        sa.Column("configuration", sa.Text(), nullable=True),  # JSON blob
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_workflow_triggers_workflow_id", "workflow_id"),
        sa.Index("ix_workflow_triggers_next_run", "enabled", "next_run_at"),
    )

    # workflow_executions — a single run of a workflow.
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workflow_id",
            sa.Uuid(),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("trigger_type", sa.String(32), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=True),  # JSON blob
        sa.Column("output_data", sa.Text(), nullable=True),  # JSON blob
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_workflow_executions_workflow_id", "workflow_id"),
        sa.Index("ix_workflow_executions_status", "status"),
    )

    # step_executions — per-step records within an execution.
    op.create_table(
        "step_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workflow_execution_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workflow_step_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_steps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("input_data", sa.Text(), nullable=True),  # JSON blob
        sa.Column("output_data", sa.Text(), nullable=True),  # JSON blob
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_step_executions_workflow_execution_id", "workflow_execution_id"),
        sa.Index("ix_step_executions_workflow_step", "workflow_execution_id", "workflow_step_id"),
    )


def downgrade() -> None:
    op.drop_table("step_executions")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_triggers")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")