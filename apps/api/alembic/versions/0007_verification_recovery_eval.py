"""Add verification, recovery & evaluation tables.

Phase 6 — Verification, Recovery & Evaluation. Adds the twelve tables that
record the reliability lifecycle layered on top of the Phases 1–5 execution
pipeline: verification (policies/runs/results), recovery (diagnoses/plans/
attempts), escalation (human-in-the-loop), and evaluation (suites/runs/cases/
results/metrics).

Revision ID: 0007_verification_recovery_eval
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_verification_recovery_eval"
down_revision = "0006_orchestrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Verification ──────────────────────────────────────────────────────────
    op.create_table(
        "verification_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("json_config", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(32), nullable=True),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="1"),
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
    op.create_index(
        "ix_verification_policies_scope",
        "verification_policies",
        ["scope_type", "scope_id"],
    )

    op.create_table(
        "verification_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("policy_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_used", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="skipped"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_verification_runs_execution", "verification_runs", ["execution_id"])
    op.create_index("ix_verification_runs_status", "verification_runs", ["status"])
    op.create_index("ix_verification_runs_created", "verification_runs", ["created_at"])

    op.create_table(
        "verification_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("verifier_type", sa.String(32), nullable=True),
        sa.Column("verifier_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("failed_criteria", sa.Text(), nullable=True),
        sa.Column("passed_criteria", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["verification_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_verification_results_execution", "verification_results", ["execution_id"])
    op.create_index("ix_verification_results_status", "verification_results", ["status"])

    # ── Recovery ──────────────────────────────────────────────────────────────
    op.create_table(
        "failure_diagnoses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("recommended_strategy", sa.String(32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_failure_diagnoses_execution", "failure_diagnoses", ["execution_id"])

    op.create_table(
        "recovery_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("strategy", sa.String(32), nullable=True),
        sa.Column("original_plan", sa.Text(), nullable=True),
        sa.Column("revised_plan", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("affected_tasks", sa.Text(), nullable=True),
        sa.Column("safety_check", sa.Text(), nullable=True),
        sa.Column("planner_info", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_recovery_plans_execution", "recovery_plans", ["execution_id"])

    op.create_table(
        "recovery_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(32), nullable=False, server_default="detected"),
        sa.Column("strategy", sa.String(32), nullable=True),
        sa.Column("verification_result_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["recovery_plans.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recovery_attempts_execution", "recovery_attempts", ["execution_id"])
    op.create_index(
        "ix_recovery_attempts_execution_created",
        "recovery_attempts",
        ["execution_id", "created_at"],
    )

    op.create_table(
        "escalations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("orchestration_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_id", sa.Uuid(), nullable=True),
        sa.Column("issue", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("state", sa.String(32), nullable=False, server_default="pending_human_review"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_escalations_execution", "escalations", ["execution_id"])
    op.create_index("ix_escalations_state", "escalations", ["state"])
    op.create_index("ix_escalations_created", "escalations", ["created_at"])

    # ── Evaluation ────────────────────────────────────────────────────────────
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("evaluation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_cases_evaluation", "evaluation_cases", ["evaluation_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("evaluation_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_runs_evaluation", "evaluation_runs", ["evaluation_id"])
    op.create_index("ix_evaluation_runs_created", "evaluation_runs", ["created_at"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("actual_outcome", sa.Text(), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_id"], ["evaluation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_results_run", "evaluation_results", ["run_id"])

    op.create_table(
        "evaluation_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evaluation_metrics_run", "evaluation_metrics", ["run_id"])


def downgrade() -> None:
    op.drop_table("evaluation_metrics")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluations")
    op.drop_table("escalations")
    op.drop_table("recovery_attempts")
    op.drop_table("recovery_plans")
    op.drop_table("failure_diagnoses")
    op.drop_table("verification_results")
    op.drop_table("verification_runs")
    op.drop_table("verification_policies")