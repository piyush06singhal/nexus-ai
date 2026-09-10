"""Add verification policy columns to workflow & orchestration.

Phase 6 — Verification, Recovery & Evaluation (integration). Adds the
verification-policy hook columns onto the Phase 3 / Phase 5 execution entities
so the workflow engine and orchestrator can run verification on step / task
output without duplicating verification logic:

- ``workflow_steps.verification_policy`` — JSON policy/criteria for a step.
- ``step_executions.verification_run_id`` — the verification run for a step.
- ``orchestrations.verification_policy`` — JSON policy/criteria for an orchestration.

Revision ID: 0008_integration_verification
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_integration_verification"
down_revision = "0007_verification_recovery_eval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_steps",
        sa.Column("verification_policy", sa.Text(), nullable=True),
    )
    op.add_column(
        "step_executions",
        sa.Column("verification_run_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "orchestrations",
        sa.Column("verification_policy", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orchestrations", "verification_policy")
    op.drop_column("step_executions", "verification_run_id")
    op.drop_column("workflow_steps", "verification_policy")