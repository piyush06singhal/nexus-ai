"""Add pgvector semantic-memory column (PostgreSQL only; a no-op elsewhere).

Tier B — pgvector-backed semantic memory:
  - ``CREATE EXTENSION IF NOT EXISTS vector`` (requires the pgvector extension
    to be present in the Postgres image; docker-compose.yml and CI both use the
    ``pgvector/pgvector`` image so it is).
  - ``memories.embedding_vector vector(1536)`` enables native cosine-distance
    ranking. The portable ``embedding`` Text column (JSON-array float vector,
    used by the Python-cosine path) is preserved unchanged — retrieval prefers
    the native column when it exists and falls back to the Python path
    otherwise (SQLite in tests/dev always falls back).
  - An HNSW index (``vector_cosine_ops``) makes ``<=>`` nearest-neighbour
    lookups fast at scale.
  - A one-time backfill copies any pre-existing portable embeddings into the
    native column so the feature is immediately useful after migration.

Dialect guard: on non-PostgreSQL engines (SQLite dev/test) this revision is a
no-op, keeping the keyless SQLite test suite and CI migration round-trip green.

Revision ID: 0015_pgvector
Revises: 0014_phase12_sim_opt_mkt
Create Date: 2026-09-14
"""

revision = "0015_pgvector"
down_revision = "0014_phase12_sim_opt_mkt"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    if not _is_postgres(bind):
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding_vector vector(1536)"
    )
    # One-time backfill from the portable JSON column (text) into the native
    # vector column; our own writes are always valid JSON float arrays.
    op.execute(
        "UPDATE memories SET embedding_vector = embedding::vector "
        "WHERE embedding IS NOT NULL AND embedding_vector IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_memories_embedding_vector "
        "ON memories USING hnsw (embedding_vector vector_cosine_ops)"
    )


def downgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    if not _is_postgres(bind):
        return

    op.execute("DROP INDEX IF EXISTS ix_memories_embedding_vector")
    op.execute("ALTER TABLE memories DROP COLUMN IF EXISTS embedding_vector")
    op.execute("DROP EXTENSION IF EXISTS vector")