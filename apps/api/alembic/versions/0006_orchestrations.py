"""Add multi-agent orchestration tables.

Phase 5 — Multi-Agent Orchestration. Adds the seven tables that record a
single multi-agent run end-to-end: `orchestrations` (the objective + lifecycle
+ final result), `orchestration_tasks` (the decomposed plan), `agent_assignments`
(agent→task), `agent_messages` (the controlled inter-agent bus), `orchestration_results`
(aggregated outputs), `orchestration_context` (shared facts/decisions), and
`agent_reviews` (agent-to-agent review).

Revision ID: 0006_orchestrations
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_orchestrations"
down_revision = "0005_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("strategy", sa.String(64), nullable=False, server_default="deterministic"),
        sa.Column("selected_agents", sa.Text(), nullable=True),
        sa.Column("execution_graph", sa.Text(), nullable=True),
        sa.Column("final_result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
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
    )
    op.create_index("ix_orchestrations_status", "orchestrations", ["status"])
    op.create_index("ix_orchestrations_created", "orchestrations", ["created_at"])

    op.create_table(
        "orchestration_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_capabilities", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("input_context", sa.Text(), nullable=True),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_orchestration_tasks_orchestration",
        "orchestration_tasks",
        ["orchestration_id", "status"],
    )
    op.create_index("ix_orchestration_tasks_agent", "orchestration_tasks", ["agent_id"])

    op.create_table(
        "agent_assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(64), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("input_context", sa.Text(), nullable=True),
        sa.Column("output_data", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agent_execution_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["orchestration_tasks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_assignments_orchestration", "agent_assignments", ["orchestration_id"])
    op.create_index("ix_agent_assignments_agent", "agent_assignments", ["agent_id"])
    op.create_index("ix_agent_assignments_task", "agent_assignments", ["task_id"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("sender_agent_id", sa.Uuid(), nullable=True),
        sa.Column("recipient_agent_id", sa.Uuid(), nullable=True),
        sa.Column("message_type", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_agent_messages_orchestration_created",
        "agent_messages",
        ["orchestration_id", "created_at"],
    )
    op.create_index("ix_agent_messages_correlation", "agent_messages", ["correlation_id"])
    op.create_index("ix_agent_messages_recipient", "agent_messages", ["recipient_agent_id"])

    op.create_table(
        "orchestration_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("assignment_id", sa.Uuid(), nullable=True),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("structured_data", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_orchestration_results_orchestration", "orchestration_results", ["orchestration_id"]
    )
    op.create_index("ix_orchestration_results_agent", "orchestration_results", ["agent_id"])

    op.create_table(
        "orchestration_context",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="shared_fact"),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_orchestration_context_orchestration", "orchestration_context", ["orchestration_id"]
    )

    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("reviewer_agent_id", sa.Uuid(), nullable=False),
        sa.Column("reviewee_agent_id", sa.Uuid(), nullable=True),
        sa.Column("request_content", sa.Text(), nullable=True),
        sa.Column("response_content", sa.Text(), nullable=True),
        sa.Column("verdict", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["orchestration_id"], ["orchestrations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_agent_reviews_orchestration", "agent_reviews", ["orchestration_id"])


def downgrade() -> None:
    op.drop_table("agent_reviews")
    op.drop_table("orchestration_context")
    op.drop_table("orchestration_results")
    op.drop_table("agent_messages")
    op.drop_table("agent_assignments")
    op.drop_table("orchestration_tasks")
    op.drop_table("orchestrations")