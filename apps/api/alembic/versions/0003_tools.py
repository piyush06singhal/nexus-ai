"""Add tool_calls and agent_tool_permissions tables.

Phase 2 — Tool & Action System:
  - ``tool_calls`` records every tool invocation within an agent execution.
  - ``agent_tool_permissions`` controls per-agent tool access.

Revision ID: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002_agent_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tool_calls — records each tool invocation.
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=True),
        sa.Column(
            "result_status",
            sa.String(16),
            nullable=False,
            server_default="success",
        ),
        sa.Column("result_data", sa.Text(), nullable=True),
        sa.Column("result_error", sa.Text(), nullable=True),
        sa.Column("execution_time_ms", sa.Float(), nullable=True),
        sa.Column("iteration", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # agent_tool_permissions — per-agent tool access control.
    op.create_table(
        "agent_tool_permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agent_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_tool_permissions")
    op.drop_table("tool_calls")
