"""Phase 12 closed-loop optimization tests (§58).

OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE → EXECUTE → MEASURE → LEARN
→ RE-SIMULATE. Optimize proposes; governance decides — execution is blocked
until a human ApprovalGate is approved, and lessons are recorded after learn.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.phase12.loop import LoopError, NEXUSOptimizationLoop


def _make_company(db: Session):
    from app.company.manager import CompanyManager

    return CompanyManager(db).create(name="Loop Co")


def _run_full_cycle(db: Session, company_id, *, name="Cycle"):
    loop = NEXUSOptimizationLoop(db)
    return loop, loop.run_full_cycle(company_id=company_id, name=name)


def _approve_cycle_gate(db: Session, cycle):
    from app.startup.gates import ApprovalGateManager

    assert cycle.approval_gate_id is not None
    return ApprovalGateManager(db).approve(cycle.company_id, cycle.approval_gate_id)


def _complete_cycle(db: Session, cycle) -> None:
    """Drive a cycle from awaiting_approval through to completed."""
    loop = NEXUSOptimizationLoop(db)
    _approve_cycle_gate(db, cycle)
    loop.execute(cycle.id)
    loop.measure(cycle.id)
    loop.learn(cycle.id)
    loop.complete(cycle.id)


class TestCreateAndObserve:
    def test_cycle_creates_observing(self, db: Session) -> None:
        company = _make_company(db)
        loop = NEXUSOptimizationLoop(db)
        cycle = loop.create_cycle(company_id=company.id, name="Observe", observe=True)
        assert cycle.status == "observing"
        assert cycle.observed_json is not None
        assert cycle.observed_json["readonly"] is True
        assert cycle.observed_json["source"] == "phase-8-kpis"
        assert "kpis" in cycle.observed_json

    def test_observe_is_read_only(self, db: Session) -> None:
        company = _make_company(db)
        loop = NEXUSOptimizationLoop(db)
        cycle = loop.create_cycle(company_id=company.id, name="RO", observe=True)
        observation = loop.observe(cycle.id)
        assert observation["readonly"] is True
        assert isinstance(observation["kpis"], dict)

    def test_full_cycle_stops_at_awaiting_approval(self, db: Session) -> None:
        company = _make_company(db)
        loop, cycle = _run_full_cycle(db, company.id)
        assert cycle.status == "awaiting_approval"
        assert cycle.approval_gate_id is not None


class TestLifecycle:
    def test_execute_blocked_before_approval(self, db: Session) -> None:
        import pytest

        company = _make_company(db)
        loop, cycle = _run_full_cycle(db, company.id)
        with pytest.raises(LoopError, match="not approved"):
            loop.execute(cycle.id)
        assert loop.get_cycle(cycle.id).status == "awaiting_approval"

    def test_lifecycle_transitions(self, db: Session) -> None:
        company = _make_company(db)
        loop = NEXUSOptimizationLoop(db)
        cycle = loop.create_cycle(company_id=company.id, name="Manual", observe=False)
        assert cycle.status == "observing"

        loop.simulate(cycle.id)
        assert loop.get_cycle(cycle.id).status == "simulating"

        loop.optimize(cycle.id)
        assert loop.get_cycle(cycle.id).status == "optimizing"

        loop.propose(cycle.id)
        assert loop.get_cycle(cycle.id).status == "proposing"

        loop.require_approval(cycle.id)
        assert loop.get_cycle(cycle.id).status == "awaiting_approval"
        assert cycle.approval_gate_id is not None

        _approve_cycle_gate(db, cycle)
        loop.execute(cycle.id)
        assert loop.get_cycle(cycle.id).status == "executing"
        assert loop.get_cycle(cycle.id).execute_ref is not None

        loop.measure(cycle.id)
        assert loop.get_cycle(cycle.id).status == "measuring"

        loop.learn(cycle.id)
        assert loop.get_cycle(cycle.id).status == "learning"

        loop.complete(cycle.id)
        assert loop.get_cycle(cycle.id).status == "completed"
        assert loop.get_cycle(cycle.id).completed_at is not None

    def test_cancel(self, db: Session) -> None:
        company = _make_company(db)
        loop = NEXUSOptimizationLoop(db)
        cycle = loop.create_cycle(company_id=company.id, name="Cancel")
        assert loop.cancel(cycle.id).status == "cancelled"

    def test_transition_from_terminal_blocked(self, db: Session) -> None:
        import pytest

        company = _make_company(db)
        loop, cycle = _run_full_cycle(db, company.id)
        _complete_cycle(db, cycle)
        assert loop.get_cycle(cycle.id).status == "completed"
        with pytest.raises(LoopError, match="terminal"):
            loop.simulate(cycle.id)


class TestLearning:
    def test_lesson_recorded(self, db: Session) -> None:
        company = _make_company(db)
        loop, cycle = _run_full_cycle(db, company.id)
        _complete_cycle(db, cycle)
        refreshed = loop.get_cycle(cycle.id)
        assert refreshed.lesson_json is not None
        assert refreshed.lesson_json["recorded"] is True


class TestIsolation:
    def test_concurrent_cycles_distinct(self, db: Session) -> None:
        company = _make_company(db)
        loop = NEXUSOptimizationLoop(db)
        c1 = loop.run_full_cycle(company_id=company.id, name="Cycle 1")
        c2 = loop.run_full_cycle(company_id=company.id, name="Cycle 2")
        assert c1.id != c2.id
        assert c1.status == c2.status == "awaiting_approval"
        assert c1.approval_gate_id != c2.approval_gate_id
        assert loop.list_cycles(company.id) and len(loop.list_cycles(company.id)) == 2
