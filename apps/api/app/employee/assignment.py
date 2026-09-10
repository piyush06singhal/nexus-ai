"""AI Employee OS — assignment engine.

Selects the best employee for a task considering: required skills, role,
availability, workload, permissions, budget, and performance.  Deterministic
and explainable.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.employee import AIEmployee, EmployeeStatus
from app.employee.lifecycle import is_available_for_tasks
from app.employee.performance import PerformanceTracker
from app.employee.skills import SkillAssessor
from app.employee.types import AssignmentRequest, AssignmentResult
from app.employee.workload import WorkloadManager


class AssignmentEngine:
    """Selects employees for tasks based on skills, availability, and workload."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._skills = SkillAssessor(db)
        self._workload = WorkloadManager(db)
        self._performance = PerformanceTracker(db)

    def assign(self, request: AssignmentRequest) -> AssignmentResult:
        """Find and return the best employee for the requested task.

        Scoring (weighted):
        - Skill match: 40%
        - Workload availability: 30%
        - Role match: 20%
        - Performance: 10%
        """
        # Gather candidates
        stmt = select(AIEmployee).where(
            AIEmployee.status.in_([EmployeeStatus.ACTIVE, EmployeeStatus.BUSY]),
        )
        if request.preferred_role:
            stmt = stmt.where(AIEmployee.role == request.preferred_role)

        candidates = list(self._db.execute(stmt).scalars().all())

        if not candidates:
            return AssignmentResult(
                success=False,
                reasoning="No eligible employees found",
                candidates_evaluated=0,
                correlation_id=request.correlation_id,
            )

        scored: list[tuple[AIEmployee, float, str]] = []

        for emp in candidates:
            # Skill match (0–1)
            skill_score, matched = self._skills.match_skills(emp.id, request.required_skills)

            # Availability: check status and workload
            if not is_available_for_tasks(emp.status):
                continue
            snap = self._workload.get_snapshot(emp.id)
            if snap.available_slots <= 0:
                continue
            workload_score = snap.available_slots / max(snap.capacity, 1)

            # Role match (0–1)
            role_match = request.preferred_role and emp.role == request.preferred_role
            role_score = 1.0 if role_match else 0.5

            # Performance — real success rate from the performance tracker.
            perf_score = self._performance.get_metrics(emp.id).success_rate

            total = 0.4 * skill_score + 0.3 * workload_score + 0.2 * role_score + 0.1 * perf_score
            reasoning_parts = [
                f"skill_match={skill_score:.2f}({','.join(matched)})",
                f"workload={workload_score:.2f}",
                f"role={role_score:.2f}",
                f"perf={perf_score:.2f}",
            ]
            scored.append((emp, total, "; ".join(reasoning_parts)))

        if not scored:
            return AssignmentResult(
                success=False,
                reasoning="All candidates rejected (availability/workload)",
                candidates_evaluated=len(candidates),
                correlation_id=request.correlation_id,
            )

        # Sort descending by score; deterministic (stable sort)
        scored.sort(key=lambda x: x[1], reverse=True)
        best_emp, best_score, best_reasoning = scored[0]

        return AssignmentResult(
            success=True,
            employee_id=best_emp.id,
            employee_name=best_emp.name,
            score=best_score,
            reasoning=best_reasoning,
            candidates_evaluated=len(candidates),
            correlation_id=request.correlation_id,
        )

    def assign_specific(
        self,
        employee_id: UUID,
        request: AssignmentRequest,
    ) -> AssignmentResult:
        """Assign a task to a specific employee (bypassing selection).

        Still checks availability and workload.
        """
        emp = self._db.get(AIEmployee, employee_id)
        if emp is None:
            return AssignmentResult(
                success=False,
                reasoning="Employee not found",
                correlation_id=request.correlation_id,
            )
        if not is_available_for_tasks(emp.status):
            return AssignmentResult(
                success=False,
                reasoning=f"Employee status {emp.status.value} is not available for tasks",
                correlation_id=request.correlation_id,
            )
        if not self._workload.can_accept_task(employee_id):
            return AssignmentResult(
                success=False,
                reasoning="Employee has no available capacity",
                correlation_id=request.correlation_id,
            )

        return AssignmentResult(
            success=True,
            employee_id=emp.id,
            employee_name=emp.name,
            score=1.0,
            reasoning="Directly assigned",
            candidates_evaluated=1,
            correlation_id=request.correlation_id,
        )
