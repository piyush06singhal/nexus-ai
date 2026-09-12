"""Autonomous Startup Engine — event names + a thin logger.

The single audit path stays :class:`app.company.events.OrgEventLogger` (Phase 8);
this module only centralizes the startup event-name vocabulary (§40) and offers
a small wrapper so every startup service records company/mission-scoped events
consistently. No second event store.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.company.events import OrgEventLogger


class StartupEvents:
    """Event-name constants for the startup engine."""

    # Mission
    MISSION_CREATED = "mission_created"
    MISSION_ANALYZED = "mission_analyzed"
    MISSION_VALIDATED = "mission_validated"
    MISSION_PLANNED = "mission_planned"
    MISSION_ACTIVATED = "mission_activated"
    MISSION_PAUSED = "mission_paused"
    MISSION_COMPLETED = "mission_completed"
    MISSION_CANCELLED = "mission_cancelled"
    # Strategy / plan
    STRATEGY_CREATED = "strategy_created"
    STARTUP_PLAN_CREATED = "startup_plan_created"
    STARTUP_PLAN_VALIDATED = "startup_plan_validated"
    STARTUP_PLAN_APPROVED = "startup_plan_approved"
    BLUEPRINT_GENERATED = "blueprint_generated"
    WORKFORCE_PLANNED = "workforce_planned"
    # Bootstrap / workforce
    COMPANY_BOOTSTRAPPED = "company_bootstrapped"
    EMPLOYEE_PROVISIONED = "employee_provisioned"
    # Product / project
    PRODUCT_CREATED = "product_created"
    PRODUCT_STATUS_CHANGED = "product_status_changed"
    PRODUCT_VALIDATED = "product_validated"
    PRODUCT_LAUNCHED = "product_launched"
    PROJECT_CREATED = "project_created"
    PROJECT_STATUS_CHANGED = "project_status_changed"
    # Execution / cycle
    EXECUTION_PLAN_CREATED = "execution_plan_created"
    TASK_EXECUTED = "task_executed"
    CYCLE_STARTED = "cycle_started"
    CYCLE_STAGE = "cycle_stage"
    CYCLE_COMPLETED = "cycle_completed"
    CYCLE_BLOCKED = "cycle_blocked"
    # Governance
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    AUTONOMY_POLICY_UPDATED = "autonomy_policy_updated"
    AUTONOMY_BLOCKED = "autonomy_blocked"
    ACTION_REQUIRES_APPROVAL = "action_requires_approval"
    # Learning
    FEEDBACK_RECORDED = "feedback_recorded"
    LESSON_RECORDED = "lesson_recorded"
    REPLAN_TRIGGERED = "replan_triggered"
    PRIORITY_DECIDED = "priority_decided"
    RESOURCE_ALLOCATED = "resource_allocated"


class StartupEventLogger:
    """Record startup events through the shared Phase 8 event log."""

    def __init__(self, db: Session) -> None:
        self._events = OrgEventLogger(db)

    def log(
        self,
        *,
        action: str,
        company_id: UUID | None = None,
        actor: str = "system",
        target_type: str | None = None,
        target_id: UUID | None = None,
        details: dict[str, Any] | None = None,
        outcome: str = "success",
    ) -> None:
        self._events.log(
            actor=actor,
            action=action,
            company_id=company_id,
            target_type=target_type,
            target_id=target_id,
            details=details,
            outcome=outcome,
        )
