"""Add memories table.

Phase 4 — Memory System:
  - ``memories`` holds all five memory kinds (working, episodic, semantic,
    procedural, structured) in one table discriminated by ``type``, scoped by
    ``namespace``, and optionally owned by an agent with provenance to its
    source (e.g. an agent execution).

Revision ID: 0005_memories
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_memories"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("namespace", sa.String(128), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("owner_type", sa.String(16), nullable=False, server_default="system"),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("source_type", sa.String(16), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(256), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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

    op.create_index("ix_memories_namespace", "memories", ["namespace"])
    op.create_index("ix_memories_namespace_owner", "memories", ["namespace", "owner_id"])
    op.create_index("ix_memories_namespace_type", "memories", ["namespace", "type"])
    op.create_index("ix_memories_namespace_status", "memories", ["namespace", "status"])
    op.create_index("ix_memories_expiry", "memories", ["expires_at", "status"])
    op.create_index("ix_memories_namespace_created", "memories", ["namespace", "created_at"])


def downgrade() -> None:
    op.drop_table("memories")
