"""0013 security governance production hardening

Phase 11 — Security, Governance & Production Hardening: the identity →
authorization → policy → resources → approval → action → verification →
audit → observability → recovery chain.

Adds 30 additive tables (nothing existing is altered):
identities, users, auth_sessions, roles, permissions, role_permissions,
identity_roles, policy_rules, policy_decisions, secrets, secret_versions,
encryption_keys, audit_events, security_events, security_alerts, incidents,
incident_actions, system_flags, break_glass_access, resource_limits,
resource_usage, rate_limit_records, feature_flags, dead_letter_jobs,
idempotency_keys, system_health_records, data_classifications,
retention_policies, governance_controls, context_authorities.

All tables are defined by ``app/db/models/security.py``; we create them from
that metadata directly so DDL can never drift from the models (this matches the
project's hand-written migration convention — a pure additive revision, no
ALTERs to existing Phase 0-10 tables).

Revision ID: 0013_security_governance
Revises: 0012_external_integrations
Create Date: 2026-09-12
"""

from collections.abc import Iterable

import sqlalchemy as sa

from alembic import op
from app.db.session import Base

revision = "0013_security_governance"
down_revision = "0012_external_integrations"
branch_labels = None
depends_on = None

# Every table introduced by this migration (must exactly match the models in
# app/db/models/security.py; a mismatch fails loudly at runtime).
_SECURITY_TABLES: Iterable[str] = (
    "identities",
    "users",
    "auth_sessions",
    "roles",
    "permissions",
    "role_permissions",
    "identity_roles",
    "policy_rules",
    "policy_decisions",
    "secrets",
    "secret_versions",
    "encryption_keys",
    "audit_events",
    "security_events",
    "security_alerts",
    "incidents",
    "incident_actions",
    "system_flags",
    "break_glass_access",
    "resource_limits",
    "resource_usage",
    "rate_limit_records",
    "feature_flags",
    "dead_letter_jobs",
    "idempotency_keys",
    "system_health_records",
    "data_classifications",
    "retention_policies",
    "governance_controls",
    "context_authorities",
)


def _tables() -> list[sa.Table]:
    missing = [n for n in _SECURITY_TABLES if n not in Base.metadata.tables]
    if missing:
        raise RuntimeError(f"Security tables missing from metadata: {missing}")
    return [Base.metadata.tables[n] for n in _SECURITY_TABLES]


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    # ``create_all`` is idempotent per-table but we guard explicitly to keep the
    # behaviour obvious when this revision runs over a partially-applied DB.
    to_create = [t for t in _tables() if t.name not in existing]
    Base.metadata.create_all(bind=bind, tables=to_create)
    _ensure_incident_id_column()


def _ensure_incident_id_column() -> None:
    """Add ``security_alerts.incident_id`` idempotently if missing.

    ``create_all`` only emits CREATE TABLE for tables that don't exist, so a
    column added to the model after this revision first ran (incident-detail
    linkage) would silently never be applied on an already-migrated DB.
    Introspect and add the column + index so the fresh path, the
    already-applied path, and re-runs all converge on the model.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "security_alerts" not in inspector.get_table_names():
        return  # table is created by create_all above and already has the column
    if any(c["name"] == "incident_id" for c in inspector.get_columns("security_alerts")):
        return
    op.add_column(
        "security_alerts",
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey(
                "incidents.id",
                ondelete="SET NULL",
                name="fk_security_alerts_incident_id_incidents",
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_security_alerts_incident_id", "security_alerts", ["incident_id"])


def downgrade() -> None:
    bind = op.get_bind()
    # Plain ``DROP TABLE IF EXISTS … CASCADE`` is metadata-independent (robust
    # to columns added after this revision first ran) and order-independent
    # (the security tables form a small FK cycle — security_alerts ⇄ incidents —
    # and all cross-references are documented internal to this set, so CASCADE
    # cannot reach Phase 0-10 tables).
    for t in reversed(_tables()):
        op.execute(f'DROP TABLE IF EXISTS "{t.name}" CASCADE')
