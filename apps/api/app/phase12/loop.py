"""Closed-loop optimization — OBSERVE → SIMULATE → OPTIMIZE → PROPOSE → APPROVE
→ EXECUTE → MEASURE → LEARN → RE-SIMULATE (§58).

Unified orchestration-level loop over the Phase 12 stack. It reuses existing
governance (ApprovalGateManager), learning (LessonRecorder), and measurement
(KPIService) — it never modifies production systems itself; after approval it
records proposed execution refs and the outcome honestly. The cycle status
enum is the authoritative state machine (observe → simulate → optimize →
propose → await_approval → execute → measure → learn → complete).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.phase12 import (
    AutonomousOptimizationCycle,
    OptimizationCycleStatus,
)
from app.db.models.startup import ApprovalGate


class LoopError(ValueError):
    """Closed-loop lifecycle error."""


class NEXUSOptimizationLoop:
    """Runs and tracks closed-loop optimization cycles."""

    def __init__(
        self,
        db: Session,
        *,
        lesson_recorder: Any | None = None,
        approval_manager: Any | None = None,
    ) -> None:
        self._db = db
        self._lesson_recorder = lesson_recorder
        self._approval_manager = approval_manager

    # ── Cycle lifecycle ────────────────────────────────────────────────

    def create_cycle(
        self,
        *,
        company_id: UUID,
        name: str,
        observe: bool = True,
        created_by: UUID | None = None,
    ) -> AutonomousOptimizationCycle:
        cycle = AutonomousOptimizationCycle(
            company_id=company_id,
            name=name,
            status=OptimizationCycleStatus.OBSERVING.value,
            observed_json={},
        )
        self._db.add(cycle)
        self._db.commit()
        if observe:
            self.observe(cycle.id)
        return cycle

    def get_cycle(self, cycle_id: UUID) -> AutonomousOptimizationCycle | None:
        return self._db.get(AutonomousOptimizationCycle, cycle_id)

    def list_cycles(self, company_id: UUID) -> list[AutonomousOptimizationCycle]:
        return list(
            self._db.execute(
                select(AutonomousOptimizationCycle)
                .where(AutonomousOptimizationCycle.company_id == company_id)
                .order_by(AutonomousOptimizationCycle.started_at.desc())
            ).scalars()
        )

    # ── Loop stages (each transitions to the next enum state) ─────────

    def observe(self, cycle_id: UUID) -> dict[str, Any]:
        """Phase 8 KPI/readiness observation — read-only."""
        cycle = self._require(cycle_id)
        if cycle.status != OptimizationCycleStatus.OBSERVING.value:
            raise LoopError(f"Cannot observe cycle in state {cycle.status}")
        kpis: dict[str, Any] = {}
        try:
            from app.company.kpis import KPIService

            svc = KPIService(self._db)
            if hasattr(svc, "compute_value_all"):
                kpis = svc.compute_value_all(cycle.company_id)
            elif hasattr(svc, "compute_value"):
                kpis = {"note": "single-metric KPI API; see list"}
        except Exception as exc:  # observation is best-effort
            kpis = {"error": str(exc)}
        observation = {
            "kpis": kpis,
            "source": "phase-8-kpis",
            "readonly": True,
        }
        cycle.observed_json = observation
        self._db.commit()
        return observation

    def simulate(
        self,
        cycle_id: UUID,
        *,
        scenario_ids: list[UUID] | None = None,
    ) -> AutonomousOptimizationCycle:
        """Record scenario linkage; the SimulationEngine executes it."""
        cycle = self._require(cycle_id)
        self._transition(cycle, OptimizationCycleStatus.SIMULATING)
        cycle.scenario_ids_json = [str(s) for s in (scenario_ids or [])]
        self._db.commit()
        return cycle

    def optimize(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        self._transition(cycle, OptimizationCycleStatus.OPTIMIZING)
        self._db.commit()
        return cycle

    def propose(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        self._transition(cycle, OptimizationCycleStatus.PROPOSING)
        self._db.commit()
        return cycle

    def require_approval(
        self,
        cycle_id: UUID,
        *,
        rationale: str | None = None,
        requester_id: UUID | None = None,
    ) -> AutonomousOptimizationCycle:
        """Open an ApprovalGateManager gate for the proposed action."""
        cycle = self._require(cycle_id)
        if cycle.status != OptimizationCycleStatus.PROPOSING.value:
            raise LoopError(f"Cannot request approval in state {cycle.status}")
        manager = self._approval_manager or self._default_approval_manager()
        gate = manager.create(
            company_id=cycle.company_id,
            gate_type=("major_strategic_change_approval"),
            requested_action={
                "action": "closed_loop.optimization.apply",
                "cycle_id": str(cycle_id),
                "module": "phase12",
            },
            rationale=rationale
            or ("Closed-loop optimization recommendation requires human approval before execution"),
            risk_level="medium",
            requester_id=requester_id,
        )
        cycle.approval_gate_id = gate.id
        cycle.status = OptimizationCycleStatus.AWAITING_APPROVAL.value
        self._db.commit()
        return cycle

    def execute(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        if cycle.status != OptimizationCycleStatus.AWAITING_APPROVAL.value:
            raise LoopError(f"Cannot execute cycle in state {cycle.status}")
        # Only proceed if the gate was approved.
        if cycle.approval_gate_id:
            gate = self._db.get(ApprovalGate, cycle.approval_gate_id)
            if gate is None or gate.status.value != "approved":
                raise LoopError("Cycle execution blocked: approval gate not approved")
        cycle.status = OptimizationCycleStatus.EXECUTING.value
        self._db.commit()
        # Execution is delegated to existing systems; the cycle only
        # records a reference. No Phase 12 system performs production
        # side effects directly (governance decides, loop references).
        cycle.execute_ref = str(cycle.id)
        self._db.commit()
        return cycle

    def measure(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        self._transition(cycle, OptimizationCycleStatus.MEASURING)
        self._db.commit()
        return cycle

    def learn(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        """Record a lesson via LessonRecorder (Phase 9 reuse)."""
        cycle = self._require(cycle_id)
        self._transition(cycle, OptimizationCycleStatus.LEARNING)
        recorder = self._lesson_recorder
        if recorder is None:
            from app.startup.lessons import LessonRecorder

            recorder = LessonRecorder(self._db)
        recorder.record(
            company_id=cycle.company_id,
            lesson_type="strategic_insight",
            title=f"Optimization cycle: {cycle.name}",
            content=(
                "Closed-loop cycle completed. Simulated forecast "
                "vs measured outcomes should be compared before "
                "re-simulation."
            ),
            source={
                "cycle_id": str(cycle.id),
                "module": "phase12",
                "simulation_run_id": (
                    str(cycle.simulation_run_id) if cycle.simulation_run_id else None
                ),
                "optimization_run_id": (
                    str(cycle.optimization_run_id) if cycle.optimization_run_id else None
                ),
                "recommendation_id": (
                    str(cycle.recommendation_id) if cycle.recommendation_id else None
                ),
            },
        )
        cycle.lesson_json = {
            "recorded": True,
            "type": "strategic_insight",
            "module": "phase12",
        }
        self._db.commit()
        return cycle

    def complete(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        cycle.status = OptimizationCycleStatus.COMPLETED.value
        cycle.completed_at = datetime.now()
        self._db.commit()
        return cycle

    def cancel(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self._require(cycle_id)
        cycle.status = OptimizationCycleStatus.CANCELLED.value
        cycle.error_message = "cancelled by operator"
        self._db.commit()
        return cycle

    def run_full_cycle(
        self,
        *,
        company_id: UUID,
        name: str,
    ) -> AutonomousOptimizationCycle:
        """Convenience: create → observe → simulate → optimize → propose."""
        cycle = self.create_cycle(company_id=company_id, name=name, observe=True)
        self.simulate(cycle.id)
        self.optimize(cycle.id)
        self.propose(cycle.id)
        self.require_approval(cycle.id)
        return cycle

    # ── Internal ───────────────────────────────────────────────────────

    def _transition(
        self,
        cycle: AutonomousOptimizationCycle,
        status: OptimizationCycleStatus,
    ) -> None:
        """Advance the cycle to ``status`` (any current state allowed
        except terminal ones)."""
        if cycle.status in (
            OptimizationCycleStatus.COMPLETED.value,
            OptimizationCycleStatus.CANCELLED.value,
            OptimizationCycleStatus.BLOCKED.value,
            OptimizationCycleStatus.FAILED.value,
        ):
            raise LoopError(f"Cannot advance cycle from terminal state {cycle.status}")
        cycle.status = status.value

    def _default_approval_manager(self) -> Any:
        from app.startup.gates import ApprovalGateManager

        return ApprovalGateManager(self._db)

    def _require(self, cycle_id: UUID) -> AutonomousOptimizationCycle:
        cycle = self.get_cycle(cycle_id)
        if cycle is None:
            raise LoopError(f"Cycle {cycle_id} not found")
        return cycle
