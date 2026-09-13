"""0014 simulation optimization marketplace

Phase 12 — Simulation, Optimization & Agent Marketplace: NEXUS can simulate
organizations, run what-if experiments, optimize allocation/strategy, benchmark
& recommend agents, and close the loop OBSERVE → SIMULATE → OPTIMIZE → PROPOSE →
APPROVE → EXECUTE → MEASURE → LEARN → RE-SIMULATE.

Adds 43 additive tables (nothing existing is altered): the simulation group
(simulations, simulation_scenarios, simulation_variables, simulation_assumptions,
simulation_runs, simulation_iterations, simulation_snapshots, simulation_outcomes,
simulation_metrics, simulation_events, simulation_comparisons, simulation_checkpoints,
simulation_entities), the optimization group (optimization_problems,
optimization_variables, optimization_constraints, optimization_objectives,
optimization_runs, optimization_candidates, optimization_scores,
optimization_recommendations, optimization_lessons), the experiment group
(experiments, experiment_variants, experiment_runs, experiment_metrics,
experiment_results), the benchmark group (benchmarks, benchmark_suites,
benchmark_cases, benchmark_runs, benchmark_results, agent_benchmark_scores),
the marketplace group (agent_packages, agent_package_versions,
agent_package_capabilities, agent_package_dependencies, agent_package_benchmarks,
agent_package_reviews, agent_installations, agent_recommendations,
agent_reputation_records), and the closed-loop table (autonomous_optimization_cycles).

All tables are defined by ``app/db/models/phase12.py``; we create them from that
metadata directly so DDL can never drift from the models (this matches the
project's hand-written migration convention — a pure additive revision, no ALTERs
to existing Phase 0-11 tables).

Revision ID: 0014_phase12_sim_opt_mkt
Revises: 0013_security_governance
Create Date: 2026-09-13
"""

from collections.abc import Iterable

import sqlalchemy as sa

from alembic import op
from app.db.session import Base

revision = "0014_phase12_sim_opt_mkt"
down_revision = "0013_security_governance"
branch_labels = None
depends_on = None

# Every table introduced by this migration (must exactly match the models in
# app/db/models/phase12.py; a mismatch fails loudly at runtime).
_PHASE12_TABLES: Iterable[str] = (
    "agent_benchmark_scores",
    "agent_installations",
    "agent_package_benchmarks",
    "agent_package_capabilities",
    "agent_package_dependencies",
    "agent_package_reviews",
    "agent_package_versions",
    "agent_packages",
    "agent_recommendations",
    "agent_reputation_records",
    "autonomous_optimization_cycles",
    "benchmark_cases",
    "benchmark_results",
    "benchmark_runs",
    "benchmark_suites",
    "benchmarks",
    "experiment_metrics",
    "experiment_results",
    "experiment_runs",
    "experiment_variants",
    "experiments",
    "optimization_candidates",
    "optimization_constraints",
    "optimization_lessons",
    "optimization_objectives",
    "optimization_problems",
    "optimization_recommendations",
    "optimization_runs",
    "optimization_scores",
    "optimization_variables",
    "simulation_assumptions",
    "simulation_checkpoints",
    "simulation_comparisons",
    "simulation_entities",
    "simulation_events",
    "simulation_iterations",
    "simulation_metrics",
    "simulation_outcomes",
    "simulation_runs",
    "simulation_scenarios",
    "simulation_snapshots",
    "simulation_variables",
    "simulations",
)


def _tables() -> list[sa.Table]:
    missing = [n for n in _PHASE12_TABLES if n not in Base.metadata.tables]
    if missing:
        raise RuntimeError(f"Phase 12 tables missing from metadata: {missing}")
    return [Base.metadata.tables[n] for n in _PHASE12_TABLES]


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    # ``create_all`` is idempotent per-table but we guard explicitly to keep the
    # behaviour obvious when this revision runs over a partially-applied DB.
    to_create = [t for t in _tables() if t.name not in existing]
    Base.metadata.create_all(bind=bind, tables=to_create)


def downgrade() -> None:
    bind = op.get_bind()
    # Plain ``DROP TABLE IF EXISTS … CASCADE`` is metadata-independent (robust
    # to columns added after this revision first ran) and order-independent
    # (the Phase 12 tables reference company/employee/agent ids only by UUID —
    # there are no internal FK cycles — so CASCADE cannot reach Phase 0-11
    # tables; company_id FKs are ON DELETE SET NULL).
    for t in reversed(_tables()):
        op.execute(f'DROP TABLE IF EXISTS "{t.name}" CASCADE')