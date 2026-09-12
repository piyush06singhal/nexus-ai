"""Tests for the deterministic Phase 9 demo chain.

``scripts.seed_autonomous_startup._run_demo`` drives the full startup engine
end-to-end (mission → analysis → strategy → startup plan → approve → bootstrap →
product → projects → operating cycles → injected failure → recovery → feedback →
replan → approval gates → final state). These tests run that same function
against the SQLite-backed test session and assert the deterministic end state:
no model API, no external calls, idempotent re-runs, and one real recovery.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session


def test_demo_runs_full_chain_deterministically(db: Session, phase6_settings) -> None:
    from scripts.seed_autonomous_startup import _run_demo

    summary = _run_demo(db, reset=True)

    # Fresh company: exactly the three demo cycles ran on it.
    assert summary["cycle_count"] == 3
    assert summary["graph_edges"] >= 30
    assert summary["policy"]["autonomy_level"] == "bounded_autonomy"

    company_id = UUID(summary["company_id"])

    # The one injected failure produced exactly one recovered execution.
    from app.startup.cycle import OperatingEngine

    cycles = OperatingEngine(db).list_cycles(company_id)
    assert [c["cycle_number"] for c in cycles] == [3, 2, 1]
    recovered = [c for c in cycles if c.get("recovery")]
    assert len(recovered) == 1
    attempt = recovered[0]["recovery"][0]
    assert attempt["outcome"] == "recovered"
    assert attempt["strategy"] == "retry_with_modified_input"

    # Feedback surfaced from the degraded cycle (governed, advisory).
    from app.startup.feedback import FeedbackService

    assert FeedbackService(db).list_(company_id)

    # The mission graph resolves back to the mission.
    from app.startup.graph import MissionGraphBuilder

    trace = MissionGraphBuilder(db).trace(company_id, "mission", UUID(summary["mission_id"]))
    assert trace["origin"]["type"] == "mission"
    assert trace["reached_mission"] is True

    # Final state is computed by the observation layer, never fabricated.
    from app.startup.observe import ObservationLayer

    final = ObservationLayer(db).observe(company_id)
    assert 0.0 <= final.overall_score <= 1.0


def test_demo_budget_bump_is_anchored_and_idempotent(db: Session, phase6_settings) -> None:
    from scripts.seed_autonomous_startup import _run_demo

    first = _run_demo(db, reset=True)
    company_id = UUID(first["company_id"])

    # The +20% bump anchors to the plan baseline (1000 → 1200), once.
    from app.company.budget import BudgetManager

    budget = BudgetManager(db).company_budget(company_id)
    assert budget is not None
    assert float(budget.monthly_limit) == 1200.0

    # Re-running without reset reuses the company instead of duplicating it.
    second = _run_demo(db, reset=False)
    assert second["company_id"] == first["company_id"]

    from sqlalchemy import select

    from app.db.models.company import Company

    companies = list(db.execute(select(Company)).scalars())
    assert len(companies) == 1, "idempotent re-run must not create a second company"

    # And the budget stays exactly at 1200 — never compounded on re-runs.
    budget_after = BudgetManager(db).company_budget(company_id)
    assert float(budget_after.monthly_limit) == 1200.0
