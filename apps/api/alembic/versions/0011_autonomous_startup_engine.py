"""0011 — Autonomous Startup Engine tables

Phase 9 — the mission/autonomy layer above the AI Company Layer (Phase 8).
Adds the mission system, strategic/startup planning, organizational blueprint
and workforce-planning tables, products/projects, the execution-plan and
operating-cycle machinery, company-state snapshots, feedback/lessons,
approval gates, per-company autonomy policies, mission traceability graph
edges, resource allocations, and priority decisions.

Enums are stored as plain String columns (project convention —
``native_enum=False``) so PostgreSQL does not create native enum types.

``operating_cycles`` and ``company_state_snapshots`` reference each other
(cycle → its snapshot, snapshot → its cycle) — a nullable circular reference.
Both tables are created without those two foreign keys and the constraints are
added afterwards so the migration is valid on both PostgreSQL and SQLite.

Revision ID: 0011_autonomous_startup_engine
Revises: 0010_company_layer
Create Date: 2026-09-11
"""

import sqlalchemy as sa

from alembic import op

revision = "0011_autonomous_startup_engine"
down_revision = "0010_company_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── missions ───────────────────────────────────────────────────────────────
    op.create_table(
        "missions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mission_statement", sa.Text(), nullable=False),
        sa.Column("desired_outcome", sa.Text(), nullable=True),
        sa.Column("target_market", sa.Text(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("success_criteria", sa.Text(), nullable=True),
        sa.Column("strategic_context", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("validation", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_missions_company_status", "missions", ["company_id", "status"])
    op.create_index("ix_missions_owner", "missions", ["owner_id"])

    # ── strategic_plans ────────────────────────────────────────────────────────
    op.create_table(
        "strategic_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vision", sa.Text(), nullable=True),
        sa.Column("objectives", sa.Text(), nullable=True),
        sa.Column("priorities", sa.Text(), nullable=True),
        sa.Column("expected_outcomes", sa.Text(), nullable=True),
        sa.Column("assumptions", sa.Text(), nullable=True),
        sa.Column("risks", sa.Text(), nullable=True),
        sa.Column("milestones", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("resource_estimates", sa.Text(), nullable=True),
        sa.Column("success_metrics", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_strategic_plans_mission", "strategic_plans", ["mission_id"])

    # ── startup_plans ──────────────────────────────────────────────────────────
    op.create_table(
        "startup_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategic_plan_id", sa.Uuid(), sa.ForeignKey("strategic_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("business_objectives", sa.Text(), nullable=True),
        sa.Column("product_objectives", sa.Text(), nullable=True),
        sa.Column("market_objectives", sa.Text(), nullable=True),
        sa.Column("organization_objectives", sa.Text(), nullable=True),
        sa.Column("operational_objectives", sa.Text(), nullable=True),
        sa.Column("milestones", sa.Text(), nullable=True),
        sa.Column("departments", sa.Text(), nullable=True),
        sa.Column("roles", sa.Text(), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("initial_products", sa.Text(), nullable=True),
        sa.Column("initial_projects", sa.Text(), nullable=True),
        sa.Column("kpi_targets", sa.Text(), nullable=True),
        sa.Column("budget_allocation", sa.Text(), nullable=True),
        sa.Column("execution_priorities", sa.Text(), nullable=True),
        sa.Column("approval_requirements", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("review", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_startup_plans_mission", "startup_plans", ["mission_id"])
    op.create_index("ix_startup_plans_status", "startup_plans", ["status"])

    # ── organizational_blueprints ──────────────────────────────────────────────
    op.create_table(
        "organizational_blueprints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("startup_plan_id", sa.Uuid(), sa.ForeignKey("startup_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default="Default blueprint"),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blueprints_startup_plan", "organizational_blueprints", ["startup_plan_id"])

    # ── workforce_plans ────────────────────────────────────────────────────────
    op.create_table(
        "workforce_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("startup_plan_id", sa.Uuid(), sa.ForeignKey("startup_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demand", sa.Text(), nullable=False),
        sa.Column("approval_policy", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workforce_plans_startup_plan", "workforce_plans", ["startup_plan_id"])

    # ── products ───────────────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(64), nullable=True),
        sa.Column("target_users", sa.Text(), nullable=True),
        sa.Column("value_proposition", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="idea"),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("strategic_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget", sa.Text(), nullable=True),
        sa.Column("success_metrics", sa.Text(), nullable=True),
        sa.Column("launch_criteria", sa.Text(), nullable=True),
        sa.Column("validation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_products_company_status", "products", ["company_id", "status"])
    op.create_index("ix_products_owner", "products", ["owner_id"])

    # ── startup_projects ───────────────────────────────────────────────────────
    op.create_table(
        "startup_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget", sa.Text(), nullable=True),
        sa.Column("milestones", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("success_criteria", sa.Text(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_startup_projects_company_status", "startup_projects", ["company_id", "status"])
    op.create_index("ix_startup_projects_product", "startup_projects", ["product_id"])
    op.create_index("ix_startup_projects_owner", "startup_projects", ["owner_id"])

    # ── company_state_snapshots (cycle_id FK added after operating_cycles) ─────
    op.create_table(
        "company_state_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", sa.Uuid(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("dimensions", sa.Text(), nullable=False),
        sa.Column("explanations", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_snapshots_company_computed", "company_state_snapshots", ["company_id", "computed_at"]
    )

    # ── operating_cycles (state_snapshot_id FK added after both exist) ─────────
    op.create_table(
        "operating_cycles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("startup_plan_id", sa.Uuid(), sa.ForeignKey("startup_plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cycle_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="initializing"),
        sa.Column("stages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("state_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("decisions", sa.Text(), nullable=True),
        sa.Column("actions", sa.Text(), nullable=True),
        sa.Column("kpis", sa.Text(), nullable=True),
        sa.Column("failures", sa.Text(), nullable=True),
        sa.Column("recovery", sa.Text(), nullable=True),
        sa.Column("approvals", sa.Text(), nullable=True),
        sa.Column("resource_usage", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_operating_cycles_company_number", "operating_cycles", ["company_id", "cycle_number"])
    op.create_index("ix_operating_cycles_mission", "operating_cycles", ["mission_id"])
    op.create_index("ix_operating_cycles_status", "operating_cycles", ["status"])

    # Resolve the nullable circular reference between cycles and snapshots.
    op.create_foreign_key(
        "fk_operating_cycles_state_snapshot",
        "operating_cycles",
        "company_state_snapshots",
        ["state_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_snapshots_cycle",
        "company_state_snapshots",
        "operating_cycles",
        ["cycle_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── startup_feedback ───────────────────────────────────────────────────────
    op.create_table(
        "startup_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("objective_type", sa.Text(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("related_goal_id", sa.Uuid(), nullable=True),
        sa.Column("related_project_id", sa.Uuid(), nullable=True),
        sa.Column("related_product_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_startup_feedback_company_created", "startup_feedback", ["company_id", "created_at"])
    op.create_index("ix_startup_feedback_mission", "startup_feedback", ["mission_id"])

    # ── startup_lessons ────────────────────────────────────────────────────────
    op.create_table(
        "startup_lessons",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("missions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lesson_type", sa.String(32), nullable=False, server_default="lesson"),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_startup_lessons_company_created", "startup_lessons", ["company_id", "created_at"])
    op.create_index("ix_startup_lessons_mission", "startup_lessons", ["mission_id"])

    # ── approval_gates ─────────────────────────────────────────────────────────
    op.create_table(
        "approval_gates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gate_type", sa.String(40), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("requested_action", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("affected_entities", sa.Text(), nullable=True),
        sa.Column("resource_impact", sa.Text(), nullable=True),
        sa.Column("requester_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approver_id", sa.Uuid(), sa.ForeignKey("ai_employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiration", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_approval_gates_company_status", "approval_gates", ["company_id", "status"])
    op.create_index("ix_approval_gates_requester", "approval_gates", ["requester_id"])
    op.create_index("ix_approval_gates_approver", "approval_gates", ["approver_id"])

    # ── autonomy_policies ──────────────────────────────────────────────────────
    op.create_table(
        "autonomy_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("autonomy_level", sa.String(32), nullable=False, server_default="bounded_autonomy"),
        sa.Column("allow_matrix", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("max_employees", sa.Integer(), nullable=True),
        sa.Column("max_departments", sa.Integer(), nullable=True),
        sa.Column("max_budget", sa.Float(), nullable=True),
        sa.Column("max_concurrent_work", sa.Integer(), nullable=True),
        sa.Column("max_provisioning_rate", sa.Integer(), nullable=True),
        sa.Column("require_approval_for", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", name="uq_autonomy_policies_company"),
    )
    op.create_index("ix_autonomy_policies_level", "autonomy_policies", ["autonomy_level"])

    # ── mission_graph_edges ────────────────────────────────────────────────────
    op.create_table(
        "mission_graph_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("relation", sa.String(32), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relation",
            name="uq_mission_graph_edge",
        ),
    )
    op.create_index("ix_mission_graph_source", "mission_graph_edges", ["source_type", "source_id"])
    op.create_index("ix_mission_graph_target", "mission_graph_edges", ["target_type", "target_id"])
    op.create_index("ix_mission_graph_company", "mission_graph_edges", ["company_id"])

    # ── resource_allocations ───────────────────────────────────────────────────
    op.create_table(
        "resource_allocations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(128), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resource_allocations_company", "resource_allocations", ["company_id"])
    op.create_index(
        "ix_resource_allocations_target", "resource_allocations", ["target_type", "target_id"]
    )

    # ── priority_decisions ─────────────────────────────────────────────────────
    op.create_table(
        "priority_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Text(), nullable=False),
        sa.Column("factors", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_priority_decisions_company", "priority_decisions", ["company_id"])
    op.create_index(
        "ix_priority_decisions_target", "priority_decisions", ["target_type", "target_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_priority_decisions_target", table_name="priority_decisions")
    op.drop_index("ix_priority_decisions_company", table_name="priority_decisions")
    op.drop_table("priority_decisions")
    op.drop_index("ix_resource_allocations_target", table_name="resource_allocations")
    op.drop_index("ix_resource_allocations_company", table_name="resource_allocations")
    op.drop_table("resource_allocations")
    op.drop_index("ix_mission_graph_company", table_name="mission_graph_edges")
    op.drop_index("ix_mission_graph_target", table_name="mission_graph_edges")
    op.drop_index("ix_mission_graph_source", table_name="mission_graph_edges")
    op.drop_table("mission_graph_edges")
    op.drop_index("ix_autonomy_policies_level", table_name="autonomy_policies")
    op.drop_table("autonomy_policies")
    op.drop_index("ix_approval_gates_approver", table_name="approval_gates")
    op.drop_index("ix_approval_gates_requester", table_name="approval_gates")
    op.drop_index("ix_approval_gates_company_status", table_name="approval_gates")
    op.drop_table("approval_gates")
    op.drop_index("ix_startup_lessons_mission", table_name="startup_lessons")
    op.drop_index("ix_startup_lessons_company_created", table_name="startup_lessons")
    op.drop_table("startup_lessons")
    op.drop_index("ix_startup_feedback_mission", table_name="startup_feedback")
    op.drop_index("ix_startup_feedback_company_created", table_name="startup_feedback")
    op.drop_table("startup_feedback")
    op.drop_constraint("fk_snapshots_cycle", "company_state_snapshots", type_="foreignkey")
    op.drop_constraint("fk_operating_cycles_state_snapshot", "operating_cycles", type_="foreignkey")
    op.drop_index("ix_operating_cycles_status", table_name="operating_cycles")
    op.drop_index("ix_operating_cycles_mission", table_name="operating_cycles")
    op.drop_index("ix_operating_cycles_company_number", table_name="operating_cycles")
    op.drop_table("operating_cycles")
    op.drop_index("ix_snapshots_company_computed", table_name="company_state_snapshots")
    op.drop_table("company_state_snapshots")
    op.drop_index("ix_startup_projects_owner", table_name="startup_projects")
    op.drop_index("ix_startup_projects_product", table_name="startup_projects")
    op.drop_index("ix_startup_projects_company_status", table_name="startup_projects")
    op.drop_table("startup_projects")
    op.drop_index("ix_products_owner", table_name="products")
    op.drop_index("ix_products_company_status", table_name="products")
    op.drop_table("products")
    op.drop_index("ix_workforce_plans_startup_plan", table_name="workforce_plans")
    op.drop_table("workforce_plans")
    op.drop_index("ix_blueprints_startup_plan", table_name="organizational_blueprints")
    op.drop_table("organizational_blueprints")
    op.drop_index("ix_startup_plans_status", table_name="startup_plans")
    op.drop_index("ix_startup_plans_mission", table_name="startup_plans")
    op.drop_table("startup_plans")
    op.drop_index("ix_strategic_plans_mission", table_name="strategic_plans")
    op.drop_table("strategic_plans")
    op.drop_index("ix_missions_owner", table_name="missions")
    op.drop_index("ix_missions_company_status", table_name="missions")
    op.drop_table("missions")